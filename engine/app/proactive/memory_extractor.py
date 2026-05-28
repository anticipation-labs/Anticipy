"""
Memory extractor — runs alongside the cascade and decides what's worth
remembering from each chunk for cross-session recall (the "second brain").

A single LLM pass per chunk. No regex, no keyword tables, no hand-rolled
slot extraction. Cop-out #9: every classification is the model's call.

Output is structured: kind ∈ {person, place, preference, commitment,
project, fact}, plus a key + value dict + importance. Writes to a
`MemoryStore` so future cascades can recall who Sarah is, where the wearer
lives, what they prefer, what's promised, etc.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.memory import Memory, MemoryStore

logger = logging.getLogger("engine.proactive.memory_extractor")


LlmCall = Callable[[str, str], Awaitable[str]]

_VALID_KINDS = {"person", "place", "preference", "commitment", "project", "fact"}


_MEMORY_EXTRACT_SYSTEM = """\
You extract durable memories from one chunk of a wearer's diarized
conversation. The wearer has a long-term "second brain" that remembers
who they know, where they live, what they like, what's promised, and
what they're working on. Your one job: identify what's worth remembering
from THIS chunk for future cross-session recall.

Output STRICT JSON only:
{
  "memories": [
    {
      "kind": "<person|place|preference|commitment|project|fact>",
      "key": "<canonical lookup key — a name, a topic, or a short slug>",
      "value": { ...structured details specific to this kind... },
      "importance": <1..5>
    },
    ...
  ]
}

Rules:
  - Only extract things explicitly stated. Never invent.
  - The right kind:
    * person: a NAMED person mentioned with any meaningful context
              (relation, traits, contact, what they do, what they like)
    * place: a NAMED place — home, office, restaurant, gym — that has
             details worth keeping (address, type, why it matters)
    * preference: a stated like / dislike / standard / habit
                  ("I always order italian", "no after-9pm meetings")
    * commitment: something the wearer said they would do, with whom,
                  by when (open commitments are gold)
    * project: an ongoing thing they're working on (renovation, job
               search, fundraise, training plan, etc.)
    * fact: anything else durably true (their kid's name, their address,
            their travel preferences) that doesn't fit the above
  - Pure conversational filler, weather chat, sports recap, hypotheticals,
    speech quoted from someone else → no memories.
  - If the chunk has no durable content, output {"memories": []}.
  - importance: 5 = critical (commitments, key relationships, identity
    facts), 3 = useful context, 1 = minor detail.
  - The "key" is what future code will use to look this up. For persons,
    the name. For places, the place's common name. For preferences, a
    short slug like "preferred_cuisine" or "no_morning_meetings".
  - Output the JSON object only — no prose, no markdown fences.
"""


@dataclass
class MemoryExtractor:
    """Runs a single LLM pass per chunk and writes any returned memories."""

    llm_call: LlmCall
    store: MemoryStore
    timeout_s: float = 8.0

    async def extract_and_write(
        self,
        user_id: str,
        chunk_text: str,
        chunk_id: int = 0,
    ) -> list[Memory]:
        text = (chunk_text or "").strip()
        if not text:
            return []

        user_prompt = (
            f"Chunk transcript:\n\"\"\"\n{text}\n\"\"\"\n\n"
            "Output the JSON."
        )
        try:
            raw = await asyncio.wait_for(
                self.llm_call(_MEMORY_EXTRACT_SYSTEM, user_prompt),
                timeout=self.timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning("memory extractor llm timeout")
            return []
        except Exception:
            logger.exception("memory extractor llm raised")
            return []

        if not raw or not raw.strip():
            return []

        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            logger.debug("memory extractor non-JSON: %r", raw[:200])
            return []

        if not isinstance(data, dict):
            return []

        memories_data = data.get("memories", [])
        if not isinstance(memories_data, list):
            return []

        out: list[Memory] = []
        for entry in memories_data:
            mem = self._row_to_memory(entry, user_id=user_id, chunk_id=chunk_id)
            if mem is None:
                continue
            try:
                written = await self.store.backend.upsert(mem)
            except Exception:
                logger.exception("memory upsert raised")
                continue
            out.append(written)
        return out

    @staticmethod
    def _row_to_memory(
        entry: object,
        *,
        user_id: str,
        chunk_id: int,
    ) -> Memory | None:
        if not isinstance(entry, dict):
            return None
        kind = str(entry.get("kind") or "").strip().lower()
        if kind not in _VALID_KINDS:
            return None
        key = str(entry.get("key") or "").strip()
        if not key:
            return None
        value = entry.get("value") or {}
        if not isinstance(value, dict):
            return None
        try:
            importance = int(entry.get("importance", 3))
        except (ValueError, TypeError):
            importance = 3
        importance = max(1, min(5, importance))
        return Memory(
            id="",
            user_id=user_id,
            kind=kind,
            key=key.strip().lower(),
            value=value,
            importance=importance,
            source_chunks=[chunk_id] if chunk_id else [],
        )
