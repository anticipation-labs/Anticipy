"""sector/wire.py — the assembly manifest.

The ONE best module per system (from CANON/THE_MAP.md), imported BY REFERENCE — no copies,
no forks. Importing this file resolves every canonical piece the skeleton wires together, so a
break anywhere in the spine surfaces here immediately. Grafts (sector/grafts/) and the new
browser code (sector/browser/) plug into the seams named in skeleton.py; they are listed here
as they land, never replacing the canonical modules.
"""
from __future__ import annotations

# --- brain / spine ---
from anticipy_engine.core import control_core            # noqa: F401  the orchestrator + owner_ingest
from anticipy_engine.proactive import decision_pipeline  # noqa: F401  the ONE extractor
from anticipy_engine.proactive import harm               # noqa: F401  the ONE safety gate (kept; §3 deferred otherwise)

# --- proactive (anticipation) ---
from anticipy_engine.core import proactive as proactive_spine  # noqa: F401  Engine A: triage→decide→act, fire-once
from anticipy_engine.proactive import derive             # noqa: F401  derive unspoken needs
from anticipy_engine.proactive import world_research     # noqa: F401  browser-only real-world research

# --- memory / context ---
from anticipy_engine import live_memory                  # noqa: F401  4 drawers + context builder
from anticipy_engine.memory import store as memory_store  # noqa: F401

# --- inputs / voice ---
from anticipy_engine.capture import transcribe           # noqa: F401  MP3/audio -> text (local Whisper)

# --- browser hands ---
from anticipy_engine.hands import browser_hand           # noqa: F401  proof-bearing hand (extension/CDP + throwaway)
from anticipy_engine.agent import webvoyager             # noqa: F401  SoM screenshot+DOM agent

CANONICAL = {
    "spine": "anticipy_engine.core.control_core",
    "extractor": "anticipy_engine.proactive.decision_pipeline",
    "safety_gate": "anticipy_engine.proactive.harm",
    "proactive": "anticipy_engine.core.proactive",
    "derive": "anticipy_engine.proactive.derive",
    "world_research": "anticipy_engine.proactive.world_research",
    "memory": "anticipy_engine.live_memory",
    "inputs": "anticipy_engine.capture.transcribe",
    "browser_hand": "anticipy_engine.hands.browser_hand",
    "browser_agent": "anticipy_engine.agent.webvoyager",
}

# Grafts to port from DEV-FINAL (sector/grafts/) — filled in as each order-of-attack step lands:
#   multi_intent      (step 2)  brain recall under density  <- product/intent_extractor.py
#   resolve_reference (step 3)  never-re-ask / "the boss"   <- anticipy/memory.py
#   style_profile     (step 3)  learn how the owner writes
# New browser code (sector/browser/) — step 5:
#   ensemble.py       screenshot-first voting decide()
#   validator.py      per-action read-back verify
