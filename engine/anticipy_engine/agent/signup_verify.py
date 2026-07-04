"""S6 — the executable core of the general ``signup-and-verify`` skill.

This is the code behind ``skills/signup-and-verify/SKILL.md``: a **workflow-CLASS** capability
(not a per-site script) that signs up for an arbitrary service and clears the email-verification
step, composing the two new hands:
  * ``hands.captcha_solver`` — auto-solve a captcha wall (→ token → inject → re-verify).
  * ``hands.email_verifier`` — read the latest verification code the service just emailed.

It carries **zero hardcoded selectors**: the abstract steps are resolved against the live page
by the actor at run time (role + visible-label semantics), and fields are matched by meaning
("the email field", "the password field"), exactly like ``agent/recipes.py`` descriptors.

Everything that touches the outside world (the browser actor, the captcha solver, the Gmail
reader) is INJECTED, so the whole flow is unit-testable with fakes and — importantly for S6 —
**performs no real signup**. Loop registration (acquire-before-task) is the S8 skills pipeline;
the S9 product wire hands this an actor bound to the connected Chrome.

The verify contract is the un-gameable part: success is a DETERMINISTIC signed-in read-back
(``verify_signed_up`` + the repeated-read :func:`confirm_signed_up` proof), never a model
self-claim and never "we submitted the form."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Sequence

from ..hands.captcha_solver import CaptchaOutcome, resolve_captcha
from ..hands.email_verifier import read_verification_code
from .proof import ArtifactProof, confirm_stable_artifact

__all__ = [
    "SignupRequest",
    "Precondition",
    "StepKind",
    "SIGNUP_STEPS",
    "verify_signed_up",
    "confirm_signed_up",
    "check_precondition",
    "handle_captcha_step",
    "fetch_verification_code",
]


# ── typed params ({service_url, email} required) ──────────────────────────────
@dataclass(frozen=True)
class SignupRequest:
    """Typed parameters for the skill. ``service_url`` + ``email`` are required."""

    service_url: str
    email: str
    password: str = ""
    username: str = ""
    first_name: str = ""
    last_name: str = ""

    def missing_required(self) -> list[str]:
        miss = []
        if not (self.service_url or "").strip():
            miss.append("service_url")
        if not _EMAIL_RE.match((self.email or "").strip()):
            miss.append("email")
        return miss


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── precondition contract ─────────────────────────────────────────────────────
@dataclass(frozen=True)
class Precondition:
    """Whether the skill is runnable now, and what's missing if not."""

    ok: bool
    missing: tuple[str, ...] = ()
    detail: str = ""


def check_precondition(request: SignupRequest, *, actor_connected: bool,
                       inbox_ready: bool, solver_available: bool) -> Precondition:
    """The skill's precondition: valid params + a connected actor + a reachable inbox.

    A captcha solver is *recommended* but NOT required — without it a captcha wall simply
    falls through to the handoff rung (a paused task, not a failure). A missing inbox IS
    blocking: the verify step can't complete without reading the emailed code.
    """
    missing = list(request.missing_required())
    if not actor_connected:
        missing.append("actor_connected")
    if not inbox_ready:
        missing.append("inbox_ready")
    detail = "" if solver_available else "no captcha solver — a captcha wall will hand off"
    return Precondition(ok=not missing, missing=tuple(missing), detail=detail)


# ── the abstract, selector-free workflow ──────────────────────────────────────
class StepKind(str, Enum):
    NAVIGATE = "navigate"                 # go to service_url (or its /signup)
    FIND_SIGNUP = "find_signup_form"      # locate the register form by semantics
    FILL_IDENTITY = "fill_identity"       # email/username/name/password by meaning
    SUBMIT = "submit_signup"              # submit the form
    SOLVE_CAPTCHA = "solve_captcha"       # if a captcha wall appears → auto-solve
    AWAIT_EMAIL = "await_verification"    # "check your email" screen
    READ_CODE = "read_email_code"         # read the latest code for this service
    ENTER_CODE = "enter_code"             # type the code + submit
    VERIFY = "verify_signed_up"           # deterministic signed-in read-back


# Ordered, site-agnostic. The actor resolves each step to live elements at run time.
SIGNUP_STEPS: tuple[StepKind, ...] = (
    StepKind.NAVIGATE,
    StepKind.FIND_SIGNUP,
    StepKind.FILL_IDENTITY,
    StepKind.SUBMIT,
    StepKind.SOLVE_CAPTCHA,
    StepKind.AWAIT_EMAIL,
    StepKind.READ_CODE,
    StepKind.ENTER_CODE,
    StepKind.VERIFY,
)


# ── the verify contract (deterministic signed-in read-back) ───────────────────
_SIGNED_IN = (
    "sign out", "log out", "logout", "my account", "account settings", "dashboard",
    "welcome,", "you're signed in", "you are signed in", "verified", "email confirmed",
    "get started", "create your first",
)
_STILL_GATED = (
    "enter your password", "verification code", "confirm your email", "check your email",
    "incorrect", "invalid code", "try again", "sign in to continue", "captcha",
)


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def verify_signed_up(observation: dict, *,
                     expected_tokens: Optional[Sequence[str]] = None) -> bool:
    """Deterministic post-condition: are we genuinely signed in (not just "submitted")?

    Passes only when a signed-in signal is present AND no still-gated signal remains. If
    ``expected_tokens`` are given (e.g. the account email, a dashboard URL) at least one must
    also appear — the un-fakeable, account-specific receipt. Reads the page's own text/url,
    never the acting model's prose.
    """
    hay = " ".join((_norm(observation.get("text")), _norm(observation.get("url")),
                    _norm(observation.get("title"))))
    if not hay.strip():
        return False
    if any(g in hay for g in _STILL_GATED):
        return False
    if not any(s in hay for s in _SIGNED_IN):
        return False
    if expected_tokens:
        toks = [_norm(t) for t in expected_tokens if str(t).strip()]
        if toks and not any(t in hay for t in toks):
            return False
    return True


async def confirm_signed_up(
    read_once: Callable[[], Awaitable[tuple[dict, Any]]], *,
    expected_tokens: Optional[Sequence[str]] = None,
    reads: int = 3, delay_seconds: float = 0.0, sleep=None,
) -> ArtifactProof:
    """The stronger contract for the completed account: the signed-in state must hold across
    REPEATED delayed reads (same seam as ``confirm_stable_artifact`` / skill admission), so a
    flash of a post-submit success screen that reverts to a login wall never counts as done.
    """
    kwargs: dict = {"reads": reads, "delay_seconds": delay_seconds}
    if sleep is not None:
        kwargs["sleep"] = sleep
    return await confirm_stable_artifact(
        read_once, lambda o: verify_signed_up(o, expected_tokens=expected_tokens), **kwargs)


# ── the two composed sub-steps (injected I/O) ─────────────────────────────────
def handle_captcha_step(page: Any, solver: Any, *, page_url: str = "") -> CaptchaOutcome:
    """SOLVE_CAPTCHA: if the page shows a captcha, auto-solve it and return the injection.

    A ``solved=False`` outcome (no captcha / no solver / solve failed) is the caller's signal
    to fall through to the handoff rung — never to fake progress.
    """
    return resolve_captcha(page, solver, page_url=page_url)


def fetch_verification_code(request: SignupRequest, *, reader: Any = None,
                            emails: Any = None,
                            llm_extract: Optional[Callable[[str], Optional[str]]] = None
                            ) -> Optional[str]:
    """READ_CODE: read the latest verification code this service emailed to ``request.email``."""
    return read_verification_code(request.service_url, reader=reader, emails=emails,
                                  llm_extract=llm_extract)
