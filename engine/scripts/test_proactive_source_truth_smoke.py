"""Source-of-truth proactive smoke cases.

This is the cheap gate for the Plan Baby Steps proactive engine circuit. It does
not claim the engine is fully sorted; it freezes the source-truth rules that have
repeatedly regressed:

- catch a real messy task
- do not act on pure vent/sarcasm
- hold vent-adjacent real tasks for confirmation
- do not adopt a request aimed at another person
- surface money as blocked, never executable

Run:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_proactive_source_truth_smoke.py
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402


CASES = [
    {
        "name": "simple_real_task",
        "text": "Please remind me to call Maya tomorrow morning.",
        "must_include": ["call maya"],
        "must_dispositions": {"do", "ask"},
    },
    {
        "name": "pure_vent_silent",
        "text": "I should just quit and move to the woods.",
        "must_be_silent": True,
    },
    {
        "name": "overwhelm_real_tasks_held",
        "text": "My brain is fried, call the dentist and book Friday at 3.",
        "must_include": ["call the dentist", "book friday"],
        "must_dispositions": {"ask"},
    },
    {
        "name": "request_to_listener_silent",
        "text": "Hey babe can you grab milk on the way home?",
        "must_be_silent": True,
    },
    {
        "name": "money_blocks",
        "text": "I need to pay the Xfinity bill today.",
        "must_include": ["xfinity"],
        "must_dispositions": {"blocked"},
    },
]


def _action_cards(out: dict) -> list[dict]:
    return [
        c for c in (out.get("cards") or [])
        if isinstance(c, dict) and c.get("disposition") in {"do", "ask", "blocked"}
    ]


def _blob(cards: list[dict]) -> str:
    return " | ".join(
        f"{c.get('disposition')} {c.get('title')} {c.get('source_text')}".lower()
        for c in cards
    )


async def main() -> None:
    core = ControlCore(data_dir=Path(tempfile.mkdtemp(prefix="anticipy-source-truth-smoke-")))
    await core.start()
    try:
        for case in CASES:
            out = await core.owner_ingest(
                "source_truth_smoke",
                case["text"],
                {
                    "source_of_truth_tags": [
                        "ST-SOURCE-TRUTH-EVAL",
                        "ST-INFER-REAL-TASKS",
                        "ST-IGNORE-VENTS",
                    ]
                },
                execute_actions=False,
            )
            cards = _action_cards(out)
            blob = _blob(cards)
            if case.get("must_be_silent"):
                assert not cards, f"{case['name']} should be silent, got {cards}"
                continue
            assert cards, f"{case['name']} produced no action cards"
            for phrase in case.get("must_include") or []:
                assert phrase in blob, f"{case['name']} missing {phrase!r}: {cards}"
            allowed = case.get("must_dispositions")
            if allowed:
                got = {c.get("disposition") for c in cards}
                assert got <= allowed, f"{case['name']} got disallowed dispositions {got}: {cards}"
            event = out.get("gateway_event") or {}
            assessment = event.get("brain_assessment") or {}
            assert assessment.get("classification") in {
                "actionable",
                "blocked",
                "ignored",
                "unknown",
            }, event
            assert "ST-SOURCE-TRUTH-EVAL" in event.get("source_of_truth_tags", []), event
    finally:
        await core.stop()


if __name__ == "__main__":
    asyncio.run(main())
    print("proactive source-truth smoke: ok")
