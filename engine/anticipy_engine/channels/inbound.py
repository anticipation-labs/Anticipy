"""InboundPoller — the owner's SMS replies come back into the engine.

Polls Twilio's Messages REST list — researched shape: GET
/2010-04-01/Accounts/{sid}/Messages.json?To=<our number>&PageSize=N with HTTP basic
auth; the response is {"messages": [{sid, body, from, to, direction, date_sent}, ...]}
with direction == "inbound" for received SMS. No DateSent inequality filters are used
(their encoding is version-fragile); newness is decided client-side by a persisted
seen-sid set plus a cold-start time floor.

Each new inbound message from the OWNER's number is either:
  - a reply — "YES <code>" / "NO <code>" (code = a >=4-char prefix of the ask id,
    case-insensitive; bare YES/NO accepted only when exactly ONE ask is pending) —
    which resolves the pending ask THROUGH ControlCore.resolve, never
    proactive.resolve_ask directly, so owner card records get their durable
    write-back (ledger F18); or
  - owner speech -> ControlCore.owner_ingest (the same Action Engine door as
    transcript/MP3/listening), with execution on — the harm-line still rules.

Safety posture:
  - No OWNER_PHONE -> the poller refuses to resolve or ingest anything (an approval
    door open to arbitrary senders is the alternative). Non-owner senders are logged
    and skipped. Ambiguous replies (no/zero/multiple matches) resolve NOTHING —
    but the owner is TOLD so (ledger F20): one bounded clarification SMS per poll
    pass, listing the exact pending codes, sent back over the same channel through
    notify_user (mock/live triad). The clarification is itself an interruption: it
    draws on the proactive AnnoyanceBudget and is suppressed toward silence when
    the daily budget is spent. It can never resolve, approve, or execute anything.
  - Processed sids persist atomically to <data>/inbound_seen.json and a message is
    marked seen BEFORE it is acted on: a crash mid-action loses one inbound toward
    silence, it never replays an approval. A missing/corrupt seen file falls back to
    the construction-time floor, so cold starts never replay history either.
  - Mock-safe: no Twilio transport is constructed unless the live env triad is
    present; tests inject `fetch`.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, List, Optional

# YES/NO, optional separator, optional short code, optional trailing punctuation.
# Anchored end-to-end so conversational lines ("no way that works") never match.
_REPLY = re.compile(r"^\s*(yes|no)\b(?:[\s,.:!-]+([A-Za-z0-9]{4,32}))?[\s.!]*$", re.I)
_SEEN_CAP = 1000
# F20 clarification bounds: list at most this many pending asks, each action
# snippet truncated — the reply must stay one bounded SMS, never a transcript dump.
_CLARIFY_LIST_CAP = 5
_CLARIFY_ACTION_CHARS = 60


def _norm_phone(s: str) -> str:
    """E.164-insensitive compare for the owner gate: keep digits and drop a leading
    country '1', so +1 604..., 1604..., (604) ..., 604-... all match the stored
    OWNER_PHONE. Defensive only — Twilio reports E.164 — but a format drift must
    NEVER silently drop the owner's own YES/NO reply (that reads as a missed loop)."""
    d = re.sub(r"\D", "", s or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return d


class InboundPoller:
    def __init__(self, core, fetch: Optional[Callable[[], List[dict]]] = None,
                 data_dir=None) -> None:
        self.core = core
        self._fetch = fetch
        self._seen_path = Path(data_dir or core.data_dir) / "inbound_seen.json"
        self.seen: List[str] = []          # insertion-ordered, capped
        self.floor: float = time.time()    # cold-start: never act on older messages
        self._clarified_pass = False       # F20: at most ONE clarification per poll pass
        self._load_seen()

    @staticmethod
    def live_ready() -> bool:
        return (os.environ.get("ANTICIPY_CHANNELS_MODE") == "live"
                and bool(os.environ.get("TWILIO_ACCOUNT_SID"))
                and bool(os.environ.get("TWILIO_AUTH_TOKEN"))
                and bool(os.environ.get("TWILIO_FROM")))

    # ---- one pass: fetch -> filter -> reply/ingest ----
    async def poll_once(self) -> dict:
        out = {"fetched": 0, "resolved": [], "ingested": [], "skipped": [], "clarified": []}
        self._clarified_pass = False
        owner = (os.environ.get("OWNER_PHONE") or "").strip()
        if not owner:
            self._log("inbound_skipped", {"reason": "OWNER_PHONE unset — refusing to "
                                          "resolve or ingest from unverified senders"})
            return out
        msgs = self._fetch() if self._fetch is not None else self._twilio_fetch()
        out["fetched"] = len(msgs)
        for m in sorted(msgs, key=self._ts):   # oldest first: replies land in spoken order
            sid = m.get("sid")
            if not sid or sid in self.seen:
                continue
            self._mark_seen(sid)               # BEFORE acting: never replay an approval
            if (m.get("direction") or "") != "inbound":
                continue
            if _norm_phone(m.get("from")) != _norm_phone(owner):
                self._log("inbound_skipped", {"sid": sid, "reason": "not the owner's number"})
                out["skipped"].append({"sid": sid, "reason": "sender"})
                continue
            if self._ts(m) < self.floor:
                self._log("inbound_skipped", {"sid": sid, "reason": "older than cold-start floor"})
                out["skipped"].append({"sid": sid, "reason": "stale"})
                continue
            body = (m.get("body") or "").strip()
            reply = _REPLY.match(body)
            if reply:
                await self._resolve_reply(sid, reply, out, owner)
            else:
                res = await self.core.owner_ingest(
                    "sms", body, {"inbound_sid": sid, "from": "owner"}, execute_actions=True)
                self._log("inbound_ingested", {"sid": sid, "cards": len(res.get("cards", []))})
                out["ingested"].append({"sid": sid, "cards": len(res.get("cards", []))})
        return out

    async def _resolve_reply(self, sid: str, reply: re.Match, out: dict, owner: str) -> None:
        approved = reply.group(1).lower() == "yes"
        code = (reply.group(2) or "").lower()
        pending = self.core.pending_asks()
        if code:   # the regex guarantees >= 4 chars — long enough to trust as a prefix
            matches = [p for p in pending if p["ask_id"].lower().startswith(code)]
        else:
            matches = pending if len(pending) == 1 else []
        if len(matches) != 1:
            # zero or many: resolving a guess approves something the owner did not —
            # refuse, loudly. (The ask SMS carries the exact code to reply with.)
            self._log("inbound_ambiguous", {"sid": sid, "code": code or None,
                                            "pending": len(pending), "matches": len(matches)})
            out["skipped"].append({"sid": sid, "reason": "ambiguous"})
            await self._clarify(sid, code, pending, owner, out)
            return
        res = await self.core.resolve(matches[0]["ask_id"], approved)   # F18: the ONE door
        self._log("inbound_resolved", {"sid": sid, "ask_id": matches[0]["ask_id"],
                                       "approved": approved,
                                       "resolved": res.get("resolved", True)})
        out["resolved"].append({"sid": sid, "ask_id": matches[0]["ask_id"], "approved": approved})

    # ---- F20: the owner answered and nothing happened — say so, bounded ----
    async def _clarify(self, sid: str, code: str, pending: list, owner: str, out: dict) -> None:
        """One bounded clarification SMS back to the owner after an ambiguous reply.

        It can only ever SEND TEXT: no resolve, no approve, no goal, no execution
        in any branch. Bounds, every one failing toward silence: at most one send
        per poll pass (a burst of ambiguous messages is one confusion, not many);
        the proactive AnnoyanceBudget both counts the send and suppresses it when
        the daily interruption budget is spent (the glassbox inbound_ambiguous
        entry above already recorded the refusal); the recipient is the
        already-verified owner number only — non-owner senders never reach here.
        """
        if self._clarified_pass:
            self._log("inbound_clarify_skipped", {"sid": sid, "reason": "already clarified this pass"})
            return
        # A failed/suppressed send must never burst-retry SMS within the pass.
        self._clarified_pass = True
        budget = self.core.proactive.budget
        now = time.time()
        if budget.count(now) >= budget.max_per_day:
            self._log("inbound_clarify_suppressed",
                      {"sid": sid, "reason": f"over interruption budget ({budget.max_per_day}/day)"})
            return
        msg = self._clarify_text(code, pending)
        res = await self.core.notify_user(msg, recipient=owner)
        sent = (res or {}).get("status") == "success"
        if sent:
            budget.record_interruption(now)   # a clarification is not free (ledger F20)
        self._log("inbound_clarified", {"sid": sid, "pending": len(pending),
                                        "listed": min(len(pending), _CLARIFY_LIST_CAP),
                                        "sent": sent})
        out["clarified"].append({"sid": sid, "pending": len(pending), "sent": sent})

    @staticmethod
    def _clarify_text(code: str, pending: list) -> str:
        """Bounded body: what didn't match, then the exact codes that WILL."""
        if not pending:
            return ("Anticipy: nothing is pending right now, so that reply didn't "
                    "change anything (the ask may already be resolved).")
        head = (f"Anticipy: code {code.upper()} doesn't match a pending ask." if code
                else f"Anticipy: {len(pending)} asks are pending, so a bare reply is ambiguous.")
        lines = [head + " Reply with the exact code:"]
        for p in pending[:_CLARIFY_LIST_CAP]:
            action = (p.get("action") or "").strip()[:_CLARIFY_ACTION_CHARS]
            lines.append(f"YES {p['ask_id'][:6]} / NO {p['ask_id'][:6]} — {action}")
        if len(pending) > _CLARIFY_LIST_CAP:
            lines.append(f"...and {len(pending) - _CLARIFY_LIST_CAP} more in the app.")
        return "\n".join(lines)

    # ---- seen-sid persistence (atomic; lose-toward-silence) ----
    def _mark_seen(self, sid: str) -> None:
        self.seen.append(sid)
        if len(self.seen) > _SEEN_CAP:
            self.seen = self.seen[-_SEEN_CAP:]
        try:
            self._seen_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._seen_path.with_suffix(self._seen_path.suffix + ".tmp")
            tmp.write_text(json.dumps({"floor": self.floor, "sids": self.seen}))
            os.replace(tmp, self._seen_path)
        except OSError as e:
            self._log("inbound_seen_persist_failed", {"error": str(e)})

    def _load_seen(self) -> None:
        if not self._seen_path.exists():
            return
        try:
            data = json.loads(self._seen_path.read_text())
            self.seen = [str(s) for s in data.get("sids", [])][-_SEEN_CAP:]
            self.floor = float(data.get("floor", self.floor))
        except Exception as e:
            # unreadable history: keep the fresh floor (now) so nothing replays
            self._log("inbound_seen_corrupt", {"path": str(self._seen_path), "error": str(e)})

    @staticmethod
    def _ts(m: dict) -> float:
        """Message send time as epoch; unparseable/absent sorts newest (still due)."""
        raw = m.get("date_sent")
        if not raw:
            return float("inf")
        try:
            return parsedate_to_datetime(raw).timestamp()
        except (TypeError, ValueError):
            return float("inf")

    # ---- live transport (env-gated; tests inject fetch instead) ----
    def _twilio_fetch(self) -> List[dict]:   # pragma: no cover
        if not self.live_ready():
            return []
        sid = os.environ["TWILIO_ACCOUNT_SID"]
        token = os.environ["TWILIO_AUTH_TOKEN"]
        params = urllib.parse.urlencode({"To": os.environ["TWILIO_FROM"], "PageSize": "50"})
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json?{params}"
        req = urllib.request.Request(url)
        req.add_header("Authorization",
                       "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode())
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return (json.loads(r.read().decode()) or {}).get("messages", []) or []
        except Exception as e:
            self._log("inbound_fetch_failed", {"error": str(e)})
            return []

    def _log(self, kind: str, data: dict) -> None:
        glass = getattr(self.core, "glassbox", None)
        if glass is not None:
            glass.log(kind, data)
