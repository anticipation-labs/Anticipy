"""The done-text carries the picture, or it says nothing about one.

`overnight/stranger_gate.py` leg 8 asks one question: can the outgoing text
carry Twilio's `MediaUrl` at all. THAT QUESTION CAN BE ANSWERED IN ONE LINE
WHILE SHIPPING NOTHING, and this file exists because of it.

`brain/worker.py` always builds a `Conversation` (worker.py, the
`Conversation(anticipy, transport=TwilioTransport(voice) ...)` line), so the
done-text reaches Twilio like this:

    worker -> Anticipy.notify_owner -> Conversation.reach_out
           -> Conversation.say -> TwilioTransport.send -> VoiceArm.text

The direct `self.voice.text(...)` inside `notify_owner` is the fallback branch
the worker does not take. Widening `VoiceArm.text` alone therefore turns leg 8
green and leaves a product where no photo is ever attached. Half of the checks
below are about the OTHER FOUR HOPS, and one of them reads brain/ as a syntax
tree so that a comment saying the chain is wired cannot answer for the chain.

THE FLOORS, from docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md:

* THE WORDS GO OUT REGARDLESS. No picture, a share door that 500s, a timeout,
  a media rejection from Twilio — the confirmation still arrives. A text that
  vanishes because a screenshot failed is strictly worse than today.
* NOBODY DOWNSTREAM PICKS THE PICTURE. The browser model deposits exactly one
  evidence id at the moment it declares the effect verified-done. Zero ids is
  no photo; MORE than one is also no photo. Breaking the tie by rule would be
  a pattern deciding what a picture MEANS (HARNESS-LAWS Law 1) and would hide
  the depositor's bug forever.
* A NON-`+1` DESTINATION GETS THE PLAIN TEXT. Twilio documents MMS as
  US/Canada on standard long codes and nobody in this repo has measured what
  a `MediaUrl` to +44 actually does. Stranger-gate leg 3 passes, so foreign
  strangers really do reach production; they get today's behaviour rather
  than an experiment run on their live week.
* A MESSAGE TWILIO ACCEPTED IS NEVER SENT TWICE. `VoiceArm._result` raises
  `SendFailed` both for a non-ok HTTP status AND for a 201 whose body carries
  a dead status or an error_code. Only the first is safe to resend, so the
  retry hangs off the RESPONSE, never off the exception.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import evidence as ev            # noqa: E402
from brain import voice_arm as va           # noqa: E402
from brain.anticipy_core import Anticipy    # noqa: E402
from brain.conversation import (            # noqa: E402
    Conversation, MockTransport, TwilioTransport,
)

BRAIN = ROOT / "brain"
MEDIA = "media"
URL = "https://backend.example/api/files/evidence/rec1234567890abc/shot_ab12cd34ef.jpg"
OTHER = "https://backend.example/api/files/evidence/rec0000000000xyz/other_zz99.jpg"
US = "+16045550111"
UK = "+442079460958"


# ---------------------------------------------------------------- the chain
#
# Read as a syntax tree, never as text. A leg of this gate was once retired by
# `# NOTE: MediaUrl is not wired yet`, and the same defect fired the other way
# and blocked a correct repair. A comment is not a node.


def _functions(path: Path) -> dict:
    tree = ast.parse(path.read_text())
    found: dict[str, list] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, []).append(node)
    return found


def _accepts_media(fn) -> bool:
    args = fn.args
    return any(a.arg == MEDIA for a in list(args.args) + list(args.kwonlyargs))


def _callee(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _media_argument(fn, callee: str):
    """The expression handed as `media` to `callee` inside `fn`, or None.

    Positional or keyword; the VALUE is returned so a caller can follow it,
    which is what separates "the parameter is passed" from "the word appears".
    """
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or _callee(node) != callee:
            continue
        for kw in node.keywords:
            if kw.arg == MEDIA:
                return kw.value
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == MEDIA:
                return arg
    return None


def _bound_to(fn, name: str):
    """Every value this local name is assigned inside `fn`."""
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    out.append(node.value)
    return out


def test_every_hop_between_the_worker_and_twilio_can_carry_a_picture():
    """The whole shipped chain, not the one function the gate leg reads.

    Each hop must ACCEPT a picture and PASS one on. A signature that accepts
    it and a body that drops it is the same product as no picture at all, and
    it is the failure this file was written to prevent.
    """
    convo = _functions(BRAIN / "conversation.py")
    arm = _functions(BRAIN / "voice_arm.py")
    core = _functions(BRAIN / "anticipy_core.py")

    text = arm["text"][0]
    assert _accepts_media(text), \
        "VoiceArm.text cannot be handed a picture, so nothing else matters"

    sends = convo["send"]
    assert len(sends) >= 2, "expected MockTransport.send and TwilioTransport.send"
    for fn in sends:
        assert _accepts_media(fn), (
            "a transport that cannot be handed a picture raises TypeError the "
            "first time one is sent, and the failure reads as a Twilio problem")
    assert any(_media_argument(fn, "text") is not None for fn in sends), \
        "TwilioTransport.send never hands the picture to the voice arm"

    say = convo["say"][0]
    assert _accepts_media(say), "Conversation.say drops the picture"
    assert _media_argument(say, "send") is not None, \
        "Conversation.say never hands the picture to the transport"

    reach = convo["reach_out"][0]
    assert _accepts_media(reach), "Conversation.reach_out drops the picture"
    assert _media_argument(reach, "say") is not None, \
        "reach_out never hands the picture to say()"

    notify = core["notify_owner"][0]
    assert _accepts_media(notify), "notify_owner drops the picture"
    assert _media_argument(notify, "reach_out") is not None, (
        "notify_owner's CONVERSATIONAL branch is the branch the worker takes; "
        "wiring only the direct voice.text fallback ships no photo at all")
    assert _media_argument(notify, "text") is not None, \
        "notify_owner's direct voice.text fallback drops the picture"


def test_the_worker_hands_the_picture_to_notify_owner():
    """The head of the chain. Nothing above it runs if the worker sends None.

    The value passed is FOLLOWED to what produced it, so a hard-coded `media=
    []` beside a comment about evidence cannot satisfy this.
    """
    worker = _functions(BRAIN / "worker.py")
    report = worker["report_finished_jobs"][0]
    handed = _media_argument(report, "notify_owner")
    assert handed is not None, (
        "the done-text send site hands notify_owner no picture, so every hop "
        "below it carries None forever")
    assert isinstance(handed, ast.Name), \
        "expected a resolved value, not a literal"
    sources = _bound_to(report, handed.id)
    assert sources, f"{handed.id} is passed but never assigned"
    assert any(isinstance(v, ast.Call)
               and _callee(v) == "picture_for_done_text" for v in sources), (
        "the picture must come from the receipt resolver, so that WHICH "
        "picture stays a question the browser model already answered")


# ------------------------------------------------------- what goes on the wire


class _Response:
    def __init__(self, payload, status=201):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _arm(monkeypatch, payload=None, statuses=(201,)):
    """A VoiceArm that believes it is deployed, with Twilio's wire recorded."""
    for name in ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_MOCK",
                 "TWILIO_API_BASE", "TWILIO_FROM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC" + "1" * 32)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "not-a-real-auth-token")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+16196584447")
    monkeypatch.setattr(va, "_rig_reason", lambda: "")
    posts: list[dict] = []
    codes = list(statuses)

    def fake_post(url, **kw):
        posts.append({"url": url, "data": dict(kw.get("data") or {})})
        status = codes[min(len(posts), len(codes)) - 1]
        body = payload if payload is not None else {"sid": "SM7", "status": "queued"}
        if status >= 400:
            body = {"code": 21620, "message": "unable to fetch the media"}
        return _Response(body, status)

    monkeypatch.setattr(va.requests, "post", fake_post)
    return va.VoiceArm(journal=lambda _line: None), posts


def test_a_picture_rides_as_twilios_own_parameter(monkeypatch):
    arm, posts = _arm(monkeypatch)
    arm.text(US, "your table is held", media=[URL])
    assert posts[-1]["data"].get("MediaUrl") == URL
    assert posts[-1]["data"]["Body"] == "your table is held"


def test_a_text_with_no_picture_posts_no_media_key_at_all(monkeypatch):
    """Not an empty one. An empty MediaUrl is a URL Twilio will try to fetch."""
    arm, posts = _arm(monkeypatch)
    arm.text(US, "your table is held")
    assert set(posts[-1]["data"]) == {"From", "To", "Body"}, posts[-1]["data"]


def test_a_foreign_number_gets_the_words_and_no_picture(monkeypatch):
    """Stranger-gate leg 3 passes, so a London stranger really does reach
    production. What Twilio does with MediaUrl to +44 is unmeasured, and the
    unmeasured outcome includes REJECTING THE WHOLE MESSAGE."""
    arm, posts = _arm(monkeypatch)
    out = arm.text(UK, "your table is held", media=[URL])
    assert "MediaUrl" not in posts[-1]["data"], \
        "an unmeasured media path was tried on a foreign stranger's week"
    assert posts[-1]["data"]["Body"] == "your table is held", \
        "the words are the floor and they did not go out"
    assert out["sid"] == "SM7"
    assert len(posts) == 1, "no retry: there was nothing to retry without"


def test_two_pictures_are_no_picture(monkeypatch):
    """A floor, not a tie-break. Picking one would be a rule deciding which
    image is the proof of what happened (Law 1) and would hide the bug."""
    arm, posts = _arm(monkeypatch)
    arm.text(US, "your table is held", media=[URL, OTHER])
    assert "MediaUrl" not in posts[-1]["data"]
    assert posts[-1]["data"]["Body"] == "your table is held"


def test_more_than_one_picture_is_said_out_loud(monkeypatch):
    said: list[str] = []
    arm, _ = _arm(monkeypatch)
    arm.journal = said.append
    arm.text(US, "your table is held", media=[URL, OTHER])
    assert any("2" in line for line in said), (
        "silently dropping a second picture hides a depositor bug forever: "
        f"{said}")


def test_a_refused_media_send_is_retried_once_without_the_picture(monkeypatch):
    """Twilio has media-specific error codes and enumerating them is the wrong
    repair: a code list rots the day Twilio adds one, and the failure mode when
    it rots is a LOST CONFIRMATION. Not-ok means Twilio queued nothing, so the
    retry cannot double-text."""
    arm, posts = _arm(monkeypatch, statuses=(400, 201))
    out = arm.text(US, "your table is held", media=[URL])
    assert len(posts) == 2, f"{len(posts)} attempts, expected exactly two"
    assert posts[0]["data"].get("MediaUrl") == URL
    assert "MediaUrl" not in posts[1]["data"], \
        "retrying with the same picture retries the same failure"
    assert posts[1]["data"]["Body"] == "your table is held", \
        "the retry has to be the SAME sentence, minus the picture"
    assert out["sid"] == "SM7", "the confirmation still went out"


def test_a_send_that_keeps_failing_raises_once_and_stops(monkeypatch):
    arm, posts = _arm(monkeypatch, statuses=(400, 400))
    with pytest.raises(va.SendFailed):
        arm.text(US, "your table is held", media=[URL])
    assert len(posts) == 2, "one retry, bounded, and then the real reason"


def test_a_message_twilio_accepted_is_never_sent_twice(monkeypatch):
    """A 201 carrying an error_code raises SendFailed and MUST NOT be resent.
    This product has a recorded incident of the same sentence going out
    repeatedly; retrying on the exception rather than on the response is how
    it comes back."""
    arm, posts = _arm(monkeypatch,
                      payload={"sid": "SM7", "status": "queued",
                               "error_code": 30008})
    with pytest.raises(va.SendFailed):
        arm.text(US, "your table is held", media=[URL])
    assert len(posts) == 1, \
        f"Twilio accepted the message and it was sent {len(posts)} times"


def test_a_plain_send_that_fails_is_not_retried(monkeypatch):
    """The retry exists to drop a picture. With no picture it would only be a
    second text on the next 5xx."""
    arm, posts = _arm(monkeypatch, statuses=(500, 201))
    with pytest.raises(va.SendFailed):
        arm.text(US, "your table is held")
    assert len(posts) == 1


# ---------------------------------------------------- the chain, actually run


def _wired(arm):
    """Exactly what brain/worker.py builds: an owner whose conversation runs
    over TwilioTransport. owner_ref/owner_id are empty so no thread rebuild
    reaches the backend."""
    owner = types.SimpleNamespace(llm=None, owner_ref="", owner_id="",
                                  owner_phone=US, voice=arm)
    owner.conversation = Conversation(owner, transport=TwilioTransport(arm))
    return owner


def test_the_shipped_chain_puts_the_picture_on_the_wire(monkeypatch):
    """THE ONE THAT MATTERS. Five hops, driven, not read.

    If this passes and `test_every_hop_...` fails, a hop is carrying the
    picture by accident. If this fails and leg 8 is green, leg 8 is certifying
    a parameter nobody passes.
    """
    arm, posts = _arm(monkeypatch)
    owner = _wired(arm)
    Anticipy.notify_owner(owner, "that's booked — here's the confirmation",
                          media=[URL])
    assert posts, "nothing reached Twilio at all"
    assert posts[-1]["data"].get("MediaUrl") == URL, (
        "the conversational branch is the branch production takes and it "
        f"dropped the picture: {posts[-1]['data']}")


def test_the_direct_fallback_carries_it_too(monkeypatch):
    """The branch the worker does not take. It is still a send path."""
    arm, posts = _arm(monkeypatch)
    owner = types.SimpleNamespace(owner_phone=US, conversation=None, voice=arm)
    Anticipy.notify_owner(owner, "that's booked", media=[URL])
    assert posts[-1]["data"].get("MediaUrl") == URL


def test_an_old_transport_that_never_heard_of_pictures_still_gets_the_text():
    """The SMS webhook and the smoke rig both define `send(self, to, body)`.
    Calling them with a keyword they have never seen is a TypeError on the one
    path that must never fail."""
    seen = []

    class Ancient:
        def send(self, to, body):
            seen.append((to, body))
            return {"to": to, "body": body}

    owner = types.SimpleNamespace(llm=None, owner_ref="", owner_id="")
    convo = Conversation(owner, transport=Ancient())
    convo.say(US, "that's booked")
    assert seen == [(US, "that's booked")]


def test_the_mock_transport_records_the_picture_without_claiming_delivery():
    rec = MockTransport().send(US, "that's booked", media=[URL])
    assert rec["media"] == [URL]
    assert rec["delivered"] is False and rec["mock"] is True


def test_the_in_app_lane_sends_no_picture_and_no_text():
    """A reply typed into the app is answered in the app. The picture is
    already reachable there through the owner's own door on the evidence
    host — it does not need a public URL to exist."""
    transport = MockTransport()
    owner = types.SimpleNamespace(llm=None, owner_ref="", owner_id="")
    convo = Conversation(owner, transport=transport)
    with convo.reply_in_app():
        out = convo.say(US, "that's booked", media=[URL])
    assert out["via"] == "in-app"
    assert transport.sent == []


# --------------------------------------------------- which picture, and whose


def _receipt(*entries):
    return json.dumps({"verified": True, "effect_key": "book:earls:1930",
                       "evidence": list(entries)})


def _yes(_owner_ref):
    return True


def test_one_evidence_id_in_the_receipt_is_the_picture(monkeypatch):
    asked = []

    def fake_post(url, **kw):
        asked.append((url, dict(kw.get("json") or {})))
        return _Response({"ok": True, "url": URL, "expires": "later"}, 200)

    monkeypatch.setattr(ev.pb, "post", fake_post)
    job = {"id": "j1", "owner_ref": "own1",
           "receipt": _receipt("url:https://earls.test/confirm",
                               "proof:booking #55",
                               "evidence:rec1234567890abc")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb") == [URL]
    assert asked == [("http://pb/evidence/share", {"id": "rec1234567890abc"})]


def test_a_receipt_naming_no_picture_is_not_an_error(monkeypatch):
    door, calls = _open_door()
    monkeypatch.setattr(ev.pb, "post", door)
    job = {"id": "j1", "receipt": _receipt("url:https://earls.test/confirm")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb") == []
    assert calls == [], "a share window was opened for a text with no picture"


def test_more_than_one_candidate_means_no_picture_and_a_loud_line(monkeypatch):
    """Two ids is a defect in the depositor, not a menu for the sender."""
    door, calls = _open_door()
    monkeypatch.setattr(ev.pb, "post", door)
    said: list[str] = []
    job = {"id": "j1", "receipt": _receipt("evidence:rec1111111111aaa",
                                           "evidence:rec2222222222bbb")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb",
                                    log=said.append) == []
    assert calls == [], "a picture was shared after refusing to choose one"
    assert any("j1" in line for line in said), (
        f"a second picture was dropped without naming the job: {said}")


def test_an_owner_who_never_said_yes_gets_no_picture(monkeypatch):
    """The switch is a FLOOR — does anything authorise attaching this picture
    — and a floor that lifts itself is not a floor. Nobody has answered means
    no."""
    door, calls = _open_door()
    monkeypatch.setattr(ev.pb, "post", door)
    job = {"id": "j1", "receipt": _receipt("evidence:rec1234567890abc")}
    assert ev.picture_for_done_text(job, lambda _ref: False,
                                    base="http://pb") == []
    assert calls == [], (
        "the owner never said yes and a photograph of their screen was put "
        "on an anonymous URL anyway")


def test_no_window_is_opened_before_the_moment_of_sending(monkeypatch):
    """A window that is open before anybody needs it is exposure bought for
    nothing. Both refusals above must cost zero share calls, which is what
    `_never_called` proves — this test names the property."""
    door, calls = _open_door()
    monkeypatch.setattr(ev.pb, "post", door)
    assert ev.picture_for_done_text({"receipt": "{}"}, _yes) == []
    assert ev.picture_for_done_text({}, _yes) == []
    assert calls == []


@pytest.mark.parametrize("door", [
    lambda url, **kw: _Response({"error": "boom"}, 500),
    lambda url, **kw: _Response({"ok": False, "reason": "that evidence is gone",
                                 "url": "", "expires": ""}, 200),
    lambda url, **kw: _Response({"ok": True, "url": ""}, 200),
])
def test_a_share_door_that_says_no_is_no_picture_not_an_exception(monkeypatch, door):
    monkeypatch.setattr(ev.pb, "post", door)
    job = {"id": "j1", "receipt": _receipt("evidence:rec1234567890abc")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb") == []


def test_a_share_door_that_never_answers_is_no_picture(monkeypatch):
    def timeout(url, **kw):
        raise OSError("timed out")

    monkeypatch.setattr(ev.pb, "post", timeout)
    # Directly, so that `picture_for_done_text`'s own outer net cannot answer
    # for this: the share call is what must degrade to "no picture".
    assert ev.open_share_window("rec1234567890abc", base="http://pb",
                                log=lambda _l: None) == ""
    job = {"id": "j1", "receipt": _receipt("evidence:rec1234567890abc")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb") == []


def test_an_unparseable_answer_is_no_picture(monkeypatch):
    class Garbage:
        ok = True
        status_code = 200

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr(ev.pb, "post", lambda url, **kw: Garbage())
    assert ev.open_share_window("rec1234567890abc", base="http://pb",
                                log=lambda _l: None) == ""
    job = {"id": "j1", "receipt": _receipt("evidence:rec1234567890abc")}
    assert ev.picture_for_done_text(job, _yes, base="http://pb") == []


@pytest.mark.parametrize("raw", ["", None, "{not json", "[]", '{"evidence": 3}',
                                 '{"evidence": ["evidence:"]}'])
def test_a_receipt_that_says_nothing_readable_names_no_picture(raw):
    assert ev.ids_in_receipt(raw) == []


def test_the_id_is_read_out_of_our_own_record_format():
    """Parsing this product's own receipt, not interpreting anybody's words.
    `evidence:` is a key beside `url:`, `proof:` and `page:`, all written by
    extension/workflow_state.js."""
    assert ev.ids_in_receipt(_receipt("url:https://earls.test/x",
                                      "title:Confirmed",
                                      "evidence:rec1234567890abc")) \
        == ["rec1234567890abc"]


def _open_door():
    """A share door that WOULD hand back a URL, and a record of every call.

    Deliberately not a fake that raises: `open_share_window` swallows every
    exception on purpose, so a raising double is swallowed too and the test
    passes no matter what the code does. Both mutations of "never open a
    window for nothing" survived a raising double and were caught only by this
    one — which is the rule about a leg that cannot fail, applied to a test.
    """
    calls = []

    def door(url, **kw):
        calls.append((url, dict(kw.get("json") or {})))
        return _Response({"ok": True, "url": URL, "expires": "later"}, 200)

    return door, calls
