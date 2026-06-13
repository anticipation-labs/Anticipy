"""Reversible note-capture commands.

"Add a note to tell customers X" asks the system to create/capture a note. The
"tell customers" phrase is note content, not a binding send. This helper stays
narrow: imperative note creation only, no broad "make visible" or "I should"
captures.
"""
from __future__ import annotations

import re
from typing import Optional


_NOTE_COMMAND_RE = re.compile(
    r"^\s*(?:please\s+)?(?:add|write|make|create|leave|put)\s+"
    r"(?:a\s+|the\s+)?note\b",
    re.I,
)


def match_note_task(text: str) -> Optional[str]:
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return None
    return line if _NOTE_COMMAND_RE.search(line) else None
