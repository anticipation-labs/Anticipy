"""
LLM-as-judge for the proactive engine eval.

The judge receives:
  - The scenario category and its expected behavior (i.e., what *would* be right)
  - The transcript the engine saw (chunk by chunk)
  - The agent's actual outputs: decisions made, executions performed, notifications sent

It returns a verdict on each of four axes:

  acted_when_should_have:    bool   — true if the agent acted (or asked) when it should have
  silent_when_should_have:   bool   — true if the agent stayed silent when it should have
  channel_appropriate:       bool   — true if the chosen channel matched urgency expectations
  refusal_appropriate:       bool   — true if Donna-style refusal happened when warranted, or didn't when not

Plus a single "correct overall" rating + a brief explanation.

The judge is INTENTIONALLY a different LLM call from anything the engine
does. This guards against the engine and the judge sharing biases (which
they would if the same model + prompt produced both).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from ..types import Decision, EngineStatusEvent
from .scenarios import Scenario

logger = logging.getLogger("engine.proactive.eval.judge")


LlmCall = Callable[[str, str], Awaitable[str]]


@dataclass
class JudgeVerdict:
    scenario_id: str
    category_name: str
    correct: bool
    acted_when_should_have: bool
    silent_when_should_have: bool
    channel_appropriate: bool
    refusal_appropriate: bool
    explanation: str
    raw: str = ""


_JUDGE_SYSTEM = """You are an evaluator scoring whether an AI personal-assistant wearable behaved \
correctly on a synthetic test scenario.

You will see:
  - The scenario CATEGORY and the IDEAL BEHAVIOR for that category.
  - The TRANSCRIPT the agent saw (the user's voice; bystanders already filtered).
  - The AGENT'S ACTIONS: every Decision it made (kind, confidence, urgency), every action it executed, \
every notification it surfaced.

Score whether the agent did the right thing on four axes (booleans):

  - acted_when_should_have: true if the agent took action (EXECUTE or ASK) when the ideal behavior \
required it. False if the ideal called for action and the agent stayed silent.

  - silent_when_should_have: true if the agent stayed silent (LOG or no decision) when the ideal \
behavior called for silence. False if the agent acted when it shouldn't have.

  - channel_appropriate: true if the notification channel chosen by the agent matches the urgency the \
ideal would expect. (NOTED for low urgency, IN_APP for normal, PUSH/SMS for higher, VOICE only for \
right-now urgency.) Mark true if no channel was needed.

  - refusal_appropriate: true if the agent REFUSED when warranted (an emotional-donna-refuse \
scenario) or did NOT refuse when not warranted. Mark true if refusal wasn't relevant.

Then return one overall correct verdict (true/false) — the agent gets the scenario "right" if all four \
axes pass.

Output STRICT JSON:
{
  "correct": <bool>,
  "acted_when_should_have": <bool>,
  "silent_when_should_have": <bool>,
  "channel_appropriate": <bool>,
  "refusal_appropriate": <bool>,
  "explanation": "<2-3 sentences>"
}

Rules:
1. STRICT JSON. No markdown.
2. Be strict but reasonable. The agent is held to the IDEAL behavior, not perfection.
3. If the agent took multiple decisions in one scenario, judge the holistic behavior, not each one.
4. Don't deduct for an extra LOG entry — logs are silent and harmless.
"""


_JUDGE_USER_TEMPLATE = """Scenario:
  category: {category}
  category_description: {category_desc}
  ideal_behavior: {ideal}

Scenario one-line: {scenario_desc}

User-voice transcript the agent saw:
\"\"\"
{transcript}
\"\"\"

Agent decisions (in order):
{decisions}

Agent executions (browser actions):
{executions}

Engine status events emitted to the user:
{statuses}

Score the agent's behavior."""


async def judge_scenario(
    llm_call: LlmCall,
    scenario: Scenario,
    decisions: list[Decision],
    executions: list[Decision],
    statuses: list[EngineStatusEvent],
    timeout_s: float = 45.0,
) -> JudgeVerdict:
    """Run the judge LLM on one scenario's outcome."""

    transcript = "\n".join(c.text for c in scenario.chunks)
    decisions_str = _format_decisions(decisions)
    executions_str = _format_decisions(executions) if executions else "(none)"
    statuses_str = "\n".join(f"  - [{s.stage}] {s.message}" for s in statuses) or "(none)"

    user_prompt = _JUDGE_USER_TEMPLATE.format(
        category=scenario.category.name,
        category_desc=scenario.category.description,
        ideal=scenario.category.expected_behavior,
        scenario_desc=scenario.description,
        transcript=transcript,
        decisions=decisions_str,
        executions=executions_str,
        statuses=statuses_str,
    )

    try:
        raw = await asyncio.wait_for(llm_call(_JUDGE_SYSTEM, user_prompt), timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning("judge_timeout", extra={"scenario_id": scenario.scenario_id})
        return _failure_verdict(scenario, "judge timeout")
    except Exception as exc:
        logger.exception("judge_error", extra={"scenario_id": scenario.scenario_id})
        return _failure_verdict(scenario, f"judge error: {exc}")

    return _parse(raw, scenario)


def _format_decisions(decisions: list[Decision]) -> str:
    if not decisions:
        return "(no decisions made — agent stayed silent)"
    lines = []
    for i, d in enumerate(decisions):
        lines.append(
            f"  {i+1}. kind={d.kind.value} verb={d.intent.action_verb} "
            f"confidence={d.confidence.score:.2f} reversibility={d.reversibility.value} "
            f"urgency={d.urgency.level} channel={d.urgency.channel.value} "
            f"text={d.intent.text!r}"
        )
    return "\n".join(lines)


def _parse(raw: str, scenario: Scenario) -> JudgeVerdict:
    """Strict JSON only. JSON mode is forced upstream."""
    raw = (raw or "").strip()
    if not raw:
        return _failure_verdict(scenario, "empty judge response")
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _failure_verdict(scenario, "unparseable judge response")
    if not isinstance(data, dict):
        return _failure_verdict(scenario, "non-object judge response")

    return JudgeVerdict(
        scenario_id=scenario.scenario_id,
        category_name=scenario.category.name,
        correct=bool(data.get("correct", False)),
        acted_when_should_have=bool(data.get("acted_when_should_have", False)),
        silent_when_should_have=bool(data.get("silent_when_should_have", False)),
        channel_appropriate=bool(data.get("channel_appropriate", False)),
        refusal_appropriate=bool(data.get("refusal_appropriate", False)),
        explanation=str(data.get("explanation") or "").strip(),
        raw=raw,
    )


def _failure_verdict(scenario: Scenario, reason: str) -> JudgeVerdict:
    return JudgeVerdict(
        scenario_id=scenario.scenario_id,
        category_name=scenario.category.name,
        correct=False,
        acted_when_should_have=False,
        silent_when_should_have=False,
        channel_appropriate=False,
        refusal_appropriate=False,
        explanation=f"judge failed: {reason}",
    )
