"""
Adversarial eval for the proactive engine — no hardcoded test cases.

The eval generates `N` synthetic conversations across diverse scenario
categories using an LLM, runs each through `ProactiveEngine`, and uses
a separate LLM as judge to score whether the agent's behavior was right.

The judge sees the scenario context (so it knows what would have been
correct) but the engine never does — so the engine has to figure it
out from chunks alone, the way it would in production.

  from engine.app.proactive.eval import run_eval
  result = await run_eval(llm_call=..., n=200)
  print(result.report())
"""

from .harness import EvalResult, run_eval
from .judge import JudgeVerdict
from .scenarios import (
    SCENARIO_CATEGORIES,
    Scenario,
    generate_scenarios,
)

__all__ = [
    "EvalResult",
    "JudgeVerdict",
    "SCENARIO_CATEGORIES",
    "Scenario",
    "generate_scenarios",
    "run_eval",
]
