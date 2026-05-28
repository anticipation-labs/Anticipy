"""Pod A pipeline orchestrator — composes audio → ASR → VAD → diarization
→ Stage 1 → Stage 1.5 → Stage 2 → publish to Supabase Realtime.

Two entry points:

  PodAPipeline.from_text(text, user_id, ...) — skips audio layers, runs
  Stage 1 onward against typed text. Used by tests against the
  gold-standard set, and by the /engine page's manual-typed-task box.

  PodAPipeline.from_wav(path, user_id, ...) — runs the full audio
  pipeline against a single WAV file. Used by
  `engine/tests/fixtures/gold_standard/*.wav` end-to-end tests.

Streaming (`from_mic`) is provided by the Mac app's audio harness,
not here — this module is the offline / per-segment entry point.

Publishing:
  - COMMIT or STORE_AS_LATENT → INSERT into `anticipy_intents_v2`
  - Memory write (sarcasm-derived aversion etc.) → INSERT into
    `anticipy_memory`
  - Supabase Realtime automatically pushes to channel
    `intent.detected.{user_id}` because the table is in the
    `supabase_realtime` publication (per the migration).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.proactive.demand_detection import DemandDecision, DemandDetector
from app.proactive.hedge_filter import HedgeFilter, HedgeResult
from app.proactive.intent_extraction import IntentExtractor, TypedIntent

_logger = logging.getLogger("anticipy.proactive.pipeline")


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """What the pipeline did with one utterance — for callers that need
    to log / display the cascade's decision."""

    utterance: str
    user_id: str
    demand: Optional[DemandDecision]
    hedge: Optional[HedgeResult]
    intent: Optional[TypedIntent]
    published: bool
    memory_written: bool


class PodAPipeline:
    """The proactive cascade. Stage 1 → 1.5 → 2 → publish."""

    def __init__(
        self,
        demand_detector: Optional[DemandDetector] = None,
        hedge_filter: Optional[HedgeFilter] = None,
        intent_extractor: Optional[IntentExtractor] = None,
        supabase=None,  # `supabase.Client | None` — lazy-imported at use
    ) -> None:
        self._demand = demand_detector or DemandDetector()
        self._hedge = hedge_filter or HedgeFilter()
        self._intent = intent_extractor or IntentExtractor()
        self._supabase = supabase

    async def from_text(
        self,
        utterance: str,
        user_id: str,
        source: str = "typed",
        utterance_window: Optional[dict] = None,
        context_transcript: Optional[str] = None,
        context_memory: Optional[str] = None,
    ) -> PipelineResult:
        """Run the cascade against an already-transcribed utterance.

        Order:
          Stage 1   → if not actionable, return (no rows written)
          Stage 1.5 → REFUSE => maybe memory write, no Intent row
                      STORE_AS_LATENT => Intent row, no Task dispatch
                      COMMIT => Intent row, middle layer dispatches
          Stage 2   → extract typed Intent (only on COMMIT or COMMIT-able
                      STORE_AS_LATENT)
          publish   → INSERT intents_v2 row → Realtime push
        """
        demand = await self._demand.classify(utterance, context_transcript)
        if not demand.actionable:
            _logger.debug("Stage 1 dropped %r as not actionable", utterance)
            return PipelineResult(
                utterance=utterance,
                user_id=user_id,
                demand=demand,
                hedge=None,
                intent=None,
                published=False,
                memory_written=False,
            )

        hedge = await self._hedge.classify(
            utterance,
            context=context_transcript,
            user_memory_summary=context_memory,
        )

        # Memory write happens for REFUSE-with-evidence (sarcasm-derived
        # aversions) AND any other store_as_memory result regardless of
        # decision (e.g. a COMMIT that also reveals a habit).
        memory_written = False
        if hedge.store_as_memory is not None:
            memory_written = self._write_memory(user_id, hedge)

        if hedge.decision == "REFUSE":
            return PipelineResult(
                utterance=utterance,
                user_id=user_id,
                demand=demand,
                hedge=hedge,
                intent=None,
                published=False,
                memory_written=memory_written,
            )

        # COMMIT or STORE_AS_LATENT — extract typed intent.
        intent = await self._intent.extract(
            utterance=utterance,
            user_id=user_id,
            utterance_window=utterance_window or {
                "transcript_segments": [{"speaker": "wearer", "text": utterance}],
                "start_ts": "",
                "end_ts": "",
            },
            hedge_result=hedge,
            source=source,
            context_transcript=context_transcript,
            context_memory=context_memory,
            detection_confidence=demand.confidence,
        )
        published = self._publish_intent(intent)
        return PipelineResult(
            utterance=utterance,
            user_id=user_id,
            demand=demand,
            hedge=hedge,
            intent=intent,
            published=published,
            memory_written=memory_written,
        )

    async def from_wav(
        self,
        path: Path,
        user_id: str,
        source: str = "mac_mic",
    ) -> PipelineResult:
        """Full audio→Intent path. Used by the gold-standard test harness
        in `engine/tests/test_proactive_pipeline.py`.

        Loads asr/vad/diarization lazily — this method fails loud if the
        heavy deps aren't installed, rather than at module import time.
        """
        from app.proactive.asr import get_asr

        asr = get_asr()
        segments = list(asr.transcribe_file(path))
        if not segments:
            _logger.info("no speech detected in %s", path)
            return PipelineResult(
                utterance="",
                user_id=user_id,
                demand=None,
                hedge=None,
                intent=None,
                published=False,
                memory_written=False,
            )
        # Concatenate all wearer-attributable segments. Diarization
        # filtering happens here in production; for fixture WAVs the
        # whole clip is assumed to be the wearer.
        utterance = " ".join(s.text for s in segments).strip()
        utterance_window = {
            "transcript_segments": [
                {"speaker": "wearer", "text": s.text, "start_s": s.start_s, "end_s": s.end_s}
                for s in segments
            ],
            "start_ts": str(segments[0].start_s),
            "end_ts": str(segments[-1].end_s),
        }
        return await self.from_text(
            utterance=utterance,
            user_id=user_id,
            source=source,
            utterance_window=utterance_window,
        )

    # ─── publishing ────────────────────────────────────────────────────

    def _ensure_supabase(self):
        if self._supabase is not None:
            return self._supabase
        try:
            from supabase import create_client  # type: ignore
            import os
        except ImportError:
            return None
        url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return None
        self._supabase = create_client(url, key)
        return self._supabase

    def _publish_intent(self, intent: TypedIntent) -> bool:
        sb = self._ensure_supabase()
        if sb is None:
            _logger.warning(
                "supabase client unavailable, intent %s not published", intent.intent_id
            )
            return False
        try:
            sb.table("anticipy_intents_v2").insert(intent.to_db_row()).execute()
            return True
        except Exception as e:
            _logger.error("publish_intent failed: %s", e)
            return False

    def _write_memory(self, user_id: str, hedge: HedgeResult) -> bool:
        if hedge.store_as_memory is None:
            return False
        sb = self._ensure_supabase()
        if sb is None:
            return False
        try:
            sb.table("anticipy_memory").insert(
                {
                    "user_id": user_id,
                    "kind": hedge.store_as_memory.kind,
                    "key": hedge.store_as_memory.key,
                    "value": hedge.store_as_memory.value,
                    "evidence_quote": hedge.store_as_memory.evidence_quote,
                    "confidence": hedge.confidence,
                }
            ).execute()
            return True
        except Exception as e:
            _logger.error("write_memory failed: %s", e)
            return False
