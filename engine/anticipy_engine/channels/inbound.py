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
    and skipped. Ambiguous replies (no/zero/multiple matches) resolve NOTHING.
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


class InboundPoller:
    def __init__(self, core, fetch: Optional[Callable[[], List[dict]]] = None,
                 data_dir=None) -> None:
        self.core = core
        self._fetch = fetch
        self._seen_path = Path(data_dir or core.data_dir) / "inbound_seen.json"
        self.seen: List[str] = []          # insertion-ordered, capped
        self.floor: float = time.time()    # cold-start: never act on older messages
        self._load_seen()

    @staticmethod
    def live_ready() -> bool:
        return (os.environ.get("ANTICIPY_CHANNELS_MODE") == "live"
                and bool(os.environ.get("TWILIO_ACCOUNT_SID"))
                and bool(os.environ.get("TWILIO_AUTH_TOKEN"))
                and bool(os.environ.get("TWILIO_FROM")))

    # ---- one pass: fetch -> filter -> reply/ingest ----
    async def poll_once(self) -> dict:
        out = {"fetched": 0, "resolved": [], "ingested": [], "skipped": []}
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
            if (m.get("from") or "").strip() != owner:
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
                await self._resolve_reply(sid, reply, out)
            else:
                res = await self.core.owner_ingest(
                    "sms", body, {"inbound_sid": sid, "from": "owner"}, execute_actions=True)
                self._log("inbound_ingested", {"sid": sid, "cards": len(res.get("cards", []))})
                out["ingested"].append({"sid": sid, "cards": len(res.get("cards", []))})
        return out

    async def _resolve_reply(self, sid: str, reply: re.Match, out: dict) -> None:
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
            return
        res = await self.core.resolve(matches[0]["ask_id"], approved)   # F18: the ONE door
        self._log("inbound_resolved", {"sid": sid, "ask_id": matches[0]["ask_id"],
                                       "approved": approved,
                                       "resolved": res.get("resolved", True)})
        out["resolved"].append({"sid": sid, "ask_id": matches[0]["ask_id"], "approved": approved})

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
