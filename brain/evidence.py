"""WHICH picture rides with the done-text, and how its URL comes to exist.

Spec: docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md.

NOTHING IN HERE CHOOSES A PICTURE. That is the whole point of the file, and it
is HARNESS-LAWS Law 1 in the one place this feature would otherwise break it.
"Which image is the proof of what happened" is a judgement about meaning, and
the rules a sender would reach for — the last evidence entry, the one whose URL
looks like a receipt, the biggest one — are patterns deciding meaning. This
repo has torn out sixty-one of those (research/2026-08-24-law1-audit.md).

The judgement is already made, once, by the model that has the page in front of
it: at the moment the browser declares the effect verified-done it deposits
EXACTLY ONE evidence row and names it in the receipt beside the entries it
already writes —

    {"verified": true, "effect_key": "...",
     "evidence": ["url:https://…", "proof:booking #55",
                  "evidence:rec1234567890abc"]}

— so downstream there is no choice left to make. Reading that `evidence:` key
out of the array is parsing THIS PRODUCT'S OWN RECORD FORMAT, the same act as
reading `proof:` or `effect_key`; it interprets nobody's words. It is said out
loud here because a reviewer scanning for `startswith(` will otherwise flag it.

THREE OUTCOMES, AND THE SENDER NEVER PICKS:

  exactly one id  -> open a window for it, attach it if the window opens
  zero            -> no picture. Not an error.
  more than one   -> NO PICTURE, said loudly. A floor, not a tie-break: the
                     question is "is there a picture this text is authorised to
                     carry", and without a single unambiguous answer the answer
                     is no. A tie-break rule would work in testing, be wrong on
                     the errand that mattered, and hide the depositor's bug for
                     months.

THE WORDS GO OUT REGARDLESS. Every function here returns "nothing" for every
failure — a 500, a timeout, a socket error, an unparseable body, `ok: false` —
and NEVER raises into the send path. A confirmation that vanishes because a
screenshot failed is strictly worse than today's confirmation with no
screenshot, and this product has already had the silent-failure version of that
day (brain/worker.py, the 2026-08-22 comment: "Two failures, and the silent one
is the worse one").

THE WINDOW IS OPENED IN THE MOMENT OF SENDING AND NEVER EARLIER. `POST
/evidence/share` puts a photograph of a page the owner was logged into on an
anonymous https URL for fifteen minutes and five fetches, because Twilio
fetches `MediaUrl` from its own infrastructure with no credential of ours
(backend/pb_hooks/evidence.pb.js). Opening one speculatively, in advance, or in
bulk is exposure bought for nothing, so every refusal above happens BEFORE the
call — which is why `wants_photo` is a callable and not a boolean.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional, Sequence

from . import pb

# The key the browser writes, beside `url:`, `title:`, `page:`, `proof:` and
# `journal:` (extension/workflow_state.js).
EVIDENCE_KEY = "evidence"

# One attempt, short. The share door is on the same host the worker already
# reads jobs from; if it is slow enough to matter, the confirmation is more
# urgent than the picture.
SHARE_TIMEOUT = 8

# Same default as brain/worker.py's PB, for the same reason it has one.
_PB_DEFAULT = "http://127.0.0.1:8090"


def _backend(base: str = "") -> str:
    return (base or os.environ.get("ANTICIPY_PB", _PB_DEFAULT)).rstrip("/")


def ids_in_receipt(raw) -> list:
    """Every evidence record id this receipt names, in the order it names them.

    Takes the raw `jobs.receipt` text (or an already-parsed dict). Anything
    unreadable is NO IDS — a receipt this cannot parse is a receipt that names
    no picture, never an exception on the way to a confirmation.
    """
    try:
        receipt = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except Exception:
        return []
    if not isinstance(receipt, dict):
        return []
    entries = receipt.get("evidence")
    if not isinstance(entries, list):
        return []
    ids = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        key, sep, rest = entry.partition(":")
        if sep and key.strip() == EVIDENCE_KEY and rest.strip():
            ids.append(rest.strip())
    return ids


def open_share_window(evidence_id: str, base: str = "",
                      timeout: float = SHARE_TIMEOUT,
                      log: Callable[[str], None] = print) -> str:
    """The URL Twilio may fetch for this one picture, or "" — never raises.

    The backend already answers `200 {ok: false, …}` for every absence it can
    see (no such row, no image on it, no https base configured). This honours
    the same shape for the failures it cannot see for us: a timeout, a 5xx, a
    socket error, a body that is not JSON.
    """
    evidence_id = str(evidence_id or "").strip()
    if not evidence_id:
        return ""
    try:
        r = pb.post(f"{_backend(base)}/evidence/share",
                    json={"id": evidence_id}, timeout=timeout)
        if not getattr(r, "ok", False):
            log(f"no picture on this text: the share door answered "
                f"{getattr(r, 'status_code', '?')} for {evidence_id}")
            return ""
        body = r.json() or {}
        if not body.get("ok"):
            log(f"no picture on this text: {body.get('reason') or 'refused'} "
                f"({evidence_id})")
            return ""
        return str(body.get("url") or "")
    except Exception as exc:
        # Deliberately every exception. Anything that reaches here has to
        # degrade to a text with no photo, because the alternative is a
        # traceback where a confirmation should be.
        log(f"no picture on this text: could not open a share window for "
            f"{evidence_id}: {exc}")
        return ""


def picture_for_done_text(job: dict,
                          wants_photo: Callable[[str], bool],
                          base: str = "",
                          log: Callable[[str], None] = print) -> list:
    """The media list for this job's done-text: [] or exactly one URL.

    `wants_photo` is asked for the owner's stored answer ONLY once a single
    unambiguous picture exists, so the common case costs no reads at all and no
    window is ever opened for a text that was never going to carry one.
    """
    try:
        job = job or {}
        ids = ids_in_receipt(job.get("receipt"))
        if not ids:
            return []
        if len(ids) > 1:
            # Loud enough that somebody finds it: this is a bug where the
            # picture is chosen, and silence would preserve it forever.
            log(f"NO PICTURE on the done-text for job {job.get('id')}: its "
                f"receipt names {len(ids)} evidence rows and exactly one is "
                "the proof of this errand. The browser deposits one at the "
                "moment it declares done; more than one is a defect there, "
                "and no rule here may pick between them.")
            return []
        if not wants_photo(str(job.get("owner_ref") or "")):
            return []
        url = open_share_window(ids[0], base=base, log=log)
        return [url] if url else []
    except Exception as exc:
        log(f"no picture on this text ({exc}); the words go out regardless")
        return []


def one_url(media: Optional[Sequence[str]]) -> str:
    """The single https URL in `media`, or "" — the same floor, at the wire.

    Zero is no picture and MORE THAN ONE IS ALSO NO PICTURE, for the reason in
    this module's header: nothing downstream of the browser model may choose
    between candidate pictures. Kept here rather than in the voice arm so the
    rule lives in one place and is read the same way at both ends.
    """
    urls = [str(u).strip() for u in (media or []) if str(u).strip()]
    if len(urls) != 1:
        return ""
    return urls[0] if urls[0].startswith("https://") else ""
