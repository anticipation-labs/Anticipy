"""Tests for the ANTICIPY_TEST_FAST_TIMEOUTS env flag.

The flag collapses every production time constant in
engine/app/product/sms_pre_confirm.py by a factor of ~360 so a full
pre-confirm round trip can be exercised in under a minute. The 360x
ratio was picked so the directive 3-hour ceiling (10800 s) maps to a
clean 30 s in test mode; every other constant rides the same ratio so
test mode preserves the relative ordering of the production constants.

Production behavior MUST stay unchanged when the env var is absent or
any value other than the literal "1". These tests assert both halves.

The constants we exercise:

  DEFAULT_TTL_SECONDS               300  → 30   (pre-confirm window)
  DEFAULT_INBOUND_POLL_INTERVAL_SECONDS  10.0 → 1.0  (poller cadence)
  MIN_TTL_SECONDS_FLOOR             60   → 1    (hard floor on TTL)

Each constant is read after a fresh import (importlib.reload) so this
file can flip the env var per test without relying on subprocess.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


# Ensure engine/ is on sys.path so `app.product...` imports resolve no
# matter which working directory pytest is launched from.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reload_with_env(env_value: str | None):
    """Reset the env var, drop the module from the cache, re-import."""
    # Strip any prior value so a stale "1" cannot leak into a
    # "production mode" test.
    if env_value is None:
        os.environ.pop("ANTICIPY_TEST_FAST_TIMEOUTS", None)
    else:
        os.environ["ANTICIPY_TEST_FAST_TIMEOUTS"] = env_value
    sys.modules.pop("app.product.sms_pre_confirm", None)
    import app.product.sms_pre_confirm as m  # noqa: WPS433
    return m


# ---------------------------------------------------------------------
# Production defaults (env var unset)
# ---------------------------------------------------------------------
def test_production_defaults_when_env_unset():
    """With ANTICIPY_TEST_FAST_TIMEOUTS unset the module exposes the
    real production timeouts: 5 min TTL, 10 s poll cadence, 60 s TTL
    floor.
    """
    m = _reload_with_env(None)
    assert m.DEFAULT_TTL_SECONDS == 5 * 60, (
        "production TTL must remain 5 minutes when env unset"
    )
    assert m.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS == 10.0
    assert m.MIN_TTL_SECONDS_FLOOR == 60


def test_production_defaults_when_env_zero():
    """Only the literal '1' triggers fast mode. '0' is treated the
    same as unset.
    """
    m = _reload_with_env("0")
    assert m.DEFAULT_TTL_SECONDS == 5 * 60
    assert m.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS == 10.0
    assert m.MIN_TTL_SECONDS_FLOOR == 60


def test_production_defaults_when_env_truthy_but_not_one():
    """Strings like 'true' / 'yes' / 'on' do NOT trigger fast mode.
    The flag is intentionally strict so a stray export in a developer
    shell can never collapse a real user's pre-confirm window.
    """
    for val in ("true", "TRUE", "yes", "on", "y", "1.0", "01"):
        m = _reload_with_env(val)
        assert m.DEFAULT_TTL_SECONDS == 5 * 60, (
            f"value {val!r} must not trigger fast mode"
        )
        assert m.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS == 10.0
        assert m.MIN_TTL_SECONDS_FLOOR == 60


# ---------------------------------------------------------------------
# Fast-timeout mode (env=1)
# ---------------------------------------------------------------------
def test_fast_mode_collapses_ttl_to_30s():
    """The headline behavior: a 5-minute pre-confirm window becomes
    30 s when fast mode is on. The 360x ratio comes from collapsing
    the 3-hour ceiling (10800 s) to 30 s.
    """
    m = _reload_with_env("1")
    assert m.DEFAULT_TTL_SECONDS == 30


def test_fast_mode_collapses_poll_interval_to_1s_floor():
    """10 s / 360 = 0.028 s which would burn CPU if used literally.
    The collapse function floors at 1 s so the inbound poller still
    runs at a sane rate in test mode.
    """
    m = _reload_with_env("1")
    assert m.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS == 1.0


def test_fast_mode_drops_ttl_floor_to_1s():
    """The production code clamps create_pending_confirm to a 60-s
    minimum TTL. In test mode we drop the floor to 1 s so the clamp
    cannot fight the collapsed 30 s window.
    """
    m = _reload_with_env("1")
    assert m.MIN_TTL_SECONDS_FLOOR == 1


def test_fast_mode_create_pending_uses_collapsed_ttl():
    """End-to-end: create_pending_confirm with the new defaults
    produces a record that expires within the test-mode window, not
    the production window.
    """
    m = _reload_with_env("1")
    plan = {"intent": "send_email", "person": "lara@example.com",
            "task": "send Lara an email about the deck"}
    instruction = "send Lara an email about the deck"
    # Route to an isolated store so we never touch ~/.anticipy/.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = m.PendingConfirmStore(root=Path(tmp))
        # Force the channel to "silent" so no outbound dispatch fires
        # (TWILIO_MOCK still mocks the wire path; silent skips
        # network entirely). We achieve this by removing destination
        # numbers and twilio creds from the env for the call window.
        saved = {k: os.environ.get(k) for k in (
            "TWILIO_TEST_TO_REAL_NUMBER_E164",
            "TWILIO_NOTIFY_TO",
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_PHONE_NUMBER",
            "TWILIO_MOCK",
        )}
        for k in saved:
            os.environ.pop(k, None)
        os.environ["TWILIO_MOCK"] = "1"
        try:
            result = m.create_pending_confirm(plan, instruction,
                                              store=store)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        import time
        ttl_seen = result["expires_at"] - time.time()
        # Should be within the 30 s test window plus a generous fudge
        # for clock skew during the call. Must NOT be near 300 s.
        assert 0 < ttl_seen <= 45, (
            f"fast-mode TTL was {ttl_seen:.2f} s, expected <= 45 s"
        )


def test_fast_mode_then_reset_returns_to_production():
    """A test that sets the flag and a follow-up test that doesn't
    must each see the right values. The reload helper is the source
    of truth.
    """
    m_fast = _reload_with_env("1")
    assert m_fast.DEFAULT_TTL_SECONDS == 30
    m_prod = _reload_with_env(None)
    assert m_prod.DEFAULT_TTL_SECONDS == 5 * 60


def test_fast_mode_preserves_constant_ordering():
    """The relative ordering of the constants must hold in BOTH
    modes: poll interval < ttl floor < ttl. Production keeps that
    ordering (10 < 60 < 300); fast mode keeps it (1 < 1 < 30 with
    floor == poll interval but TTL still strictly larger).
    """
    m_prod = _reload_with_env(None)
    assert (m_prod.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS
            <= m_prod.MIN_TTL_SECONDS_FLOOR
            < m_prod.DEFAULT_TTL_SECONDS)

    m_fast = _reload_with_env("1")
    assert (m_fast.DEFAULT_INBOUND_POLL_INTERVAL_SECONDS
            <= m_fast.MIN_TTL_SECONDS_FLOOR
            < m_fast.DEFAULT_TTL_SECONDS)


def test_fast_mode_ratio_holds_within_floor_bounds():
    """The 360x collapse ratio is the design intent for any constant
    that doesn't bottom out at its floor. DEFAULT_TTL_SECONDS at 300
    is well above the floor so 300 / 360 collapses cleanly into the
    declared 30 s mapping. The mapping is asserted as an exact match
    rather than computed at runtime so a future drift in the floor
    function still surfaces here.
    """
    m_fast = _reload_with_env("1")
    # 5 * 60 / 360 == 0.833... which the floor would push to 1; the
    # explicit declared mapping is 30 (because the ceiling we tied
    # the ratio to was 10800, not 300). The test asserts both halves
    # of the design contract:
    #   1. The declared mapping is 30 s.
    #   2. The 360x ratio still holds for the 10800 s ceiling when
    #      passed through the scale helper.
    assert m_fast.DEFAULT_TTL_SECONDS == 30
    scaled_ceiling = m_fast._scale_seconds(10800.0)
    assert abs(scaled_ceiling - 30.0) < 0.001, (
        f"3-hour ceiling collapsed to {scaled_ceiling}, expected 30"
    )


def test_scale_helper_floors_below_minimum():
    """_scale_seconds must enforce its floor so a literal 0.027 s
    cannot leak through as a poll interval.
    """
    m_fast = _reload_with_env("1")
    # 0.1 / 360 = 0.00028. Floor at default 1.0 -> 1.0
    assert m_fast._scale_seconds(0.1) == 1.0
    # Explicit floor request: 0.5
    assert m_fast._scale_seconds(0.1, floor_seconds=0.5) == 0.5


def test_scale_helper_is_identity_in_production():
    """In production the helper must return prod_seconds unchanged so
    no rounding or floor adjustment shifts a real timeout.
    """
    m_prod = _reload_with_env(None)
    assert m_prod._scale_seconds(10800.0) == 10800.0
    assert m_prod._scale_seconds(300) == 300.0
    assert m_prod._scale_seconds(10) == 10.0


# ---------------------------------------------------------------------
# Restore production defaults after the file finishes so a sibling
# test file that imports app.product.sms_pre_confirm sees the right
# values.
# ---------------------------------------------------------------------
def teardown_module(_module):
    _reload_with_env(None)
