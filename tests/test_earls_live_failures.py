"""The 2026-08-15 live Earls booking, pinned.

Watched failing in production with the owner narrating in real time:
1. Three legitimate needs_user question-rounds exhausted the attempt cap;
   every later owner re-approval minted a version the extension refused to
   claim, then its at-cap cancel 409'd forever (23 identical rejections).
2. The app's resume overwrote facts["owner_answer"], destroying the
   contact-details answer the moment "No u don't" arrived.
3. The raw answer blob got typed verbatim into OpenTable's "Add Special
   Request" box — the done-verifier had rejected completion for
   "owner_answer not evidenced", teaching the model to put it on the page.
4. The last-resort research URL shipped the unsanitized goal (with the
   owner's overheard conversation) to Bing.
5. The pre-submit auditor flagged an untouched placeholder select
   ("Select an occasion") as an unapproved value 7 times until the
   1-minute table hold expired.
6. Twilio inbound was dead for three days: its URL carried a stale
   "?token=..." that broke signature validation, and the worker's
   self-heal compared URLs with the query stripped, masking it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path  # noqa: E402

from brain.workflow import (Consequence, PlanState, approve, claim,  # noqa: E402
                            new_plan)

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "app/ios/Anticipy/AnticipyApp.swift").read_text()
LOOP = (ROOT / "extension/agent_loop.js").read_text()
BACKGROUND = (ROOT / "extension/background.js").read_text()
WORKFLOW_STATE = (ROOT / "extension/workflow_state.js").read_text()
PAGE_MAP = (ROOT / "extension/page_map.js").read_text()
WORKER = (ROOT / "brain/worker.py").read_text()


# ------------------------------------------------------------- failure 1

def test_owner_approval_resets_the_attempt_budget():
    plan = new_plan(owner_ref="o", lineage_key="dinner", goal="book Earls",
                    consequence=Consequence.CONSEQUENTIAL,
                    source_event_id="ev", authority_text="book earls")
    worn = plan.__class__(**{**plan.__dict__, "attempts": 3})
    out = approve(worn, expected_version=worn.version, owner_words="go ahead")
    assert out.attempts == 0
    # and the re-approved plan is actually claimable again
    claimed = claim(out, expected_version=out.version, actor_id="agent-1")
    assert claimed.state == PlanState.RUNNING


def test_app_resume_resets_attempts_on_row_and_plan():
    assert '"attempts": 0,' in APP
    assert 'workflow["attempts"] = 0' in APP


def test_agent_cancel_no_longer_touches_approval():
    # The guard forbids an executor rewriting approval; the cancelled
    # transition must therefore leave the approval field out of its patch.
    cancelled_branch = WORKFLOW_STATE.split('nextState === "cancelled"')[1][:400]
    assert 'patch.approval' not in cancelled_branch
    assert 'next.approval = null' not in cancelled_branch


def test_poll_failures_are_loud():
    assert "poll cycle failed" in BACKGROUND


# ------------------------------------------------------------- failure 2

def test_app_answers_accumulate_and_structure():
    assert 'facts["owner_answer"] = ownerWords' not in APP
    assert 'owner_answer_v\\(approvedVersion)' in APP
    for key in ('"email"', '"phone"', '"name"'):
        assert key in APP  # deterministic contact structuring


# ------------------------------------------------------------- failure 3

def test_conversational_answers_are_exempt_from_page_evidence():
    import subprocess
    out = subprocess.run(
        ["node", "--input-type=module", "-e", """
import { unsupportedApprovedFacts } from '%s/extension/agent_loop.js';
const state = { text: 'Earls Kitchen reservation for 2 at 7:30 PM', elements: '', fields: [] };
const facts = {
  owner_answer_v4: 'I need a name. Okay Omar. Email is o@x.com. Phone is 604-724-5161.',
  time: '9:45 PM',
};
const bad = unsupportedApprovedFacts(facts, state);
if (bad.includes('owner_answer_v4')) throw new Error('answer blob still demands page evidence');
if (!bad.includes('time')) throw new Error('short unevidenced facts must still be caught');
console.log('ok');
""" % ROOT], capture_output=True, text=True)
    assert "ok" in out.stdout, out.stderr


def test_owner_answers_never_ride_along_as_typed_facts():
    assert "/^owner_answer/i.test(k)" in BACKGROUND


# ------------------------------------------------------------- failure 4

def test_last_resort_research_is_sanitized():
    assert "encodeURIComponent(sanitizedResearchTerms(goal))" in LOOP
    assert "encodeURIComponent(goal)" not in LOOP


# ------------------------------------------------------------- failure 5

def test_placeholder_selects_read_as_empty():
    assert "placeholder" in PAGE_MAP
    assert "el.selectedIndex <= 0" in PAGE_MAP


def test_optional_fields_never_block_is_law():
    low = " ".join(LOOP.split()).lower()
    assert "optional fields never block" in low
    assert "login claims need proof" in low
    assert "page countdowns are real" in low


# ------------------------------------------------------------- failure 6

def test_webhook_self_heal_compares_full_urls():
    assert 'current == ours and not shadowed' in WORKER
    assert 'current.split("?")[0] == ours.split("?")[0]' not in WORKER


def test_sms_rejections_are_logged():
    sms = (ROOT / "backend/pb_hooks/sms.pb.js").read_text()
    assert "signature mismatch" in sms
