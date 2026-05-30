"""Sector profiles package (Phase 8).

Hints, not hardcoded recipes.

The planner uses ``detector.detect_sector(dossier)`` to pick one of nine
sector names ("construction", "sales", "job_seeking", "healthcare",
"startup_founder", "stay_at_home_parent", "pensioner", "freelance",
"generic") from the user's coldstart dossier, then calls
``loader.load_hints(name)`` to get a system prompt fragment to inject
into the planner LLM call.

Everything in here is a hint: vocab, common tools, common goals,
detection signals, preferred channels, sample personas. NO recipes
("click button X", "fill in form Y") are stored. The planner LLM is
still free to decide what to do.

If no sector scores above a confidence threshold, "generic" is used.
"""

from .detector import detect_sector
from .loader import KNOWN_SECTORS, format_system_prompt, load_hints

__all__ = [
    "detect_sector",
    "load_hints",
    "format_system_prompt",
    "KNOWN_SECTORS",
]
