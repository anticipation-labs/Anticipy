"""Wall handoff — pause -> ask the human -> resume (no fake success, no auto-auth).

The recipe shared by Operator, Claude for Chrome, and the Vercel AI SDK: on a
login / payment / CAPTCHA wall the agent does NOT give up, and it does NOT type
credentials or solve the captcha itself. It PAUSES, asks the human to clear that
one step in the live browser, and RESUMES once they say go — feeding their action
back into the loop (Operator `acknowledged_safety_checks`; Vercel
`addToolApprovalResponse`). Takeover is private: we stop observing while the human
is at the wall, so we never screenshot what they type (Operator takeover mode).

This module is the general seam. Real text delivery (Twilio) and real mid-plan
state persistence are swapped in behind it; the agent-facing contract is stable.
NO site-specific logic lives here.
"""
from __future__ import annotations

import re

# General wall signatures — NOT site-specific (no brand/host names).
_CAPTCHA = re.compile(
    r"captcha|are you (a )?(robot|human)|verify you are human|unusual traffic|"
    r"press & hold|checking your browser|enter the characters|access denied",
    re.I,
)
_LOGIN = re.compile(
    r"sign ?in|log ?in|enter your password|forgot password|create (an )?account|continue with",
    re.I,
)
# MFA / 2FA / one-time-code challenge (sweep #16) — a first-class wall: we NEVER read a code from the
# user's texts or type it ourselves; we pause, ask the human to complete it, and resume.
_MFA = re.compile(
    r"2fa|two[- ]factor|multi[- ]factor|one[- ]time (code|pass)|verification code|authenticator|"
    r"enter the \d+[- ]digit|\b\d-digit code|security code|otp\b|we (texted|sent|emailed) you a code|"
    r"approve (the|this) (sign[- ]?in|login|request)|check your phone",
    re.I,
)


def classify_wall(text: str) -> str:
    """captcha | mfa | login | block — best-effort, from page text only."""
    t = text or ""
    if _CAPTCHA.search(t):
        return "captcha"
    if _MFA.search(t):
        return "mfa"
    if _LOGIN.search(t):
        return "login"
    return "block"


def ask_message(wall_kind: str, url: str) -> str:
    """The human-facing text we send (the 'pause -> ask' half of the seam)."""
    site = url or "the open tab"
    what = {
        "login": "log in",
        "mfa": "approve the sign-in / enter the verification code",
        "captcha": "clear the verification / captcha",
        "block": "get past the block",
    }.get(wall_kind, "clear it")
    return (
        f"I hit a {wall_kind} wall on {site}. Please {what} in the Chrome tab I left open, "
        "then reply “go” and I’ll finish the task. "
        "(I won’t type your password or solve the captcha myself, and I’m not watching while you do.)"
    )
