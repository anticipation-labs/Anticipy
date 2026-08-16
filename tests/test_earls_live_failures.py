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

def test_a_card_he_must_approve_is_always_approvable(monkeypatch):
    # Live 2026-08-16, and this one was MY regression. Asked-for details were
    # made REQUIRED plan facts, which parks a plan in DRAFT. But the brain
    # still showed him a card saying "Send it" — and the phone refuses to
    # approve a draft, so Send failed with "I couldn't reach Anticipy Claude
    # version" and nothing anywhere explained why. His dinner never queued.
    #
    # The rule: a card the owner is being asked to approve must be
    # approvable. HIS APPROVAL IS THE ANSWER. Holding for missing facts
    # protects work that runs WITHOUT him, not work he is standing over.
    #
    # And triage writes prose into `missing` — that day it held "The current
    # date is Saturday, August 15, 2026. Tomorrow is Sunday..." and the word
    # "date" in that sentence became a required fact. A field name is never
    # a sentence.
    import json as _json
    import brain.anticipy_core as coremod
    from brain.anticipy_core import Anticipy, _required_from_missing
    from brain.memory import Memory

    assert _required_from_missing(["time", "party size"]) == ("time", "party_size")
    assert _required_from_missing("which Earls location") == ("location",)
    assert _required_from_missing(["favourite colour"]) == ()   # never wedges
    # the exact prose that froze his card
    assert _required_from_missing([
        "The current date is Saturday, August 15, 2026. Tomorrow is Sunday, "
        "August 16, 2026. The user specified Saturday for tomorrow's booking."
    ]) == ()

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
    assert wf["state"] == "awaiting_approval", "a held card must be approvable"
    assert tuple(wf["required"]) == (), "a card he approves holds no required facts"
    assert posted["workflow_state"] == "awaiting_approval"


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


# ------------------------------------------- "feel like it's hard-coded"

def test_her_own_words_survive_the_fact_guard():
    # Live 2026-08-16 he received, again and again, the identical robot line
    # "I'm nearly through Book dinner for 2 at Earls in West Van tomorrow
    # (Saturday) at 6 PM — ..." and said "feel like it's hard-coded". He was
    # right, and the cause was a guard, not a template: a paraphrase was
    # rejected if it contained ANY fact token absent from the blocker text.
    # The model is shown the TASK too, so mentioning the 6 PM from the goal
    # counted as an invention and every natural sentence was thrown away.
    from brain.worker import _fact_tokens, carries_facts

    blocker = "I need your email address"
    goal = "Book dinner for 2 at Earls in West Van tomorrow at 6 PM"
    allowed = f"{blocker} {goal}"
    human = "I'm almost done booking Earls for 6 PM tomorrow — what's your email?"

    def accepted_for(blk, said, task=goal):
        allow = f"{blk} {task}"
        return (carries_facts(said, blk)
                or (_fact_tokens(blk) <= _fact_tokens(said)
                    and _fact_tokens(said) <= _fact_tokens(allow)))

    def accepted(said):
        return accepted_for(blocker, said)

    assert not carries_facts(human, blocker), "this is the rejection he hit"
    assert accepted(human), "a sentence using the task's own facts must survive"
    # ...but inventing a fact neither the blocker nor the task ever had is
    # still refused: that is what the guard exists for.
    assert not accepted("I'm almost done booking Earls for 9 PM — your email?")
    # and a time the blocker DID name must still survive the rewrite
    timed = "I need the 7:15 slot confirmed"
    assert not accepted_for(timed, "I'm nearly done — confirm?"), \
        "a rewrite that drops the blocker's own time is still refused"

    src = (ROOT / "brain/worker.py").read_text()
    assert "asking again with them pinned" in src, "one retry before the robot voice"


# ------------------------- asking into a sentence that is still arriving

def test_a_question_waits_for_the_sentence_to_finish():
    """Live 2026-08-16, and the clearest example of the pattern he named.

    The 8-second flush ceiling cuts continuous speech into fragments. Triage
    runs per fragment, so "...should grab dinner tomorrow at like 6 PM for"
    was judged complete on its own and she asked "which restaurant, and for
    how many people?" — four seconds before the next fragment said "let's do
    Earls". She asked for something he was in the middle of saying.

    Deferring costs one cycle. The card stays, later fragments merge into it
    by lineage, and she asks only about what is genuinely still missing.
    """
    import brain.worker as w

    w.LAST_HEARD_AT = w.time.time()
    assert w.SPEAK_ONCE("which restaurant?", "book dinner", "ask") == "defer", (
        "a question born mid-conversation must wait")

    # Once they have actually stopped, the question goes out.
    w.LAST_HEARD_AT = w.time.time() - (w.LIVE_CONVERSATION_S + 2)
    assert w.SPEAK_ONCE("which restaurant?", "book dinner", "ask") is not "defer"

    # The window must outlast the flush ceiling, or the gaps between a
    # person's OWN fragments read as the end of their turn.
    assert w.LIVE_CONVERSATION_S > 8


def test_the_clock_names_the_days_so_nothing_has_to_compute_them():
    # Twice in two days a card read "tomorrow (Saturday)" — on Saturday, and
    # again on Sunday. The clock line gave only "right now", so the model did
    # the weekday arithmetic itself and got it wrong both times.
    from brain.llm import now_line
    line = now_line("America/Vancouver")
    assert "Tomorrow is" in line and "Yesterday was" in line
    assert "Never write a weekday next to a relative day" in line


# ---------------------------- the two-hour CAPTCHA that never existed

def test_the_compliance_badge_is_not_a_captcha_wall():
    """Live 2026-08-16: the Cactus Club booking parked claiming a CAPTCHA and
    texted him about it four times over two hours. There was no CAPTCHA —
    only the invisible reCAPTCHA v3 badge every booking page carries, and a
    date-of-birth field. He was looking straight at it: "there's no captcha,
    just press submit, enter a date of birth and press submit."
    """
    import subprocess
    out = subprocess.run(["node", "--input-type=module", "-e", """
import { looksLikeCaptcha } from '%s/extension/agent_loop.js';
const badge = {url:'https://sevenrooms.com/reservations/cactusclub', title:'Reserve',
  text:'Complete your reservation. Date of birth. Submit. This site is protected by reCAPTCHA and the Google Privacy Policy and Terms of Service apply.'};
const real = {url:'https://www.google.com/sorry/index', title:'',
  text:'Our systems have detected unusual traffic from your computer network.'};
if (looksLikeCaptcha(badge)) throw new Error('a compliance badge is not a wall');
if (!looksLikeCaptcha(real)) throw new Error('a real challenge must still stop it');
console.log('ok');
""" % ROOT], capture_output=True, text=True)
    assert "ok" in out.stdout, out.stderr


def test_someone_looking_at_the_screen_outranks_the_agents_diagnosis():
    from brain.conversation import Conversation
    d = Conversation._disputes_or_directs
    need = "solve the CAPTCHA"
    # the sentence that should have saved the booking
    assert d("I'm looking at your page there's no captcha just press submit "
             "enter a date of birth and press submit", need)
    assert d("No there is none", need)
    assert d("press submit", need)
    # ...but an ordinary answer, or a real refusal, is unchanged
    assert not d("Ebrahim", "I need your last name and email")
    assert not d("no", need)
    assert not d("make it 6", "I need the 6-digit verification code")


def test_she_may_not_promise_what_only_a_person_can_do():
    core = (ROOT / "brain/anticipy_core.py").read_text()
    low = " ".join(core.split()).lower()
    assert "never agree to do something you cannot do" in low
    assert "when they describe the screen, they are right and you are wrong" in low
    assert "sending the same sentence twice is not a follow-up" in low
