"""Tests for app.end_state_verifier — per-task-kind verification."""

from __future__ import annotations

from typing import Any

import pytest

from app.end_state_verifier import (
    EFFECT_WINDOW_SECONDS,
    VerificationResult,
    verify_end_state,
)


# ─────────────────────────────────────────────────────────────────────────
# MockBridge — implements BridgeProtocol; deterministic, scriptable.
# ─────────────────────────────────────────────────────────────────────────


class MockBridge:
    """Test double that tracks navigations and returns scripted text.

    Pass ``url_to_text`` mapping URL substrings → page text. The first
    matching pattern wins. Unknown navigations land on ``default_text``.
    """

    def __init__(
        self,
        url_to_text: dict[str, str] | None = None,
        default_text: str = "",
        raise_on_navigate: bool = False,
        raise_on_text: bool = False,
    ) -> None:
        self.url_to_text = url_to_text or {}
        self.default_text = default_text
        self.raise_on_navigate = raise_on_navigate
        self.raise_on_text = raise_on_text
        self.navigations: list[str] = []
        self._current_url = ""

    async def navigate(self, url: str) -> None:
        if self.raise_on_navigate:
            raise RuntimeError("navigate boom")
        self.navigations.append(url)
        self._current_url = url

    async def get_text(self, selector: str | None = None) -> str:
        if self.raise_on_text:
            raise RuntimeError("get_text boom")
        for needle, body in self.url_to_text.items():
            if needle and needle in self._current_url:
                return body
        return self.default_text

    async def get_url(self) -> str:
        return self._current_url


# ─────────────────────────────────────────────────────────────────────────
# read_extract
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_extract_passes_when_facts_present_in_done():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text='Tell me the headline of "Top Story 5"',
        agent_done_payload={
            "message": "The headline reads: Top Story 5 — markets close higher",
            "required_facts": ["Top Story 5"],
        },
        bridge=bridge,
    )
    assert result.ok
    assert result.missing == []


@pytest.mark.asyncio
async def test_read_extract_fails_when_required_fact_missing():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text='Tell me the headline of "Top Story 5"',
        agent_done_payload={
            "message": "I went to the page but couldn't find it.",
            "required_facts": ["Top Story 5"],
        },
        bridge=bridge,
    )
    assert not result.ok
    assert "Top Story 5" in result.missing


@pytest.mark.asyncio
async def test_read_extract_uses_heuristic_facts_when_planner_missing():
    """When required_facts is absent, use heuristic extraction from task."""
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text='Find "Acme Corp" and its CEO name',
        agent_done_payload={
            "message": "The CEO is Jane Doe of Acme Corp.",
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_read_extract_no_facts_accepts_any_substantive_answer():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text="just check the page",
        agent_done_payload={"message": "Page loaded successfully."},
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_read_extract_no_facts_rejects_empty_answer():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text="just check the page",
        agent_done_payload={"message": ""},
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# email_send
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_email_send_passes_when_subject_in_sent_recently():
    bridge = MockBridge(
        url_to_text={
            "mail.google.com": (
                "Inbox  Sent  Drafts\n"
                "Test Subject ABC — sent just now\n"
                "Old Mail — 2 weeks ago"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob about the test",
        agent_done_payload={"subject": "Test Subject ABC"},
        bridge=bridge,
    )
    assert result.ok
    # Bridge was navigated to the Sent folder
    assert any("sent" in n for n in bridge.navigations)
    assert result.missing == []


@pytest.mark.asyncio
async def test_email_send_fails_when_subject_not_in_sent():
    bridge = MockBridge(
        url_to_text={
            "mail.google.com": "Inbox  Sent  Drafts\nOld Mail — 2 weeks ago",
        },
    )
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob about the test",
        agent_done_payload={"subject": "Test Subject ABC"},
        bridge=bridge,
    )
    assert not result.ok
    # Specifically: missing the sent message
    assert any("sent_message" in m for m in result.missing)


@pytest.mark.asyncio
async def test_email_send_fails_when_subject_present_but_old():
    bridge = MockBridge(
        url_to_text={
            "mail.google.com": (
                "Test Subject ABC — sent 3 hours ago\n"
                "Other mail — yesterday"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "Test Subject ABC"},
        bridge=bridge,
    )
    assert not result.ok
    # Negative case: subject is there but no recent timestamp
    assert any(f"within_{EFFECT_WINDOW_SECONDS}s" in m for m in result.missing)


@pytest.mark.asyncio
async def test_email_send_fails_when_navigation_broken():
    bridge = MockBridge(raise_on_navigate=True)
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "X"},
        bridge=bridge,
    )
    assert not result.ok
    assert "sent_folder_navigable" in result.missing


@pytest.mark.asyncio
async def test_email_send_fails_when_text_extraction_breaks():
    bridge = MockBridge(raise_on_text=True)
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "X"},
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# calendar_create
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_create_passes_when_title_in_calendar():
    bridge = MockBridge(
        url_to_text={
            "calendar.google.com": (
                "May 10 - May 16\n"
                "Mon: Standup at 9 AM\n"
                "Tue: Team Sync 2pm\n"
                "Wed: Lunch with Bob\n"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="calendar_create",
        task_text="schedule team sync tuesday at 2pm",
        agent_done_payload={"title": "Team Sync 2pm"},
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_calendar_create_fails_when_title_not_in_calendar():
    bridge = MockBridge(
        url_to_text={
            "calendar.google.com": "May 10 - May 16\nNo events this week",
        },
    )
    result = await verify_end_state(
        task_kind="calendar_create",
        task_text="schedule team sync",
        agent_done_payload={"title": "Team Sync 2pm"},
        bridge=bridge,
    )
    assert not result.ok
    assert "calendar_event_title_present" in result.missing


@pytest.mark.asyncio
async def test_calendar_create_fails_when_title_unknown():
    bridge = MockBridge(
        url_to_text={"calendar.google.com": "events list..."},
    )
    result = await verify_end_state(
        task_kind="calendar_create",
        task_text="schedule a thing",
        agent_done_payload={},
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# comment_post
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_comment_post_passes_when_author_text_recent():
    bridge = MockBridge(
        url_to_text={
            "example.com/thread/42": (
                "Thread #42\n"
                "alice: First!\n"
                "bob_user: Looks great — just now\n"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="comment_post",
        task_text="post a comment",
        agent_done_payload={
            "author": "bob_user",
            "comment_text": "Looks great",
            "source_url": "https://example.com/thread/42",
        },
        bridge=bridge,
    )
    assert result.ok
    assert any("thread/42" in n for n in bridge.navigations)


@pytest.mark.asyncio
async def test_comment_post_fails_when_author_missing():
    bridge = MockBridge(
        url_to_text={
            "example.com/thread/42": (
                "Thread #42\n"
                "alice: First!\n"
                "(your comment hasn't appeared yet)\n"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="comment_post",
        task_text="post a comment",
        agent_done_payload={
            "author": "bob_user",
            "comment_text": "Looks great",
            "source_url": "https://example.com/thread/42",
        },
        bridge=bridge,
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_comment_post_fails_without_recency_marker():
    bridge = MockBridge(
        url_to_text={
            "example.com/thread/42": (
                "Thread #42\n"
                "bob_user: Looks great — 4 hours ago\n"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="comment_post",
        task_text="post a comment",
        agent_done_payload={
            "author": "bob_user",
            "comment_text": "Looks great",
            "source_url": "https://example.com/thread/42",
        },
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# cart_add
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cart_add_passes_when_title_in_cart():
    bridge = MockBridge(
        url_to_text={
            "shop.example.com/cart": (
                "Your Cart (1 item)\n"
                "Acme Widget Pro - $29.99\n"
                "Subtotal: $29.99\n"
            ),
        },
    )
    result = await verify_end_state(
        task_kind="cart_add",
        task_text="add the widget to cart",
        agent_done_payload={
            "title": "Acme Widget Pro",
            "cart_url": "https://shop.example.com/cart",
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_cart_add_passes_when_sku_in_cart():
    bridge = MockBridge(
        url_to_text={
            "shop.example.com/cart": "Your Cart\nSKU-1234 - $19.99",
        },
    )
    result = await verify_end_state(
        task_kind="cart_add",
        task_text="add the widget",
        agent_done_payload={
            "sku": "SKU-1234",
            "cart_url": "https://shop.example.com/cart",
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_cart_add_fails_when_item_not_in_cart():
    bridge = MockBridge(
        url_to_text={
            "shop.example.com/cart": "Your Cart is empty.",
        },
    )
    result = await verify_end_state(
        task_kind="cart_add",
        task_text="add the widget",
        agent_done_payload={
            "title": "Acme Widget Pro",
            "cart_url": "https://shop.example.com/cart",
        },
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# form_submit
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_form_submit_passes_with_thank_you_text():
    bridge = MockBridge(
        url_to_text={
            "/thank-you": (
                "Thank you for your submission. Your reference number is "
                "ABC-12345."
            ),
        },
    )
    # Pre-position the bridge to the confirmation URL
    await bridge.navigate("https://example.com/thank-you")
    result = await verify_end_state(
        task_kind="form_submit",
        task_text="submit the form",
        agent_done_payload={
            "confirmation_url": "https://example.com/thank-you",
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_form_submit_passes_with_confirmation_number_only():
    bridge = MockBridge(
        url_to_text={
            "example.com/done": "Order ABC123XYZ has been placed.",
        },
    )
    await bridge.navigate("https://example.com/done")
    result = await verify_end_state(
        task_kind="form_submit",
        task_text="place order",
        agent_done_payload={
            "confirmation_url": "https://example.com/done",
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_form_submit_fails_on_error_page():
    bridge = MockBridge(
        url_to_text={
            "example.com/form": "Sorry, something went wrong. Please retry.",
        },
    )
    await bridge.navigate("https://example.com/form")
    result = await verify_end_state(
        task_kind="form_submit",
        task_text="submit form",
        agent_done_payload={"confirmation_url": "https://example.com/form"},
        bridge=bridge,
    )
    assert not result.ok
    assert "confirmation_marker" in result.missing


# ─────────────────────────────────────────────────────────────────────────
# generic
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generic_passes_with_facts_in_answer():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="generic",
        task_text='Tell me "Current price" and "ticker"',
        agent_done_payload={
            "message": "Current price is $123. The ticker is ACME."
        },
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_generic_falls_back_to_page_text():
    bridge = MockBridge(default_text="Current price quoted at $123 today.")
    result = await verify_end_state(
        task_kind="generic",
        task_text='What is "Current price"?',
        agent_done_payload={"message": "n/a"},
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_generic_fails_when_facts_nowhere():
    bridge = MockBridge(default_text="404 Not Found")
    result = await verify_end_state(
        task_kind="generic",
        task_text='Tell me "Current price"',
        agent_done_payload={"message": "I couldn't load it."},
        bridge=bridge,
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_generic_no_facts_accepts_substantive():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="generic",
        task_text="do a thing",
        agent_done_payload={"message": "Done with thing."},
        bridge=bridge,
    )
    assert result.ok


@pytest.mark.asyncio
async def test_generic_no_facts_rejects_trivial():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="generic",
        task_text="do a thing",
        agent_done_payload={"message": "."},
        bridge=bridge,
    )
    assert not result.ok


# ─────────────────────────────────────────────────────────────────────────
# Dispatcher edge cases
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_task_kind_falls_back_to_generic():
    bridge = MockBridge(default_text="page text with no facts")
    result = await verify_end_state(
        task_kind="bogus_kind_42",
        task_text="do something",
        agent_done_payload={"message": "Done with something."},
        bridge=bridge,
    )
    # Generic accepts a substantive answer with no facts
    assert result.ok


@pytest.mark.asyncio
async def test_non_dict_payload_treated_as_empty():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="read_extract",
        task_text='Tell me "X"',
        agent_done_payload="not a dict",  # type: ignore[arg-type]
        bridge=bridge,
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_routine_raises_returns_fail_closed():
    """If the per-kind routine throws, we fail closed (cop-out #6)."""
    bridge = MockBridge(raise_on_text=True, raise_on_navigate=True)
    result = await verify_end_state(
        task_kind="email_send",
        task_text="email Bob",
        agent_done_payload={"subject": "X"},
        bridge=bridge,
    )
    assert not result.ok


@pytest.mark.asyncio
async def test_returns_verification_result_type():
    bridge = MockBridge()
    result = await verify_end_state(
        task_kind="generic",
        task_text="x",
        agent_done_payload={"message": "ok"},
        bridge=bridge,
    )
    assert isinstance(result, VerificationResult)
    assert isinstance(result.ok, bool)
    assert isinstance(result.missing, list)
    assert isinstance(result.evidence, list)


# ─────────────────────────────────────────────────────────────────────────
# Effect window constant is exposed for tests/configurability
# ─────────────────────────────────────────────────────────────────────────


def test_effect_window_constant_is_60s():
    assert EFFECT_WINDOW_SECONDS == 60
