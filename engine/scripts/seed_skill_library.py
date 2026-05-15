"""Seed skill_library with all 11 reference skills as `shadow` status.

Run once after deploying the executor. Each row gets:
  skill_id              : the executor-side ID from executor/skills/<id>.js
  intent_match_pattern  : the action_category Pod A would emit for this skill
  code                  : empty bytea (the executor JS is the real "code"; this
                          column is for future codegen-driven skills)
  selector_chain        : the recipe scaffold for the skill (informational)
  verifier_code         : empty bytea (executor JS has the verifier)
  postcondition_spec    : free-text human description
  status                : "shadow" — promoted to "active" by Hermes once
                          10 runs pass at 85%+
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")


SKILLS = [
    {
        "skill_id": "navigate_fact_lookup",
        "intent_match_pattern": "fact_lookup | navigate_to",
        "postcondition_spec": "Extracted text >= 5 chars in evidence.parsed_confirmations.",
    },
    {
        "skill_id": "google_calendar_create_event",
        "intent_match_pattern": "schedule_event",
        "postcondition_spec": "Event created with non-null id + htmlLink + start.dateTime.",
    },
    {
        "skill_id": "gmail_send",
        "intent_match_pattern": "send_email",
        "postcondition_spec": "Message in Sent folder (labelIds contains SENT).",
    },
    {
        "skill_id": "slack_send_message",
        "intent_match_pattern": "post_message | send_email",
        "postcondition_spec": "chat.postMessage response.ok=true with ts + channel.",
    },
    {
        "skill_id": "notion_create_page",
        "intent_match_pattern": "create_issue | update_contact | log_expense",
        "postcondition_spec": "Page object created with id + url; object='page'.",
    },
    {
        "skill_id": "spotify_add_to_queue",
        "intent_match_pattern": "queue_song",
        "postcondition_spec": "Spotify queue POST returned 204 with track URI.",
    },
    {
        "skill_id": "google_maps_save_directions",
        "intent_match_pattern": "navigate_to | set_reminder",
        "postcondition_spec": "Saved-confirmation toast text visible on directions panel.",
    },
    {
        "skill_id": "google_sheets_write_cell",
        "intent_match_pattern": "update_contact | log_expense",
        "postcondition_spec": "values PUT response: updatedCells >= 1 with updatedRange.",
    },
    {
        "skill_id": "linear_create_issue",
        "intent_match_pattern": "create_issue",
        "postcondition_spec": "issueCreate.success=true with issue.id + identifier + url.",
    },
    {
        "skill_id": "amazon_reorder_sub5",
        "intent_match_pattern": "reorder",
        "postcondition_spec": "Order-confirmation text visible AND extracted price <= $5 cap.",
    },
    {
        "skill_id": "resy_book_reservation",
        "intent_match_pattern": "book_reservation",
        "postcondition_spec": "Confirmation modal text contains 'confirm' or 'reservation'.",
    },
]


def main() -> int:
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        print("supabase-py not installed", file=sys.stderr)
        return 2
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("supabase env keys missing", file=sys.stderr)
        return 2
    sb = create_client(url, key)

    empty_bytea = base64.b64encode(b"").decode("ascii")
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for s in SKILLS:
        row = {
            "skill_id": s["skill_id"],
            "intent_match_pattern": s["intent_match_pattern"],
            "code": empty_bytea,
            "selector_chain": {"executor_module": f"executor/skills/{s['skill_id']}.js"},
            "verifier_code": empty_bytea,
            "postcondition_spec": s["postcondition_spec"],
            "status": "shadow",
            "success_count": 0,
            "failure_count": 0,
            "updated_at": now,
        }
        # Upsert: if exists, only update intent_match_pattern + postcondition_spec
        # (don't reset counts/status)
        existing = (
            sb.table("skill_library")
            .select("skill_id,status")
            .eq("skill_id", s["skill_id"])
            .limit(1)
            .execute()
        )
        rows = getattr(existing, "data", None) or []
        if rows:
            sb.table("skill_library").update({
                "intent_match_pattern": s["intent_match_pattern"],
                "postcondition_spec": s["postcondition_spec"],
                "updated_at": now,
            }).eq("skill_id", s["skill_id"]).execute()
            results.append({"skill_id": s["skill_id"], "action": "updated", "status": rows[0]["status"]})
        else:
            sb.table("skill_library").insert(row).execute()
            results.append({"skill_id": s["skill_id"], "action": "inserted_shadow", "status": "shadow"})

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
