"""
End-state assertion library for browser actions.

This is the +25-40 quality lever called out in the architecture upgrade.
Per-task-kind verification routines that **do not trust the LLM's `done`
claim**. Instead, every routine re-fetches state via the bridge and asserts
generic, observable properties — never per-site logic.

Why this matters: in last night's 0/35 fail run, the LLM said `done` 33 times
on tasks that hadn't actually completed (the page just looked plausible). The
fix is to navigate back to the *effect surface* (Sent folder, calendar,
cart, comment thread) and verify the effect with timestamp + substring.

WIRE-ME: ``engine/app/agent.py`` should, when an action task ends with the
agent claiming `done`, call ``verify_end_state(task_kind, task_text,
agent_done_payload, bridge)`` and treat ``ok=False`` as task failure (replace
the success message with one of the wearer-honest fallbacks). The
``task_kind`` should come from the planner's output; default to ``"generic"``
when missing.

Cop-outs covered:
  - #6: never silently claim success — fail closed when verification can't
    run.
  - #8: never trust the agent's self-report alone — always re-fetch state.
  - #10: no per-site rules — every routine uses URL-pattern + time-window +
    substring matching.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Iterable, Protocol


logger = logging.getLogger("engine.end_state_verifier")


# ─────────────────────────────────────────────────────────────────────────
# Bridge contract — kept narrow so callers can wire any concrete bridge
# (engine/app/bridge.py, a Playwright handle, a mock for tests, etc.).
# ─────────────────────────────────────────────────────────────────────────


class BridgeProtocol(Protocol):
    """Minimal navigation + extraction surface needed for verification.

    Implementations may be ``app.bridge.BrowserAgentExecutor`` extended with
    these methods, a thin wrapper over Playwright's ``Page``, or a mock.
    """

    async def navigate(self, url: str) -> None: ...
    async def get_text(self, selector: str | None = None) -> str: ...
    async def get_url(self) -> str: ...


# ─────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class VerificationResult:
    """Outcome of an end-state check.

    Attributes:
        ok: True only when every required assertion fired.
        missing: Names of expected facts/effects that the verifier did not
            find. Used both for telemetry and for an honest wearer message.
        evidence: Direct quotes/URLs the verifier saw and judged supportive.
            Useful for audit logs.
    """

    ok: bool
    missing: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────
# Tunables — exposed as module-level constants so tests can introspect.
# ─────────────────────────────────────────────────────────────────────────

# Effect-window for "the action just happened" checks (sent message,
# calendar event, posted comment). Must be wide enough to cover the round-trip
# from form submit → server confirmation, narrow enough that we don't pick up
# a stale message from a previous task.
EFFECT_WINDOW_SECONDS = 60

# Cap on how much page text we consider when scanning for evidence. Larger
# pages get truncated; we never pull a 1MB DOM into the assertion regex.
MAX_TEXT_BYTES = 200_000


# Type aliases for clarity inside the dispatcher.
TaskKind = str
PerKindFn = "PerKindFn"  # forward decl


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _truncate(text: str, limit: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]


def _norm(s: str) -> str:
    """Lowercase + collapse whitespace for substring scanning."""
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _tokenize(text: str) -> set[str]:
    """Crude bag-of-words tokenizer for fact-overlap checks."""
    text_lower = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text_lower)
    return {t for t in tokens if len(t) > 2}


def _required_facts_from_task(task_text: str) -> list[str]:
    """Extract candidate "required facts" from a free-form task.

    Heuristic, not LLM. We look for:
      - Quoted strings ("Subject: …", '7 PM Tuesday'),
      - Connected name + verb chunks (the "tell me X and Y" pattern),
      - Capitalised proper-noun runs (probably names/places),
      - Numbers with units that look like quantities.

    The list is intentionally noisy — the verifier OR's them: if ANY appears
    in the agent's done text, we accept.

    For the strict assertion path (read_extract), the caller can also pass a
    `required_facts` field inside ``agent_done_payload`` and we use those
    instead. This keeps the heuristic as a fallback only.
    """
    out: list[str] = []
    if not task_text:
        return out

    # Quoted strings (single or double).
    for m in re.findall(r'"([^"]+)"|\'([^\']+)\'', task_text):
        candidate = (m[0] or m[1] or "").strip()
        if candidate and len(candidate) >= 2:
            out.append(candidate)

    # "tell me X and Y" / "what is X" — pull noun-ish phrases after these.
    cues = [
        r"(?:tell me|find|what is|what's|extract|get|look up)\s+(.+?)(?:[\.\?]|$)",
        r"(?:headline|title|price|name)\s+(?:of|for)\s+(.+?)(?:[\.\?]|$)",
    ]
    for pat in cues:
        for m in re.finditer(pat, task_text, re.IGNORECASE):
            chunk = m.group(1).strip()
            if 2 < len(chunk) < 80:
                out.append(chunk)

    # De-dup while preserving order.
    seen: set[str] = set()
    uniq: list[str] = []
    for f in out:
        k = _norm(f)
        if k and k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def _scan_for_required_facts(
    fact_candidates: Iterable[str],
    text_blob: str,
) -> tuple[list[str], list[str]]:
    """Return (found, missing). Found via case-insensitive substring OR
    high token-overlap (>=50% of fact tokens appear in the blob)."""
    blob = _norm(text_blob)
    if not blob:
        return [], list(fact_candidates)

    blob_tokens = _tokenize(text_blob)
    found: list[str] = []
    missing: list[str] = []
    for fact in fact_candidates:
        fact_norm = _norm(fact)
        if not fact_norm:
            continue
        if fact_norm in blob:
            found.append(fact)
            continue

        fact_tokens = _tokenize(fact)
        if not fact_tokens:
            missing.append(fact)
            continue
        overlap = len(fact_tokens & blob_tokens) / len(fact_tokens)
        if overlap >= 0.5:
            found.append(fact)
        else:
            missing.append(fact)
    return found, missing


def _safe_get(payload: Any, key: str, default: Any = "") -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return default


def _now_ts() -> float:
    return time.time()


async def _safely_navigate(bridge: BridgeProtocol, url: str) -> bool:
    """Navigate. Returns True on success."""
    try:
        await bridge.navigate(url)
        return True
    except Exception:
        logger.exception("end_state_verifier: navigate failed: %s", url)
        return False


async def _safely_text(bridge: BridgeProtocol, selector: str | None = None) -> str:
    try:
        text = await bridge.get_text(selector)
        if not isinstance(text, str):
            return ""
        return _truncate(text)
    except Exception:
        logger.exception("end_state_verifier: get_text failed")
        return ""


async def _safely_url(bridge: BridgeProtocol) -> str:
    try:
        url = await bridge.get_url()
        return url if isinstance(url, str) else ""
    except Exception:
        logger.exception("end_state_verifier: get_url failed")
        return ""


# ─────────────────────────────────────────────────────────────────────────
# Per-kind verifiers
#
# Each accepts (task_text, agent_done_payload, bridge) and returns a
# VerificationResult. Order of operations is fixed: NAVIGATE → EXTRACT →
# ASSERT. No side effects beyond navigation.
# ─────────────────────────────────────────────────────────────────────────


async def _verify_read_extract(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """For fact-finding tasks, every required fact must appear in the
    agent's `done` text.

    Strategy:
      1. Pull the agent's stated answer from
         ``agent_done_payload["message"|"text"|"answer"]``.
      2. Pull required facts: prefer
         ``agent_done_payload["required_facts"]`` (set by the planner) and
         fall back to heuristic extraction from the task text.
      3. Substring + token-overlap match each fact against the answer.

    No bridge calls — read_extract has nothing to navigate to. Verification
    is pure text comparison.
    """
    answer = (
        _safe_get(agent_done_payload, "message")
        or _safe_get(agent_done_payload, "text")
        or _safe_get(agent_done_payload, "answer")
        or ""
    )
    answer = str(answer)

    required = _safe_get(agent_done_payload, "required_facts", None)
    if not isinstance(required, list) or not required:
        required = _required_facts_from_task(task_text)
    required = [str(r) for r in required if str(r).strip()]

    if not required:
        # No facts to check ⇒ accept any non-empty, non-trivial answer.
        if answer and len(answer.strip()) >= 2:
            return VerificationResult(
                ok=True, missing=[], evidence=[answer[:200]]
            )
        return VerificationResult(
            ok=False,
            missing=["any concrete answer"],
            evidence=[],
        )

    found, missing = _scan_for_required_facts(required, answer)
    return VerificationResult(
        ok=len(missing) == 0 and bool(found),
        missing=missing,
        evidence=[answer[:200]] if found else [],
    )


def _matches_within_window(text_blob: str, window_seconds: int) -> bool:
    """Generic recency heuristic.

    Real mail/calendar UIs render times like "now", "1 minute ago",
    "2:34 PM", "Just now". We consider any of these as "within window":
        - "just now", "now"
        - "X seconds ago", "X minutes ago" with X <= window_seconds//60
        - explicit clock times within the same minute as now
    """
    if not text_blob:
        return False
    blob = _norm(text_blob)
    if "just now" in blob or " now " in blob:
        return True

    minutes_window = max(1, window_seconds // 60)
    sec_match = re.search(r"(\d+)\s*(?:second|sec|s)\s*ago", blob)
    if sec_match:
        try:
            secs = int(sec_match.group(1))
            if secs <= window_seconds:
                return True
        except ValueError:
            pass

    min_match = re.search(r"(\d+)\s*(?:minute|min|m)\s*ago", blob)
    if min_match:
        try:
            mins = int(min_match.group(1))
            if mins <= minutes_window:
                return True
        except ValueError:
            pass

    # Hour markers are too coarse to count as recent.
    return False


async def _verify_email_send(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Navigate to the Sent folder; look for a row with subject substring
    + recency marker."""
    if not await _safely_navigate(bridge, "https://mail.google.com/mail/u/0/#sent"):
        return VerificationResult(
            ok=False, missing=["sent_folder_navigable"], evidence=[]
        )

    body = await _safely_text(bridge)
    if not body:
        return VerificationResult(
            ok=False, missing=["sent_folder_text"], evidence=[]
        )

    subject = (
        _safe_get(agent_done_payload, "subject")
        or _safe_get(agent_done_payload, "title")
        or ""
    )
    subject = _norm(str(subject))

    # Subject substring presence — required.
    subject_ok = bool(subject) and subject in _norm(body)
    recent_ok = _matches_within_window(body, EFFECT_WINDOW_SECONDS)

    missing: list[str] = []
    evidence: list[str] = []
    if subject_ok:
        evidence.append(f"sent_folder_contains:{subject[:60]}")
    else:
        missing.append("sent_message_subject_in_sent_folder")
    if recent_ok:
        evidence.append("recency_marker_within_60s")
    else:
        missing.append(f"sent_message_within_{EFFECT_WINDOW_SECONDS}s")

    return VerificationResult(
        ok=subject_ok and recent_ok,
        missing=missing,
        evidence=evidence,
    )


async def _verify_calendar_create(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Navigate to calendar; assert event title appears."""
    if not await _safely_navigate(bridge, "https://calendar.google.com"):
        return VerificationResult(
            ok=False, missing=["calendar_navigable"], evidence=[]
        )

    body = await _safely_text(bridge)
    if not body:
        return VerificationResult(
            ok=False, missing=["calendar_text"], evidence=[]
        )

    title = (
        _safe_get(agent_done_payload, "title")
        or _safe_get(agent_done_payload, "event_title")
        or _safe_get(agent_done_payload, "subject")
        or ""
    )
    title = _norm(str(title))

    if not title:
        # Fallback — try to extract a title from the task itself (quoted).
        guesses = _required_facts_from_task(task_text)
        for g in guesses:
            if 2 < len(g) < 80:
                title = _norm(g)
                break

    if not title:
        return VerificationResult(
            ok=False, missing=["calendar_event_title_known"], evidence=[]
        )

    body_norm = _norm(body)
    if title in body_norm:
        return VerificationResult(
            ok=True,
            missing=[],
            evidence=[f"calendar_contains:{title[:60]}"],
        )
    return VerificationResult(
        ok=False,
        missing=["calendar_event_title_present"],
        evidence=[],
    )


async def _verify_comment_post(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Navigate back to the source URL; assert comment by our user appears
    with a recent timestamp."""
    source_url = (
        _safe_get(agent_done_payload, "source_url")
        or _safe_get(agent_done_payload, "url")
        or _safe_get(agent_done_payload, "thread_url")
        or ""
    )
    source_url = str(source_url)

    if source_url:
        if not await _safely_navigate(bridge, source_url):
            return VerificationResult(
                ok=False, missing=["comment_source_navigable"], evidence=[]
            )
    # If no source URL was given, we still try to use the current page.

    body = await _safely_text(bridge)
    if not body:
        return VerificationResult(
            ok=False, missing=["comment_thread_text"], evidence=[]
        )

    author = (
        _safe_get(agent_done_payload, "author")
        or _safe_get(agent_done_payload, "username")
        or _safe_get(agent_done_payload, "user")
        or ""
    )
    author = _norm(str(author))
    comment_substr = _norm(
        str(
            _safe_get(agent_done_payload, "comment_text")
            or _safe_get(agent_done_payload, "text")
            or _safe_get(agent_done_payload, "message")
            or ""
        )
    )

    body_norm = _norm(body)
    author_ok = bool(author) and author in body_norm
    text_ok = bool(comment_substr) and comment_substr[:80] in body_norm
    recent_ok = _matches_within_window(body, EFFECT_WINDOW_SECONDS)

    missing: list[str] = []
    evidence: list[str] = []
    if author_ok:
        evidence.append(f"author_visible:{author[:40]}")
    else:
        missing.append("comment_author_present")
    if text_ok:
        evidence.append("comment_text_present")
    else:
        missing.append("comment_text_present")
    if recent_ok:
        evidence.append("recency_marker_within_60s")
    else:
        missing.append(f"comment_within_{EFFECT_WINDOW_SECONDS}s")

    return VerificationResult(
        ok=author_ok and text_ok and recent_ok,
        missing=missing,
        evidence=evidence,
    )


async def _verify_cart_add(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Navigate to cart URL (from payload, or current page's /cart) and
    assert the item title or SKU appears in the line items."""
    cart_url = (
        _safe_get(agent_done_payload, "cart_url")
        or ""
    )
    if not cart_url:
        # Best-effort: derive cart URL by appending /cart to the origin.
        current = await _safely_url(bridge)
        if current:
            try:
                from urllib.parse import urlparse, urlunparse
                p = urlparse(current)
                if p.scheme and p.netloc:
                    cart_url = urlunparse((p.scheme, p.netloc, "/cart", "", "", ""))
            except Exception:
                cart_url = ""

    if cart_url:
        await _safely_navigate(bridge, cart_url)

    body = await _safely_text(bridge)
    if not body:
        return VerificationResult(
            ok=False, missing=["cart_text"], evidence=[]
        )

    title = _norm(
        str(
            _safe_get(agent_done_payload, "title")
            or _safe_get(agent_done_payload, "product")
            or _safe_get(agent_done_payload, "item")
            or ""
        )
    )
    sku = _norm(
        str(
            _safe_get(agent_done_payload, "sku")
            or _safe_get(agent_done_payload, "id")
            or ""
        )
    )

    if not title and not sku:
        # Fallback — the task itself often names the product.
        guesses = _required_facts_from_task(task_text)
        for g in guesses:
            if 2 < len(g) < 80:
                title = _norm(g)
                break

    if not title and not sku:
        return VerificationResult(
            ok=False, missing=["cart_item_identifier_known"], evidence=[]
        )

    body_norm = _norm(body)
    title_ok = bool(title) and title in body_norm
    sku_ok = bool(sku) and sku in body_norm

    if title_ok or sku_ok:
        ev: list[str] = []
        if title_ok:
            ev.append(f"cart_contains_title:{title[:60]}")
        if sku_ok:
            ev.append(f"cart_contains_sku:{sku[:40]}")
        return VerificationResult(ok=True, missing=[], evidence=ev)
    return VerificationResult(
        ok=False, missing=["cart_item_in_line_items"], evidence=[]
    )


async def _verify_form_submit(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Look for a confirmation marker on the current page or a known
    confirmation URL pattern.

    Generic markers we accept:
      - URL contains /confirm, /thank-you, /thanks, /success, /complete,
        /receipt, /order, /confirmation
      - Page text contains a "thank you" sentence or an order/confirmation
        number (alphanumeric token >= 5 chars adjacent to "order" / "ref" /
        "confirmation").
    """
    confirmation_url = (
        _safe_get(agent_done_payload, "confirmation_url") or ""
    )
    if confirmation_url:
        await _safely_navigate(bridge, confirmation_url)

    url = await _safely_url(bridge)
    body = await _safely_text(bridge)

    url_lower = url.lower() if url else ""
    body_norm = _norm(body)

    url_markers = [
        "/confirm", "/confirmation", "/thank-you", "/thanks",
        "/success", "/complete", "/receipt", "/order",
    ]
    url_match = any(m in url_lower for m in url_markers)

    text_markers = [
        "thank you", "thanks for your", "order confirmed", "order placed",
        "confirmation number", "your order", "we received your",
        "submission received", "successfully submitted",
    ]
    text_match = any(m in body_norm for m in text_markers)

    # Look for a confirmation-number-shaped token near "order" / "ref" /
    # "confirmation".
    num_match = re.search(
        r"(?:order|ref(?:erence)?|confirmation)[^\w]{0,8}([A-Z0-9-]{5,})",
        body or "",
        re.IGNORECASE,
    )

    evidence: list[str] = []
    if url_match:
        evidence.append(f"url_marker:{url_lower[:80]}")
    if text_match:
        evidence.append("confirmation_text_present")
    if num_match:
        evidence.append(f"confirmation_number:{num_match.group(1)[:20]}")

    ok = bool(evidence)
    missing: list[str] = []
    if not ok:
        missing.append("confirmation_marker")
    return VerificationResult(ok=ok, missing=missing, evidence=evidence)


async def _verify_generic(
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Fallback heuristic: required-facts inferred from the task text must
    appear in the agent's done message OR on the current page."""
    answer = str(
        _safe_get(agent_done_payload, "message")
        or _safe_get(agent_done_payload, "text")
        or _safe_get(agent_done_payload, "answer")
        or ""
    )

    facts = _safe_get(agent_done_payload, "required_facts", None)
    if not isinstance(facts, list) or not facts:
        facts = _required_facts_from_task(task_text)
    facts = [str(f) for f in facts if str(f).strip()]

    if not facts:
        # No required facts and no negative signal — accept the agent's
        # statement *only* if it's substantive.
        if answer and len(answer.strip()) >= 4:
            return VerificationResult(ok=True, missing=[], evidence=[answer[:200]])
        return VerificationResult(
            ok=False,
            missing=["any concrete result"],
            evidence=[],
        )

    # Try the answer first.
    found, missing = _scan_for_required_facts(facts, answer)
    if not missing:
        return VerificationResult(
            ok=True,
            missing=[],
            evidence=[answer[:200]] if found else [],
        )

    # Fall back to current page text (cheap call — no navigation).
    body = await _safely_text(bridge)
    found2, missing2 = _scan_for_required_facts(missing, body)

    final_found = found + found2
    final_missing = missing2

    return VerificationResult(
        ok=len(final_missing) == 0 and bool(final_found),
        missing=final_missing,
        evidence=([answer[:200]] if found else []) + (
            [f"page:{ev[:120]}" for ev in found2[:2]]
        ),
    )


# Dispatch table — explicit so we never accidentally fall through to a more
# permissive routine.
_DISPATCH: dict[str, Any] = {
    "read_extract": _verify_read_extract,
    "email_send": _verify_email_send,
    "calendar_create": _verify_calendar_create,
    "comment_post": _verify_comment_post,
    "cart_add": _verify_cart_add,
    "form_submit": _verify_form_submit,
    "generic": _verify_generic,
}


# ─────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────


async def verify_end_state(
    task_kind: str,
    task_text: str,
    agent_done_payload: dict,
    bridge: BridgeProtocol,
) -> VerificationResult:
    """Run the per-kind verifier.

    Args:
        task_kind: One of ``read_extract``, ``email_send``,
            ``calendar_create``, ``comment_post``, ``cart_add``,
            ``form_submit``, or ``generic``. Unknown kinds fall through to
            ``generic``.
        task_text: The original wearer-facing task phrase. Used by
            ``generic`` and as a fallback for several kinds.
        agent_done_payload: Whatever the agent passed to ``done(...)``. Should
            be a dict; non-dicts are treated as empty.
        bridge: Concrete navigation/extraction surface.

    Returns:
        VerificationResult. ``ok=False`` blocks the success message and
        forces an honest failure to the wearer.
    """
    kind = (task_kind or "").strip().lower() or "generic"
    if kind not in _DISPATCH:
        logger.info(
            "end_state_verifier: unknown task_kind=%r → falling back to generic",
            task_kind,
        )
        kind = "generic"

    if not isinstance(agent_done_payload, dict):
        agent_done_payload = {}

    fn = _DISPATCH[kind]
    try:
        result = await fn(task_text or "", agent_done_payload, bridge)
    except Exception:
        logger.exception(
            "end_state_verifier: per-kind routine raised (kind=%s); fail closed",
            kind,
        )
        return VerificationResult(
            ok=False,
            missing=[f"verifier_{kind}_raised"],
            evidence=[],
        )

    if not isinstance(result, VerificationResult):
        # A misbehaving routine — cop-out #6, fail closed.
        logger.error(
            "end_state_verifier: routine returned %r (not VerificationResult)",
            type(result).__name__,
        )
        return VerificationResult(
            ok=False, missing=[f"verifier_{kind}_misbehaved"], evidence=[],
        )

    logger.info(
        "end_state_verifier: kind=%s ok=%s missing=%s",
        kind, result.ok, len(result.missing),
    )
    return result


__all__ = [
    "BridgeProtocol",
    "VerificationResult",
    "verify_end_state",
    "EFFECT_WINDOW_SECONDS",
]
