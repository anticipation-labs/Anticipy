"""End-to-end test for app.verifier.verify_at_done — agent claims done with
a wrong answer; verifier catches it via re-fetched bridge state."""

from __future__ import annotations

import pytest

from app.verifier import DoneVerification, verify_at_done


# ─────────────────────────────────────────────────────────────────────────
# MockBridge: same shape as the one in test_end_state_verifier — each
# bridge implements BridgeProtocol.
# ─────────────────────────────────────────────────────────────────────────


class MockBridge:
    def __init__(
        self,
        url_to_text: dict[str, str] | None = None,
        default_text: str = "",
    ):
        self.url_to_text = url_to_text or {}
        self.default_text = default_text
        self.navigations: list[str] = []
        self._current_url = ""

    async def navigate(self, url: str) -> None:
        self.navigations.append(url)
        self._current_url = url

    async def get_text(self, selector: str | None = None) -> str:
        for needle, body in self.url_to_text.items():
            if needle and needle in self._current_url:
                return body
        return self.default_text

    async def get_url(self) -> str:
        return self._current_url


# ─────────────────────────────────────────────────────────────────────────
# Wrong-answer e2e: read_extract task. Agent says it found the headline,
# but the agent's own done() text doesn't actually contain the required
# fact. verify_at_done must catch this.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_at_done_catches_wrong_answer_in_read_extract():
    bridge = MockBridge()
    # Agent claims done with a vague text that doesn't actually contain
    # the required fact ("Top Story 5 — markets close higher").
    payload = {
        "message": "I found the page and skimmed it.",
        "required_facts": ["Top Story 5 — markets close higher"],
    }
    result = await verify_at_done(
        task_kind="read_extract",
        task_text='Tell me the headline that says "Top Story 5"',
        agent_done_payload=payload,
        bridge=bridge,
    )
    assert isinstance(result, DoneVerification)
    assert result.passed is False
    assert any("Top Story 5" in m for m in result.missing)
    # Wearer-friendly failure message rendered.
    msg = result.honest_message.lower()
    assert msg
    assert "retry" in msg or "try again" in msg


@pytest.mark.asyncio
async def test_verify_at_done_passes_when_answer_carries_required_facts():
    bridge = MockBridge()
    payload = {
        "message": "The headline reads: Top Story 5 — markets close higher.",
        "required_facts": ["Top Story 5"],
    }
    result = await verify_at_done(
        task_kind="read_extract",
        task_text='Tell me the headline',
        agent_done_payload=payload,
        bridge=bridge,
    )
    assert result.passed is True
    assert result.missing == []
    assert result.honest_message == ""


# ─────────────────────────────────────────────────────────────────────────
# Wrong-answer e2e: email_send. Agent claims it sent, but the Sent folder
# (re-fetched via bridge) doesn't show a recent message with the subject.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_at_done_catches_unsent_email():
    bridge = MockBridge(
        url_to_text={
            "mail.google.com": (
                "Inbox  Sent  Drafts\n"
                "(no recent sent messages match)\n"
                "Old Mail — 4 days ago"
            ),
        },
    )
    result = await verify_at_done(
        task_kind="email_send",
        task_text="email Bob about Q3 numbers",
        agent_done_payload={"subject": "Q3 numbers"},
        bridge=bridge,
    )
    assert result.passed is False
    # The agent's lie was caught by re-fetching the Sent folder.
    assert any("sent" in m.lower() for m in result.missing)
    assert any("mail.google.com" in n for n in bridge.navigations)
    assert "Sent folder" in result.honest_message or "retry" in result.honest_message.lower()


@pytest.mark.asyncio
async def test_verify_at_done_passes_when_email_visible_recently():
    bridge = MockBridge(
        url_to_text={
            "mail.google.com": (
                "Inbox  Sent  Drafts\n"
                "Q3 numbers — just now\n"
            ),
        },
    )
    result = await verify_at_done(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "Q3 numbers"},
        bridge=bridge,
    )
    assert result.passed is True


# ─────────────────────────────────────────────────────────────────────────
# Wrong-answer e2e: calendar_create. Agent claims event was created.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_at_done_catches_missing_calendar_event():
    bridge = MockBridge(
        url_to_text={
            "calendar.google.com": "May 10 - May 16\n(no events created)",
        },
    )
    result = await verify_at_done(
        task_kind="calendar_create",
        task_text='create event "Team Sync 2pm" tuesday',
        agent_done_payload={"title": "Team Sync 2pm"},
        bridge=bridge,
    )
    assert result.passed is False
    assert any("calendar" in m.lower() for m in result.missing)


# ─────────────────────────────────────────────────────────────────────────
# Wrong-answer e2e: cart_add — item never made it.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_at_done_catches_empty_cart():
    bridge = MockBridge(
        url_to_text={
            "shop.com/cart": "Your Cart is empty",
        },
    )
    result = await verify_at_done(
        task_kind="cart_add",
        task_text="add the widget to cart",
        agent_done_payload={
            "title": "Acme Widget Pro",
            "cart_url": "https://shop.com/cart",
        },
        bridge=bridge,
    )
    assert result.passed is False
    assert any("cart" in m.lower() for m in result.missing)


# ─────────────────────────────────────────────────────────────────────────
# Failure modes — bridge that misbehaves.
# ─────────────────────────────────────────────────────────────────────────


class _ExplodingBridge:
    async def navigate(self, url: str) -> None:
        raise RuntimeError("network down")

    async def get_text(self, selector: str | None = None) -> str:
        raise RuntimeError("dom down")

    async def get_url(self) -> str:
        raise RuntimeError("page closed")


@pytest.mark.asyncio
async def test_verify_at_done_fails_closed_when_bridge_explodes():
    """Even with a totally broken bridge we don't crash — fail closed."""
    bridge = _ExplodingBridge()
    result = await verify_at_done(
        task_kind="email_send",
        task_text="email someone",
        agent_done_payload={"subject": "X"},
        bridge=bridge,
    )
    assert result.passed is False
    assert result.honest_message  # wearer-facing message present


@pytest.mark.asyncio
async def test_verify_at_done_handles_non_dict_payload():
    bridge = MockBridge()
    result = await verify_at_done(
        task_kind="read_extract",
        task_text='Tell me "X"',
        agent_done_payload="agent forgot to pass a dict",  # type: ignore[arg-type]
        bridge=bridge,
    )
    assert result.passed is False


# ─────────────────────────────────────────────────────────────────────────
# Unknown task_kind falls through to generic
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_at_done_falls_back_to_generic_for_unknown_kind():
    bridge = MockBridge(default_text="page text — Acme Widget priced at $29.99")
    result = await verify_at_done(
        task_kind="bizarre_unknown",
        task_text='find "Acme Widget"',
        agent_done_payload={"message": "Found Acme Widget at $29.99."},
        bridge=bridge,
    )
    assert result.passed is True
    assert result.task_kind == "bizarre_unknown"


# ─────────────────────────────────────────────────────────────────────────
# Honest message tone: NEVER contains technical jargon.
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_honest_message_has_no_technical_jargon():
    bridge = MockBridge()
    result = await verify_at_done(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "X"},
        bridge=bridge,
    )
    assert result.passed is False
    msg = result.honest_message.lower()
    forbidden = ["json", "selector", "dom", "http", "model", "api", "token", "url"]
    for fw in forbidden:
        assert fw not in msg, f"honest_message leaked tech term {fw!r}: {result.honest_message!r}"


@pytest.mark.asyncio
async def test_passing_result_has_empty_honest_message():
    """Don't render a wearer message when the verifier passed."""
    bridge = MockBridge()
    payload = {"message": "Found it: Top Story 5", "required_facts": ["Top Story 5"]}
    result = await verify_at_done(
        task_kind="read_extract",
        task_text="x",
        agent_done_payload=payload,
        bridge=bridge,
    )
    assert result.passed is True
    assert result.honest_message == ""
