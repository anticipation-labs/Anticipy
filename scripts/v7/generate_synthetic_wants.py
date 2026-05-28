#!/usr/bin/env python3
"""Generate a small V7 inference bootstrap dataset."""

from __future__ import annotations

import json
from pathlib import Path


OUT = Path("state/inference_dataset/synthetic_wants.jsonl")


EXAMPLES = [
    {
        "id": "want_email_001",
        "input_mode": "transcript",
        "text": "I should get the launch recap over to Maya before standup.",
        "contains_actionable_want": True,
        "want_owner": "user",
        "want_type": "draft_email",
        "desired_state": "draft a launch recap email to Maya",
        "evidence_spans": ["get the launch recap over to Maya"],
        "known_surface_exists": True,
        "known_skill_exists": True,
        "missing_slots": ["email_body"],
        "risk_tier": 2,
        "gold_action_or_decline": "ask_first",
        "flags": {"hypothetical": False, "joke": False, "quoted_speech": False, "media_reference": False, "third_party": False, "already_satisfied": False},
    },
    {
        "id": "want_calendar_001",
        "input_mode": "computer_mic",
        "text": "Block Friday afternoon so I can prep the renewal review.",
        "contains_actionable_want": True,
        "want_owner": "user",
        "want_type": "calendar_block",
        "desired_state": "create a self calendar block on Friday afternoon",
        "evidence_spans": ["Block Friday afternoon"],
        "known_surface_exists": True,
        "known_skill_exists": True,
        "missing_slots": [],
        "risk_tier": 2,
        "gold_action_or_decline": "execute_notify",
        "flags": {"hypothetical": False, "joke": False, "quoted_speech": False, "media_reference": False, "third_party": False, "already_satisfied": False},
    },
    {
        "id": "want_crm_decline_001",
        "input_mode": "mp3",
        "text": "Update the Salesforce renewal stage unless the source pages are missing.",
        "contains_actionable_want": True,
        "want_owner": "user",
        "want_type": "crm_update",
        "desired_state": "update CRM only if visible proof exists",
        "evidence_spans": ["Update the Salesforce renewal stage"],
        "known_surface_exists": False,
        "known_skill_exists": True,
        "missing_slots": ["visible_record_proof"],
        "risk_tier": 3,
        "gold_action_or_decline": "decline",
        "flags": {"hypothetical": False, "joke": False, "quoted_speech": False, "media_reference": False, "third_party": False, "already_satisfied": False},
    },
    {
        "id": "negative_quote_001",
        "input_mode": "transcript",
        "text": "Maya said, quote, remind me to send the contract tomorrow.",
        "contains_actionable_want": False,
        "want_owner": "other",
        "want_type": "none",
        "desired_state": "do not act on quoted speech",
        "evidence_spans": ["Maya said, quote"],
        "known_surface_exists": False,
        "known_skill_exists": False,
        "missing_slots": [],
        "risk_tier": 0,
        "gold_action_or_decline": "silent_decline",
        "flags": {"hypothetical": False, "joke": False, "quoted_speech": True, "media_reference": False, "third_party": True, "already_satisfied": False},
    },
    {
        "id": "negative_media_001",
        "input_mode": "computer_mic",
        "text": "This podcast host keeps saying he needs to book a flight.",
        "contains_actionable_want": False,
        "want_owner": "other",
        "want_type": "none",
        "desired_state": "do not act on media reference",
        "evidence_spans": ["podcast host keeps saying"],
        "known_surface_exists": False,
        "known_skill_exists": False,
        "missing_slots": [],
        "risk_tier": 0,
        "gold_action_or_decline": "silent_decline",
        "flags": {"hypothetical": False, "joke": False, "quoted_speech": False, "media_reference": True, "third_party": True, "already_satisfied": False},
    },
]


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in EXAMPLES),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "path": str(OUT), "examples": len(EXAMPLES)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
