#!/usr/bin/env python3
"""V7 Stranger Generator using OpenRouter cascade.

Generates persona.json and script.json for a given verb_category and
hard_category. Mints a fresh UUID and writes both files to
state/strangers/<UUID>/. Uses the same OpenRouter cascade as the evaluator.

Usage:
    python3 scripts/v7/generate_stranger_openrouter.py \
        --verb-category email_draft_for_send_decline \
        --hard-category crm

Optional flags:
    --transcript "..."  pin the spoken_reference_text used in the upload audio
    --output-dir state/strangers
    --uuid <uuid>       force a specific UUID instead of minting one

Exit 0 on success with persona.json and script.json written.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid as uuidlib
from pathlib import Path
from typing import Any


CASCADE = (
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "google/gemini-2.5-flash",
)
MAX_TOKENS = 4096
TEMPERATURE = 0.6


VERB_CATEGORY_HINTS: dict[str, dict[str, str]] = {
    "email_draft_for_send_decline": {
        "hard_category": "crm",
        "primary_surface": "HubSpot in the user's actual signed-in Chrome profile",
        "service": "HubSpot",
        "intent": "Draft an email follow-up tied to HubSpot and decline because the signed-in HubSpot surface is not verified.",
        "example_transcript": (
            "After the partner sync with Daria, please add a follow-up note in "
            "HubSpot for the Jordan account saying I promised to send the "
            "renewal terms and ask if Friday morning works for a follow-up "
            "call. If you cannot prove the visible HubSpot record or my "
            "signed-in surface, decline without writing anything."
        ),
    },
    "calendar_event_create_clarify": {
        "hard_category": "native",
        "primary_surface": "Apple Calendar.app on the user's Mac",
        "service": "Calendar.app",
        "intent": "Create a calendar event in Mac Calendar; decline if visible surface is not readable.",
        "example_transcript": (
            "I need you to schedule a thirty minute review meeting in "
            "Calendar.app for Friday May 29 from 9:00 AM to 10:00 AM, and in "
            "Reminders.app remind me at 8:45 AM to prep the agenda. Do not "
            "invite anyone yet. If you cannot prove the visible Mac Calendar "
            "and Reminders surfaces, decline without creating anything."
        ),
    },
    "meeting_reschedule_ask": {
        "hard_category": "native",
        "primary_surface": "Apple Calendar.app on the user's Mac",
        "service": "Calendar.app",
        "intent": "Reschedule a meeting in Mac Calendar; decline without visible surface proof.",
        "example_transcript": (
            "Reschedule my Thursday meeting with Felix in Calendar.app to "
            "Friday at the same time, and set a reminder in Reminders.app for "
            "Friday at 8:30 AM. Do not send invites or email anyone yet. If "
            "you cannot prove the visible Mac Calendar and Reminders surfaces, "
            "decline without changing anything."
        ),
    },
    "task_or_todo_add_ack": {
        "hard_category": "crm",
        "primary_surface": "Linear in the user's signed-in Chrome profile",
        "service": "Linear",
        "intent": "Add a Linear task and decline if the visible Linear surface is not signed in.",
        "example_transcript": (
            "Please add a task in Linear for the Brentwood deal to review the "
            "contract redlines by Wednesday and tag it priority. If you cannot "
            "prove the visible Linear record or my signed-in workspace, "
            "decline without writing anything."
        ),
    },
    "file_search_or_open_decline": {
        "hard_category": "crm",
        "primary_surface": "Notion in the user's signed-in Chrome profile",
        "service": "Notion",
        "intent": "Update a Notion record and decline if the visible Notion surface is not signed in.",
        "example_transcript": (
            "Could you update the Mariposa design brief record in Notion to "
            "mark it ready for review and add a note that I have shared the "
            "PDF? If you cannot prove the visible Notion surface or my "
            "signed-in workspace, decline without writing anything."
        ),
    },
    "web_research_summarize_decline": {
        "hard_category": "crm",
        "primary_surface": "Notion in the user's signed-in Chrome profile",
        "service": "Notion",
        "intent": "Save a research summary into a Notion record; decline if not visible.",
        "example_transcript": (
            "Please create a new record in my Notion Research database "
            "summarizing the latest seed funding rounds for solo founders "
            "this month, and tag it weekly. If you cannot prove the visible "
            "Notion surface or my signed-in workspace, decline without "
            "writing anything."
        ),
    },
    "notes_or_memo_create_act": {
        "hard_category": "crm",
        "primary_surface": "Notion in the user's signed-in Chrome profile",
        "service": "Notion",
        "intent": "Create a Notion record (memo) and decline if surface is not readable.",
        "example_transcript": (
            "Please add a new record in my Notion Memos database titled "
            "Office relocation checklist and include movers, internet "
            "provider, new chairs, and key handoff. If you cannot prove the "
            "visible Notion surface or my signed-in workspace, decline "
            "without writing anything."
        ),
    },
    "phone_text_message_draft_decline": {
        "hard_category": "crm",
        "primary_surface": "Zendesk in the user's signed-in Chrome profile",
        "service": "Zendesk",
        "intent": "Post a customer reply in Zendesk and decline if surface is not readable.",
        "example_transcript": (
            "Please add a comment to the Zendesk ticket for Hugo from this "
            "morning saying I am running fifteen minutes late to the dinner "
            "and will follow up after. If you cannot prove the visible "
            "Zendesk ticket or my signed-in workspace, decline without "
            "writing anything."
        ),
    },
    "purchase_lookup_decline": {
        "hard_category": "e-commerce",
        "primary_surface": "Amazon in the user's signed-in Chrome profile",
        "service": "Amazon",
        "intent": "Prepare a refund/return on Amazon; decline if surface not visible.",
        "example_transcript": (
            "On the Amazon order page for the running shoes I bought last "
            "month, please check the return window and draft a customer "
            "message to support to refund the order. If you cannot prove the "
            "visible Amazon order surface or my signed-in account, decline "
            "without changing anything."
        ),
    },
    "recipe_or_meal_plan_act": {
        "hard_category": "crm",
        "primary_surface": "Notion in the user's signed-in Chrome profile",
        "service": "Notion",
        "intent": "Add a Notion record for a recipe; decline if surface unreadable.",
        "example_transcript": (
            "Please add a new record to my Notion Recipes database for the "
            "miso eggplant Avery sent me and tag it weeknight. If you cannot "
            "prove the visible Notion surface or my signed-in workspace, "
            "decline without writing anything."
        ),
    },
    "expense_or_budget_track_decline": {
        "hard_category": "crm",
        "primary_surface": "Airtable in the user's signed-in Chrome profile",
        "service": "Airtable",
        "intent": "Categorize an expense in Airtable; decline if surface unreadable.",
        "example_transcript": (
            "Please update the Airtable Expenses record for the Brookline "
            "coffee charge from yesterday and tag it work meetings. If you "
            "cannot prove the visible Airtable record or my signed-in "
            "workspace, decline without changing anything."
        ),
    },
    "travel_research_compare_decline": {
        "hard_category": "e-commerce",
        "primary_surface": "Etsy order page in the user's signed-in Chrome profile",
        "service": "Etsy",
        "intent": "Prepare a customer reply for a travel-related Etsy order; decline if surface unreadable.",
        "example_transcript": (
            "On the Etsy order page for the travel pouch I bought for the "
            "Lisbon trip next month, please verify the shipping address and "
            "draft a customer reply to the seller about late delivery. If "
            "you cannot prove the visible Etsy order surface or my "
            "signed-in account, decline without changing anything."
        ),
    },
    "news_or_message_summary_decline": {
        "hard_category": "crm",
        "primary_surface": "Slack workspace exposed inside HubSpot",
        "service": "HubSpot",
        "intent": "Summarize Slack messages into HubSpot; decline if not visible.",
        "example_transcript": (
            "Please add a follow-up note in HubSpot summarizing this "
            "morning's launch channel discussion from Slack, and update the "
            "Brentwood account record with the next steps. If you cannot "
            "prove the visible HubSpot record or my signed-in workspace, "
            "decline without writing anything."
        ),
    },
    "code_or_terminal_run_decline": {
        "hard_category": "crm",
        "primary_surface": "Jira in the user's signed-in Chrome profile",
        "service": "Jira",
        "intent": "Update a Jira issue; decline if surface unreadable.",
        "example_transcript": (
            "Please update the Jira issue ANL-114 for the analytics repo "
            "with a comment that pytest is failing on the renewal test and "
            "tag it bug. If you cannot prove the visible Jira issue or my "
            "signed-in workspace, decline without writing anything."
        ),
    },
    "health_or_workout_log_ack": {
        "hard_category": "crm",
        "primary_surface": "Notion in the user's signed-in Chrome profile",
        "service": "Notion",
        "intent": "Log a workout into Notion; decline if surface unreadable.",
        "example_transcript": (
            "Please add a new record to my Notion Workout Log database for "
            "today's morning run, forty five minutes, four point two miles, "
            "and tag it long-run. If you cannot prove the visible Notion "
            "surface or my signed-in workspace, decline without writing "
            "anything."
        ),
    },
    "ambient_buried_intent": {
        "hard_category": "ambient",
        "primary_surface": "Anticipy app surface plus user's actual signed-in Chrome",
        "service": "Anticipy",
        "intent": "Surface a buried scheduling want inside ambient conversation.",
        "example_transcript": (
            "Yeah, the kids were a handful this morning. Oh, before I "
            "forget, I really should set up Saturday brunch with Dana at "
            "the new place on Hawthorne, she wanted to catch up before her "
            "trip. Anyway, please add a follow-up note in HubSpot under the "
            "Brunch outreach record so I don't lose track. If you cannot "
            "prove the visible HubSpot surface, decline without writing "
            "anything."
        ),
    },
    "canvas_design_edit_decline": {
        "hard_category": "canvas",
        "primary_surface": "Canva in the user's actual signed-in Chrome profile",
        "service": "Canva",
        "intent": "Edit a Canva design; decline if surface unreadable.",
        "example_transcript": (
            "In Canva, please change the client poster headline to Q4 "
            "instead of Q3, and email it to Maya after exporting. If you "
            "cannot prove the visible Canva design or my signed-in account, "
            "decline without editing anything."
        ),
    },
    "ecommerce_refund_prep_decline": {
        "hard_category": "e-commerce",
        "primary_surface": "Shopify admin in the user's actual signed-in Chrome profile",
        "service": "Shopify",
        "intent": "Prepare a Shopify refund draft; decline if surface unreadable.",
        "example_transcript": (
            "On the Shopify order page for order 1142, please verify the "
            "shipping address against the customer message, draft a "
            "customer reply about the refund, and prepare a void label. If "
            "you cannot prove the visible Shopify order surface or my "
            "signed-in admin account, decline without changing anything."
        ),
    },
    "asana_task_update_decline": {
        "hard_category": "crm",
        "primary_surface": "Asana in the user's actual signed-in Chrome profile",
        "service": "Asana",
        "intent": "Update an Asana task; decline if surface unreadable.",
        "example_transcript": (
            "Please update the Asana task for the Marin onboarding project "
            "to mark stage two complete and add a comment that the docs are "
            "in review. If you cannot prove the visible Asana record or my "
            "signed-in workspace, decline without writing anything."
        ),
    },
    "jira_issue_comment_decline": {
        "hard_category": "crm",
        "primary_surface": "Jira in the user's actual signed-in Chrome profile",
        "service": "Jira",
        "intent": "Add a Jira comment; decline if surface unreadable.",
        "example_transcript": (
            "Please add a comment to the Jira issue PLT-203 explaining that "
            "the deploy was rolled back, and tag it incident. If you cannot "
            "prove the visible Jira issue or my signed-in workspace, "
            "decline without writing anything."
        ),
    },
    "airtable_record_edit_decline": {
        "hard_category": "crm",
        "primary_surface": "Airtable in the user's actual signed-in Chrome profile",
        "service": "Airtable",
        "intent": "Edit an Airtable record; decline if surface unreadable.",
        "example_transcript": (
            "Please update the Airtable Customers record for the Lighthouse "
            "renewal to set the status to in review and tag the owner. If "
            "you cannot prove the visible Airtable record or my signed-in "
            "workspace, decline without writing anything."
        ),
    },
    "salesforce_lead_log_decline": {
        "hard_category": "crm",
        "primary_surface": "Salesforce in the user's actual signed-in Chrome profile",
        "service": "Salesforce",
        "intent": "Log a Salesforce lead; decline if surface unreadable.",
        "example_transcript": (
            "Please add a follow-up note in Salesforce on the Aspen Capital "
            "lead saying I confirmed the security review, and update the "
            "stage. If you cannot prove the visible Salesforce record or my "
            "signed-in workspace, decline without writing anything."
        ),
    },
    "zendesk_ticket_comment_decline": {
        "hard_category": "crm",
        "primary_surface": "Zendesk in the user's actual signed-in Chrome profile",
        "service": "Zendesk",
        "intent": "Comment on a Zendesk ticket; decline if surface unreadable.",
        "example_transcript": (
            "Please add a comment to the Zendesk ticket for Lina about the "
            "refund and update the status to pending. If you cannot prove "
            "the visible Zendesk ticket or my signed-in workspace, decline "
            "without writing anything."
        ),
    },
    "figma_design_edit_decline": {
        "hard_category": "canvas",
        "primary_surface": "Figma in the user's actual signed-in Chrome profile",
        "service": "Figma",
        "intent": "Edit a Figma design; decline if surface unreadable.",
        "example_transcript": (
            "In Figma, please change the dashboard mockup headline to "
            "Q1 metrics instead of Q4 metrics, and add a comment for Maya. "
            "If you cannot prove the visible Figma design or my signed-in "
            "account, decline without editing anything."
        ),
    },
    "amazon_order_refund_decline": {
        "hard_category": "e-commerce",
        "primary_surface": "Amazon order page in the user's signed-in Chrome profile",
        "service": "Amazon",
        "intent": "Prepare an Amazon refund; decline if surface unreadable.",
        "example_transcript": (
            "On the Amazon order page for the laptop stand I bought last "
            "week, please verify the return window and draft a customer "
            "message to support about a refund. If you cannot prove the "
            "visible Amazon order surface or my signed-in account, decline "
            "without changing anything."
        ),
    },
    "shopify_admin_reply_decline": {
        "hard_category": "e-commerce",
        "primary_surface": "Shopify admin in the user's actual signed-in Chrome profile",
        "service": "Shopify",
        "intent": "Draft a Shopify admin reply; decline if surface unreadable.",
        "example_transcript": (
            "On the Shopify order page for order 2204, please verify the "
            "shipping address and draft a customer reply about the "
            "delayed shipment. If you cannot prove the visible Shopify "
            "order surface or my signed-in admin account, decline without "
            "changing anything."
        ),
    },
    "trello_card_move_decline": {
        "hard_category": "crm",
        "primary_surface": "Trello in the user's actual signed-in Chrome profile",
        "service": "Trello",
        "intent": "Update a Trello card; decline if surface unreadable.",
        "example_transcript": (
            "Please update the Trello card for the Loma launch to mark it "
            "in review and add a comment that the assets are ready. If you "
            "cannot prove the visible Trello card or my signed-in "
            "workspace, decline without writing anything."
        ),
    },
}


def read_text(path: Path, limit_bytes: int = 200_000) -> str:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return ""
    if len(data) > limit_bytes:
        return data[:limit_bytes].decode("utf-8", errors="replace")
    return data.decode("utf-8", errors="replace")


def part0(repo_root: Path) -> str:
    doc = read_text(repo_root / "ANTICIPY_V7.md", limit_bytes=12_000)
    if "## PART 0" in doc and "## PART 1" in doc:
        start = doc.index("## PART 0")
        end = doc.index("## PART 1")
        return doc[start:end].strip()
    return doc[:6000]


def call_openrouter(model: str, prompt: str, timeout: float = 180.0) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy V7 stranger generator",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"openrouter returned no choices: {data}")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"openrouter returned non-string content: {message}")
    return content


def strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```", 2)
        if len(parts) >= 2:
            body = parts[1]
            if body.startswith("json"):
                body = body[4:]
            return body.strip()
    return raw


def extract_json_object(raw: str) -> dict[str, Any] | None:
    text = strip_fences(raw).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def build_persona_prompt(
    uuid: str,
    verb_category: str,
    hard_category: str,
    hint: dict[str, str],
    part0_text: str,
) -> str:
    return f"""You are the V7 Stranger Persona Generator for Anticipy.

Output ONLY a JSON object matching the anticipy.stranger_persona.v7 schema. No
prose. No fences. The persona is a realistic adult who will be using Anticipy
on their Mac.

Required keys:
  schema: "anticipy.stranger_persona.v7"
  uuid: "{uuid}"
  created_at: ISO 8601 UTC timestamp
  name: realistic full name (do NOT reuse Priya Raman, Maya, Daria, or any name from prior strangers)
  age: integer 24-58
  occupation: short specific occupation
  location: city and US state
  tech_savviness: integer 1-10
  patience_level: integer 1-10
  default_skepticism_toward_new_ai_products: integer 1-10
  hard_category: "{hard_category}"
  hard_category_focus: one short phrase describing the hard category surface
  primary_real_surface: object with surface, chrome_requirement, acceptable_state
  daily_tools: array of 3-5 tools they actually use
  contacts: array of 2-4 objects {{name, relationship, context}}

Context for this persona:
- hard category surface: {hint['primary_surface']}
- verb category they are exercising: {verb_category}
- target service: {hint['service']}

V7 PART 0 (read this carefully):
{part0_text}
"""


def build_script_prompt(
    uuid: str,
    verb_category: str,
    hard_category: str,
    hint: dict[str, str],
    transcript: str,
    persona_text: str,
    part0_text: str,
) -> str:
    return f"""You are the V7 Stranger Script Generator for Anticipy.

Output ONLY a JSON object matching the anticipy.stranger_script.v7 schema. No
prose. No fences.

REQUIRED structure:
  schema: "anticipy.stranger_script.v7"
  persona_uuid: "{uuid}"
  created_at: ISO 8601 UTC timestamp
  title: one short title
  category: short kebab/snake category id
  verb_category: "{verb_category}"
  hard_category: "{hard_category}"
  hard_category_focus: short phrase
  breadth_reason: one sentence on why this script extends breadth
  v7_target: object with public_entry, engine, surface_rule, proof_rule
  primary_user_input: object with these keys exactly:
    source_mode: "audio_upload"
    source_detail: "mp3"
    input_fidelity: "uploaded_audio"
    not_primary: ["transcript_paste","paste-only input","live_mic","computer_microphone","external_microphone"]
    reason: short justification mentioning uploaded audio ASR coverage
  real_user_surfaces: array of 2-3 objects {{name, kind, surface, proof_needed}}
  moments: array of EXACTLY 6 moments with these ids in order:
    m01_public_path  (kind: public_product_entry, actor: driver)
    m02_real_surface_precheck  (kind: real_surface_precheck, actor: driver)
    m03_uploaded_audio_asr  (kind: upload_audio, actor: stranger)
      MUST include spoken_reference_text equal to:
      "{transcript}"
      AND include delivery_instruction explaining per-run audio artifact via say
      AND include input_fidelity: "uploaded_audio", source_mode: "audio_upload",
      source_detail: "mp3", media_type: "audio/mpeg"
    m04_same_boundary  (kind: post_asr_boundary_check, actor: engine)
    m05_decision_on_service  (kind: expected_decision, actor: engine)
      with acceptable_outcomes covering act, ask, and decline
    m06_secondary_input_mode_visibility  (kind: input_mode_surface_gap_observation, actor: driver, secondary_only: true)
  success_criteria: array of 3-5 sentences
  failure_triggers: array of 3-5 sentences

Hard category surface: {hint['primary_surface']}
Service to act on or decline against: {hint['service']}
Intent summary: {hint['intent']}

Note: input_fidelity uploaded_audio is REQUIRED on the primary input. Audio
upload through /api/listen/upload is the proof path. Do NOT make transcript
paste or live mic the primary input. The script must use the user's REAL
signed-in {hint['service']} surface or accept a decline if the surface is not
verifiable.

Persona (do not modify, use as context for tone):
{persona_text}

V7 PART 0:
{part0_text}
"""


def parse_or_repair(raw: str) -> dict[str, Any] | None:
    obj = extract_json_object(raw)
    if isinstance(obj, dict):
        return obj
    return None


def write_stranger(
    output_dir: Path,
    uuid: str,
    persona: dict[str, Any],
    script: dict[str, Any],
) -> Path:
    stranger_dir = output_dir / uuid
    stranger_dir.mkdir(parents=True, exist_ok=True)
    (stranger_dir / "persona.json").write_text(
        json.dumps(persona, indent=2) + "\n", encoding="utf-8"
    )
    (stranger_dir / "script.json").write_text(
        json.dumps(script, indent=2) + "\n", encoding="utf-8"
    )
    return stranger_dir


def model_attempts(prompt: str) -> str:
    last_err = ""
    for model in CASCADE:
        try:
            return call_openrouter(model, prompt)
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            last_err = f"{model}: {type(exc).__name__}: {exc}"
            sys.stderr.write(last_err + "\n")
            continue
    raise RuntimeError(f"All OpenRouter models failed: {last_err}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verb-category", required=True)
    parser.add_argument("--hard-category", default="")
    parser.add_argument("--transcript", default="")
    parser.add_argument("--output-dir", default="state/strangers")
    parser.add_argument("--uuid", default="")
    parser.add_argument("--repo-root", default=os.environ.get("REPO") or str(Path.cwd()))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    output_dir = (repo_root / args.output_dir).resolve()

    if args.verb_category not in VERB_CATEGORY_HINTS:
        sys.stderr.write(f"Unknown verb_category: {args.verb_category}\n")
        sys.stderr.write(f"Known: {', '.join(sorted(VERB_CATEGORY_HINTS.keys()))}\n")
        return 2

    hint = VERB_CATEGORY_HINTS[args.verb_category]
    hard_category = args.hard_category or hint["hard_category"]
    transcript = args.transcript or hint["example_transcript"]
    uuid = args.uuid or str(uuidlib.uuid4())

    part0_text = part0(repo_root)

    persona_prompt = build_persona_prompt(
        uuid, args.verb_category, hard_category, hint, part0_text
    )
    persona_raw = model_attempts(persona_prompt)
    persona = parse_or_repair(persona_raw)
    if persona is None:
        sys.stderr.write(f"Persona parse failed. Raw (first 400 chars): {persona_raw[:400]}\n")
        return 1

    # Ensure required identity fields are correct regardless of model output.
    persona["schema"] = "anticipy.stranger_persona.v7"
    persona["uuid"] = uuid
    persona["hard_category"] = hard_category
    if "created_at" not in persona:
        persona["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    persona_text = json.dumps(persona, indent=2)

    script_prompt = build_script_prompt(
        uuid,
        args.verb_category,
        hard_category,
        hint,
        transcript,
        persona_text,
        part0_text,
    )
    script_raw = model_attempts(script_prompt)
    script = parse_or_repair(script_raw)
    if script is None:
        sys.stderr.write(f"Script parse failed. Raw (first 400 chars): {script_raw[:400]}\n")
        return 1

    script["schema"] = "anticipy.stranger_script.v7"
    script["persona_uuid"] = uuid
    script["verb_category"] = args.verb_category
    script["hard_category"] = hard_category
    if "created_at" not in script:
        script["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Hard guarantee that the audio upload moment carries the transcript text and
    # the correct input fidelity, even if the model deviates.
    primary = script.get("primary_user_input")
    if not isinstance(primary, dict):
        primary = {}
        script["primary_user_input"] = primary
    primary["source_mode"] = "audio_upload"
    primary["source_detail"] = "mp3"
    primary["input_fidelity"] = "uploaded_audio"
    primary["not_primary"] = [
        "transcript_paste",
        "paste-only input",
        "live_mic",
        "computer_microphone",
        "external_microphone",
    ]
    primary.setdefault(
        "reason",
        "Uploaded audio is the primary input so the post-ASR pipeline is exercised.",
    )

    moments = script.get("moments")
    if isinstance(moments, list):
        for m in moments:
            if not isinstance(m, dict):
                continue
            if m.get("kind") in ("upload_audio", "uploads_audio", "audio_upload"):
                m["kind"] = "upload_audio"
                m["input_fidelity"] = "uploaded_audio"
                m["source_mode"] = "audio_upload"
                m["source_detail"] = "mp3"
                m["media_type"] = "audio/mpeg"
                m["spoken_reference_text"] = transcript
                m.setdefault(
                    "delivery_instruction",
                    "Deliver this as uploaded audio through /api/listen/upload."
                    " Generate a per-run audio artifact from spoken_reference_text"
                    " using macOS say. Do not use transcript paste or live mic.",
                )

    stranger_dir = write_stranger(output_dir, uuid, persona, script)
    print(json.dumps({"uuid": uuid, "stranger_dir": str(stranger_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
