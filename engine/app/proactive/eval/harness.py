"""
Adversarial proactive-engine eval harness.

Pipeline:
  1. Generate N synthetic scenarios via the LLM (no fixed fixtures).
  2. For each scenario, instantiate a fresh ProactiveEngine and stream its
     chunks through `on_transcript_chunk`.
  3. Capture every Decision, every status event, every executed action.
  4. Pass the captured outcome + the scenario context to the judge.
  5. Aggregate.

Targets (matching audit doc §8.2):
  correctness > 0.85
  false-positive rate (acted when shouldn't have) < 0.1
  false-negative rate (stayed silent when shouldn't have) < 0.15
  channel-appropriate rate > 0.8

The harness is `await`-able and produces an `EvalResult`. Print it for a
human-readable report; serialize for CI dashboards.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..engine import ProactiveEngine
from ..types import Decision, DecisionKind, TranscriptChunk
from .judge import JudgeVerdict, judge_scenario
from .scenarios import SCENARIO_CATEGORIES, Scenario, ScenarioCategory, generate_scenarios

logger = logging.getLogger("engine.proactive.eval.harness")


LlmCall = Callable[[str, str], Awaitable[str]]


# --- Result types ---------------------------------------------------------------


@dataclass
class ScenarioOutcome:
    scenario: Scenario
    decisions: list[Decision]
    executions: list[Decision]  # subset of decisions that EXECUTE (or were ASK→yes)
    verdict: JudgeVerdict
    duration_s: float


@dataclass
class EvalResult:
    outcomes: list[ScenarioOutcome] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    @property
    def n(self) -> int:
        return len(self.outcomes)

    @property
    def correctness_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for o in self.outcomes if o.verdict.correct) / self.n

    @property
    def false_positive_rate(self) -> float:
        """Acted when ideal was silence."""
        if not self.outcomes:
            return 0.0
        # FP = scenario where silent_when_should_have is False
        # AND the ideal called for silence (categories that say "do nothing"
        # / "log only" / "stay silent")
        fp = sum(
            1 for o in self.outcomes
            if not o.verdict.silent_when_should_have
            and _category_expects_silence(o.scenario.category)
        )
        denom = sum(1 for o in self.outcomes if _category_expects_silence(o.scenario.category))
        return fp / denom if denom else 0.0

    @property
    def false_negative_rate(self) -> float:
        """Stayed silent when ideal was action."""
        if not self.outcomes:
            return 0.0
        fn = sum(
            1 for o in self.outcomes
            if not o.verdict.acted_when_should_have
            and not _category_expects_silence(o.scenario.category)
        )
        denom = sum(1 for o in self.outcomes if not _category_expects_silence(o.scenario.category))
        return fn / denom if denom else 0.0

    @property
    def channel_appropriate_rate(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(1 for o in self.outcomes if o.verdict.channel_appropriate) / self.n

    def by_category(self) -> dict[str, dict[str, float]]:
        grouped: dict[str, list[ScenarioOutcome]] = defaultdict(list)
        for o in self.outcomes:
            grouped[o.scenario.category.name].append(o)
        result: dict[str, dict[str, float]] = {}
        for cat_name, items in grouped.items():
            n = len(items)
            result[cat_name] = {
                "n": n,
                "correctness": sum(1 for o in items if o.verdict.correct) / n if n else 0.0,
                "channel_ok": sum(1 for o in items if o.verdict.channel_appropriate) / n if n else 0.0,
            }
        return result

    def report(self) -> str:
        lines = [
            f"Proactive engine eval — {self.n} scenarios",
            f"  correctness:           {self.correctness_rate:.1%}  (target >85%)",
            f"  false_positive_rate:   {self.false_positive_rate:.1%}  (target <10%)",
            f"  false_negative_rate:   {self.false_negative_rate:.1%}  (target <15%)",
            f"  channel_appropriate:   {self.channel_appropriate_rate:.1%}  (target >80%)",
            f"  wall_clock_s:          {(self.finished_at or time.time()) - self.started_at:.1f}",
            "",
            "By category:",
        ]
        for cat, metrics in sorted(self.by_category().items()):
            lines.append(
                f"  {cat:<40s}  n={int(metrics['n']):>3d}  "
                f"correct={metrics['correctness']:.0%}  channel={metrics['channel_ok']:.0%}"
            )
        return "\n".join(lines)


_SILENCE_CATEGORIES = {
    "self_talk_venting",
    "distractor_no_intent",
    "quoted_speech",
    "question_to_self",
    "user_changes_mind",  # post-retraction, agent should be silent
    "ambiguous_low_confidence",
}


def _category_expects_silence(cat: ScenarioCategory) -> bool:
    return cat.name in _SILENCE_CATEGORIES


# --- Runner ---------------------------------------------------------------------


async def run_eval(
    llm_call: LlmCall,
    n: int = 200,
    *,
    judge_llm_call: LlmCall | None = None,
    categories: list[ScenarioCategory] | None = None,
    parallel: int = 4,
) -> EvalResult:
    """Generate N scenarios, run them through ProactiveEngine, and judge.

    `judge_llm_call` defaults to `llm_call` but should be a *different model*
    (or at least a different prompt) in production runs to avoid shared bias.

    `parallel` caps the number of concurrent scenarios in flight.
    """
    judge_call = judge_llm_call or llm_call
    cats = categories or SCENARIO_CATEGORIES

    logger.info("eval_generating_scenarios", extra={"n": n, "categories": [c.name for c in cats]})
    scenarios = await generate_scenarios(llm_call=llm_call, n=n, categories=cats)
    logger.info("eval_generated_scenarios", extra={"got": len(scenarios)})

    sem = asyncio.Semaphore(parallel)

    async def _run_one(scn: Scenario) -> ScenarioOutcome | None:
        async with sem:
            return await _run_scenario(llm_call, judge_call, scn)

    raw = await asyncio.gather(*(_run_one(s) for s in scenarios), return_exceptions=False)
    outcomes = [o for o in raw if o is not None]

    return EvalResult(
        outcomes=outcomes,
        finished_at=time.time(),
    )


async def _run_scenario(
    llm_call: LlmCall,
    judge_call: LlmCall,
    scenario: Scenario,
) -> ScenarioOutcome | None:
    started = time.time()

    engine = ProactiveEngine(
        user_id=scenario.user_id,
        llm_call=llm_call,
    )

    captured: list[Decision] = []
    for chunk in scenario.chunks:
        # Rewrite chunk session_id to match the scenario's session_id.
        bound_chunk = TranscriptChunk(
            chunk_id=chunk.chunk_id,
            session_id=scenario.session_id,
            user_id=scenario.user_id,
            text=chunk.text,
            start_ts=chunk.start_ts,
            end_ts=chunk.end_ts,
            confidence=chunk.confidence,
            is_self_talk=chunk.is_self_talk,
            is_addressed_to_agent=chunk.is_addressed_to_agent,
        )
        try:
            decisions = await engine.on_transcript_chunk(bound_chunk)
            captured.extend(decisions)
        except Exception:
            logger.exception("scenario_chunk_error", extra={
                "scenario_id": scenario.scenario_id,
                "chunk_id": bound_chunk.chunk_id,
            })

    # Settling buffer: flush any decisions that were extracted on the last
    # chunk(s) but never had a follow-up chunk to settle them.
    try:
        captured.extend(await engine.flush_pending())
    except Exception:
        logger.exception("scenario_flush_error", extra={"scenario_id": scenario.scenario_id})

    # Auto-confirm any pending ASKs to test the executor path. The judge
    # will mark "asked when should have asked" separately from "executed
    # something user wouldn't want."
    # In a stricter run, you'd auto-confirm only for categories that
    # expect EXECUTE, but this path tests the full pipeline.
    # We give pending decisions a moment to surface to the engine's
    # _pending_confirmations dict before yes-ing them.
    await asyncio.sleep(0.2)
    pending_ids = list(engine._pending_confirmations.keys())  # internal access OK in eval
    for did in pending_ids:
        await engine.on_confirmation(did, "yes")

    # Drain any executor side-effects queued by the auto-confirms.
    await asyncio.sleep(0.5)

    executions = [d for d in captured if d.kind in (DecisionKind.EXECUTE, DecisionKind.ASK)]

    verdict = await judge_scenario(
        llm_call=judge_call,
        scenario=scenario,
        decisions=captured,
        executions=executions,
        statuses=engine.status_events,
    )

    return ScenarioOutcome(
        scenario=scenario,
        decisions=captured,
        executions=executions,
        verdict=verdict,
        duration_s=time.time() - started,
    )


# --- CLI entry (optional) -------------------------------------------------------


async def _cli_demo(n: int = 100) -> None:  # pragma: no cover
    """At-scale eval runner using the live MODEL_CHAIN via JSON-mode adapter.

    Usage: python -m app.proactive.eval.harness [N]
    Default N=100. The harness generates N synthetic conversations via Gemini
    JSON mode, runs each through the cascade, and judges with the same chain.
    The judge LLM is called via a separate adapter so it has its own context
    and can't share state with the engine LLM.
    """
    from app.proactive.llm_adapter import make_json_llm_call

    cascade_call = make_json_llm_call(max_tokens=1024)
    judge_call = make_json_llm_call(max_tokens=1024)

    print(f"Running proactive eval with n={n} scenarios...")
    print("(generating + cascading + judging via MODEL_CHAIN — this takes a few minutes)")
    print()

    # Adapt parallel concurrency to the provider stack. Groq/Kimi free tiers
    # are tighter than Gemini, so when those are likely the active providers
    # (Gemini disabled or first), serialize.
    from app.config import MODEL_CHAIN as _CHAIN
    parallel = 2 if (_CHAIN and _CHAIN[0]["name"] == "gemini") else 1
    result = await run_eval(
        llm_call=cascade_call,
        judge_llm_call=judge_call,
        n=n,
        parallel=parallel,
    )
    print(result.report())

    # JSON dump for CI / future regression comparisons
    import json as _json
    summary = {
        "n": result.n,
        "correctness_rate": result.correctness_rate,
        "false_positive_rate": result.false_positive_rate,
        "false_negative_rate": result.false_negative_rate,
        "channel_appropriate_rate": result.channel_appropriate_rate,
        "wall_clock_s": (result.finished_at or 0) - result.started_at,
        "by_category": result.by_category(),
    }
    with open("/tmp/proactive_eval_summary.json", "w") as f:
        _json.dump(summary, f, indent=2)

    # Full per-scenario dump — needed to actually diagnose failures, not just
    # category-level numbers. Pulls scenario text, decisions made, and judge verdict.
    detail = []
    for o in result.outcomes:
        detail.append({
            "scenario_id": o.scenario.scenario_id,
            "category": o.scenario.category.name,
            "expected_behavior": o.scenario.category.expected_behavior,
            "scenario_description": o.scenario.description,
            "transcript": [c.text for c in o.scenario.chunks],
            "decisions": [
                {
                    "kind": d.kind.value,
                    "verb": d.intent.action_verb,
                    "intent_text": d.intent.text,
                    "params": d.intent.parameters,
                    "confidence": d.confidence.score,
                    "reversibility": d.reversibility.value,
                    "urgency": d.urgency.level,
                    "channel": d.urgency.channel.value,
                    "user_facing_question": d.user_facing_question,
                    "completion_message": d.completion_message,
                    "refusal_reason": d.refusal_reason,
                }
                for d in o.decisions
            ],
            "verdict": {
                "correct": o.verdict.correct,
                "acted_when_should_have": o.verdict.acted_when_should_have,
                "silent_when_should_have": o.verdict.silent_when_should_have,
                "channel_appropriate": o.verdict.channel_appropriate,
                "refusal_appropriate": o.verdict.refusal_appropriate,
                "explanation": o.verdict.explanation,
            },
            "duration_s": o.duration_s,
        })
    with open("/tmp/proactive_eval_detail.json", "w") as f:
        _json.dump(detail, f, indent=2)
    print()
    print(f"Summary saved to /tmp/proactive_eval_summary.json")
    print(f"Per-scenario detail saved to /tmp/proactive_eval_detail.json ({len(detail)} scenarios)")


if __name__ == "__main__":  # pragma: no cover
    import sys

    n_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    asyncio.run(_cli_demo(n_arg))
