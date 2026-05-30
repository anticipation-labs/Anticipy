"""Unified timeline (ARCHITECTURE.md section 3).

Append-only JSONL feed at ``~/.anticipy/v7/timeline.jsonl`` that records
every Anticipy action (sends, web actions, notes, user replies) in a
single store. The popover renders this as one feed, filterable by kind /
status / goal_id.

Public API:

    from app.timeline import append, tail, filter_by

    append({"kind": "sms_sent", "status": "done",
            "summary": "Confirmed lunch with Sarah", "channel": "twilio_sms"})

    last_50 = tail(50)
    for row in filter_by(kind="email_sent", since_ts=time.time() - 3600):
        print(row["summary"])

Per-row schema (see ARCHITECTURE.md section 3):

    {
      "ts": 1780174000.123,
      "goal_id": "g-abc123",
      "kind": "email_sent|sms_sent|voice_call|web_action|note|user_reply",
      "channel": "resend|twilio_sms|twilio_voice|chrome|popover",
      "status": "pending|done|failed|wait_user",
      "summary": "Drafted email to Sarah Lin about Friday demo",
      "payload": { ... arbitrary JSON ... }
    }
"""

from __future__ import annotations

from .reader import filter_by, tail
from .writer import (
    DEFAULT_TIMELINE_PATH,
    MAX_BYTES_BEFORE_ROTATE,
    REQUIRED_FIELDS,
    VALID_KINDS,
    VALID_STATUSES,
    append,
    new_goal_id,
)

__all__ = [
    "DEFAULT_TIMELINE_PATH",
    "MAX_BYTES_BEFORE_ROTATE",
    "REQUIRED_FIELDS",
    "VALID_KINDS",
    "VALID_STATUSES",
    "append",
    "filter_by",
    "new_goal_id",
    "tail",
]
