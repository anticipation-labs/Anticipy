"""Stage 1.5 — hedge / sarcasm / abandonment classifier.

Sits between Stage 1 demand detection and Stage 2 typed-Intent extraction.
For any utterance that passes Stage 1, decides:

  COMMIT          — clear request to act with enough specificity
  STORE_AS_LATENT — intent expressed but not committed (hedging,
                    "I should probably text Sarah"). Surfaces later
                    when the wearer follows up.
  REFUSE          — sarcasm, retraction, past-tense recap, third-party
                    reporting, conditional. NO action fires, but the
                    utterance may still write to memory (sarcasm reveals
                    aversion — that's data).

This module supports two backends, set at construction:

  backend="cascade"  : few-shot prompt over the engine's free-tier cascade
                       (Mistral → Gemini → Groq via llm_adapter). DEFAULT.
                       Works today against the existing infra.
  backend="adapter"  : the QLoRA adapter at
                       ~/.anticipy/adapters/hedge_filter_v1/. Phase 1's
                       trained-on-synthetic-data adapter — drops in
                       transparently once available.

The few-shot examples come from `engine/data/synth/gold_standard.jsonl`.
We sample one row per boundary tag so the classifier sees the full
breadth of failure modes in every call.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from app.proactive.llm_adapter import make_json_llm_call

_logger = logging.getLogger("anticipy.proactive.hedge_filter")

HedgeDecision = Literal["COMMIT", "STORE_AS_LATENT", "REFUSE"]

GOLD_STANDARD_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "synth" / "gold_standard.jsonl"
)

_SYSTEM_PROMPT_TEMPLATE = """\
You are the Stage 1.5 hedge / sarcasm / abandonment classifier for an
ambient AI wearable. The wearer talks continuously throughout the day;
the engine has already filtered out obvious non-asks. Your job is to
look at this utterance + prior context + the wearer's long-term memory,
and decide ONE of:

  COMMIT          — clear request to act with enough specificity that
                    the executor can run it (with memory-resolved slots).
  STORE_AS_LATENT — intent expressed but NOT committed: hedging, future
                    tense without specifics, "should probably / maybe /
                    gotta remember to ...". Surfaces later when the
                    wearer follows up.
  REFUSE          — sarcasm, retraction, past-tense recap (already
                    done), third-party reporting (someone else did it),
                    conditional / counterfactual ("if I had time I'd"),
                    abandoned mid-utterance. NO action.

A REFUSE may still write a memory row when the utterance reveals
durable info — most importantly sarcasm-derived aversions. E.g.
"Oh yeah I'd LOVE another Saturday at the DMV" → REFUSE the action
AND store an aversion to DMV visits.

ALWAYS prefer REFUSE over COMMIT when uncertain. False positives on
COMMIT are CATASTROPHIC (the wearer sees an unwanted action). False
negatives on COMMIT are recoverable (the wearer just re-says it).

CRITICAL DISTINCTION — brainstorm vs hedging:
  - "We could maybe rent that Airbnb..."           → REFUSE (brainstorm,
                                                    speaker isn't asking
                                                    the agent to act)
  - "Maybe we should book the conference room..."  → REFUSE (brainstorm,
                                                    plural pronoun + no
                                                    follow-through cue)
  - "I should probably text Sarah back."           → STORE_AS_LATENT
                                                    (single-actor
                                                    self-reminder)

Rule: when the wearer floats an idea using "we could / maybe we should /
what if we" with PLURAL subject and no time/place specificity, it's a
brainstorm (REFUSE). STORE_AS_LATENT is for SOLO self-reminders the
wearer might follow through on alone.

OUTPUT STRICT JSON ONLY:

{
  "decision": "COMMIT" | "STORE_AS_LATENT" | "REFUSE",
  "reason": "<short why>",
  "confidence": 0.0..1.0,
  "store_as_memory": null | {
    "kind": "preference" | "aversion" | "contact" | "habit" | "recurrence" | "sentiment_fact",
    "key": "<short id>",
    "value": "<value>",
    "evidence_quote": "<verbatim substring of the utterance>"
  }
}

Here are CALIBRATION EXAMPLES from the gold-standard set. Use these
to map surface form -> decision:

{FEWSHOT_EXAMPLES}
"""


@dataclass(frozen=True, slots=True)
class MemoryWriteSpec:
    kind: str
    key: str
    value: str
    evidence_quote: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "key": self.key,
            "value": self.value,
            "evidence_quote": self.evidence_quote,
        }


@dataclass(frozen=True, slots=True)
class HedgeResult:
    decision: HedgeDecision
    reason: str
    confidence: float
    store_as_memory: Optional[MemoryWriteSpec]


class HedgeFilter:
    """Stage 1.5 classifier with two backends (cascade few-shot, QLoRA adapter)."""

    def __init__(
        self,
        backend: Literal["cascade", "adapter"] = "cascade",
        fewshot_count: int = 8,
        max_tokens: int = 400,
        gold_standard_path: Path = GOLD_STANDARD_PATH,
    ) -> None:
        self.backend = backend
        self.fewshot_count = fewshot_count
        self._gold = self._load_gold(gold_standard_path)
        if backend == "cascade":
            self._llm = make_json_llm_call(max_tokens=max_tokens)
            self._adapter = None
        elif backend == "adapter":
            self._llm = None
            self._adapter = self._load_adapter()
        else:
            raise ValueError(f"unknown hedge_filter backend: {backend!r}")

    @staticmethod
    def _load_gold(path: Path) -> list[dict]:
        if not path.exists():
            _logger.warning("gold_standard.jsonl not found at %s", path)
            return []
        rows: list[dict] = []
        with path.open() as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        return rows

    def _load_adapter(self):
        """Load the Phase-1 QLoRA adapter. Imports mlx-lm lazily."""
        try:
            from mlx_lm import load  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "mlx-lm is not installed. Run: uv pip install 'mlx-lm>=0.20'"
            ) from e
        adapter_dir = Path.home() / ".anticipy" / "adapters" / "hedge_filter_v1"
        if not adapter_dir.exists():
            raise RuntimeError(
                f"QLoRA adapter not found at {adapter_dir}. Run Phase 1 fine-tune first."
            )
        return load(
            "mlx-community/Qwen3-8B-MLX-4bit",
            adapter_path=str(adapter_dir),
        )

    def _build_fewshot_block(self) -> str:
        """Sample ONE example per boundary tag (or all if fewer than count)."""
        if not self._gold:
            return "(no gold-standard fixtures available)"
        # Group by boundary tag, pick one per group
        by_tag: dict[str, list[dict]] = {}
        for row in self._gold:
            by_tag.setdefault(row.get("boundary_tag", "unknown"), []).append(row)
        sampled: list[dict] = []
        for tag, rows in by_tag.items():
            sampled.append(random.choice(rows))
        # Cap at fewshot_count
        if len(sampled) > self.fewshot_count:
            sampled = random.sample(sampled, self.fewshot_count)
        blocks: list[str] = []
        for row in sampled:
            payload = {
                "decision": row["expected_label"],
                "reason": row["expected_reason"],
                "confidence": 0.9,
                "store_as_memory": row.get("expected_memory_write"),
            }
            blocks.append(
                f"UTTERANCE: {row['utterance']}\nOUTPUT: {json.dumps(payload)}"
            )
        return "\n\n".join(blocks)

    async def classify(
        self,
        utterance: str,
        context: Optional[str] = None,
        user_memory_summary: Optional[str] = None,
    ) -> HedgeResult:
        if self.backend == "cascade":
            return await self._classify_cascade(utterance, context, user_memory_summary)
        return self._classify_adapter(utterance, context, user_memory_summary)

    async def _classify_cascade(
        self,
        utterance: str,
        context: Optional[str],
        user_memory_summary: Optional[str],
    ) -> HedgeResult:
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.replace(
            "{FEWSHOT_EXAMPLES}", self._build_fewshot_block()
        )
        user_msg_parts = []
        if context and context.strip():
            user_msg_parts.append(f"PRIOR CONVERSATION:\n{context.strip()}")
        if user_memory_summary and user_memory_summary.strip():
            user_msg_parts.append(f"WEARER LONG-TERM MEMORY:\n{user_memory_summary.strip()}")
        user_msg_parts.append(f"WEARER'S MOST RECENT UTTERANCE:\n{utterance.strip()}")
        user_msg_parts.append(
            "Return the JSON object now. No prose. No fences. No preamble."
        )
        user_msg = "\n\n".join(user_msg_parts)

        raw = await self._llm(system_prompt, user_msg)
        if not raw:
            # Full cascade failure -> safest is REFUSE (no action fires).
            return HedgeResult(
                decision="REFUSE",
                reason="cascade_failed_closed",
                confidence=0.0,
                store_as_memory=None,
            )
        return self._parse(raw, utterance)

    def _classify_adapter(
        self,
        utterance: str,
        context: Optional[str],
        user_memory_summary: Optional[str],
    ) -> HedgeResult:
        """QLoRA adapter inference (Phase 1 trained). Sync — MLX LM
        already runs locally so async wrapping just adds overhead.
        """
        from mlx_lm import generate  # type: ignore

        prompt = _SYSTEM_PROMPT_TEMPLATE.replace(
            "{FEWSHOT_EXAMPLES}", self._build_fewshot_block()
        )
        if context and context.strip():
            prompt += f"\n\nPRIOR CONVERSATION:\n{context.strip()}"
        if user_memory_summary and user_memory_summary.strip():
            prompt += f"\n\nWEARER LONG-TERM MEMORY:\n{user_memory_summary.strip()}"
        prompt += f"\n\nWEARER'S MOST RECENT UTTERANCE:\n{utterance.strip()}\n\nOUTPUT:"

        model, tokenizer = self._adapter
        raw = generate(model, tokenizer, prompt=prompt, max_tokens=400, verbose=False)
        return self._parse(raw, utterance)

    @staticmethod
    def _parse(raw: str, utterance: str) -> HedgeResult:
        # Extract the JSON object (cascade returns clean JSON, adapter may
        # have prose around it). Take the first {...} block.
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            _logger.warning("hedge_filter: no JSON in response: %s", raw[:200])
            return HedgeResult(
                decision="REFUSE",
                reason="parse_failed_closed",
                confidence=0.0,
                store_as_memory=None,
            )
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as e:
            _logger.warning("hedge_filter: JSON decode failed: %s; raw=%s", e, raw[:200])
            return HedgeResult(
                decision="REFUSE",
                reason="parse_failed_closed",
                confidence=0.0,
                store_as_memory=None,
            )
        decision = parsed.get("decision")
        if decision not in {"COMMIT", "STORE_AS_LATENT", "REFUSE"}:
            return HedgeResult(
                decision="REFUSE",
                reason=f"invalid_decision:{decision!r}",
                confidence=0.0,
                store_as_memory=None,
            )
        mem = parsed.get("store_as_memory")
        memory_write: Optional[MemoryWriteSpec] = None
        if isinstance(mem, dict):
            evidence = str(mem.get("evidence_quote", ""))
            # Reject hallucinated evidence quotes — must be substring.
            if evidence and evidence in utterance:
                memory_write = MemoryWriteSpec(
                    kind=str(mem.get("kind", "")),
                    key=str(mem.get("key", "")),
                    value=str(mem.get("value", "")),
                    evidence_quote=evidence,
                )
        return HedgeResult(
            decision=decision,  # type: ignore[arg-type]
            reason=str(parsed.get("reason", ""))[:240],
            confidence=float(parsed.get("confidence", 0.5)),
            store_as_memory=memory_write,
        )
