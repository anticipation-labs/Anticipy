"""
Notes recorder.

Always-on side effect of listening: a scrollable record of meaningful moments
from the user's day. The notes feed is *the user's* — a personal journal
extracted from their voice, not a transcript dump.

Design choices:

- Notes are *summaries*, not raw transcript. The phone-side notes recorder
  collapses repeated content and extracts structured items (todos, names,
  dates, decisions, quotes from the user that they might want back later).
- Notes are written periodically, not per-chunk. Every 60 s of sustained
  speech, OR at end-of-conversation (extended silence > 60 s), we run a
  cheap LLM compaction over the recent buffer and emit notes.
- Notes are scoped per-session (continuous listening session) so that
  scrolling shows conversation arcs rather than disjoint chunks.
- Notes never include audio. Notes never include transcript chunks
  themselves — only summaries derived from them.
- Notes can be turned off entirely (privacy mode); when off, the recorder
  is a no-op but the proactive engine still works (it just has no
  notes-side-effect output).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from .types import Note, TranscriptChunk

logger = logging.getLogger("engine.proactive.notes")


# How long a sustained conversation can run before we compact to notes.
COMPACT_AFTER_SECONDS = 60.0
# After how much silence we treat the conversation as ended and force a flush.
END_OF_CONVERSATION_SILENCE = 60.0
# Max chars of transcript we send to the LLM in one compaction call.
COMPACT_MAX_CHARS = 6000

LLM_TIMEOUT_SECONDS = 8.0

LlmCall = Callable[[str, str], Awaitable[str]]


# --- Storage protocol -----------------------------------------------------------


class NotesStore(Protocol):
    """Where notes get persisted. Server-side: Supabase. Phone-side: SQLite."""

    async def append(self, note: Note) -> None: ...
    async def list_for_session(self, user_id: str, session_id: str) -> list[Note]: ...


@dataclass
class _MemoryNotesStore:
    notes: list[Note] = field(default_factory=list)

    async def append(self, note: Note) -> None:
        self.notes.append(note)

    async def list_for_session(self, user_id: str, session_id: str) -> list[Note]:
        return [n for n in self.notes if n.user_id == user_id and n.session_id == session_id]


# --- The recorder ---------------------------------------------------------------


@dataclass
class _SessionState:
    """In-flight per-session compaction state."""

    user_id: str
    session_id: str
    pending_chunks: list[TranscriptChunk] = field(default_factory=list)
    last_compact_ts: float = field(default_factory=time.time)
    last_chunk_ts: float = field(default_factory=time.time)


class NotesRecorder:
    """Periodically compacts user transcripts into Notes via an LLM."""

    def __init__(
        self,
        llm_call: LlmCall | None,
        store: NotesStore | None = None,
    ) -> None:
        self._llm_call = llm_call
        self._store = store or _MemoryNotesStore()
        self._sessions: dict[str, _SessionState] = {}
        self._enabled = True

    def set_enabled(self, enabled: bool) -> None:
        """Turn notes on/off (privacy mode toggle)."""
        self._enabled = enabled

    async def record(self, chunk: TranscriptChunk) -> None:
        """Buffer a chunk; compact if criteria met."""
        if not self._enabled:
            return
        st = self._sessions.setdefault(
            chunk.session_id,
            _SessionState(user_id=chunk.user_id, session_id=chunk.session_id),
        )
        st.pending_chunks.append(chunk)
        st.last_chunk_ts = time.time()

        if self._should_compact(st):
            await self._compact(st)

    async def flush(self, session_id: str) -> None:
        """Force-compact a session's pending chunks. Call on shutdown / session end."""
        st = self._sessions.get(session_id)
        if st is None or not st.pending_chunks:
            return
        await self._compact(st)

    async def list_session_notes(self, user_id: str, session_id: str) -> list[Note]:
        return await self._store.list_for_session(user_id, session_id)

    # --- Internals -------------------------------------------------------------

    def _should_compact(self, st: _SessionState) -> bool:
        if not st.pending_chunks:
            return False
        time_since_compact = time.time() - st.last_compact_ts
        if time_since_compact >= COMPACT_AFTER_SECONDS:
            return True
        time_since_chunk = time.time() - st.last_chunk_ts
        if time_since_chunk >= END_OF_CONVERSATION_SILENCE:
            return True
        # Also compact aggressively if buffer is huge (chatty user)
        total_chars = sum(len(c.text) for c in st.pending_chunks)
        if total_chars >= COMPACT_MAX_CHARS:
            return True
        return False

    async def _compact(self, st: _SessionState) -> None:
        if self._llm_call is None or not st.pending_chunks:
            return
        chunks = list(st.pending_chunks)
        st.pending_chunks.clear()
        st.last_compact_ts = time.time()

        transcript = "\n".join(c.text for c in chunks if c.text)
        chunk_ids = [c.chunk_id for c in chunks]

        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYSTEM_PROMPT, _user_prompt(transcript)),
                timeout=LLM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("notes_compact_timeout", extra={"session_id": st.session_id})
            return
        except Exception:
            logger.exception("notes_compact_error")
            return

        for parsed in _parse_notes(raw):
            note = Note(
                note_id=uuid.uuid4().hex,
                user_id=st.user_id,
                session_id=st.session_id,
                body=parsed["body"],
                kind=parsed["kind"],
                source_chunk_ids=chunk_ids,
            )
            try:
                await self._store.append(note)
            except Exception:
                logger.exception("notes_store_append_failed")


# --- Prompts --------------------------------------------------------------------


_SYSTEM_PROMPT = """You are extracting *useful notes* from a recent segment of one user's spoken \
transcript (their own voice — diarization already filtered out other speakers). The notes will \
appear in the user's personal journal, scrollable later.

Return STRICT JSON only.

Note kinds (pick the most appropriate; one note can be only one kind):
  - "highlight": a meaningful moment the user might want back ("met Jamie at the cafe")
  - "todo": something the user said they should do (NOT necessarily a triggered intent — just a note)
  - "name": a person mentioned with enough context to remember
  - "date": a date/time mentioned with enough context
  - "decision": a choice the user announced ("I'm going with the blue one")
  - "quote": a memorable thing the user said about themselves

Output schema:
{
  "notes": [
    { "body": "<readable, in 3rd person>", "kind": "<one of the kinds above>" }
  ]
}

Rules:
1. STRICT JSON only.
2. Skip filler, smalltalk, repeats, music lyrics, and self-talk that is just thinking aloud.
3. Compress aggressively — better to emit 0-3 useful notes than 10 noise notes.
4. Body must be a complete sentence, in 3rd person, that makes sense without the transcript.
5. Do NOT include direct addresses to the agent ("Hey Anticipy do X") as notes — those are intents.
6. If nothing is worth noting, return {"notes": []}.
"""


def _user_prompt(transcript: str) -> str:
    return f"""Recent user-voice transcript:
\"\"\"
{transcript[-COMPACT_MAX_CHARS:]}
\"\"\"

Extract notes."""


def _parse_notes(raw: str) -> list[dict]:
    """Strict JSON only. JSON mode is forced upstream; on parse failure, drop the batch."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    notes_data = data.get("notes") or []
    valid_kinds = {"highlight", "todo", "name", "date", "decision", "quote"}
    out = []
    for item in notes_data:
        body = (item.get("body") or "").strip()
        kind = (item.get("kind") or "highlight").strip().lower()
        if not body or kind not in valid_kinds:
            continue
        out.append({"body": body, "kind": kind})
    return out
