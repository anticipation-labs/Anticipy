"""The phone on a worker is a cache, never continuing send authority.

These regressions remove the canonical number after the periodic refresh but
before each external effect.  Results must still reach the app; questions and
digests must remain retryable; no stale number may receive an SMS or call.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
import types

import pytest

import brain.worker as W
from brain.anticipy_core import Anticipy
from brain.conversation import Conversation, TwilioTransport
from brain.memory import Memory


FIXTURES = Path(__file__).parent / "fixtures" / "real_world_action_scenarios.json"


class Resp:
    def __init__(self, payload=None, ok=True):
        self.ok = ok
        self.status_code = 200 if ok else 409
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("write refused")


class Transport:
    def __init__(self):
        self.effects = []

    @property
    def attempts(self):
        return len(self.effects)

    def text(self, phone, message, **kwargs):
        self.effects.append(("sms", phone, message))
        return {"sid": "SM-REVOCATION"}

    def call(self, phone, message):
        self.effects.append(("call", phone, message))
        return {"sid": "CA-REVOCATION"}


class Composer:
    def __init__(self):
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        prompt = " ".join(str(value) for value in args)
        text = ("Your Chrome closed, so this stopped partway. I'll pick it "
                "up when Chrome is open again."
                if "browser" in prompt.lower() else
                "The team sync is arranged.")
        return types.SimpleNamespace(text=text)


@pytest.fixture(autouse=True)
def clean_worker_state():
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    W.DIGEST_PENDING = None
    yield
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    W.DIGEST_PENDING = None


def event_backend(monkeypatch, jobs):
    events = []
    patches = []

    def fake_get(url, **kwargs):
        if "/collections/events/" in url:
            filt = str((kwargs.get("params") or {}).get("filter") or "")
            return Resp({
                "items": [
                    dict(row) for row in events
                    if row.get("external_event_id")
                    and str(row["external_event_id"]) in filt
                ]
            })
        return Resp({"items": [dict(row) for row in jobs], "totalPages": 1})

    def fake_post(url, **kwargs):
        row = dict(kwargs.get("json") or {})
        durable_id = str(row.get("external_event_id") or "")
        if durable_id and any(
                existing.get("external_event_id") == durable_id
                for existing in events):
            return Resp(ok=False)
        if "/collections/events/" in url:
            events.append(row)
        return Resp()

    def fake_patch(*args, **kwargs):
        patches.append(dict(kwargs.get("json") or {}))
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)
    monkeypatch.setattr(W.pb, "patch", fake_patch)
    return events, patches


def assistant(phone="+16045550101"):
    transport = Transport()
    composer = Composer()
    instance = Anticipy(
        memory=Memory(":memory:"), llm=composer,
        backend_url="http://revocation.test", voice=transport,
        owner_phone=phone, owner_id="legacy-owner", owner_ref="account-one",
    )
    return instance, transport, composer


def remove_phone_before_effect(monkeypatch, instance):
    reads = []

    def canonical(owner_ref=""):
        reads.append(owner_ref)
        return ""

    monkeypatch.setattr(W, "fetch_owner_phone", canonical)
    W.install_canonical_notification_guard(instance)
    return reads


def daytime(monkeypatch):
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)


def test_finished_report_uses_app_but_never_claims_the_removed_phone(monkeypatch):
    instance, transport, composer = assistant()
    reads = remove_phone_before_effect(monkeypatch, instance)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    job = {
        "id": "finished-after-phone-removal",
        "goal": "schedule the team sync",
        "result": "the team sync is arranged",
        "status": "done", "lane": "", "params": "{}",
        "owner": "legacy-owner", "owner_ref": "account-one",
        "updated": now,
    }
    events, _ = event_backend(monkeypatch, [job])

    W.report_finished_jobs(instance)

    assert reads == ["account-one"]
    assert instance.owner_phone == ""
    assert transport.effects == []
    assert [row["external_event_id"] for row in events
            if row.get("kind") == "anticipy_says"] == [
                "job-result:finished-after-phone-removal"]
    assert not any("sms_attempted" in str(row.get("external_event_id"))
                   for row in events), "a removed cached route must not earn a send claim"
    assert any(row.get("decision") == "sms_skipped" for row in events)
    assert composer.calls == 1


def test_parked_question_rechecks_after_refresh_and_stays_retryable(monkeypatch):
    instance, transport, _ = assistant()
    reads = remove_phone_before_effect(monkeypatch, instance)
    now = time.time()
    instance._pending_ask = ("Which time works for the team sync?", now - 30, 0.0)
    monkeypatch.setattr(W, "MEETING_ARMED", False)
    monkeypatch.setattr(W, "LAST_HEARD_AT", 0.0)
    daytime(monkeypatch)
    monkeypatch.setattr(W, "uninvited_sent_today", lambda *a, **k: 0)
    monkeypatch.setattr(W, "already_said", lambda *a, **k: False)
    monkeypatch.setattr(W, "post_event", lambda *a, **k: pytest.fail(
        "an unsent question must not be recorded as asked"))

    W.maybe_ask_parked(instance, now=now)

    assert reads == ["account-one"]
    assert transport.effects == []
    assert instance.owner_phone == ""
    assert instance._pending_ask is not None, "the question must remain retryable"


def test_digest_rechecks_after_refresh_and_keeps_its_cards(monkeypatch):
    instance, transport, _ = assistant()
    reads = remove_phone_before_effect(monkeypatch, instance)
    now = time.time()
    entries = [("job-sync", "schedule the team sync")]
    instance._meeting_held = list(entries)
    W.DIGEST_PENDING = ("One thing is ready from your meeting.",
                        now - 30, 0.0, list(entries))
    monkeypatch.setattr(W, "MEETING_ARMED", False)
    monkeypatch.setattr(W, "LAST_HEARD_AT", 0.0)
    monkeypatch.setattr(W, "SPEAK_ONCE", lambda *a, **k: True)

    W.deliver_pending_digest(instance, now=now)

    assert reads == ["account-one"]
    assert transport.effects == []
    assert instance.owner_phone == ""
    assert W.DIGEST_PENDING is not None, "a removed phone is retryable, not delivered"
    assert instance._meeting_held == entries, "unsent digest cards must remain"


def test_guard_blocks_calls_as_well_as_sms_when_canonical_state_is_unknown(
        monkeypatch):
    instance, transport, _ = assistant()
    monkeypatch.setattr(W, "fetch_owner_phone", lambda owner_ref="": None)
    W.install_canonical_notification_guard(instance)

    assert instance.notify_owner("urgent update", channel="call") is None
    assert instance.owner_phone == ""
    assert transport.effects == []


def test_inbound_reply_rechecks_after_owner_match_and_keeps_the_app_copy(
        monkeypatch):
    """Removal after inbound authorization cannot leak one last SMS.

    ``handle_inbound`` first compares the event's sender with the worker cache.
    The canonical profile changes inside ``on_reply`` below: deliberately after
    that comparison and immediately before ``Conversation.say`` reaches the
    Twilio transport. The reply remains useful in the app, but the old phone is
    no longer an authorized effect destination.
    """
    old_phone = "+16045550101"
    instance, _, _ = assistant(phone=old_phone)
    arm = Transport()
    canonical = {"phone": old_phone}
    reads = []

    def fetch(owner_ref=""):
        reads.append(owner_ref)
        return canonical["phone"]

    monkeypatch.setattr(W, "fetch_owner_phone", fetch)
    transport = TwilioTransport(
        arm,
        before_send=lambda destination: W.canonical_phone_allows_effect(
            instance, destination),
    )
    convo = Conversation(instance, transport=transport, llm=None)
    instance.conversation = convo

    def reply(phone, _text):
        # The webhook was legitimately routed while this was the owner's
        # number. They remove it before the worker's eventual reply leaves.
        canonical["phone"] = ""
        sent = convo.say(phone, "The team sync is arranged.")
        assert sent is None
        return {
            "intent": "chat", "pending_id": None, "changes": None,
            "acted": None, "reply": "The team sync is arranged.",
        }

    convo.on_reply = reply
    marks = []
    app_events = []
    monkeypatch.setattr(
        W, "mark_processed",
        lambda event_id, decision, **_kwargs: marks.append(
            (event_id, decision)) or True)
    monkeypatch.setattr(
        W, "post_event",
        lambda kind, text, **kwargs: app_events.append(
            {"kind": kind, "text": text, **kwargs}))

    outcome = W.handle_inbound({
        "id": "sms-reply-after-removal", "kind": "sms_reply",
        "text": "yes", "goal": old_phone,
    }, convo, instance)

    assert outcome == "chat", "the cached owner match must reach the send boundary"
    assert reads == ["account-one"]
    assert instance.owner_phone == ""
    assert arm.effects == [], "the removed number must receive no final reply"
    assert ("sms-reply-after-removal", "processing") in marks
    assert ("sms-reply-after-removal", "chat") in marks
    assert app_events == [{
        "kind": "anticipy_text", "text": "The team sync is arranged.",
    }], "the channel failure must not discard the reply from the app"


def test_in_app_reply_suppression_never_consults_or_touches_twilio(monkeypatch):
    """The transport guard is external-effect-only, never an app dependency."""
    instance, _, _ = assistant(phone="")
    arm = Transport()

    def should_not_run(_destination):
        pytest.fail("an in-app reply must stop before the Twilio effect guard")

    convo = Conversation(
        instance,
        transport=TwilioTransport(arm, before_send=should_not_run),
        llm=None,
    )
    instance.conversation = convo

    def reply(phone, _text):
        sent = convo.say(phone, "I kept that answer in the app.")
        assert sent.get("via") == "in-app"
        return {
            "intent": "chat", "pending_id": None, "changes": None,
            "acted": None, "reply": "I kept that answer in the app.",
        }

    convo.on_reply = reply
    app_events = []
    monkeypatch.setattr(W, "mark_processed", lambda *_a, **_k: True)
    monkeypatch.setattr(
        W, "post_event",
        lambda kind, text, **kwargs: app_events.append((kind, text)))

    outcome = W.handle_inbound({
        "id": "app-reply-no-phone", "kind": "app_reply",
        "text": "yes", "goal": "",
    }, convo, instance)

    assert outcome == "chat"
    assert arm.effects == []
    assert app_events == [("anticipy_text", "I kept that answer in the app.")]


def test_browser_offline_fixture_is_app_first_without_phone_or_completion(
        monkeypatch):
    data = json.loads(FIXTURES.read_text())
    case = next(row for row in data["browser_cases"]
                if row["id"] == "browser_offline_never_completes")
    instance, transport, _ = assistant(phone="")
    reads = remove_phone_before_effect(monkeypatch, instance)
    job = {
        "id": case["id"], "goal": case["goal"],
        "result": case["map_error"], "status": "running",
        "lane": "", "params": "{}", "owner": "legacy-owner",
        "owner_ref": "account-one", "updated": "2026-08-31 10:00:00",
    }
    events, patches = event_backend(monkeypatch, [job])
    daytime(monkeypatch)
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)

    W.report_stalled_work(instance)

    notices = [row for row in events
               if row.get("kind") == "anticipy_says"
               and row.get("decision") == "stalled"]
    assert reads == ["account-one"]
    assert transport.effects == []
    assert len(notices) == 1
    assert notices[0]["external_event_id"] == (
        "job-stalled:browser_offline_never_completes:running")
    assert "Chrome" in notices[0]["text"]
    assert job["status"] == "running" and patches == [], (
        "a notice reports the stalled state; it must not invent completion")


def test_stall_notices_for_duplicate_goals_keep_both_exact_job_ids(monkeypatch):
    instance, transport, _ = assistant(phone="")
    remove_phone_before_effect(monkeypatch, instance)
    common = {
        "goal": "schedule the team sync", "status": "queued", "lane": "",
        "params": "{}", "owner": "legacy-owner", "owner_ref": "account-one",
        "updated": "2026-08-31 10:00:00",
    }
    jobs = [dict(common, id="same-goal-a"), dict(common, id="same-goal-b")]
    events, _ = event_backend(monkeypatch, jobs)
    daytime(monkeypatch)
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)

    W.report_stalled_work(instance)

    ids = {row.get("external_event_id") for row in events
           if row.get("kind") == "anticipy_says"}
    assert ids == {
        "job-stalled:same-goal-a:queued",
        "job-stalled:same-goal-b:queued",
    }
    assert transport.effects == []
