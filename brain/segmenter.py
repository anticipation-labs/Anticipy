"""Conversation segmentation — where a conversation begins and ends.

STEP 1 of CAPTURE-ARCHITECTURE.md. The functions here are PURE (dicts in,
decisions out) so the rules can be tested without a database, a network, or a
model. `SegmentStore` is the only part that talks to PocketBase.

The central idea: a conversation is not "however long a recognizer happened to
live". It is a row that stays OPEN with a rolling `last_speech_at`. A dropped
Bluetooth link, a backgrounded app or a recognizer swap therefore cannot end a
conversation — only real silence can.

THE RULE THAT MUST NEVER BE BROKEN: every boundary decision keys off CAPTURE
time, never arrival time. Store-and-forward backlog arrives long after it was
spoken; judging it by arrival shatters one conversation into many (the bug Omi
ships as #6551). Our pendant is store-and-forward, so this is guaranteed, not
hypothetical.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import pb

# --- boundary parameters (CAPTURE-ARCHITECTURE.md) ------------------------
CONTINUE_S = 45          # silence below this = same conversation, zero cost
GATE_BAND_S = 300        # below: lean same-topic; above: lean new
LINK_MAX_S = 1200        # beyond 20 min, never link
MAX_SEGMENT_S = 1800     # force-close a runaway segment, then relink
LATE_MAX_S = 6 * 3600    # older than this: remember, never act

_STOP = {
    "the", "a", "an", "and", "or", "but", "so", "to", "of", "in", "on", "at",
    "for", "with", "is", "are", "was", "were", "be", "been", "it", "that",
    "this", "i", "you", "we", "they", "he", "she", "my", "your", "our", "me",
    "just", "like", "have", "has", "had", "do", "does", "did", "not", "no",
    "yes", "okay", "ok", "well", "then", "there", "here", "what", "when",
}

# A short line that leans on what came before ("anyway, where were we") is a
# continuation signal, not a new subject.
_ANAPHORIC = re.compile(
    r"^\s*(so|anyway|anyways|okay|ok|right|back to|where were we|and|but|also|"
    r"it|that|they|he|she|those|these|which)\b", re.IGNORECASE)


# A capture time is only believable inside a window a person could have spoken
# in. 2001 to 2096 in seconds, the same window in milliseconds. Anything else —
# a date written as 20260806, a duration, a zero — is not a moment in time, and
# guessing at it would put speech in the wrong conversation.
_EPOCH_S_MIN, _EPOCH_S_MAX = 1_000_000_000, 4_000_000_000
_EPOCH_MS_MIN, _EPOCH_MS_MAX = _EPOCH_S_MIN * 1000, _EPOCH_S_MAX * 1000


def parse_ts(value) -> Optional[datetime]:
    """PocketBase, ISO8601 and epoch numbers, always tz-aware UTC.

    Epoch is handled because the alternative is worse than a wrong format: an
    unreadable capture time makes a turn UNPLACEABLE, and an unplaceable turn is
    silently dropped. Losing what someone said, because a number arrived where a
    string was expected, is not a failure this is allowed to have.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):            # True is not a timestamp
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        if _EPOCH_S_MIN <= n <= _EPOCH_S_MAX:
            return datetime.fromtimestamp(n, tz=timezone.utc)
        if _EPOCH_MS_MIN <= n <= _EPOCH_MS_MAX:
            return datetime.fromtimestamp(n / 1000.0, tz=timezone.utc)
        return None
    s = str(value).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # A bare epoch that arrived as text is still a moment in time.
        try:
            return parse_ts(float(s))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(w) > 2 and w not in _STOP}


def proper_nouns(text: str) -> set[str]:
    """Capitalised words that aren't sentence-initial — names, places, brands."""
    words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", text or "")
    return {w.lower() for w in words}


def capture_span(event: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """When this was SPOKEN. Falls back to arrival only while older app builds
    are still posting — step 2 removes the fallback."""
    start = parse_ts(event.get("capture_started_at")) or parse_ts(event.get("created"))
    end = parse_ts(event.get("capture_ended_at")) or start
    return start, end


def decide_link(gap_s: float, text: str, prev_segment: Optional[dict]) -> tuple[str, str]:
    """Does this turn continue the previous conversation?

    Returns (decision, why) where decision is one of:
      append   — the open segment is still live, no model call
      link     — new segment, but threaded onto the previous one
      new      — genuinely unrelated
      escalate — ambiguous; worth one cheap model call
    """
    if gap_s < CONTINUE_S:
        return "append", f"gap {gap_s:.0f}s < {CONTINUE_S}s"
    if prev_segment is None:
        return "new", "nothing to link to"
    if gap_s >= LINK_MAX_S:
        return "new", f"gap {gap_s:.0f}s >= {LINK_MAX_S}s"

    try:
        prior_entities = set(json.loads(prev_segment.get("entities") or "[]"))
    except Exception:
        prior_entities = set()
    prior_words = content_words(prev_segment.get("summary") or "") | prior_entities

    words = content_words(text)
    names = proper_nouns(text)

    # A shared name is the strongest free signal that a topic resumed.
    if names & prior_entities:
        return "link", "shares a name with the previous conversation"
    overlap = words & prior_words
    if len(overlap) >= 2:
        return "link", f"shares {sorted(overlap)[:3]}"

    # Count words as SPOKEN, not content words: "I should probably book the
    # flights for that trip" is a substantive sentence even though most of it
    # is stopwords, and treating it as a passing remark wrongly glued it onto
    # whatever came before.
    short = len((text or "").split()) < 8
    if _ANAPHORIC.match(text or "") or short:
        # "anyway…", "so…", or just a brief remark: leans on prior context.
        return ("link", "anaphoric/short, still inside the near band") if gap_s < GATE_BAND_S \
            else ("escalate", "anaphoric/short but a long way back")
    if gap_s >= GATE_BAND_S:
        return "new", "substantive, no overlap, beyond the near band"
    return "escalate", "substantive, no overlap, but recent"


def should_close(open_segment: dict, now: datetime) -> tuple[bool, str]:
    """Has this conversation gone quiet long enough to be over?"""
    last = parse_ts(open_segment.get("last_speech_at"))
    started = parse_ts(open_segment.get("started_at"))
    if last is None:
        return False, "no speech recorded yet"
    if (now - last).total_seconds() >= CONTINUE_S:
        return True, f"quiet for {(now - last).total_seconds():.0f}s"
    if started and (now - started).total_seconds() >= MAX_SEGMENT_S:
        return True, f"ran {MAX_SEGMENT_S}s — force-closing, will relink"
    return False, "still live"


def is_late(event: dict, now: datetime) -> bool:
    """Too old to act on — remember it, never act."""
    start, _ = capture_span(event)
    return bool(start and (now - start).total_seconds() > LATE_MAX_S)


def _as_prev_segment(turns: list[dict]) -> dict:
    """Shape a conversation-so-far the way `decide_link` expects to read one.

    Mirrors what SegmentStore.append writes: the spoken text as the summary,
    and the accumulated proper nouns as entities, capped the same way.
    """
    text = " ".join((t.get("text") or "") for t in turns)
    entities: set[str] = set()
    for t in turns:
        entities |= proper_nouns(t.get("text") or "")
    return {"summary": text, "entities": json.dumps(sorted(entities)[:40])}


def segment_all(turns: list[dict]) -> list[list[dict]]:
    """Group heard turns into conversations. Pure — no database, no network,
    no model, and no wall clock.

    This exists so the one question that matters can actually be ASKED: "how
    many conversations was that?" Everything else in this module answers it one
    turn at a time against PocketBase, which means the only way to check the
    boundary rules was to run the whole system and look at a screenshot.

    THE LAW IT UPHOLDS: the answer depends on when things were SPOKEN and on
    nothing else. The pendant is store-and-forward — it buffers and flushes, so
    arrival order is not speech order, and a backlog can land in one lump
    minutes later. Judging by arrival is what shatters one phone call into three
    conversations (Omar's screenshot; the bug Omi ships as #6551). So turns are
    ordered by capture time, ties are broken by content, and `created` is never
    read except as a fallback for old app builds that posted no capture time.

    Turns with no usable capture time at all are left out rather than guessed
    at — they cannot be placed in time, and inventing a position for them is
    exactly the kind of filled-in blank that causes the damage elsewhere.

    MAX_SEGMENT_S is deliberately NOT applied here. Force-closing a runaway
    segment bounds the size of a database row; it does not mean the person
    stopped having the conversation. A forty-minute call is one call.

    Returns conversations in capture order, each a list of turns in capture
    order. The input list is not modified.
    """
    placed: list[tuple[datetime, datetime, dict]] = []
    for t in turns or []:
        if not isinstance(t, dict):
            continue
        start, end = capture_span(t)
        if start is None:
            continue
        placed.append((start, end or start, t))
    if not placed:
        return []

    # Capture time, then content. Never arrival: two turns spoken in the same
    # second must land in the same order however the network delivered them.
    placed.sort(key=lambda p: (p[0], p[1],
                               str(p[2].get("id") or ""), str(p[2].get("text") or "")))

    conversations: list[list[dict]] = []
    spans: list[tuple[datetime, datetime]] = []      # (started, last speech)
    for start, end, turn in placed:
        if not conversations:
            conversations.append([turn])
            spans.append((start, end))
            continue
        began, last = spans[-1]
        gap_s = max(0.0, (start - last).total_seconds())
        decision, _why = decide_link(gap_s, turn.get("text") or "",
                                     _as_prev_segment(conversations[-1]))
        # `append` is the same breath; `link` is the same subject picked back
        # up, which is the same conversation by any human reading. `escalate`
        # means the rules genuinely cannot tell — and with no model to ask,
        # this stays with what the live path does with it: start a new one.
        if decision in ("append", "link"):
            conversations[-1].append(turn)
            spans[-1] = (began, max(last, end))
        else:
            conversations.append([turn])
            spans.append((start, end))
    return conversations


class SegmentStore:
    """The thin PocketBase layer. Everything above is pure."""

    def __init__(self, backend_url: str, owner: str = ""):
        self.base = backend_url.rstrip("/")
        self.owner = owner

    def open_segment(self) -> Optional[dict]:
        try:
            filt = 'status="open"'
            if self.owner:
                filt += f' && owner="{self.owner}"'
            r = pb.get(f"{self.base}/api/collections/segments/records",
                       params={"filter": filt, "sort": "-last_speech_at", "perPage": 1})
            items = r.json().get("items", []) if r.ok else []
            return items[0] if items else None
        except Exception:
            return None

    def last_closed(self) -> Optional[dict]:
        try:
            filt = 'status="closed"'
            if self.owner:
                filt += f' && owner="{self.owner}"'
            r = pb.get(f"{self.base}/api/collections/segments/records",
                       params={"filter": filt, "sort": "-ended_at", "perPage": 1})
            items = r.json().get("items", []) if r.ok else []
            return items[0] if items else None
        except Exception:
            return None

    def recent_turns(self, segment_id: str, limit: int = 8) -> list[str]:
        """What was already said in this conversation — the context a question
        needs. 'What time is the demo day Monday' means nothing alone."""
        try:
            r = pb.get(f"{self.base}/api/collections/events/records",
                       params={"filter": f'segment="{segment_id}" && kind="transcript"',
                               "sort": "-created", "perPage": limit})
            items = r.json().get("items", []) if r.ok else []
            return [i.get("text", "") for i in reversed(items) if i.get("text")]
        except Exception:
            return []

    def create(self, started: datetime, parent: Optional[str] = None) -> Optional[dict]:
        try:
            r = pb.post(f"{self.base}/api/collections/segments/records", json={
                "owner": self.owner, "status": "open",
                "started_at": iso(started), "last_speech_at": iso(started),
                "turn_count": 0, "word_count": 0,
                "parent_segment": parent or "", "entities": "[]",
                "triaged_through_seq": 0, "dirty": False,
            })
            return r.json() if r.ok else None
        except Exception:
            return None

    def append(self, segment: dict, event: dict, ended: datetime) -> None:
        text = event.get("text") or ""
        try:
            entities = set(json.loads(segment.get("entities") or "[]"))
        except Exception:
            entities = set()
        entities |= proper_nouns(text)
        try:
            pb.patch(f"{self.base}/api/collections/segments/records/{segment['id']}", json={
                "last_speech_at": iso(ended),
                "turn_count": int(segment.get("turn_count") or 0) + 1,
                "word_count": int(segment.get("word_count") or 0) + len(text.split()),
                "entities": json.dumps(sorted(entities)[:40]),
            })
        except Exception:
            pass

    def close(self, segment: dict, ended: datetime) -> None:
        try:
            pb.patch(f"{self.base}/api/collections/segments/records/{segment['id']}",
                     json={"status": "closed", "ended_at": iso(ended)})
        except Exception:
            pass

    def stamp_event(self, event_id: str, segment_id: str) -> None:
        try:
            pb.patch(f"{self.base}/api/collections/events/records/{event_id}",
                     json={"segment": segment_id})
        except Exception:
            pass


def place_turn(store: SegmentStore, event: dict, now: Optional[datetime] = None) -> dict:
    """Put one heard turn into the right conversation. Step 1 ONLY records
    this — nothing downstream reads it yet, so behaviour is unchanged."""
    now = now or datetime.now(timezone.utc)
    start, end = capture_span(event)
    if start is None:
        return {"decision": "skipped", "why": "no usable capture time"}
    end = end or start

    seg = store.open_segment()
    if seg:
        close_it, why_close = should_close(seg, start)
        if close_it:
            store.close(seg, parse_ts(seg.get("last_speech_at")) or start)
            prev, seg = seg, None
        else:
            prev = None
    else:
        prev = store.last_closed()

    if seg is not None:
        store.append(seg, event, end)
        store.stamp_event(event["id"], seg["id"])
        return {"decision": "append", "why": "conversation still open",
                "segment": seg["id"]}

    gap_s = LINK_MAX_S + 1
    if prev is not None:
        prev_end = parse_ts(prev.get("ended_at")) or parse_ts(prev.get("last_speech_at"))
        if prev_end:
            gap_s = max(0.0, (start - prev_end).total_seconds())
    decision, why = decide_link(gap_s, event.get("text") or "", prev)
    parent = prev["id"] if (prev and decision in ("link", "escalate")) else None
    fresh = store.create(start, parent=parent)
    if not fresh:
        return {"decision": "failed", "why": "could not open a segment"}
    store.append(fresh, event, end)
    store.stamp_event(event["id"], fresh["id"])
    return {"decision": decision, "why": why, "segment": fresh["id"],
            "gap_s": round(gap_s, 1), "parent": parent}
