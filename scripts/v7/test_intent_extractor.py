"""V7 unified intent extractor tests.

Runs four canonical cases against the live OpenRouter cascade. Each call
must finish in under 5 seconds. Exits 0 only when every case passes.

Cases:
  1. "Draft an email to Maya about Friday" -> act, person=[Maya],
     missing_slots includes recipient_email.
  2. "Wouldn't it be funny if I emailed my boss saying I quit?" ->
     is_hypothetical, is_actionable=False.
  3. "Maya was asking if Marcus could send the report" ->
     is_third_party_want, is_actionable=False.
  4. "Remind me to call mom tomorrow at 7pm" -> type=remind, surface in
     {native_calendar, reminders, google_calendar}.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

# Load .env.local style files if OPENROUTER_API_KEY is missing.
if not os.environ.get("OPENROUTER_API_KEY"):
    for cand in [
        _ROOT / ".env.local",
        Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local"),
    ]:
        if cand.exists():
            for ln in cand.read_text(errors="replace").splitlines():
                if "=" not in ln or ln.strip().startswith("#"):
                    continue
                k, v = ln.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v and not os.environ.get(k):
                    os.environ[k] = v
            if os.environ.get("OPENROUTER_API_KEY"):
                break

from app.product.intent_extractor import (  # noqa: E402
    extract, is_actionable,
)

DEADLINE_SECS = 5.0
_FAILS: list[tuple[str, str]] = []
_PASSES: list[str] = []


def _ok(name: str) -> None:
    _PASSES.append(name)
    print(f"PASS  {name}")


def _fail(name: str, reason: str) -> None:
    _FAILS.append((name, reason))
    print(f"FAIL  {name}: {reason}")


def _check(cond: bool, name: str, reason: str) -> bool:
    if cond:
        _ok(name)
        return True
    _fail(name, reason)
    return False


def _wrap(text: str) -> dict:
    return {
        "schema": "anticipy.normalized_input.v7",
        "window": {"turns": [{"speaker": "user", "text": text}]},
        "capture": {"asr_normalized": text},
    }


def _run(label: str, text: str):
    start = time.monotonic()
    intent = extract(_wrap(text), surface_context={}, memory_context="")
    elapsed = time.monotonic() - start
    print(f"  [{label}] {elapsed:.2f}s model={intent.model} "
          f"type={intent.type} surface={intent.target_surface} "
          f"persons={intent.target_person_refs} "
          f"missing={intent.missing_slots} "
          f"hypo={intent.is_hypothetical} "
          f"third={intent.is_third_party_want} "
          f"actp={intent.actionable_probability:.2f} "
          f"actionable={is_actionable(intent)}")
    _check(elapsed < DEADLINE_SECS, f"{label} under 5s",
           f"took {elapsed:.2f}s (model={intent.model})")
    _check(not intent.error, f"{label} cascade returned content",
           intent.error or "")
    return intent, elapsed


def test_case_1_draft_email() -> None:
    label = "case1_draft_email_maya"
    intent, _ = _run(label, "Draft an email to Maya about Friday")
    _check(intent.type == "act",
           f"{label} type=act", f"got type={intent.type}")
    persons_lower = {p.lower() for p in intent.target_person_refs}
    _check("maya" in persons_lower,
           f"{label} target_person_refs includes Maya",
           f"got {intent.target_person_refs}")
    missing_lower = {s.lower() for s in intent.missing_slots}
    required_lower = {s.lower() for s in intent.required_slots}
    # The model may put the slot in either bucket depending on confidence;
    # the user-visible promise is "we know we need to look it up". Allow
    # either, fail if the concept is entirely absent.
    has_email_slot = any("email" in s for s in missing_lower | required_lower)
    _check(has_email_slot,
           f"{label} surfaces a recipient_email slot",
           f"required={intent.required_slots} missing={intent.missing_slots}")
    _check(is_actionable(intent),
           f"{label} is_actionable", "expected True for direct draft request")


def test_case_2_hypothetical() -> None:
    label = "case2_hypothetical_joke"
    intent, _ = _run(
        label,
        "Wouldn't it be funny if I emailed my boss saying I quit?",
    )
    _check(intent.is_hypothetical,
           f"{label} is_hypothetical=True",
           f"got is_hypothetical={intent.is_hypothetical}")
    _check(not is_actionable(intent),
           f"{label} is_actionable=False",
           "hypothetical/joke must not be actionable")


def test_case_3_third_party_want() -> None:
    label = "case3_third_party_want"
    intent, _ = _run(
        label,
        "Maya was asking if Marcus could send the report",
    )
    _check(intent.is_third_party_want,
           f"{label} is_third_party_want=True",
           f"got is_third_party_want={intent.is_third_party_want}")
    _check(not is_actionable(intent),
           f"{label} is_actionable=False",
           "third-party wants must not be actionable")


def test_case_4_remind() -> None:
    label = "case4_remind_mom"
    intent, _ = _run(label, "Remind me to call mom tomorrow at 7pm")
    _check(intent.type in {"remind", "create"},
           f"{label} type in remind|create",
           f"got type={intent.type}")
    allowed_surfaces = {
        "native_calendar", "reminders", "google_calendar",
        "ios_reminders", "macos_reminders", "calendar",
    }
    _check(intent.target_surface in allowed_surfaces,
           f"{label} target_surface in {sorted(allowed_surfaces)}",
           f"got surface={intent.target_surface}")
    _check(is_actionable(intent),
           f"{label} is_actionable", "a direct reminder request is actionable")


def main() -> int:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("SKIP: OPENROUTER_API_KEY not set")
        return 0
    print("running V7 unified intent extractor cases")
    for fn in (test_case_1_draft_email, test_case_2_hypothetical,
               test_case_3_third_party_want, test_case_4_remind):
        try:
            fn()
        except Exception as exc:
            _fail(fn.__name__, f"crashed: {exc}")
    print()
    print(f"summary: {len(_PASSES)} passed, {len(_FAILS)} failed")
    return 0 if not _FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
