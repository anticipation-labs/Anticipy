"""S5 — the guarded-step cell: deterministic verify-and-recover (the reliability keystone).

Design-of-record: ``final/browser/PLAN.md`` §4.1–§4.4. The single biggest reliability
lever for a browser agent is that **no action can skip read-back**: after every action
we run a DETERMINISTIC read-back verify (never the acting model self-grading), and on
failure we walk the L0–L5 recovery ladder — cheapest remedy first, escalating only when
forced, with loop/stuck detectors and a hard frontier-call cap so an escalation storm
can never run away.

Two audit facts this codifies:
  * ~34.2% of browser-agent actions are silent no-ops the model *believes* worked — so
    a state-delta check (did the page actually change?) is mandatory, not optional.
  * 90/100 model self-reflections rubber-stamp their own action; replacing self-critique
    with a deterministic post-condition is worth +13–29pp. Hence: NEVER self-grade.

For IRREVERSIBLE artifacts (a submitted form, a placed order, a created draft/event) the
verification is stronger: :func:`confirm_irreversible` delegates to
``agent.proof.confirm_stable_artifact`` — the artifact must stay visible across *repeated*
delayed reads before the mutation counts as done. This is the same un-gameable read-back
seam that gates skill admission (§4.7).

This module is intentionally dependency-light and side-effect-free: everything the loop
needs (dispatch, observe, sign, reflect) is injected as a callable, so the whole cell is
unit-testable with fakes and never imports the acting model. It does NOT import
``webvoyager`` (which imports this) — no cycle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable, Optional, Sequence

from .proof import ArtifactProof, confirm_stable_artifact

Observation = dict[str, Any]
ReadOnce = Callable[[], Awaitable[tuple[Observation, Any]]]
Verifier = Callable[[Observation], bool]

__all__ = [
    "Progress",
    "Ladder",
    "Contingency",
    "VerifyResult",
    "LoopDetector",
    "FrontierBudget",
    "LadderState",
    "RecoveryDecision",
    "state_delta",
    "typed_field_landed",
    "success_token_present",
    "readback_verify",
    "classify_contingency",
    "next_recovery",
    "confirm_irreversible",
    "MUTATION_CTRL",
    "TRANSIENT_MARKERS",
]


# ── A4 READBACK_VERIFY — the three deterministic layers (§4.2) ────────────────
# Cheapest first: (1) state delta off _sig, (2) typed-field .value == intent /
# success-token after submit, (3) a validator VLM (grounder) — layer 3 lives in
# vision_verifier.py and is injected, never the acting model.

class Progress(IntEnum):
    """State-delta verdict, computed from signatures — the code-only layer 1."""

    REGRESSION = -1   # landed back on an already-visited state
    NO_CHANGE = 0     # signature identical -> the ~34.2% silent-no-op class
    PROGRESS = 1      # a genuinely new state


# Controls whose click/submit is an IRREVERSIBLE mutation (submit a form, place an
# order, pay, send, create). Used to decide when read-back must escalate to the
# stronger repeated-read confirm_stable_artifact proof.
MUTATION_CTRL = re.compile(
    r"\b(submit|send|place\s+order|place\s+your\s+order|pay\b|pay\s+now|checkout|"
    r"check\s*out|buy\b|buy\s+now|purchase|order\s+now|confirm(\s+(order|purchase|"
    r"payment|booking))?|add\s+to\s+(cart|bag|basket)|book\b|reserve|create|"
    r"save\b|apply\b|publish|post\b)\b",
    re.I,
)

# Transient / retryable conditions (L1) — NEVER retry into a ban, but these are
# worth a bounded backoff+re-observe rather than a plan change.
TRANSIENT_MARKERS = (
    "429", "too many requests", "rate limit", "temporarily unavailable",
    "just a moment", "checking your browser", "please wait", "loading",
    "service unavailable", "503", "gateway time", "try again",
)


def state_delta(prev_sig: Optional[str], new_sig: Optional[str],
                visited: Optional[dict] = None) -> Progress:
    """Layer 1 — did the world actually change? Pure signature comparison.

    ``visited`` is the URL/DOM-signature history; a signature we've already seen is
    a REGRESSION (circling), an unchanged signature is NO_CHANGE (the silent-no-op
    class), anything genuinely new is PROGRESS.
    """
    if new_sig is not None and new_sig == prev_sig:
        return Progress.NO_CHANGE
    if visited and new_sig in visited:
        return Progress.REGRESSION
    return Progress.PROGRESS


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _element_value(observation: Observation, *, index: Any = None,
                   name: Optional[str] = None) -> str:
    """Read back an element's committed value from the observation's element map.

    Prefers an explicit ``value``/``state`` field (the extension's ``doAct`` re-reads
    ``.value`` after a type, so this is a free byproduct), matched by ``idx`` first
    then by ``name``.
    """
    els = (observation or {}).get("elements") or []
    target = None
    if index is not None:
        target = next((e for e in els if e.get("idx") == index), None)
    if target is None and name:
        n = _norm(name)
        target = next((e for e in els if _norm(e.get("name")) == n), None)
    if not target:
        return ""
    if target.get("value") is not None:
        return str(target.get("value"))
    # element states are serialized like "value=California" / "filled: 90210"
    st = str(target.get("state") or "")
    m = re.search(r"value=([^|;]+)", st)
    if m:
        return m.group(1).strip()
    m = re.search(r"filled:?\s*([^|;]+)", st)
    if m:
        return m.group(1).strip()
    return ""


def typed_field_landed(observation: Observation, intent: str, *,
                       index: Any = None, name: Optional[str] = None) -> bool:
    """Layer 2a — after a type/write, re-read ``.value`` and assert it == intent.

    Catches the silent-write class (the most dangerous failure: the field never
    took the text yet the page looks exactly like success). Substring-tolerant so
    a field that reformats the value (adds a currency symbol, trims) still passes.
    """
    want = _norm(intent)
    if not want:
        return False
    got = _norm(_element_value(observation, index=index, name=name))
    if not got:
        return False
    return want in got or got in want


def success_token_present(observation: Observation,
                          tokens: Sequence[str]) -> bool:
    """Layer 2b — after a submit/mutation, assert an expected success token surfaced.

    The token is the un-fakeable receipt: an echoed nonce (httpbin round-trips every
    POSTed field back as JSON), an order id, a "thank you"/"submitted" confirmation.
    Read from the page's own read-back text + URL, never the model's prose.
    """
    toks = [t for t in (tokens or []) if str(t).strip()]
    if not toks:
        return False
    hay = (_norm((observation or {}).get("text")) + " "
           + _norm((observation or {}).get("url")) + " "
           + _norm((observation or {}).get("title")))
    return any(_norm(t) in hay for t in toks)


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of the deterministic read-back. ``ok`` is never a model self-report."""

    ok: bool
    progress: Progress
    mode: str            # which layer decided: "state_delta" | "typed_field" | "success_token"
    detail: str = ""


# Element-targeted verbs whose no-op we can attribute to a specific field/control.
_TYPED_VERBS = ("type", "fill", "write", "input")
_SUBMIT_VERBS = ("submit", "click", "check", "select", "press", "navigate")


def readback_verify(action: dict, *, prev_sig: Optional[str], new_obs: Observation,
                    new_sig: Optional[str], visited: Optional[dict] = None,
                    intent: Optional[str] = None,
                    success_tokens: Optional[Sequence[str]] = None) -> VerifyResult:
    """A4 — the mandatory external read-back verify for one action (layers 1+2).

    Deterministic and model-free. Escalates through the cheapest evidence that
    applies: a strong positive (typed value landed / success token present) passes
    even if the coarse signature didn't move; otherwise the state-delta is the
    verdict (NO_CHANGE / REGRESSION => not ok => recovery ladder).
    """
    verb = _norm(action.get("action"))
    progress = state_delta(prev_sig, new_sig, visited)

    # Layer 2a: a typed field is the ground truth for type/write actions.
    if verb in _TYPED_VERBS and intent:
        landed = typed_field_landed(new_obs, intent,
                                    index=action.get("index"), name=action.get("text"))
        return VerifyResult(landed, progress, "typed_field",
                            "value==intent" if landed else "value!=intent (silent-write)")

    # Layer 2b: an explicit success token is the receipt for a submit/mutation.
    if success_tokens:
        present = success_token_present(new_obs, success_tokens)
        if present:
            return VerifyResult(True, progress, "success_token", "receipt present")
        # token expected but absent AND the page didn't move => not done.
        if progress != Progress.PROGRESS:
            return VerifyResult(False, progress, "success_token", "receipt absent")

    ok = progress == Progress.PROGRESS
    return VerifyResult(ok, progress, "state_delta", progress.name)


# ── The nine contingency classes (§4.4): detector -> entry ladder level ───────

class Contingency(IntEnum):
    NONE = 0
    SILENT_NOOP = 1          # _sig unchanged after act                -> L0
    LOOP = 2                 # action-hash 3-strike                    -> L0->L2
    HALLUCINATED_CLICK = 3   # target not in fresh obs / off-site      -> L0
    MODAL = 4                # cookie/paywall/A-B overlay              -> L0
    CAPTCHA = 5              # "unusual traffic"                       -> L4
    LOGIN = 6                # sign-in / session expiry                -> L4
    MFA = 7                  # 2FA / OTP                               -> L4
    RATE_LIMIT = 8           # 429 / Cloudflare JS-challenge          -> L1
    SILENT_WRITE = 9         # field .value != intent on read-back     -> L0->L1


# The walls that must PAUSE -> text the user -> resume (never auto-solved here).
_WALL = {Contingency.CAPTCHA, Contingency.LOGIN, Contingency.MFA}


class Ladder(IntEnum):
    """The recovery ladder (§4.3) — cheapest first; resets on any PROGRESS."""

    L0_REROUTE = 0        # deterministic reroute: switch modality / dismiss modal
    L1_RETRY = 1          # tactical retry: backoff + re-observe (never into a ban)
    L2_REFLECT_REPLAN = 2 # reflect + replan from the reached page (1 frontier call)
    L3_DECOMPOSE = 3      # decompose / backtrack (best-of-N, verifier-selected)
    L4_HANDOFF = 4        # human gate: pause -> text user -> resume (a feature, NOT success)
    L5_ABANDON = 5        # honest abandon: best-effort read-back; NEVER fake success


# Which ladder level a contingency ENTERS at when first detected.
CONTINGENCY_ENTRY: dict[Contingency, Ladder] = {
    Contingency.NONE: Ladder.L0_REROUTE,
    Contingency.SILENT_NOOP: Ladder.L0_REROUTE,
    Contingency.LOOP: Ladder.L0_REROUTE,
    Contingency.HALLUCINATED_CLICK: Ladder.L0_REROUTE,
    Contingency.MODAL: Ladder.L0_REROUTE,
    Contingency.CAPTCHA: Ladder.L4_HANDOFF,
    Contingency.LOGIN: Ladder.L4_HANDOFF,
    Contingency.MFA: Ladder.L4_HANDOFF,
    Contingency.RATE_LIMIT: Ladder.L1_RETRY,
    Contingency.SILENT_WRITE: Ladder.L0_REROUTE,
}


_CAPTCHA_MARKERS = ("unusual traffic", "are you a robot", "verify you are human",
                    "captcha", "hcaptcha", "recaptcha", "cf-challenge", "turnstile")
_LOGIN_MARKERS = ("sign in", "log in", "enter your password", "session expired",
                  "please log in", "continue with", "to continue")
_MFA_MARKERS = ("verification code", "one-time", "one time code", "2-step",
                "two-factor", "authenticator", "enter the code we sent", " otp")


def classify_contingency(*, verify: VerifyResult, page_text: str = "",
                         is_loop: bool = False, target_missing: bool = False,
                         has_modal: bool = False) -> Contingency:
    """Detector — map the failed step to one of the nine contingency classes.

    Walls (captcha/login/mfa) win first (they must not be papered over by a retry),
    then transient rate-limits, then the structural classes. Text markers are read
    from the page's own read-back, never inferred by the acting model.
    """
    t = _norm(page_text)
    if any(m in t for m in _CAPTCHA_MARKERS):
        return Contingency.CAPTCHA
    if any(m in t for m in _MFA_MARKERS):
        return Contingency.MFA
    if any(m in t for m in _LOGIN_MARKERS):
        return Contingency.LOGIN
    if any(m in t for m in TRANSIENT_MARKERS):
        return Contingency.RATE_LIMIT
    if verify.mode == "typed_field" and not verify.ok:
        return Contingency.SILENT_WRITE
    if target_missing:
        return Contingency.HALLUCINATED_CLICK
    if has_modal:
        return Contingency.MODAL
    if is_loop:
        return Contingency.LOOP
    if not verify.ok:
        return Contingency.SILENT_NOOP
    return Contingency.NONE


# ── Loop / stuck detectors + the frontier-call cap (§4.6) ─────────────────────

class LoopDetector:
    """Action-hash 3-strike loop detector + visited-state (regression) memory.

    Keyed on ``(tool, args, descriptor)`` so a control that re-renders (indices
    shift) is still recognised as the SAME repeated action.
    """

    def __init__(self, strike: int = 3) -> None:
        self.strike = max(2, int(strike))
        self._last: Optional[str] = None
        self._run = 0
        self._counts: dict[str, int] = {}
        self._states: dict[str, int] = {}

    @staticmethod
    def action_hash(action: dict, descriptor: str = "") -> str:
        return "|".join((
            _norm(action.get("action")),
            _norm(action.get("text")),
            _norm(descriptor or action.get("index")),
        ))

    def record(self, action_hash: str) -> int:
        """Record one action; return the length of the current consecutive run."""
        self._counts[action_hash] = self._counts.get(action_hash, 0) + 1
        if action_hash == self._last:
            self._run += 1
        else:
            self._last = action_hash
            self._run = 1
        return self._run

    def is_loop(self, action_hash: str) -> bool:
        return self._run >= self.strike and action_hash == self._last

    def record_state(self, sig: Optional[str]) -> bool:
        """Record a visited signature; return True if it was seen before (regression)."""
        if not sig:
            return False
        seen = sig in self._states
        self._states[sig] = self._states.get(sig, 0) + 1
        return seen

    def reset_run(self) -> None:
        """Any genuine PROGRESS clears the consecutive-run (the ladder resets)."""
        self._last, self._run = None, 0


@dataclass
class FrontierBudget:
    """Hard cap on frontier-model calls (the expensive reflect/replan/best-of-N).

    An escalation storm is the classic runaway-cost bug: every failure escalates,
    every escalation fails, forever. The cap makes L2/L3 exhaustible so the ladder
    is forced down to L4 (handoff) or L5 (honest abandon) instead of burning budget.
    """

    cap: int = 2
    spent: int = 0

    def can_spend(self) -> bool:
        return self.spent < self.cap

    def spend(self) -> bool:
        if not self.can_spend():
            return False
        self.spent += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.spent)


@dataclass
class LadderState:
    """Mutable per-task recovery state that drives :func:`next_recovery`."""

    consecutive_stuck: int = 0        # NO_CHANGE/REGRESSION streak (resets on PROGRESS)
    replans_used: int = 0
    max_replans: int = 2
    decompositions_used: int = 0
    max_decompositions: int = 1
    nav_blocks: int = 0
    max_nav_blocks: int = 3
    steps_exhausted: bool = False     # step/$/wall-clock ceiling reached
    frontier: FrontierBudget = field(default_factory=FrontierBudget)

    def on_progress(self) -> None:
        """PROGRESS resets the ladder (§4.3): the stuck streak clears."""
        self.consecutive_stuck = 0

    def on_stuck(self) -> None:
        self.consecutive_stuck += 1


@dataclass(frozen=True)
class RecoveryDecision:
    """A pure decision about the next remedy — the loop executes it, this only decides."""

    level: Ladder
    remedy: str            # "reroute" | "retry" | "reflect_replan" | "decompose" | "handoff" | "abandon"
    reason: str
    uses_frontier: bool = False


_REMEDY = {
    Ladder.L0_REROUTE: "reroute",
    Ladder.L1_RETRY: "retry",
    Ladder.L2_REFLECT_REPLAN: "reflect_replan",
    Ladder.L3_DECOMPOSE: "decompose",
    Ladder.L4_HANDOFF: "handoff",
    Ladder.L5_ABANDON: "abandon",
}


def next_recovery(contingency: Contingency, state: LadderState) -> RecoveryDecision:
    """The recovery ladder as a pure function (§4.3) — cheapest viable remedy first.

    Order of resolution:
      * hard ceiling (steps/$/wall-clock) with nothing left        -> L5 honest abandon
      * an unresolved wall (captcha/login/mfa)                      -> L4 human gate
      * a transient (429/spinner/stale)                            -> L1 tactical retry
      * else escalate by how stuck we are:
          not-yet-stuck (streak < 2)                               -> L0 deterministic reroute
          stuck (>=2) & a replan + frontier budget remain          -> L2 reflect+replan
          replans spent but a decompose + frontier remain          -> L3 decompose/backtrack
          all frontier remedies spent                              -> L4 handoff (ask), else L5
    """
    # L5 — nothing left to try.
    if state.steps_exhausted:
        return RecoveryDecision(Ladder.L5_ABANDON, "abandon",
                                "budget/step ceiling reached — best-effort read-back, never fake success")

    # L4 — a wall we cannot pass here: pause -> text user -> resume.
    if contingency in _WALL:
        return RecoveryDecision(Ladder.L4_HANDOFF, "handoff",
                                f"{contingency.name.lower()} wall — pause and text the user with the artifact")

    # L1 — transient: bounded backoff + re-observe (never retry into a ban).
    if contingency == Contingency.RATE_LIMIT:
        return RecoveryDecision(Ladder.L1_RETRY, "retry",
                                "transient (rate-limit/challenge) — backoff + re-observe")

    # L0 — first, cheap deterministic reroute (switch modality / dismiss modal / re-ground).
    if state.consecutive_stuck < 2:
        return RecoveryDecision(Ladder.L0_REROUTE, "reroute",
                                f"{contingency.name.lower()}: switch modality / re-ground on live DOM")

    # L2 — stuck: reflect + replan from the reached page (one frontier call).
    if state.replans_used < state.max_replans and state.frontier.can_spend():
        return RecoveryDecision(Ladder.L2_REFLECT_REPLAN, "reflect_replan",
                                "2+ no-progress — reflect then replan from the reached page",
                                uses_frontier=True)

    # L3 — replan didn't move it: decompose / backtrack (best-of-N, verifier-selected).
    if state.decompositions_used < state.max_decompositions and state.frontier.can_spend():
        return RecoveryDecision(Ladder.L3_DECOMPOSE, "decompose",
                                "replan exhausted — decompose the subgoal / backtrack a checkpoint",
                                uses_frontier=True)

    # Frontier remedies spent — hand off if a human can unblock, else abandon honestly.
    if contingency != Contingency.NONE:
        return RecoveryDecision(Ladder.L4_HANDOFF, "handoff",
                                "L2/L3 exhausted — pause and text the user with the specific artifact")
    return RecoveryDecision(Ladder.L5_ABANDON, "abandon",
                            "no remaining path — honest read-back, never fake success")


# ── Irreversible-artifact confirmation — the repeated-read proof (§4.2 tail) ──

async def confirm_irreversible(read_once: ReadOnce, is_verified: Verifier, *,
                               score=None, reads: int = 3,
                               delay_seconds: float = 0.0, sleep=None) -> ArtifactProof:
    """Wire ``agent.proof.confirm_stable_artifact`` into the guarded step.

    For an IRREVERSIBLE artifact (a submitted form, a placed order, a created draft/
    event) a single positive read is not enough — a flicker, an optimistic-then-
    reverted UI, or a slow redirect can look like success and then vanish. This
    requires the artifact to stay verified across every one of ``reads`` delayed
    re-reads; the first failed read fails closed. It is the un-gameable completion
    seam and the same contract that gates skill admission (§4.7).
    """
    kwargs: dict = {"score": score, "reads": reads, "delay_seconds": delay_seconds}
    if sleep is not None:
        kwargs["sleep"] = sleep
    return await confirm_stable_artifact(read_once, is_verified, **kwargs)
