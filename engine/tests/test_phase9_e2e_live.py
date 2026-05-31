"""Phase 9 gate: end-to-end integration test on the owner's live machine.

This test exercises the full Anticipy pipeline that ARCHITECTURE.md
section 14 names as the Phase 9 gate:

    listen.inject -> classify -> plan -> dispatch -> SMS preconfirm
    -> wait for user reply -> simulate YES via /api/sms/inbound
    -> verify the action dispatch fires (Gmail draft via extension
       native bridge surface) -> assert timeline rows materialize.

Hard constraints (per Phase 9 instructions and project memory):

  * NEVER send real email or SMS to anyone other than
    ``omarkebrahim+anticipy-test@gmail.com`` (email recipient) or
    ``+16047245161`` (SMS recipient). The test enforces this by
    setting ``TWILIO_MOCK=1`` and asserting that every outbound
    Twilio call returns ``mock=True``.
  * Read-only with respect to production code. The test only
    monkeypatches isolated entry points (SurfaceRuntime, browser
    surface picker, CDP probe) so the real engine code path is
    exercised with deterministic substitutes for external network
    IO.
  * Uses a temp ``ANTICIPY_TIMELINE_PATH`` and temp
    ``ANTICIPY_V7_PENDING_CONFIRM_ROOT`` so the live user timeline
    at ``~/.anticipy/v7/timeline.jsonl`` and the live pending
    confirm store are NOT mutated by this test.

The test verifies the 9 sub-steps named in the Phase 9 prompt by
splitting them across focused test functions; each one cites the
specific artifact (timeline row, response payload field) the
Phase 9 report cross-references.

Important note on actual product behavior versus the Phase 9
prompt's idealized flow: the production /api/act top-level
short-circuits explicit "draft an email to X with subject Y
saying Z" instructions through ``parse_draft_intent`` /
``_try_direct_gmail_draft`` BEFORE reaching the SMS preconfirm
gate. The gate's docstring explicitly notes this:

  >>> # Z-001 uses the explicit "Draft an email to lara@... saying"
  >>> # shape, which `parse_draft_intent` catches above and returns
  >>> # at _try_direct_gmail_draft. That early return runs BEFORE this
  >>> # gate, so Z-001's draft-only path is unaffected.

Therefore the Phase 9 prompt's idealized "inject draft + receive
preconfirm SMS" flow does NOT match production code today. The
test reflects what the code actually does: explicit drafts go
straight to the extension bridge dispatch, and the preconfirm
gate fires only for non-draft "send/post/pay" verbs OR for
ambiguous instructions where parse_draft_intent returns None.
The Phase 9 report records this discrepancy honestly per
VERIFICATION_PROTOCOL.md.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

import pytest


# ---------------------------------------------------------------------------
# Bootstrap engine import path. Same pattern as the existing
# test_action_dispatch_via_extension and test_engine_port_reclaim suites.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE_ROOT = os.path.dirname(_HERE)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# Pin a high port string so the eager `_acquire_singleton_lock` import in
# server.py never tries to clobber the live engine's lock file at 8731.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59731")

# Mark this run as test-only so any code that branches on the test flag
# (e.g. faster sweeper cadence) takes the test path.
os.environ.setdefault("ANTICIPY_TEST_FAST_TIMEOUTS", "1")


# ---------------------------------------------------------------------------
# Constants for the Phase 9 scenario. These are the ONLY recipients the
# test is allowed to address. The per-test fixtures below enforce that
# every outbound Twilio call is mocked so no real SMS leaves the host.
# ---------------------------------------------------------------------------

EMAIL_RECIPIENT = "omarkebrahim+anticipy-test@gmail.com"
SMS_RECIPIENT = "+16047245161"

# Two scenario texts. The first matches the Phase 9 prompt verbatim
# (uses the verb "draft"). The second is the variant the SMS preconfirm
# gate actually triggers for (uses the verb "send"). Both flow through
# the same engine entry points; the difference is which downstream gate
# fires.
SCENARIO_DRAFT = (
    "Draft a thank you email to "
    f"{EMAIL_RECIPIENT} with subject Friday demo saying "
    "Thanks for the great Friday demo, follow up next week."
)
SCENARIO_SEND = (
    "send "
    f"{EMAIL_RECIPIENT} the Friday demo follow up email about next week"
)


# ---------------------------------------------------------------------------
# Stub SurfaceRuntime so the test never touches the live native bridge
# on :7777. The stub mirrors the real receipt shape ``surface_runtime``
# returns so ``bridge_extension.dispatch`` builds the same response a
# real Chrome would.
# ---------------------------------------------------------------------------


class _StubRuntime:
    """In-test replacement for ``SurfaceRuntime`` that records every
    invocation so the test can assert on the verb + target."""

    captured: list[dict[str, Any]] = []

    def __init__(self, *a, **kw) -> None:
        pass

    def available(self) -> bool:
        return True

    def availability(self) -> dict[str, Any]:
        return {"ok": True, "surface": {"kind": "browser"}}

    def run_browser_task(self, *, verb, target, task):
        _StubRuntime.captured.append(
            {"verb": verb, "target": target, "task": task})
        url = target if target else "https://mail.google.com/mail/"
        return {
            "ok": True,
            "surface": {"kind": "browser", "url": url},
            "proof": {
                "url": url,
                "screenshot_path": "/tmp/anticipy-phase9-stub.png",
            },
            "source": "chrome_extension_native_messaging",
            "error": "",
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_state(monkeypatch) -> Iterator[dict[str, Path]]:
    """Route the unified timeline + pending confirm store to a tmp dir.

    The Phase 9 prompt forbids mutating the real ``~/.anticipy/v7/``
    state. Both the timeline writer and the SMS pending-confirm store
    honor env overrides; pointing them at a tmpdir guarantees a clean,
    asserttable surface for the test.
    """
    _StubRuntime.captured = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        timeline_path = tmp_path / "timeline.jsonl"
        confirm_root = tmp_path / "pending_confirms"
        confirm_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("ANTICIPY_TIMELINE_PATH", str(timeline_path))
        monkeypatch.setenv(
            "ANTICIPY_V7_PENDING_CONFIRM_ROOT", str(confirm_root))
        yield {"timeline": timeline_path, "confirm_root": confirm_root}


@pytest.fixture
def mock_twilio_env(monkeypatch) -> None:
    """Force every outbound Twilio call onto the mock branch.

    The directive in feedback_no_real_send_testing.md says: NEVER send
    real SMS during tests. ``TWILIO_MOCK=1`` plus
    ``TWILIO_TEST_TO_REAL_NUMBER=0`` puts every Twilio send through the
    mock path inside ``send_sms_sync`` which returns
    ``{ok: True, mock: True, mock_reason: ...}`` and writes the
    timeline row exactly as the live path would.
    """
    monkeypatch.setenv("TWILIO_MOCK", "1")
    monkeypatch.setenv("TWILIO_TEST_TO_REAL_NUMBER", "0")
    monkeypatch.setenv("TWILIO_TEST_TO_REAL_NUMBER_E164", SMS_RECIPIENT)
    monkeypatch.setenv("TWILIO_NOTIFY_TO", SMS_RECIPIENT)
    # The website-side broker would otherwise make a real HTTP call to
    # anticipy.ai; disable it.
    monkeypatch.delenv("ANTICIPY_TWILIO_BROKER", raising=False)


@pytest.fixture
def stub_surface_runtime(monkeypatch) -> type[_StubRuntime]:
    """Replace SurfaceRuntime everywhere it's imported so the bridge
    dispatcher never tries to talk to the live native-messaging daemon
    on :7777. The test asserts on ``_StubRuntime.captured`` to verify
    the dispatcher reached the bridge layer with the right verb +
    target.
    """
    _StubRuntime.captured = []
    monkeypatch.setattr(
        "app.product.surface_runtime.SurfaceRuntime", _StubRuntime)
    return _StubRuntime


@pytest.fixture
def force_extension_surface(monkeypatch) -> None:
    """Force the engine's surface picker to report the extension bridge
    so ``_dispatch_via_extension_bridge`` is exercised even when the
    test host's CDP on :9222 might be reachable.
    """
    monkeypatch.setattr(
        "app.product.server._browser_surface",
        lambda: "extension_native_bridge",
        raising=False,
    )
    monkeypatch.setattr(
        "app.product.server._ensure_cdp_chrome",
        lambda: False,
        raising=False,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_timeline(path: Path) -> list[dict[str, Any]]:
    """Return every timeline row as a list of dicts, oldest first."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _kinds(rows: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("kind")) for r in rows]


def _make_client():
    """TestClient bound to the engine's FastAPI app.

    Imported lazily so the env vars set by fixtures take effect BEFORE
    the heavy server module loads. server.py reads
    ``ANTICIPY_ENGINE_PORT`` at import time for its singleton lock.
    """
    from app.product import server as _srv
    from fastapi.testclient import TestClient
    return _srv, TestClient(_srv.app)


# ---------------------------------------------------------------------------
# Sub-step tests
# ---------------------------------------------------------------------------


def test_phase9_step1_listen_inject_accepts_scenario(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-step 1: POST /api/listen/inject accepts the Phase 9 scenario
    transcript and returns a structured response with an ingest id and
    a plan / pending entry.

    Artifact: response JSON body with ingest_id + transcript echo.
    """
    _srv, client = _make_client()
    resp = client.post(
        "/api/listen/inject",
        json={"text": SCENARIO_DRAFT, "source": "phase9-e2e"},
    )
    assert resp.status_code == 200, (
        f"listen/inject returned {resp.status_code} "
        f"body={resp.text[:300]}"
    )
    body = resp.json()
    assert body.get("ingest_id"), f"missing ingest_id in {body!r}"
    assert body.get("transcript") == SCENARIO_DRAFT
    # The outcome label is allowed to vary because the LLM-driven
    # classifier may bucket this to DEFERRED (no LLM in test env),
    # ACTION, or LIFE_LOG. The contract this step verifies is that
    # the transcript was accepted and ingested through the same
    # entry point a real voice transcript would use.
    valid_outcomes = {
        "LIFE_LOG", "TRIVIA_FIRE", "ACTION", "DECLINED",
        "DEFERRED", "CONFIRMED",
    }
    assert body.get("outcome") in valid_outcomes, (
        f"unexpected outcome {body.get('outcome')!r}"
    )


def test_phase9_step2_parse_draft_intent_extracts_recipient(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-step 2: The deterministic regex parser
    ``parse_draft_intent`` (used by /api/act's fast path) extracts the
    recipient email and subject from the scenario instruction. This is
    the path /api/act takes BEFORE consulting the LLM planner.

    Artifact: ``DraftRequest`` dataclass with non-empty to + subject.
    """
    from app.action_engine.gmail_compose import parse_draft_intent
    parsed = parse_draft_intent(SCENARIO_DRAFT)
    assert parsed is not None, (
        f"parse_draft_intent rejected the scenario text {SCENARIO_DRAFT!r}"
    )
    assert parsed.to == EMAIL_RECIPIENT, (
        f"recipient mismatch: got {parsed.to!r}, "
        f"expected {EMAIL_RECIPIENT!r}"
    )
    assert parsed.subject, "subject must be non-empty"
    # The body either contains the dictation OR the default Anticipy
    # placeholder when nothing followed "saying".
    assert parsed.body, "body must be non-empty"


def test_phase9_step3_api_act_routes_explicit_draft_through_bridge(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-step 3: POST /api/act with the explicit "draft to X with
    subject Y saying Z" instruction routes through the extension
    native bridge dispatch (via parse_draft_intent fast path), since
    CDP on :9222 is patched unavailable.

    Artifact: response.path == "extension_native_bridge" and the
    stub SurfaceRuntime recorded a run_browser_task call.

    Note: this path BYPASSES the SMS preconfirm gate. The gate's
    docstring documents this: explicit drafts are draft-only and
    safe; only ambiguous or send-shape instructions get gated.
    Step 4 below covers the gate path.
    """
    _srv, client = _make_client()
    _srv._LISTEN["pending"] = None
    resp = client.post(
        "/api/act", json={"instruction": SCENARIO_DRAFT})
    assert resp.status_code in (200, 502), (
        f"unexpected status {resp.status_code} "
        f"body={resp.text[:300]}"
    )
    body = resp.json()
    # Either ran=True with the extension bridge path, or the planner
    # routed differently. The contract: SOME dispatcher attempt was
    # made (the test stubs SurfaceRuntime so any bridge path lands).
    if body.get("ran"):
        assert body.get("path") == "extension_native_bridge", (
            f"dispatched but path={body.get('path')!r}; "
            f"expected extension_native_bridge"
        )
        assert stub_surface_runtime.captured, (
            "ran=True but SurfaceRuntime.run_browser_task never called"
        )
        rows = _read_timeline(isolated_state["timeline"])
        kinds = _kinds(rows)
        assert "web_action" in kinds, (
            f"ran=True but no web_action timeline row; kinds={kinds}"
        )
    elif body.get("awaiting_sms_confirm"):
        # Engine routed to the preconfirm gate instead. Acceptable but
        # unexpected for this explicit draft shape.
        rows = _read_timeline(isolated_state["timeline"])
        assert any(
            r.get("kind") == "sms_sent"
            and r.get("status") == "wait_user"
            for r in rows
        ), (
            f"awaiting_sms_confirm but no preconfirm timeline row; "
            f"kinds={_kinds(rows)}"
        )
    else:
        pytest.fail(
            f"/api/act returned neither dispatch nor preconfirm: "
            f"{body!r}"
        )


def test_phase9_step4_preconfirm_gate_fires_for_send_shape_plan(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-step 4: A send-shape plan (intent=email_draft +
    instruction containing 'send' or a real-send verb) triggers the
    SMS preconfirm gate, which queues an SMS via the mock Twilio
    branch and writes a timeline row of kind=sms_sent status=wait_user.

    Artifact: PendingConfirm record on disk + sms_sent wait_user
    timeline row + response body.awaiting_sms_confirm=True.
    """
    from app.product import sms_pre_confirm as _sms_pre
    # Verify the gate decision first.
    plan = {
        "mode": "act",
        "intent": "email_draft",
        "task": (
            f"Send an email to {EMAIL_RECIPIENT} about Friday demo"
        ),
        "person": EMAIL_RECIPIENT,
        "thing": "Friday demo",
    }
    assert _sms_pre.should_pre_confirm(plan, SCENARIO_SEND), (
        "should_pre_confirm refused a send-shape plan; gate broken"
    )
    # Fire the preconfirm gate directly to exercise the same code
    # path the engine internal /api/act gate triggers after a
    # _compose_task_from_memory plan with a send verb.
    result = _sms_pre.create_pending_confirm(plan, SCENARIO_SEND)
    assert result.get("awaiting_sms_confirm") is True, (
        f"create_pending_confirm did not gate: {result!r}"
    )
    assert result.get("task_id"), f"missing task_id: {result!r}"
    assert result.get("to_number") == SMS_RECIPIENT, (
        f"preconfirm went to {result.get('to_number')!r}, "
        f"expected {SMS_RECIPIENT!r}"
    )
    # Twilio mock must have been used; no real SMS leaves the host.
    twilio_block = result.get("twilio") or {}
    assert twilio_block.get("mock") is True, (
        f"non-mock Twilio call leaked: {twilio_block!r}"
    )
    # Timeline row exists.
    rows = _read_timeline(isolated_state["timeline"])
    wait_rows = [
        r for r in rows
        if r.get("kind") == "sms_sent"
        and r.get("status") == "wait_user"
    ]
    assert wait_rows, (
        f"expected sms_sent wait_user row; kinds={_kinds(rows)}"
    )
    for r in wait_rows:
        payload = r.get("payload") or {}
        assert payload.get("mock") is True, (
            f"non-mock Twilio send leaked through timeline: {r!r}"
        )
        assert payload.get("to") == SMS_RECIPIENT, (
            f"preconfirm SMS targeted disallowed phone: {r!r}"
        )


def test_phase9_step5_through_8_sms_inbound_yes_triggers_dispatch(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-steps 5, 6, 7, 8: After the preconfirm gate fires, posting
    Body=YES to /api/sms/inbound resolves the pending task, dispatches
    via the extension bridge (mocked SurfaceRuntime), and emits the
    user_reply timeline row.

    Sequence:
      5. Pending task waits (created in step 4).
      6. /api/sms/inbound with Body=YES -> resolves the task.
      7. Engine fires _run_action_engine_post_sms_confirm which
         reaches the extension bridge dispatch.
      8. Receipt path runs (timeline carries user_reply row + the
         dispatch web_action row).

    Artifact: response.reply_class == "yes" + dispatched.ok == True
    + timeline carries user_reply + web_action rows.
    """
    from app.product import sms_pre_confirm as _sms_pre
    _srv, client = _make_client()

    # Pre-arm the gate by directly creating the pending confirm. This
    # mirrors what the /api/act top-level gate would do for a
    # send-shape plan that hit the gate.
    plan = {
        "mode": "act",
        "intent": "email_draft",
        "task": f"Send an email to {EMAIL_RECIPIENT} about Friday demo",
        "person": EMAIL_RECIPIENT,
        "thing": "Friday demo",
    }
    created = _sms_pre.create_pending_confirm(plan, SCENARIO_SEND)
    task_id = created.get("task_id")
    assert task_id, f"failed to create pending confirm: {created!r}"

    # Simulate the user replying YES via the engine's SMS inbound
    # webhook. The handler resolves the pending task, dispatches the
    # action (which goes through the mocked extension bridge), and
    # emits the user_reply timeline row.
    inbound_resp = client.post(
        "/api/sms/inbound",
        data={
            "Body": "YES",
            "From": SMS_RECIPIENT,
            "To": "+15555555555",
            "MessageSid": f"SMphase9{int(time.time())}",
            "task_id": task_id,
        },
        headers={"Accept": "application/json"},
    )
    assert inbound_resp.status_code == 200, (
        f"sms/inbound returned {inbound_resp.status_code} "
        f"body={inbound_resp.text[:300]}"
    )
    inbound_body = inbound_resp.json()
    assert inbound_body.get("ok") is True, (
        f"inbound resolution not ok: {inbound_body!r}"
    )
    assert inbound_body.get("reply_class") == "yes", (
        f"inbound classification != yes: {inbound_body!r}"
    )
    assert inbound_body.get("new_status") == "approved", (
        f"task not approved after YES: {inbound_body!r}"
    )
    dispatched = inbound_body.get("dispatched") or {}
    assert dispatched.get("ok") is True, (
        f"dispatch did not run after YES: {dispatched!r}"
    )
    inner_body = dispatched.get("body") or {}
    assert inner_body.get("ran") is True, (
        f"inner action did not ran=True: {inner_body!r}"
    )
    assert inner_body.get("path") == "extension_native_bridge", (
        f"dispatch did not go through extension bridge: {inner_body!r}"
    )
    # The stub captured the bridge call.
    assert stub_surface_runtime.captured, (
        "dispatch reported ran=True but SurfaceRuntime never invoked"
    )
    # Timeline carries the user_reply row.
    rows = _read_timeline(isolated_state["timeline"])
    kinds = _kinds(rows)
    assert "user_reply" in kinds, (
        f"expected user_reply timeline row after YES; kinds={kinds}"
    )
    # And a web_action row from the post-YES dispatch.
    assert "web_action" in kinds, (
        f"expected web_action timeline row after YES dispatch; "
        f"kinds={kinds}"
    )


def test_phase9_step9_timeline_carries_expected_ordering(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Sub-step 9: After the full flow runs, the unified timeline at
    the temp path carries the rows in chronological order:

      sms_sent wait_user  (preconfirm queued)
      user_reply done     (YES arrived via /api/sms/inbound)
      web_action done     (dispatch fired through extension bridge)

    The Phase 9 prompt also names a final "sms_sent done (receipt)"
    row. That row only emits when ANTICIPY_RECEIPT_ON_SUCCESS=1 OR
    when the caller hits /api/dispatch/with_receipt. The default
    /api/act path skips it so routine probes don't spam the user.
    Step 9 verifies the first three rows and records the receipt row
    as PARTIAL in the report (correctly gated, not fired).
    """
    from app.product import sms_pre_confirm as _sms_pre
    _srv, client = _make_client()

    plan = {
        "mode": "act",
        "intent": "email_draft",
        "task": f"Send an email to {EMAIL_RECIPIENT} about Friday demo",
        "person": EMAIL_RECIPIENT,
        "thing": "Friday demo",
    }
    created = _sms_pre.create_pending_confirm(plan, SCENARIO_SEND)
    task_id = created["task_id"]
    client.post(
        "/api/sms/inbound",
        data={
            "Body": "YES",
            "From": SMS_RECIPIENT,
            "To": "+15555555555",
            "MessageSid": f"SMphase9order{int(time.time())}",
            "task_id": task_id,
        },
        headers={"Accept": "application/json"},
    )
    rows = _read_timeline(isolated_state["timeline"])
    sms_pre_idx = None
    user_reply_idx = None
    web_action_idx = None
    for i, r in enumerate(rows):
        if (sms_pre_idx is None
                and r.get("kind") == "sms_sent"
                and r.get("status") == "wait_user"):
            sms_pre_idx = i
        if user_reply_idx is None and r.get("kind") == "user_reply":
            user_reply_idx = i
        if (web_action_idx is None
                and r.get("kind") == "web_action"
                and r.get("status") == "done"):
            web_action_idx = i
    assert sms_pre_idx is not None, (
        f"missing sms_sent wait_user row; kinds={_kinds(rows)}"
    )
    assert user_reply_idx is not None, (
        f"missing user_reply row; kinds={_kinds(rows)}"
    )
    assert web_action_idx is not None, (
        f"missing web_action done row; kinds={_kinds(rows)}"
    )
    # Chronological ordering.
    assert sms_pre_idx < user_reply_idx, (
        f"preconfirm landed after user_reply (sms_pre_idx="
        f"{sms_pre_idx} user_reply_idx={user_reply_idx})"
    )
    assert user_reply_idx < web_action_idx, (
        f"user_reply landed after web_action (user_reply_idx="
        f"{user_reply_idx} web_action_idx={web_action_idx})"
    )


def test_phase9_no_real_send_leakage_cross_cut(
    isolated_state, mock_twilio_env, stub_surface_runtime,
    force_extension_surface,
):
    """Cross-cutting assertion: across the entire pipeline run, every
    sms_sent row in the timeline must carry payload.mock=True OR
    payload.error explaining why it could not send (no destination
    configured, etc.). This guards the no_real_send memory.

    Also asserts every SMS goes to the test-allowed phone only.
    """
    from app.product import sms_pre_confirm as _sms_pre
    _srv, client = _make_client()
    client.post(
        "/api/listen/inject",
        json={"text": SCENARIO_DRAFT, "source": "phase9-e2e-leak"},
    )
    # Fire both the draft path and the gate path.
    client.post("/api/act", json={"instruction": SCENARIO_DRAFT})
    _sms_pre.create_pending_confirm(
        {
            "mode": "act",
            "intent": "email_draft",
            "task": f"Send to {EMAIL_RECIPIENT}",
            "person": EMAIL_RECIPIENT,
            "thing": "Friday demo",
        },
        SCENARIO_SEND,
    )
    rows = _read_timeline(isolated_state["timeline"])
    for r in rows:
        if r.get("kind") != "sms_sent":
            continue
        payload = r.get("payload") or {}
        mock_flag = payload.get("mock")
        error = str(payload.get("error") or "")
        to_phone = str(payload.get("to") or "")
        # Either the send was explicitly mocked, OR it failed because
        # no destination was configured. Anything else = real send.
        assert mock_flag is True or error or not to_phone, (
            f"non-mock SMS row leaked through to {to_phone!r}: {r!r}"
        )
        # And if a phone IS set, it MUST be the test-allowed number.
        if to_phone:
            assert to_phone == SMS_RECIPIENT, (
                f"sms_sent row went to disallowed phone {to_phone!r}: "
                f"{r!r}"
            )
