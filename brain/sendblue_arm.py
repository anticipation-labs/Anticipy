"""Anticipy's Sendblue arm: the one place in the brain that talks to Sendblue.

Sendblue (iMessage/SMS API) is the second outbound message channel beside
Twilio. Thin REST wrapper, no SDK: one POST to /api/send-message, authenticated
with the two headers Sendblue documents (`sb-api-key-id`, `sb-api-secret-key`).
Credentials come from the environment; nothing is hardcoded.

THE CONTRACT IS VoiceArm's, TO THE FIELD. brain/conversation.py's transport
calls `arm.text(to, body, media=None)` and nothing else, and every caller above
it reads the result the same way: a dict {"sid", "status", "delivered"} on a
send the vendor took, and `voice_arm.SendFailed` — raised, never returned — on
anything else. Keeping the shape identical is what lets the worker swap the
arm under the transport without a single caller learning a vendor's name.

Two guarantees are inherited rather than reimplemented, because a second copy
is a second place to forget:

1. A RIG NEVER REACHES A REAL PERSON. `_guard` calls `voice_arm._rig_reason`
   — the same function, the same order (muzzle first, then the physical
   impossibility of this arm's own wire, then pytest, then a local backend).
   On 2026-08-19 a laptop worker that had inherited production credentials
   did real damage; a laptop that has inherited SENDBLUE_* can text a real
   person just as easily, and the environment is not permission here either.
2. A FAILED SEND IS NEVER A RECORD. A non-2xx, a body with no JSON, a reply
   with no message_handle, a status Sendblue documents as not-sent (ERROR,
   DECLINED) or an error_code all raise. `delivered` is False for QUEUED —
   Sendblue has the message, no handset has seen it — for the reason
   voice_arm gives: nothing in the brain may print "sent" off a create call.

THE SECRET IS NEVER LOGGED. The key id is public-ish (it names the key); the
secret is what a leaked log would hand an attacker, so every line this file
writes and every exception it raises names the key by its last four characters
and is scrubbed of the secret before it leaves.

Sendblue's own vocabulary, read off docs.sendblue.com on 2026-09-05 and not
interpreted: REGISTERED, PENDING, QUEUED, ACCEPTED, SENT, DELIVERED, READ are
stages of one message on its way; ERROR ("failed to send") and DECLINED
("rejected") are the two documented ways it does not go.
"""
from __future__ import annotations

import os
from typing import Callable, Mapping, Optional
from urllib.parse import urlsplit

import requests

from . import voice_arm as va
from .evidence import one_url

# What no Sendblue account can send without. The from number is REQUIRED by
# the API and must be one of the account's own Sendblue numbers; that second
# fact cannot be checked from here without a request, so a wrong number shows
# up as DECLINED on the first send and nowhere earlier.
REQUIRED_ENV = ("SENDBLUE_API_KEY_ID", "SENDBLUE_API_SECRET_KEY",
                "SENDBLUE_FROM_NUMBER")
DEFAULT_API_BASE = "https://api.sendblue.com"
SEND_PATH = "/api/send-message"

# Sendblue's documented not-sent statuses, plus Twilio's, so a status that
# means "dead" on either wire is dead on both. Lowercased: Sendblue answers in
# capitals and `_result` lowercases before comparing.
DEAD_STATES = ("error", "declined") + va.DEAD_STATES
# ONE definition of delivered for both arms, and it lives in voice_arm. A
# second tuple here would let the two channels disagree about whether a
# handset saw a message, and the feed would inherit whichever one was wrong.
DELIVERED_STATES = va.DELIVERED_STATES

TIMEOUT_SECONDS = 15


class SendblueNotConfigured(RuntimeError):
    """Sendblue credentials are absent or unusable. Names exactly which."""


def api_base(env: Optional[Mapping[str, str]] = None) -> str:
    """Sendblue's REST root, overridable so an outbound send can be PROVED.

    proof/sendblue_outbound_proof.py points SENDBLUE_API_BASE at a loopback
    recorder and asserts the path, the two headers and every field of the JSON
    this file builds — a real send, executed by the real code, that Sendblue
    never hears about. Same rule and same reason as voice_arm.api_base.
    """
    env = os.environ if env is None else env
    return (env.get("SENDBLUE_API_BASE") or DEFAULT_API_BASE).rstrip("/")


def has_credentials(env: Optional[Mapping[str, str]] = None) -> bool:
    """Can this process talk to Sendblue at all? The live/mock gate's twin."""
    env = os.environ if env is None else env
    return bool(not va.muzzled(env)
                and all((env.get(name) or "").strip() for name in REQUIRED_ENV))


def choose_provider(env: Optional[Mapping[str, str]] = None) -> str:
    """Which arm the worker texts through: "sendblue" | "twilio" | "mock".

    ONE RULE, THREE READERS — the worker's transport build, its `worker up`
    banner, and overnight/does_she_reach_them.py — so a gate can never
    measure a different vendor than the one the worker is texting through.

    ANTICIPY_SMS_PROVIDER names a vendor outright. Unset, the choice is
    Sendblue when its three variables are all present, else Twilio when its
    credentials are, else mock. POLARITY, decided here: a vendor that is
    NAMED but NOT CONFIGURED is "mock", never the other vendor. An operator
    who wrote `sendblue` and forgot the secret has asked for one channel and
    must not be answered on another — falling through to Twilio would text
    the owner from a number he has just been told is retired. Mock sends
    nothing, and the banner says `sms=mock` where the operator is looking.
    An unrecognised name is the same case: a typo is not a vendor.
    """
    env = os.environ if env is None else env
    asked = (env.get("ANTICIPY_SMS_PROVIDER") or "").strip().lower()
    sendblue = has_credentials(env)
    twilio = va.has_credentials(env)
    if asked == "sendblue":
        return "sendblue" if sendblue else "mock"
    if asked == "twilio":
        return "twilio" if twilio else "mock"
    if asked:
        return "mock"
    if sendblue:
        return "sendblue"
    if twilio:
        return "twilio"
    return "mock"


def key_tail(key_id: str) -> str:
    """The last four characters of a key id — what a log may say about it."""
    return "…" + str(key_id or "")[-4:]


def _cannot_reach_a_phone() -> str:
    """Why THIS arm's wire is physically unable to reach a handset, or "".

    SENDBLUE_API_BASE on loopback: the recorder in
    proof/sendblue_outbound_proof.py answers every request itself. Read by
    voice_arm._rig_reason in place of Twilio's check, and only for this arm —
    see the parameter's note there for why the two are never merged.
    """
    host = (urlsplit(api_base()).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return f"SENDBLUE_API_BASE points at a recorder on {host}"
    return ""


class SendblueArm:
    """Sendblue's send-message API, and nothing else.

    `journal` receives one line for every attempt, refusal and outcome. It
    defaults to stdout so no rung of the ladder is ever silent (MVP §09).
    """

    def __init__(self, journal: Optional[Callable[[str], None]] = None):
        missing = [f"{name} unset" for name in REQUIRED_ENV
                   if not (os.environ.get(name) or "").strip()]
        if missing:
            raise SendblueNotConfigured(
                "Sendblue is not configured on this process: "
                + "; ".join(missing) + ". She cannot text.")
        self.journal = journal
        self.key_id = os.environ["SENDBLUE_API_KEY_ID"].strip()
        # Underscored and never formatted anywhere: see `_scrub`.
        self._secret = os.environ["SENDBLUE_API_SECRET_KEY"].strip()
        self.from_number = os.environ["SENDBLUE_FROM_NUMBER"].strip()
        if not va.E164.match(self.from_number):
            # Sendblue requires E.164 and rejects anything else on every send.
            # Refusing at construction is louder and earlier than a DECLINED
            # per text, and it happens while the operator is watching the
            # deploy rather than the next time she has something to say.
            raise SendblueNotConfigured(
                f"SENDBLUE_FROM_NUMBER {self.from_number!r} is not an E.164 "
                "number (+15551234567). Sendblue would decline every text.")
        self.status_callback = (os.environ.get("SENDBLUE_STATUS_CALLBACK")
                                or "").strip()
        # Safe to log: the id's tail, never the secret.
        self.credential = f"Sendblue key {key_tail(self.key_id)}"
        self.base = api_base()

    # -------------------------------------------------------------- plumbing

    def _scrub(self, line: str) -> str:
        """No string leaves this file carrying the secret. Belt and braces:
        nothing here formats it on purpose, and a vendor error body that
        echoed a header back would otherwise land in the journal verbatim."""
        return str(line).replace(self._secret, "[secret]") if self._secret else str(line)

    def _log(self, line: str) -> None:
        (self.journal or print)(self._scrub(line))

    def _guard(self, what: str, to: str) -> None:
        reason = va._rig_reason(_cannot_reach_a_phone)
        if reason:
            # Loud, and with the number it was about to reach, because the
            # failure mode this replaces was a real text to a real person.
            self._log(f"REFUSED to {what} {str(to)[:6]}… from a rig: {reason}. "
                      f"Sendblue credentials in the environment are not permission.")
            raise va.SendFailed(f"refusing to {what} a real number: {reason}")

    def _headers(self) -> dict:
        return {"sb-api-key-id": self.key_id,
                "sb-api-secret-key": self._secret}

    def _result(self, response, what: str, to: str) -> dict:
        if not response.ok:
            # A 401 is the credential, and the credential is named by its
            # tail so the operator knows WHICH key Sendblue rejected without
            # the log ever holding what it rejected it for.
            raise va.SendFailed(self._scrub(
                f"Sendblue refused the {what} to {str(to)[:6]}… using "
                f"{self.credential}: HTTP {response.status_code} "
                f"{response.text[:200]}"))
        try:
            out = response.json()
        except ValueError as exc:
            raise va.SendFailed(
                f"Sendblue returned no JSON for the {what}: {exc}") from exc
        if not isinstance(out, dict):
            raise va.SendFailed(
                f"Sendblue returned a non-object for the {what}: "
                f"{str(out)[:80]!r}")
        status = str(out.get("status") or "").lower()
        handle = str(out.get("message_handle") or "")
        if not handle or status in DEAD_STATES or out.get("error_code"):
            raise va.SendFailed(self._scrub(
                f"{what} to {str(to)[:6]}… did not go out: "
                f"status={status or 'none'} error={out.get('error_code')} "
                f"{out.get('error_message') or ''}".strip()))
        # `delivered` exists because "queued" is the honest answer to "did
        # Sendblue take it?" and a dishonest answer to "did he get it?".
        return {"sid": handle, "status": status,
                "delivered": status in DELIVERED_STATES}

    # ------------------------------------------------------------------ text

    def text(self, to: str, body: str, media=None) -> dict:
        """The words, and the picture if this channel can carry one.

        THE WORDS ARE THE FLOOR — VoiceArm.text's rule, verbatim in effect.
        `media` may be dropped for any reason and every one of those still
        sends the sentence. A confirmation that vanishes because a screenshot
        failed is strictly worse than the confirmation with no screenshot.
        """
        self._guard("text", to)
        payload = {"from_number": self.from_number, "number": to,
                   "content": body}
        if self.status_callback:
            payload["status_callback"] = self.status_callback
        picture = _picture_this_channel_can_carry(self._log, to, media)
        if picture:
            payload["media_url"] = picture
        # ONE POST SITE, AND THE RETRY IS THE SAME ONE — the credential rides
        # through exactly one line somebody has read, and the payload is
        # visible at the post.
        #
        # ONE RETRY, AND ONLY WHEN NOTHING WENT OUT. The retry exists to drop
        # the picture and send the same words again, so it may run only when
        # it is CERTAIN no message is on its way, or it is a second text to a
        # real person — and this product has a recorded incident of exactly
        # that. Two shapes are certain: a non-2xx (Sendblue queued nothing),
        # and a 2xx whose status is one Sendblue documents as not-sent
        # (ERROR "failed to send", DECLINED "rejected"). A 2xx carrying a live
        # status (QUEUED, ACCEPTED, SENT…) is a message Sendblue HAS, whatever
        # its error_code says; it never reaches the retry, and `_result`
        # raises for it below. Enumerating media-specific error codes is the
        # wrong repair for the reason voice_arm gives: a code list rots, and
        # when it rots the failure is a lost confirmation.
        for _attempt in (1, 2):
            response = requests.post(
                f"{self.base}{SEND_PATH}",
                headers=self._headers(),
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
            if "media_url" not in payload or not _nothing_went_out(response):
                break
            self._log(f"Sendblue did not take the text to {str(to)[:6]}… with "
                      f"a picture attached (HTTP {response.status_code}, "
                      f"status={_status_of(response) or 'none'}); sending the "
                      "same words again without it.")
            payload.pop("media_url")
        return self._result(response, "text", to)

    # ------------------------------------------------------------------ call

    def call(self, plan, say: Optional[str] = None, voice: str = "") -> dict:
        """Sendblue does not dial. Refused with the reason rather than an
        AttributeError, because the worker installs this arm where
        brain/anticipy_core.py's notify_owner may ask for a call, and "she
        cannot call on this channel" is an answer where a stack trace is not.
        Calls stay on Twilio (brain/voice_arm.py), which the worker still
        builds when it is configured."""
        self._log("REFUSED a call: Sendblue carries messages, not calls. "
                  "Voice stays on Twilio's arm.")
        raise va.CallRefused("Sendblue does not place calls; the Twilio arm does")


def _status_of(response) -> str:
    """The lowercased `status` in a JSON reply, or "" when there is none."""
    try:
        out = response.json()
    except ValueError:
        return ""
    return str(out.get("status") or "").lower() if isinstance(out, dict) else ""


def _nothing_went_out(response) -> bool:
    """Is it CERTAIN this reply means no message is on its way? The only
    condition under which a retry cannot double-text. Not-ok is certain; a
    2xx with a documented dead status is certain; everything else is a
    message the vendor may have, and is not retried."""
    if not response.ok:
        return True
    return _status_of(response) in DEAD_STATES


def _picture_this_channel_can_carry(log: Callable[[str], None], to: str,
                                    media) -> str:
    """The one URL that may ride on a text to `to`, or "".

    VoiceArm._picture_this_channel_can_carry's twin, with the same two
    refusals and the same reasons: `one_url` is the floor from
    brain/evidence.py (zero candidates is no picture, more than one is ALSO
    no picture — nothing downstream of the browser model may choose), and
    the `+1` test reads a NUMBER'S COUNTRY CODE, which is transport
    addressing. iMessage carries media to any country; the SMS fallback
    Sendblue applies when a number is not on iMessage is MMS, and nobody in
    this repo has measured what that does outside US/Canada. A foreign
    stranger gets exactly Twilio's behaviour — the words — rather than an
    experiment on their live week. Relax it when somebody measures it.
    """
    picture = one_url(media)
    if not picture:
        given = len(list(media or []))
        if given > 1:
            log(f"NO PICTURE on this text: {given} were offered and exactly "
                "one is the proof of this errand. Nothing here may pick "
                "between them.")
        return ""
    if not str(to).startswith("+1"):
        log(f"no picture on this text: {str(to)[:6]}… is outside the numbers "
            "this arm has been measured delivering media to, and the words "
            "matter more than the picture.")
        return ""
    return picture
