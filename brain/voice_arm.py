"""Anticipy's voice arm: the one place in the brain that talks to Twilio.

Thin REST wrapper, no SDK: SMS via Messages, real phone calls via Calls with
inline TwiML so she speaks in her own voice. Credentials come from the
environment; nothing is hardcoded.

OUTBOUND AUTHENTICATES WITH AN API KEY; INBOUND CANNOT. Outbound prefers
TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET — scoped, revocable, rotatable —
and falls back to TWILIO_AUTH_TOKEN (see `rest_credential`). Twilio signs
INBOUND webhooks with the account auth token and offers no API-key
equivalent, so backend/pb_hooks/sms.pb.js validates against TWILIO_AUTH_TOKEN
and always will. The two halves use different credentials on purpose; the
auth token is not leftovers to be tidied away.

Two guarantees live here rather than in the callers, because a caller that
forgets one of them places a real call to a real human being:

1. A CALL IS A `CallPlan` OR IT DOES NOT HAPPEN. MVP spec §08 classes voice
   calls as "Speak: always ask, script shown before dialing", and §06 adds
   "outbound to businesses only ... never calls people in the user's life
   unless the user explicitly asked for that exact call". Those are properties
   of the request, so they are fields on the request, and `call()` refuses
   anything that cannot show them. Refusals raise; there is no quiet no-op,
   because a swallowed refusal is indistinguishable from a placed call.
2. A RIG NEVER REACHES A REAL PERSON. On 2026-08-19 a laptop worker that had
   inherited the production Twilio credentials repointed the owner's live
   number at http://127.0.0.1:8090 (see brain/worker.py:342-366). The same
   inherited environment can just as easily TEXT him from a test. Credentials
   in the environment are therefore not permission to send: see `_rig_reason`.

Failures raise instead of returning. Every caller in the brain treats a
falsy/raising send as "not delivered" (brain/anticipy_core.py:2124-2155,
brain/worker.py:250), so raising is what keeps a failed send from being
recorded as a message the owner was told.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Mapping, Optional
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

import requests

from .evidence import one_url

# What no Twilio account can work without, whatever it authenticates WITH.
ACCOUNT_ENV = ("TWILIO_ACCOUNT_SID", "TWILIO_PHONE_NUMBER")
# The preferred outbound credential. See `rest_credential`.
API_KEY_ENV = ("TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET")
# Kept, and kept named, because the auth token is still (a) the fallback
# outbound credential and (b) the ONLY thing on earth that can validate an
# INBOUND webhook signature (backend/pb_hooks/sms.pb.js:77). "Finishing" the
# API-key migration by deleting it silently 403s every text he sends.
REQUIRED_ENV = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER")

# Twilio's test credentials accept a create request, answer with a canned
# success and SEND NOTHING — the only way to exercise this file against the
# real api.twilio.com without a handset ringing. This is the owner's TEST
# Account SID, read off his console; the matching test auth token lives beside
# it there and is deliberately not in this repo.
TEST_ACCOUNT_SID = "ACef51de468dd2315a008b980d94d36818"
# Twilio rejects every other From under test credentials.
TEST_FROM_NUMBER = "+15005550006"

DEFAULT_VOICE = "Polly.Joanna"

# MVP spec §06: every call "discloses itself where law requires". A machine that
# speaks into a two-party-consent state has to disclose, and deciding that per
# call is a decision that will one day be got wrong, so it is not a decision:
# it is the first sentence of every script, prepended here where it cannot be
# edited out by a caller or by a model writing the script.
DISCLOSURE = ("Hi — this is an automated assistant calling on behalf of "
              "{on_behalf_of}. This call may be recorded.")

# Twilio accepts a create request and then reports the outcome in `status`. A
# 201 whose status is one of these is a FAILED send wearing a success code, and
# it used to be returned to the caller as {"sid": ..., "status": "failed"} —
# truthy, therefore "delivered".
DEAD_STATES = ("failed", "undelivered", "canceled", "cancelled")

# ...and the inverse trap. Twilio answers a create request with "queued" or
# "accepted", which means IT took the request, not that a handset saw it.
# Delivery is asynchronous and is reported later on a StatusCallback this
# deployment does not run, so the honest word for a fresh send is "accepted".
# `text()`/`call()` therefore return `delivered` and it is False for a queued
# message: nothing in the brain may print the word "sent" off a create call.
DELIVERED_STATES = ("sent", "delivered", "received", "read",
                    "in-progress", "completed", "answered")

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
VOICE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


class VoiceNotConfigured(RuntimeError):
    """Twilio credentials are absent. Names exactly which ones."""


class SendFailed(RuntimeError):
    """A text or call did not go out. Never returned as a value."""


class CallRefused(RuntimeError):
    """The call did not satisfy MVP §06/§08 and was not dialed."""


def api_base(env: Optional[Mapping[str, str]] = None) -> str:
    """Twilio's REST root, overridable so an outbound send can be PROVED.

    proof/twilio_outbound_proof.py points TWILIO_API_BASE at a loopback
    recorder and then asserts the URL, the Authorization header and every
    parameter of the request this file builds — a real send, executed by the
    real code, that no carrier ever hears about. Precedent, same reason:
    backend/pb_hooks/password_reset.pb.js:104.
    """
    env = os.environ if env is None else env
    return (env.get("TWILIO_API_BASE") or "https://api.twilio.com").rstrip("/")


@dataclass(frozen=True)
class Credential:
    """One HTTP basic-auth pair for Twilio's REST API, and what it is."""

    user: str = ""
    secret: str = ""
    describes: str = ""     # safe to log: never contains the secret
    complaint: str = ""     # "" when nothing about this is misconfigured

    def basic(self) -> tuple[str, str]:
        return (self.user, self.secret)

    def __bool__(self) -> bool:
        return bool(self.user and self.secret)


def rest_credential(env: Optional[Mapping[str, str]] = None) -> Credential:
    """The credential every OUTBOUND Twilio request authenticates with.

    PREFERS an API key, in the owner's console's own words: "API keys can be
    limited to specific products and permissions and easily rotated or revoked.
    The auth token grants full account access, exposing your entire account if
    it's compromised." An API key does not replace the account — it
    authenticates AS it — so TWILIO_ACCOUNT_SID stays in the URL path either
    way and only the basic-auth username/password change.

    THE AUTH TOKEN IS NOT DEAD, AND MUST NOT BE DELETED. Twilio signs inbound
    webhooks with the account auth token and with nothing else; there is no
    API-key equivalent, so backend/pb_hooks/sms.pb.js keeps reading
    TWILIO_AUTH_TOKEN forever. Outbound may move; the signature check may not.
    Auth token also stays as the outbound FALLBACK so nothing breaks in the
    window before a key is minted.

    A half-configured key (one of the two names set) falls back and SAYS SO
    rather than refusing: a typo in one env var must not stop her texting, and
    it must not quietly promote the full-access token behind anyone's back.
    """
    env = os.environ if env is None else env
    key_sid = (env.get("TWILIO_API_KEY_SID") or "").strip()
    key_secret = (env.get("TWILIO_API_KEY_SECRET") or "").strip()
    account = (env.get("TWILIO_ACCOUNT_SID") or "").strip()
    token = (env.get("TWILIO_AUTH_TOKEN") or "").strip()
    half = ""
    if key_sid and key_secret:
        # The key SID is public (it appears in Twilio's own console listing);
        # the secret is what must never be logged, so only the SID is described.
        return Credential(key_sid, key_secret, f"API key {key_sid}")
    if key_sid or key_secret:
        missing = "TWILIO_API_KEY_SECRET" if key_sid else "TWILIO_API_KEY_SID"
        half = (f"{missing} is unset while its other half is set, so outbound "
                f"fell back to the full-account auth token. Set both or neither.")
    if account and token:
        return Credential(account, token,
                          "account auth token (full-account access)", half)
    return Credential(complaint=half or (
        "no Twilio credential: set TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET "
        "(preferred — scoped and revocable) or TWILIO_AUTH_TOKEN"))


# The two names that muzzle every outbound arm. TWILIO_MOCK is the original
# and stays honoured forever (it sits in .env.local and in proof/local_rig.sh);
# ANTICIPY_SMS_MOCK is the provider-neutral spelling added with the Sendblue
# arm, because a switch named after one vendor reads as "Twilio only" to the
# operator who has just switched vendors — and that operator is texting a real
# person from a laptop the moment the muzzle he set is not the one being read.
MUZZLE_ENV = ("ANTICIPY_SMS_MOCK", "TWILIO_MOCK")


def muzzle_flag(env: Optional[Mapping[str, str]] = None) -> str:
    """The NAME of the muzzle that is set on this process, or "" if none is.

    Named rather than boolean so a refusal can say which switch it obeyed:
    "TWILIO_MOCK is set" sends the operator to the right variable, and a
    refusal that cannot name its reason is the kind that gets worked around.
    """
    env = os.environ if env is None else env
    for name in MUZZLE_ENV:
        if (env.get(name) or "").strip().lower() in ("1", "true", "yes", "on"):
            return name
    return ""


def muzzled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Has this deployment been told to send nothing? TWILIO_MOCK or
    ANTICIPY_SMS_MOCK — either is enough, and both arms read the same answer.

    The switch is not new: TWILIO_MOCK=true is what silenced two services that
    were texting the owner test traffic, and it sits in .env.local today. What
    was new, and dangerous, is that NOTHING IN THE TREE READ IT. Anyone setting
    it to stop a process from texting got real texts and a false sense of
    safety, which is the worst possible outcome for a switch whose entire
    purpose is to be trusted. It is read in exactly two places, both here: the
    worker's live/mock decision (`has_credentials`, and its twin in
    brain/sendblue_arm.py) and the send guard (`_rig_reason`), so a muzzled
    process cannot text even if a caller builds an arm by hand.
    """
    return bool(muzzle_flag(env))


def has_credentials(env: Optional[Mapping[str, str]] = None) -> bool:
    """Can this process talk to Twilio at all? What `live_sms` means."""
    env = os.environ if env is None else env
    return bool(not muzzled(env)
                and all(env.get(name) for name in ACCOUNT_ENV)
                and rest_credential(env))


@dataclass(frozen=True)
class CallPlan:
    """Everything that has to be true and SHOWN before Anticipy dials.

    `approved_by_owner` is not a courtesy flag. It is the record that this
    exact script, goal and number were put in front of the owner and he said
    go — §08's "always ask, script shown before dialing". Whoever sets it is
    asserting that `approval_card()` (or its equivalent in the feed) was
    displayed first, so the field is named after the human act, not after a
    boolean.
    """

    to: str
    goal: str            # what a successful call returns with, in one line
    script: str          # what she actually says, minus the disclosure
    callee: str          # who is being dialed, in words: "Earls, Yaletown"
    callee_kind: str = "business"        # "business" | "person"
    approved_by_owner: bool = False
    explicitly_requested: bool = False   # he asked for THIS call, to THIS person
    on_behalf_of: str = "my owner"

    def refusal(self) -> str:
        """The reason this must not be dialed, or "" if it may be."""
        if not E164.match(str(self.to or "")):
            return f"{self.to!r} is not an E.164 number"
        if len(str(self.goal or "").strip()) < 8:
            return "no goal: MVP §06 requires every call to have one"
        if len(str(self.script or "").strip()) < 8:
            return "no script: MVP §06/§08 require one, shown before dialing"
        if not str(self.callee or "").strip():
            return ("no callee: the approval card has to name who is being "
                    "dialed, or the owner is approving a phone number")
        if self.callee_kind not in ("business", "person"):
            return f"callee_kind {self.callee_kind!r} is neither business nor person"
        if not self.approved_by_owner:
            return ("not approved by the owner — MVP §08 classes a voice call "
                    "as Speak: always ask, script shown before dialing")
        # §06, stated as a rule instead of a hope: the only way to dial a human
        # being is for the owner to have asked for that one call. A planner that
        # merely believes a number belongs to a business cannot get here.
        if self.callee_kind == "person" and not self.explicitly_requested:
            return ("MVP §06: outbound calls go to BUSINESSES only. Calling a "
                    "person needs an explicit request for that exact call")
        return ""

    def spoken(self) -> str:
        """The disclosure, then the script. In that order, always."""
        return (DISCLOSURE.format(on_behalf_of=self.on_behalf_of or "my owner")
                + " " + str(self.script).strip())

    def approval_card(self) -> str:
        """The text to show the owner BEFORE dialing. §08's "script shown"."""
        return (f"Call {self.callee} at {self.to}?\n"
                f"Goal: {self.goal}\n"
                f"I'll say: {self.spoken()}")


def twiml_for(plan: CallPlan, voice: str = DEFAULT_VOICE) -> str:
    """Pure, so what she will say is testable without dialing anything."""
    if not VOICE_NAME.match(str(voice or "")):
        # The voice name lands inside an XML attribute. An allowlist is shorter
        # than reasoning about quoting, and there is no legitimate Twilio voice
        # outside it.
        raise CallRefused(f"{voice!r} is not a Twilio voice name")
    return (f'<Response><Say voice="{voice}">'
            f'{escape(plan.spoken())}</Say></Response>')


def _cannot_reach_a_phone() -> str:
    """Why this configuration is PHYSICALLY unable to ring a handset, or "".

    This is not a hole in the rig guard below — it is how the outbound path is
    proved correct without a send, which is the only way to prove it at all
    when the one number available to test with belongs to the owner:

    - TWILIO_API_BASE on loopback: proof/twilio_outbound_proof.py records the
      request this file builds and asserts the URL, the auth header and every
      parameter. Twilio never hears about it.
    - the account IS Twilio's test account: test credentials accept the
      request, answer with a canned SID and deliver nothing, ever.

    Both are configurations a deployed worker cannot have by accident: the
    production Account SID is not the test one, and nothing sets
    TWILIO_API_BASE in any deploy.
    """
    host = (urlsplit(api_base()).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return f"TWILIO_API_BASE points at a recorder on {host}"
    if (os.environ.get("TWILIO_ACCOUNT_SID") or "").strip() == TEST_ACCOUNT_SID:
        return "TWILIO_ACCOUNT_SID is Twilio's TEST account, which sends nothing"
    return ""


def _rig_reason(cannot_reach_a_phone: Callable[[], str] = _cannot_reach_a_phone) -> str:
    """Why this process must not reach a real phone, or "" if it may.

    Credentials in the environment are not permission. A shell export outlives
    the terminal it was typed in, and the configurations below are the ones
    that are demonstrably NOT a worker that may text the owner:

    - TWILIO_MOCK / ANTICIPY_SMS_MOCK says so out loud. First, and ahead of
      every exemption, so that setting it is always enough (see `muzzled`).
    - pytest is running. A test that texts the owner is a bug with a receipt.
    - the backend is on this machine. proof/local_rig.sh exists precisely
      because a laptop worker holding production credentials did real damage on
      2026-08-19; it defends itself by unsetting TWILIO_*, which is a
      convention, and a convention is not an enforcement.

    ANTICIPY_PB's default matches brain/worker.py:38, so an unset backend URL
    is a local rig here for the same reason it is one there.

    `cannot_reach_a_phone` is the ONE thing that differs between arms: the
    physical-impossibility exemption reads the arm's OWN wire (TWILIO_API_BASE
    here, SENDBLUE_API_BASE in brain/sendblue_arm.py). It is a parameter rather
    than a shared check so that pointing one vendor's base at loopback can
    never exempt a send that goes to the other vendor's real API. Everything
    else — the muzzle, pytest, the local backend, and their ORDER — is this one
    function, read by both arms, so there is exactly one place to forget it.
    """
    flag = muzzle_flag()
    if flag:
        return f"{flag} is set on this process"
    if cannot_reach_a_phone():
        return ""
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return "pytest is running in this process"
    host = (urlsplit(os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")).hostname
            or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0") or host.endswith(".local"):
        return f"the backend is local (ANTICIPY_PB host {host!r})"
    return ""


class VoiceArm:
    """Twilio's Messages and Calls APIs, and nothing else.

    `journal` receives one line for every attempt, refusal and outcome. It
    defaults to stdout so no rung of the ladder is ever silent (MVP §09);
    wiring it to the feed is what satisfies §06's "drops the transcript in the
    feed" for the call record itself.
    """

    def __init__(self, journal: Optional[Callable[[str], None]] = None):
        # os.environ[...] here raised a bare KeyError naming one variable, which
        # is a stack trace instead of an answer when a deploy is missing two.
        missing = [f"{name} unset" for name in ACCOUNT_ENV
                   if not os.environ.get(name)]
        credential = rest_credential()
        if not credential:
            # Named as a credential, not as a variable, because there are now
            # two ways to satisfy it and a message naming one of them sends
            # whoever reads it looking for the wrong thing.
            missing.append(credential.complaint)
        if missing:
            raise VoiceNotConfigured(
                "Twilio is not configured on this process: "
                + "; ".join(missing) + ". She cannot text or call.")
        self.journal = journal
        self.sid = os.environ["TWILIO_ACCOUNT_SID"]
        self.from_number = os.environ["TWILIO_PHONE_NUMBER"]
        # The pair `requests` puts in the Authorization header. The Account SID
        # stays in the path either way: an API key authenticates AS the account.
        self.auth = credential.basic()
        self.credential = credential.describes
        if credential.complaint:
            self._log(f"TWILIO CREDENTIAL: {credential.complaint}")
        self.base = f"{api_base()}/2010-04-01/Accounts/{self.sid}"
        if self.sid == TEST_ACCOUNT_SID:
            # Otherwise a deploy on test credentials looks perfectly healthy —
            # 201s, real SIDs, a queued status — and delivers nothing, forever.
            self._log("TWILIO TEST CREDENTIALS are in use on this process: "
                      "Twilio will accept every message and call and DELIVER "
                      "NOTHING. This is the proof mode, not a deployment.")

    # -------------------------------------------------------------- plumbing

    def _log(self, line: str) -> None:
        (self.journal or print)(line)

    def _guard(self, what: str, to: str) -> None:
        reason = _rig_reason()
        if reason:
            # Loud, and with the number it was about to reach, because the
            # failure mode this replaces was a real text to a real person.
            self._log(f"REFUSED to {what} {str(to)[:6]}… from a rig: {reason}. "
                      f"Twilio credentials in the environment are not permission.")
            raise SendFailed(f"refusing to {what} a real number: {reason}")

    def _result(self, response, what: str, to: str) -> dict:
        if not response.ok:
            # Twilio's error body carries a code and a human message and never
            # the auth token, so it is safe to surface and it is the only thing
            # that distinguishes "unverified number" from "account suspended".
            raise SendFailed(
                f"Twilio refused the {what} to {str(to)[:6]}…: "
                f"HTTP {response.status_code} {response.text[:200]}")
        try:
            out = response.json()
        except ValueError as exc:
            raise SendFailed(f"Twilio returned no JSON for the {what}: {exc}") from exc
        status = str(out.get("status") or "").lower()
        sid = str(out.get("sid") or "")
        if not sid or status in DEAD_STATES or out.get("error_code"):
            raise SendFailed(
                f"{what} to {str(to)[:6]}… did not go out: status={status or 'none'} "
                f"error={out.get('error_code')} {out.get('error_message') or ''}".strip())
        # `delivered` exists because "queued" is the honest answer to "did
        # Twilio take it?" and a dishonest answer to "did he get it?". A caller
        # that wants to record delivery has to read a field that says so.
        return {"sid": sid, "status": status,
                "delivered": status in DELIVERED_STATES}

    # ------------------------------------------------------------------ text

    def text(self, to: str, body: str, media=None) -> dict:
        """The words, and the picture if this channel can carry one.

        THE WORDS ARE THE FLOOR. `media` may be dropped for any reason — a
        destination MMS does not reach, more than one candidate, a URL Twilio
        would refuse — and every one of those still sends the sentence. A
        confirmation that vanishes because a screenshot failed is strictly
        worse than the confirmation with no screenshot that shipped yesterday.
        """
        self._guard("text", to)
        payload = {"From": self.from_number, "To": to, "Body": body}
        picture = self._picture_this_channel_can_carry(to, media)
        if picture:
            payload["MediaUrl"] = picture
        # ONE POST SITE, AND THE RETRY IS THE SAME ONE. A second authenticated
        # post for the retry would make three credential-bearing send sites in
        # this file where the reviewed design has two — Messages.json and
        # Calls.json — and
        # tests/test_twilio_auth_and_delivery.py pins that count on purpose:
        # every send must authenticate through one path somebody has read.
        # A loop keeps the credential in one place AND keeps the payload
        # visible at the post, which is what stranger-gate leg 8 reads.
        #
        # ONE RETRY, ON THE RESPONSE, NEVER ON THE EXCEPTION. Twilio has
        # media-specific error codes and enumerating them is the wrong repair:
        # a code list rots the day Twilio adds one, and the failure mode when
        # it rots is a LOST CONFIRMATION. Not-ok means Twilio queued NOTHING,
        # so dropping the picture and sending the same words again cannot
        # double-text. A 201 carrying an error_code is a message Twilio
        # ACCEPTED — it is `ok`, so it never reaches the retry, and `_result`
        # raises for it below. This product has a recorded incident of the
        # same sentence going out repeatedly; that ordering is what prevents
        # its return.
        for _attempt in (1, 2):
            response = requests.post(
                f"{self.base}/Messages.json",
                auth=self.auth,
                data=payload,
                timeout=15,
            )
            if response.ok or "MediaUrl" not in payload:
                break
            self._log(f"Twilio refused the text to {str(to)[:6]}… with a "
                      f"picture attached (HTTP {response.status_code}); "
                      "sending the same words again without it.")
            payload.pop("MediaUrl")
        return self._result(response, "text", to)

    def _picture_this_channel_can_carry(self, to: str, media) -> str:
        """The one URL that may ride on a text to `to`, or "".

        TWO REFUSALS, AND NEITHER DECIDES WHAT ANYTHING MEANS.

        `one_url` is the floor from brain/evidence.py: zero candidates is no
        picture and more than one is ALSO no picture, because nothing
        downstream of the browser model may choose between them.

        The `+1` test reads a NUMBER'S COUNTRY CODE, which is transport
        addressing — the same kind of check `e164` itself is — and it is here
        because Twilio documents MMS as US/Canada on standard long codes and
        NOBODY IN THIS REPO HAS MEASURED what a MediaUrl to +44 does. The
        possibilities include rejecting the whole message. Stranger-gate leg 3
        passes, so a London stranger really does reach production with a +44
        number; they get exactly today's behaviour rather than an experiment
        run on their live week. Relax it when somebody measures it, not before.
        """
        picture = one_url(media)
        if not picture:
            given = len(list(media or []))
            if given > 1:
                self._log(f"NO PICTURE on this text: {given} were offered and "
                          "exactly one is the proof of this errand. Nothing "
                          "here may pick between them.")
            return ""
        if not str(to).startswith("+1"):
            self._log(f"no picture on this text: {str(to)[:6]}… is outside "
                      "the numbers Twilio delivers MMS to, and the words "
                      "matter more than the picture.")
            return ""
        return picture

    # ------------------------------------------------------------------ call

    def call(self, plan, say: Optional[str] = None,
             voice: str = DEFAULT_VOICE) -> dict:
        """Place an approved, scripted call to a business.

        `say` exists only so the old two-argument shape can be REFUSED with an
        explanation instead of a TypeError. brain/anticipy_core.py:2151 still
        holds `self.voice.call(self.owner_phone, message)`, and a bare string
        carries no goal, no named callee and no record that anyone approved it
        — which is precisely the call that must not happen.
        """
        if not isinstance(plan, CallPlan):
            self._log("REFUSED an unscripted call: call() now takes a CallPlan "
                      "(script + goal + owner approval). MVP §06/§08.")
            raise CallRefused(
                "call() takes a CallPlan carrying a script, a goal, the callee "
                "and the owner's approval; got "
                f"{type(plan).__name__}{' plus a bare say= string' if say else ''}")
        reason = plan.refusal()
        if reason:
            self._log(f"REFUSED to call {plan.callee or plan.to}: {reason}")
            raise CallRefused(reason)
        self._guard("call", plan.to)
        # The record of the call exists BEFORE the call does, so a crash mid-dial
        # still leaves the script and the goal behind.
        self._log(f"CALLING {plan.callee} at {plan.to} · goal: {plan.goal} · "
                  f"saying: {plan.spoken()}")
        out = self._result(
            requests.post(
                f"{self.base}/Calls.json",
                auth=self.auth,
                data={"From": self.from_number, "To": plan.to,
                      "Twiml": twiml_for(plan, voice)},
                timeout=15,
            ),
            "call", plan.to)
        self._log(f"call {out['sid']} to {plan.callee}: {out['status']}")
        return {**out, "goal": plan.goal, "said": plan.spoken(),
                "callee": plan.callee}
