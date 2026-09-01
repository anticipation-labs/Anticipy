"""The texting lane must never act on the wrong job or narrate one it did not.

Every case here is a way she told him something true-sounding about work that
had not moved, or moved work he had not named: a detail smeared across two
jobs, a half-failed scrap reported as a clean sweep, an amendment announced as
a booking, a remembered surname counted as progress, two blocked tasks fighting
over the word "name", an hour-old call-off menu answering a later yes.
"""
import json
import re

import pytest

import brain.conversation as convmod
from brain.anticipy_core import Anticipy
from brain.conversation import Conversation
from brain.memory import Memory


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p


def _pb(monkeypatch, jobs, refuse=()):
    """A backend over `jobs`. Ids in `refuse` 4xx on PATCH — the extension
    claiming a job inside the poll window looks exactly like this."""

    def get(url, **kw):
        tail = url.rstrip("/").rsplit("/", 1)[-1]
        for j in jobs:
            if j["id"] == tail:
                return _R(j)
        if "/jobs/" not in url:
            return _R({"items": []})
        want = re.search(r'status="(\w+)"', (kw.get("params") or {}).get("filter", ""))
        status = want.group(1) if want else None
        return _R({"items": [j for j in jobs if j.get("status") == status]})

    def patch(url, **kw):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        if jid in refuse:
            return _R({}, ok=False)
        for j in jobs:
            if j["id"] == jid:
                j.update(kw.get("json") or {})
                return _R(j)
        return _R({}, ok=False)

    monkeypatch.setattr(convmod, "pb", type("PB", (), {
        "get": staticmethod(get), "patch": staticmethod(patch)}))
    return jobs


def _bare():
    return Conversation(Anticipy(memory=Memory(":memory:"), llm=None,
                                 owner_id="t"), llm=None)


def _spoken(monkeypatch, parsed):
    """A conversation whose classifier said exactly `parsed`."""
    c = _bare()
    monkeypatch.setattr(c, "_classify", lambda phone, text: dict(parsed))
    monkeypatch.setattr(c, "_about_pending", lambda phone, text: "no")
    return c


def _two_held():
    return [{"id": "dinner", "goal": "Book dinner at Earls",
             "status": "awaiting_confirm",
             "params": json.dumps({"source": "book dinner at earls"})},
            {"id": "email", "goal": "Email Mark the deck",
             "status": "awaiting_confirm",
             "params": json.dumps({"source": "email mark the deck"})}]


# ---------------------------------------------------------------- multi-item

def test_a_detail_in_a_two_item_yes_lands_only_on_its_own_job(monkeypatch):
    """"yes to both, make the dinner 7pm" wrote time=7pm into the EMAIL job's
    params and into its approved_scope as a value that "overrides the task
    wording"."""
    jobs = _pb(monkeypatch, _two_held())
    c = _spoken(monkeypatch, {"intent": "confirm", "pending_id": "dinner",
                              "pending_ids": ["dinner", "email"],
                              "changes": {"time": "7pm"},
                              "reply": "On it — both going out."})
    c.on_reply("+15550001", "yes to both, make the dinner 7pm")
    dinner, email = json.loads(jobs[0]["params"]), json.loads(jobs[1]["params"])
    assert dinner["time"] == "7pm"
    assert "time" not in email
    assert "7pm" not in email.get("approved_scope", "")


def test_a_detail_with_no_owner_is_asked_about_not_smeared_or_dropped(monkeypatch):
    """With the change attached to neither of the two, releasing both without
    it books the old time while her reply reads the new one back."""
    jobs = _pb(monkeypatch, _two_held())
    c = _spoken(monkeypatch, {"intent": "confirm", "pending_id": None,
                              "pending_ids": ["dinner", "email"],
                              "changes": {"time": "7pm"},
                              "reply": "On it — both going out at 7."})
    out = c.on_reply("+15550001", "yes to both, make it 7pm")
    assert out["acted"] is None
    assert "which one" in out["reply"].lower()
    assert all(j["status"] == "awaiting_confirm" for j in jobs), jobs


def test_a_half_failed_scrap_is_never_reported_as_both_gone(monkeypatch):
    """The model drafts "Done — scrapped both." before either write is tried.
    One of them can lose the race and still be running."""
    jobs = _pb(monkeypatch, _two_held(), refuse={"email"})
    c = _spoken(monkeypatch, {"intent": "decline", "pending_id": None,
                              "pending_ids": ["dinner", "email"],
                              "changes": None, "reply": "Done — scrapped both."})
    out = c.on_reply("+15550001", "scrap both of those")
    assert out["reply"] != "Done — scrapped both."
    assert "Book dinner at Earls" in out["reply"]
    assert "couldn't stop Email Mark the deck" in out["reply"]
    assert jobs[0]["status"] == "cancelled"
    assert jobs[1]["status"] == "awaiting_confirm"


# ------------------------------------------------------------ what she says

def test_an_amendment_never_goes_out_as_a_booking_claim(monkeypatch):
    """The old gate skipped the rewrite whenever the reply shared a 4-letter
    word with the job — and `params` carries the whole transcript, so every
    on-topic sentence kept its claim."""
    jobs = _pb(monkeypatch, [{
        "id": "dinner", "goal": "Book dinner at Earls for 2 tomorrow",
        "status": "awaiting_confirm",
        "params": json.dumps({"source": "let's book dinner at Earls tomorrow"})}])
    c = _spoken(monkeypatch, {
        "intent": "modify", "pending_id": "dinner", "pending_ids": [],
        "changes": {"time": "7pm"},
        "reply": "Perfect — moving the dinner to 7, I'll get it booked."})
    out = c.on_reply("+15550001", "make it 7 instead")
    assert out["acted"] == "amended:dinner"
    assert "booked" not in out["reply"]
    assert "waiting on your go-ahead" in out["reply"]
    assert jobs[0]["status"] == "awaiting_confirm"


def test_remembering_his_surname_is_not_progress_on_a_blocked_task(monkeypatch):
    """2026-08-02, verbatim: two tasks blocked, he tells her his last name,
    neither requirement is covered, and she says she is finishing the booking."""
    jobs = _pb(monkeypatch, [
        {"id": "code", "goal": "Finish the signup", "status": "needs_user",
         "result": "I need the 6-digit verification code", "params": "{}"},
        {"id": "phone", "goal": "Book the table", "status": "needs_user",
         "result": "I need a phone for the reservation", "params": "{}"}])
    c = _spoken(monkeypatch, {"intent": "answer", "pending_id": None,
                              "pending_ids": [], "changes": None,
                              "reply": "Perfect — I'll finish that booking now."})
    monkeypatch.setattr(c, "_remember_about_owner",
                        lambda text: {"last_name": "Ebrahim"})
    monkeypatch.setattr(c, "_still_need",
                        lambda blocked: "I still need the code.")
    out = c.on_reply("+15550001", "my last name is Ebrahim")
    assert out["reply"] == "I still need the code."
    assert all(j["status"] == "needs_user" for j in jobs), jobs


def test_an_ambiguous_detail_lists_the_blocked_jobs_not_an_empty_approval_menu(
        monkeypatch):
    jobs = _pb(monkeypatch, [
        {"id": "code", "goal": "Finish the signup", "status": "needs_user",
         "result": "I need the verification code", "params": "{}"},
        {"id": "phone", "goal": "Book the table", "status": "needs_user",
         "result": "I need the reservation phone", "params": "{}"}])
    c = _spoken(monkeypatch, {
        "intent": "answer", "pending_id": None, "pending_ids": [],
        "changes": {"verification_code": "428913"}, "reply": "Got it.",
    })
    out = c.on_reply("+15550001", "the code is 428913")
    assert "which one should i answer" in out["reply"].lower()
    assert "1) Finish the signup" in out["reply"]
    assert "2) Book the table" in out["reply"]
    assert all(j["status"] == "needs_user" for j in jobs), jobs


# --------------------------------------------------------- matching answers

def _name_pair():
    return [{"id": "signup", "goal": "Sign up for the account",
             "status": "needs_user",
             "result": "I need your full name for the signup",
             "params": json.dumps({"approved_scope": "Task: sign up."})},
            {"id": "table", "goal": "Book a table", "status": "needs_user",
             "result": "I need the name of the restaurant you want",
             "params": json.dumps({"approved_scope": "Task: book a table."})}]


def test_his_own_name_never_becomes_the_restaurant(monkeypatch):
    """Both needs end in "name", so the head-noun fallback matched both and
    the booking was handed "Omar Ebrahim" as an answer stamped final."""
    jobs = _pb(monkeypatch, _name_pair())
    out = _bare()._resume_stuck({"full_name": "Omar Ebrahim"},
                                owner_text="Omar Ebrahim")
    assert out == "resumed:signup"
    assert jobs[0]["status"] == "queued"
    assert jobs[1]["status"] == "needs_user"
    assert "Omar Ebrahim" not in jobs[1]["params"]


def test_two_tasks_wanting_the_same_noun_resume_neither(monkeypatch):
    """One weak match is a fair read of the room; two is a coin toss."""
    jobs = _pb(monkeypatch, [
        {"id": "a", "goal": "Book a table", "status": "needs_user",
         "result": "I need the name of the restaurant", "params": "{}"},
        {"id": "b", "goal": "Add the guest", "status": "needs_user",
         "result": "I need the name on the reservation", "params": "{}"}])
    assert _bare()._resume_stuck({"full_name": "Omar Ebrahim"},
                                 owner_text="Omar Ebrahim") is None
    assert all(j["status"] == "needs_user" for j in jobs), jobs


# ------------------------------------------------------------- resume paths

def test_a_correction_made_while_parked_rides_in_with_the_answer(monkeypatch):
    """He moved it to 6 while it sat parked; then he answered the question it
    was parked on. Only _release ever folded corrections into the authority,
    so the resumed run read 8pm out of the goal and booked 8pm."""
    job = {"id": "j1", "goal": "Book dinner at Earls for 8pm",
           "status": "needs_user", "result": "which location did you want?",
           "params": json.dumps({"authorized": True,
                                 "approved_scope": "Task: book dinner at 8pm.",
                                 "corrections": {"time": "6"}})}
    _pb(monkeypatch, [job])
    out = _bare()._amend("j1", {"location": "Park Royal"},
                         owner_text="the Park Royal one")
    assert out == "resumed:j1"
    scope = json.loads(job["params"])["approved_scope"]
    assert "time: 6" in scope
    assert "override the task wording" in scope


def test_a_correction_survives_the_remembered_answer_path_too(monkeypatch):
    job = {"id": "j1", "goal": "Book dinner at Earls for 8pm",
           "status": "needs_user", "result": "I need your phone number",
           "params": json.dumps({"approved_scope": "Task: book dinner at 8pm.",
                                 "corrections": {"time": "6"}})}
    _pb(monkeypatch, [job])
    out = _bare()._resume_stuck({"phone_number": "604-555-0101"},
                                owner_text="my number is 604-555-0101")
    assert out == "resumed:j1"
    assert "time: 6" in json.loads(job["params"])["approved_scope"]


def test_a_refused_resume_is_never_reported_as_resumed(monkeypatch):
    """_requeue fired the PATCH and returned the id whatever came back, so a
    409 still reported the job as resumed and her reply said it was moving."""
    job = {"id": "j1", "goal": "Book the table", "status": "needs_user",
           "result": "I need your phone number", "params": "{}"}
    _pb(monkeypatch, [job], refuse={"j1"})
    assert _bare()._resume_stuck({"phone_number": "604-555-0101"},
                                 owner_text="604-555-0101") is None
    assert job["status"] == "needs_user"


# --------------------------------------------------------- the numbered menu

def test_the_numbered_item_he_picks_is_the_one_she_can_reach(monkeypatch):
    """A call-off menu lists blocked work, but the positional pick was only
    ever checked against awaiting_confirm — so picking the parked email
    resolved to nothing and the dinner died in its place."""
    _pb(monkeypatch, [
        {"id": "dinner", "goal": "book dinner", "status": "awaiting_confirm",
         "params": "{}"},
        {"id": "email", "goal": "email mark", "status": "needs_user",
         "result": "", "params": "{}"}])
    c = _bare()
    menu = c._which_one(cancel=True)
    assert "1) book dinner" in menu and "2) email mark" in menu
    assert c._choice_from_position("the second one") == "email"
    assert c._choice_from_position("the first one") == "dinner"


def test_an_hour_old_cancel_menu_cannot_answer_a_later_yes(monkeypatch):
    """_offered/_offered_cancel were never cleared, so "yeah do it all" to a
    much later "want me to lock in Earls for 7?" resolved against the stale
    CALL-OFF list and scrapped every open job in answer to a yes."""
    jobs = _pb(monkeypatch, _two_held())
    c = _spoken(monkeypatch, {"intent": "confirm", "pending_id": None,
                              "pending_ids": [], "changes": None,
                              "reply": "On it."})
    c._which_one(cancel=True)
    c._offered_at -= 3600
    c.say("+15550001", "Want me to lock in Earls for 7?")
    c.on_reply("+15550001", "yeah do it all")
    assert all(j["status"] == "awaiting_confirm" for j in jobs), jobs


# ------------------------------------------------------------------- values

def test_a_code_he_typed_with_a_space_still_counts_as_his():
    """He texted "code is 428 913", the model tidied it to "428913", the
    literal substring test failed, and she asked for it again. And again."""
    assert Conversation._drop_unquoted_codes(
        {"verification_code": "428913"}, "code is 428 913") \
        == {"verification_code": "428913"}
    assert Conversation._drop_unquoted_codes(
        {"verification_code": "7G4K9P"}, "it's 7g4k9p") \
        == {"verification_code": "7G4K9P"}


def test_a_code_he_never_typed_is_still_refused():
    assert Conversation._drop_unquoted_codes(
        {"verification_code": "6"}, "I told you to make it 6 dammit") == {}
    assert Conversation._drop_unquoted_codes(
        {"verification_code": "123456"}, "just sent it, check your messages") == {}


def test_a_postal_code_is_not_a_secret():
    assert Conversation._drop_unquoted_codes(
        {"postal_code": "V6B1A1"}, "my postal code is v6b 1a1") \
        == {"postal_code": "V6B1A1"}
    assert Conversation._drop_unquoted_codes(
        {"area_code": "604"}, "604") == {"area_code": "604"}


# -------------------------------------------------------- the offline lane

def test_no_worries_is_not_a_cancellation(monkeypatch):
    """This fallback runs on ANY malformed model reply, not just an outage.
    A bare \\bno\\b inside a pleasantry cancelled his only held booking and
    closed the promise behind it."""
    _pb(monkeypatch, [{"id": "dinner", "goal": "Book dinner at Earls",
                       "status": "awaiting_confirm", "params": "{}"}])
    c = _bare()
    assert c._classify("+15550001", "no worries, thanks")["intent"] == "chat"
    assert c._classify("+15550001", "no rush")["intent"] == "chat"
    assert c._classify("+15550001", "i don't know")["intent"] == "chat"
    # A real refusal still is one.
    assert c._classify("+15550001", "no")["intent"] == "decline"
    assert c._classify("+15550001", "forget it")["intent"] == "decline"
