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
    assert 'String(format: "owner_answer_v%03d", approvedVersion)' in APP
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


# ------------------------------------------------- ask-then-run-anyway

def test_an_asked_detail_holds_the_plan_until_answered(monkeypatch):
    # Cactus, live: "what time and how many people?" went out, was never
    # answered, and the browser booked toward an invented 7 PM for 2.
    # An asked-for detail is now a REQUIRED plan fact: the plan parks in
    # DRAFT (status awaiting_confirm — unclaimable) until the answer fills it.
    import json as _json
    import brain.anticipy_core as coremod
    from brain.anticipy_core import Anticipy, _required_from_missing
    from brain.memory import Memory

    assert _required_from_missing(["time", "party size"]) == ("time", "party_size")
    assert _required_from_missing("which Earls location") == ("location",)
    assert _required_from_missing(["favourite colour"]) == ()  # never wedges

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    posted = {}

    class R:
        ok = True
        def raise_for_status(self): pass
        def json(self): return {"id": "j-held", "status": posted.get("status", "")}

    def post(url, **kw):
        posted.update(kw.get("json") or {})
        return R()

    monkeypatch.setattr(coremod, "pb", type("PB", (), {
        "post": staticmethod(post),
        "get": staticmethod(lambda *a, **k: type("E", (), {
            "ok": False, "json": lambda self: {"items": []}})()),
    }))
    a._queue_job("book dinner at Cactus Club", {
        "source": "book cactus club west van tomorrow",
        "missing": ["time", "party size"]}, hold=True)
    wf = _json.loads(posted["params"])["_workflow"]
    assert tuple(wf["required"]) == ("time", "party_size")
    assert posted["status"] == "awaiting_confirm"   # not claimable
    assert wf["state"] == "draft"


def test_the_answer_fills_required_facts_even_with_odd_keys(monkeypatch):
    import json
    import brain.conversation as convmod
    from tests.test_correction_integrity import _conv, _pb
    from brain.workflow import Consequence, new_plan, put_in_params
    plan = new_plan(owner_ref="o", lineage_key="dinner", goal="book Earls",
                    consequence=Consequence.CONSEQUENTIAL,
                    source_event_id="ev", authority_text="earls tmrw",
                    required=("location",))
    assert plan.state.value == "draft"
    params = put_in_params({}, plan)
    job = {"id": "j1", "goal": "book Earls",
           "status": "awaiting_confirm", "params": json.dumps(params)}
    patched = _pb(monkeypatch, convmod, job)
    out = _conv()._amend("j1", {"which_location": "West Vancouver"},
                         owner_text="West van")
    assert out == "amended:j1"
    p = json.loads(patched["params"])
    assert p["_workflow"]["facts"]["location"] == "West Vancouver"
    assert p["_workflow"]["state"] == "awaiting_approval"  # unparked


# ------------------------------------------------- questions reach the owner

def test_needs_user_questions_are_never_swallowed_into_fallback():
    gate = LOOP.split('decision.action === "needs_user"')[1][:1400]
    assert "questionShaped" in gate
    assert "pageFailure" in gate
    # fallback requires BOTH not-a-question AND an explicit page failure
    assert "!questionShaped && pageFailure" in gate


# ------------------------------------------- one conversation, one card

def test_one_conversation_never_becomes_three_cards(monkeypatch):
    # Live 2026-08-16: a single dinner chat with Jessica produced THREE
    # awaiting_confirm cards — "Confirm dinner tomorrow", "Plan dinner with
    # Jessica tomorrow at Earls at 7:30 PM" (a venue nobody said), and "Plan
    # dinner for tomorrow at Cactus Club Cafe" — every one of them carrying
    # the SAME lineage_key k6xjtydqwapvstr, the segment id of that one
    # conversation. The system knew and asked a model's opinion on wording
    # anyway. The lineage is deterministic; it decides now.
    import brain.anticipy_core as coremod
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory

    SEG = "k6xjtydqwapvstr"
    cards = {}
    patched = {}

    class R:
        ok = True
        def __init__(self, payload): self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p

    def get(url, **kw):
        flt = (kw.get("params") or {}).get("filter", "")
        if f'lineage_key="{SEG}"' in flt and 'status="awaiting_confirm"' in flt:
            return R({"items": list(cards.values())})
        return R({"items": []})

    def post(url, **kw):
        body = kw.get("json") or {}
        jid = f"job{len(cards) + 1}"
        cards[jid] = {"id": jid, "goal": body.get("goal", ""),
                      "params": body.get("params", "{}"),
                      "status": "awaiting_confirm"}
        return R({**cards[jid]})

    def patch(url, **kw):
        patched.update(kw.get("json") or {})
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        if jid in cards:
            cards[jid].update(kw.get("json") or {})
        return R(cards.get(jid, {}))

    monkeypatch.setattr(coremod, "pb", type("PB", (), {
        "get": staticmethod(get), "post": staticmethod(post),
        "patch": staticmethod(patch)}))

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a._lineage_key = SEG
    monkeypatch.setattr(Anticipy, "_covered_by", lambda self, new, old: False)

    first = a._queue_job("Confirm dinner tomorrow",
                         {"source": "we should have dinner tomorrow",
                          "lineage_key": SEG}, hold=True)
    second = a._queue_job("Plan dinner with Jessica tomorrow at Earls at 7:30 PM",
                          {"source": "Let's do tomorrow", "lineage_key": SEG},
                          hold=True)
    third = a._queue_job("Plan dinner tomorrow at Cactus Club Cafe West Van 7:30",
                         {"source": "at 7:30 in cactus at West Van",
                          "lineage_key": SEG}, hold=True)

    assert first == second == third, "one conversation must hold ONE card"
    assert len(cards) == 1, f"minted {len(cards)} cards from one conversation"
    # and the surviving card carries the latest, richest wording
    assert "Cactus" in cards[first]["goal"]


def test_a_declared_new_task_still_gets_its_own_card(monkeypatch):
    # The merge must not swallow a genuinely separate errand said in the same
    # breath — "also, separately, book my haircut" is not the dinner.
    import brain.anticipy_core as coremod
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory

    made = []

    class R:
        ok = True
        def __init__(self, p): self._p = p
        def raise_for_status(self): pass
        def json(self): return self._p

    monkeypatch.setattr(coremod, "pb", type("PB", (), {
        "get": staticmethod(lambda *a, **k: R({"items": [
            {"id": "job1", "goal": "dinner", "status": "awaiting_confirm",
             "params": "{}"}]})),
        "post": staticmethod(lambda *a, **k: (
            made.append((k.get("json") or {}).get("goal")),
            R({"id": f"new{len(made)}", "status": "awaiting_confirm"}))[1]),
        "patch": staticmethod(lambda *a, **k: R({}))}))

    a = Anticipy(memory=Memory(":memory:"), llm=None, owner_id="t")
    a._lineage_key = "seg-1"
    out = a._queue_job("book a haircut",
                       {"lineage_key": "seg-1",
                        "source": "separate thing, book my haircut"}, hold=True)
    assert out and out.startswith("new"), "a declared new task keeps its own card"
