"""5-day-in-the-life persona runner — the WHOLE product, one persona, across five days.

Runs ONE persona through the real assembled engine (the same ControlCore.owner_ingest the app calls)
across 5 consecutive days on a SINGLE core, so memory + intent accumulate exactly like real life:
day-1 context must be resolvable from a day-3 vague reference, a handled task must not re-surface, a
vent on any day must stay silent, money on any day must stay blocked.

This is the deterministic ENGINE runner. It does NOT judge — it emits the cards the engine actually
produced per day so an independent judge (a workflow agent that knows the persona's hidden key) can
score cardinal sins, catch-rate, autonomy correctness, and cross-day continuity.

Usage:
  PYTHONPATH=engine ANTICIPY_MODEL_PROVIDER=openrouter ANTICIPY_HANDS_MODE=mock \
    engine/.venv/bin/python engine/scripts/persona_run.py <persona.json> <out.json>

Persona JSON:
  {"persona_id": "...", "domain": "...",
   "profile": {"owner_name": "...", "preferences": ["..."],
               "people": [{"name":"Sam","relationship":"cofounder","channels":["text"]}]},
   "days": [ ["line","line",...],   # day 1
             ["line",...], ... ]}   # up to day 5
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_onboarding import (  # noqa: E402
    OwnerOnboardingIn, OwnerPersonIn,
)


def _card_view(c: dict) -> dict:
    return {
        "source_text": c.get("source_text") or c.get("text"),
        "disposition": c.get("disposition"),
        "autonomy_mode": c.get("autonomy_mode"),
        "reason": (c.get("reason") or "")[:160],
        "follow_up": bool(c.get("follow_up")),
        "title": (c.get("title") or "")[:90],
    }


async def run_persona(spec: dict) -> dict:
    d = Path(tempfile.mkdtemp(prefix="persona-"))
    core = ControlCore(data_dir=d)
    await core.start()
    out_days = []
    try:
        prof = spec.get("profile") or {}
        people = [
            OwnerPersonIn(
                name=p.get("name", ""),
                relationship=p.get("relationship", ""),
                channels=p.get("channels", []) or [],
            )
            for p in (prof.get("people") or [])
            if p.get("name")
        ]
        try:
            await core.owner_onboard(OwnerOnboardingIn(
                owner_name=prof.get("owner_name", ""),
                preferences=prof.get("preferences", []) or [],
                people=people,
                source="persona_test",
            ))
        except Exception as e:  # onboarding must never abort the run
            out_days.append({"day": 0, "onboard_error": repr(e)[:160]})

        for i, day_lines in enumerate(spec.get("days") or [], start=1):
            text = "\n".join(day_lines)
            try:
                res = await core.owner_ingest(
                    "typed", text, {"persona": spec.get("persona_id"), "day": i},
                    execute_actions=True,
                )
                cards = [_card_view(c) for c in (res.get("cards") or [])]
                err = res.get("_error")
            except Exception as e:
                cards, err = [], repr(e)[:200]
            out_days.append({
                "day": i,
                "input_lines": day_lines,
                "cards": cards,
                **({"error": err} if err else {}),
            })
    finally:
        try:
            await core.stop()
        except Exception:
            pass
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    return {"persona_id": spec.get("persona_id"), "domain": spec.get("domain"), "days": out_days}


def main():
    if len(sys.argv) < 3:
        print("usage: persona_run.py <persona.json> <out.json>", file=sys.stderr)
        raise SystemExit(2)
    spec = json.loads(Path(sys.argv[1]).read_text())
    result = asyncio.run(run_persona(spec))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2))
    nd = len(result["days"])
    ncards = sum(len(x.get("cards", [])) for x in result["days"])
    print(f"persona {result['persona_id']}: {nd} days, {ncards} cards -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
