"""FormPrepareAgent — the safe 'do it' browser WRITE hand: PREPARE, then HAND OFF.

Live-write browser agents are still ~33% reliable, and a wrong final click on a
real form is a real side effect (an order placed, a message sent, money moved).
So this arm never takes the last step. It fills a form's fields up to — but NOT
including — the submit control, reads the filled values BACK off the page as the
only proof it really typed them, and returns that filled-field state for the
OWNER to confirm and submit. Submit is the human's click, always.

General machinery, no site-specific logic. Same observe->act->observe primitives
as WebVoyagerAgent, the same set-of-marks element model
({idx, role, name, type, state, inView, ...}), and the same hard discipline:
  - DETERMINISTIC field mapping (label / name / placeholder), no model guesswork.
  - text/email/tel/textarea     -> click + type the value (trusted CDP input).
  - radio / checkbox            -> click the option whose label matches the value;
                                   a checkbox already in the wanted state is left.
  - SUBMIT IS FORBIDDEN. A control matching the submit guard is never clicked; if
    the only way to "finish" were to submit, we stop and hand off instead.
  - READ-BACK proof: after filling, observe again and confirm each value is now
    present in the field (input value / checked state). A field that did not take
    is reported as not-filled — never faked.
The result is a handoff envelope: what was filled, what is still blank, the submit
control we deliberately left for the owner, and the final screenshot.

ABSOLUTELY NO submit, NO login, NO money. Prepare-then-handoff only.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id

# The single hard stop. A control whose label matches this is NEVER clicked by
# this agent — submitting is the owner's job. Deliberately broad on the write
# side (the opposite of the read-side PURCHASE_GUARD, which must stay narrow):
# here a false "this looks like submit, don't click it" is SAFE (we just hand
# off), while a missed submit control would be the cardinal sin.
SUBMIT_GUARD = re.compile(
    r"\b(submit|place\s+(your\s+)?order|send|buy|pay|checkout|check\s*out|"
    r"continue|confirm|complete|finish|proceed|book|reserve|sign\s*up|"
    r"register|order\s+now|post|apply|save|next)\b",
    re.I,
)

# A field is "typeable" (we type text into it) vs "toggleable" (we click it).
_TEXT_TYPES = {"text", "email", "tel", "url", "search", "number", "password",
               "date", "time", "datetime-local", "month", "week", ""}
_TEXT_ROLES = {"textarea", "input", "textbox"}
_TOGGLE_TYPES = {"radio", "checkbox"}
_TOGGLE_ROLES = {"radio", "checkbox", "option"}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _norm(s: str) -> str:
    return " ".join(_WORD_RE.findall((s or "").lower()))


def _tokens(s: str) -> set[str]:
    return set(_WORD_RE.findall((s or "").lower()))


def _is_text_field(el: dict) -> bool:
    role = (el.get("role") or "").lower()
    typ = (el.get("type") or "").lower()
    if role in _TOGGLE_ROLES or typ in _TOGGLE_TYPES:
        return False
    if role == "textarea" or role in _TEXT_ROLES:
        return True
    if role == "input":
        return typ in _TEXT_TYPES
    # some pages surface role==type for bare inputs
    return typ in _TEXT_TYPES and role not in {"button", "a", "link", "submit"}


def _is_toggle(el: dict) -> bool:
    role = (el.get("role") or "").lower()
    typ = (el.get("type") or "").lower()
    return role in _TOGGLE_ROLES or typ in _TOGGLE_TYPES


def _is_submit(el: dict) -> bool:
    """Is this element a SUBMIT control we must never click?

    type=submit/image (and <button> with no type defaults to submit) are submit
    controls by HTML. A name-based match ("Submit order", "Place order", ...) is
    only a submit control on a CLICKABLE element — a text input or textarea whose
    LABEL happens to contain a submit-y word (e.g. "Send message to") is a field
    we fill, not a button we are forbidden to press."""
    typ = (el.get("type") or "").lower()
    if typ in {"submit", "image"}:
        return True
    if _is_text_field(el):
        return False
    role = (el.get("role") or "").lower()
    clickable = role in {"button", "a", "link", "submit"} or typ in {"button", ""}
    if not clickable:
        return False
    return SUBMIT_GUARD.search(el.get("name") or "") is not None


def _label_score(field_label: str, el: dict) -> int:
    """How well an element matches a requested field label. Higher is better.
    Uses the element's accessible name (which the extension fills from
    aria-label / placeholder / value / title / nearby text)."""
    want = _tokens(field_label)
    if not want:
        return 0
    have = _tokens(el.get("name"))
    if not have:
        return 0
    overlap = want & have
    if not overlap:
        return 0
    score = len(overlap) * 4
    # exact/substring label match is a strong signal
    if _norm(field_label) and _norm(field_label) in _norm(el.get("name") or ""):
        score += 6
    if _norm(el.get("name") or "") and _norm(el.get("name") or "") in _norm(field_label):
        score += 3
    return score


def _value_is_checked(el: dict) -> bool:
    return "checked" in (el.get("state") or "")


class FormPrepareAgent:
    """Fill a form to the submit screen, stop, and hand the filled state back.

    Inputs: a navigable form URL and a dict of {field_label: value}. Values are
    plain strings for text fields, and the option label for radio/checkbox
    (a truthy bare value like True/"yes" on a single checkbox just checks it)."""

    def __init__(self, link: BrowserLink, max_fields: int = 30) -> None:
        self.link = link
        self.max_fields = max_fields
        self._cur_shot = None

    async def _observe(self, url: Optional[str] = None):
        r = await self.link.send_browse(
            new_id(), "observe", {"url": url} if url else {}, timeout=60.0
        )
        return (r.get("output") or {}), (r.get("proof") or {}).get("screenshot")

    async def _act(self, action: dict):
        try:
            return await self.link.send_browse(new_id(), "act", action, timeout=20.0)
        except Exception:
            return {"status": "error"}

    # ---- field matching ----
    def _match_text_field(self, label: str, elements: List[dict],
                          used: set) -> Optional[dict]:
        best, best_score = None, 0
        for el in elements:
            idx = el.get("idx")
            if idx in used or not _is_text_field(el) or _is_submit(el):
                continue
            score = _label_score(label, el)
            if score > best_score:
                best, best_score = el, score
        return best if best_score > 0 else None

    def _match_toggle(self, label: str, value, elements: List[dict],
                      used: set) -> Optional[dict]:
        """For radio/checkbox: match the option whose label equals the wanted
        value, scoped (when possible) by the field label too."""
        want_value = _tokens(value if isinstance(value, str) else "")
        best, best_score = None, 0
        for el in elements:
            idx = el.get("idx")
            if idx in used or not _is_toggle(el) or _is_submit(el):
                continue
            have = _tokens(el.get("name"))
            if not have:
                continue
            # option-label match against the value is the primary signal
            if want_value:
                ov = want_value & have
                if not ov:
                    continue
                score = len(ov) * 5
                if _norm(str(value)) and _norm(str(value)) in _norm(el.get("name") or ""):
                    score += 6
            else:
                # bare truthy single-checkbox: match on the field label instead
                score = _label_score(label, el)
                if score <= 0:
                    continue
            if score > best_score:
                best, best_score = el, score
        return best if best_score > 0 else None

    async def run(self, url: str, fields: dict) -> dict:
        history: List[str] = []
        out, shot = await self._observe(url)
        self._cur_shot = shot
        elements = out.get("elements") or []
        if not elements:
            return self._handoff(out, history, filled=[], pending=list(fields or {}),
                                 reason="form page returned no actionable elements")

        used: set = set()
        planned: list = []  # (label, value, el, kind)
        unmatched: list = []
        for label, value in list((fields or {}).items())[: self.max_fields]:
            toggle_value = isinstance(value, bool) or (
                isinstance(value, str) and len(_tokens(value)) <= 4
            )
            el = None
            kind = ""
            # try text first for string values, toggle for option-like values
            if isinstance(value, str):
                el = self._match_text_field(label, elements, used)
                if el:
                    kind = "text"
            if el is None:
                el = self._match_toggle(label, value, elements, used)
                if el:
                    kind = "toggle"
            if el is None and toggle_value:
                el = self._match_toggle(label, str(value), elements, used)
                if el:
                    kind = "toggle"
            if el is None:
                unmatched.append(label)
                continue
            used.add(el.get("idx"))
            planned.append((label, value, el, kind))

        if not planned:
            return self._handoff(out, history, filled=[],
                                 pending=list(fields or {}),
                                 reason="no requested field matched a form input")

        # ---- fill (never submit) ----
        for label, value, el, kind in planned:
            idx = el.get("idx")
            if _is_submit(el):  # belt-and-suspenders: never act on a submit control
                history.append(f"SKIPPED submit-like control idx={idx} '{el.get('name')}'")
                continue
            if kind == "text":
                await self._act({"action": "click", "index": idx})
                await self._act({"action": "type", "index": idx, "text": str(value)})
                history.append(f"typed '{value}' into idx={idx} ('{label}')")
            else:  # toggle
                if _is_toggle(el) and _value_is_checked(el):
                    history.append(f"left idx={idx} already selected ('{label}'={value})")
                    continue
                await self._act({"action": "click", "index": idx})
                history.append(f"selected idx={idx} ('{label}'={value})")

        # ---- read-back proof: observe again, confirm each value actually took ----
        verify_out, verify_shot = await self._observe()
        self._cur_shot = verify_shot or self._cur_shot
        verify_elements = verify_out.get("elements") or []
        by_idx = {e.get("idx"): e for e in verify_elements}

        filled: list = []
        pending: list = []
        for label, value, el, kind in planned:
            idx = el.get("idx")
            after = by_idx.get(idx, {})
            ok = False
            observed = after.get("name") or ""
            if kind == "text":
                # the extension surfaces the input's .value as the element name
                ok = _norm(str(value)) != "" and _norm(str(value)) in _norm(observed)
            else:
                ok = _value_is_checked(after)
            entry = {"label": label, "value": value, "kind": kind,
                     "index": idx, "observed": observed[:90]}
            (filled if ok else pending).append(entry)

        # the submit control we deliberately leave for the owner
        submit_el = next((e for e in verify_elements if _is_submit(e)), None)
        for label in unmatched:
            pending.append({"label": label, "value": (fields or {}).get(label),
                            "kind": "unmatched", "index": None, "observed": ""})

        # Fully confirmed only when EVERY requested field was staged and read
        # back — an unmatched field or a value that did not take both mean "not
        # confirmed", so the owner is never told it is all set when it is not.
        confirmed = bool(filled) and not pending
        return {
            "prepared": True,
            "submitted": False,
            "handoff": True,
            "confirmed_fields": confirmed,
            "final_url": verify_out.get("url") or out.get("url"),
            "final_shot": self._cur_shot,
            "filled_fields": filled,
            "pending_fields": pending,
            "submit_control": (
                {"index": submit_el.get("idx"), "name": submit_el.get("name")}
                if submit_el else None
            ),
            "history": history,
            "answer": self._summary(filled, pending, submit_el),
        }

    def _summary(self, filled, pending, submit_el) -> str:
        parts = []
        if filled:
            parts.append(
                "Filled " + ", ".join(f"{f['label']}={f['value']}" for f in filled)
            )
        if pending:
            parts.append(
                "Still needs " + ", ".join(p["label"] for p in pending)
            )
        tail = (
            f" Left the '{submit_el.get('name')}' button for you to confirm and submit."
            if submit_el else " Review and submit when ready."
        )
        return ("; ".join(parts) or "Nothing to fill") + " I did NOT submit." + tail

    def _handoff(self, out, history, *, filled, pending, reason) -> dict:
        return {
            "prepared": False,
            "submitted": False,
            "handoff": True,
            "confirmed_fields": False,
            "final_url": (out or {}).get("url"),
            "final_shot": self._cur_shot,
            "filled_fields": filled,
            "pending_fields": [
                {"label": p, "value": None, "kind": "unmatched",
                 "index": None, "observed": ""}
                for p in pending
            ],
            "submit_control": None,
            "history": history,
            "reason": reason,
            "answer": "",
        }
