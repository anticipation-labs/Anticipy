from pathlib import Path

import pytest

from app.surface_runtime import (
    ActionPrimitive,
    EvidenceKind,
    LearnedRecipe,
    PrimitiveKind,
    ProofReceipt,
    ProofValidationError,
    RecipeStore,
    SurfaceKind,
    choose_evidence_strategy,
    validate_proof_receipt,
)


def test_engine_log_is_not_a_proof_receipt():
    receipt = ProofReceipt(
        evidence_kind=EvidenceKind.ENGINE_LOG,
        surface_kind=SurfaceKind.BROWSER_DOM,
        target="gmail",
        summary="engine says it drafted the message",
    )

    with pytest.raises(ProofValidationError):
        validate_proof_receipt(receipt)


def test_dom_receipt_is_valid_for_browser_surface():
    receipt = ProofReceipt(
        evidence_kind=EvidenceKind.DOM_SNAPSHOT,
        surface_kind=SurfaceKind.BROWSER_DOM,
        target="gmail drafts",
        summary="draft row contains the expected recipient and subject",
        observed_state={"recipient": "maya@example.com"},
    )

    assert validate_proof_receipt(receipt, required_surface=SurfaceKind.BROWSER_DOM) is receipt


def test_provider_callback_cannot_replace_visible_surface_proof():
    receipt = ProofReceipt(
        evidence_kind=EvidenceKind.PROVIDER_CALLBACK,
        surface_kind=SurfaceKind.BROWSER_DOM,
        target="gmail",
        summary="provider says accepted",
    )

    with pytest.raises(ProofValidationError):
        validate_proof_receipt(receipt)


def test_provider_callback_allowed_for_notification_receipt_only():
    receipt = ProofReceipt(
        evidence_kind=EvidenceKind.PROVIDER_CALLBACK,
        surface_kind=SurfaceKind.NOTIFICATION,
        target="twilio sms",
        summary="Twilio returned a queued message sid",
    )

    assert validate_proof_receipt(
        receipt,
        required_surface=SurfaceKind.NOTIFICATION,
        allow_provider_callback=True,
    ) is receipt


def test_canvas_surfaces_start_with_screenshot_and_vision():
    strategy = choose_evidence_strategy(SurfaceKind.BROWSER_CANVAS)

    assert strategy[:2] == [EvidenceKind.SCREENSHOT, EvidenceKind.VISION_ANSWER]


def test_hostile_dom_surface_uses_visual_read_before_dom():
    strategy = choose_evidence_strategy(
        SurfaceKind.BROWSER_DOM,
        PrimitiveKind.READ,
        hostile_or_canvas_only=True,
    )

    assert strategy[:2] == [EvidenceKind.SCREENSHOT, EvidenceKind.VISION_ANSWER]


def test_recipe_store_is_per_user_and_bounded(tmp_path: Path):
    store = RecipeStore(tmp_path)
    receipt = ProofReceipt(
        evidence_kind=EvidenceKind.AX_TREE,
        surface_kind=SurfaceKind.NATIVE_AX,
        target="Calendar.app",
        summary="event was visible in Calendar.app",
    )
    primitive = ActionPrimitive(
        primitive=PrimitiveKind.SHORTCUT,
        surface_kind=SurfaceKind.NATIVE_AX,
        target="Calendar.app",
        args={"keys": "cmd+n"},
    )
    store.learn(
        LearnedRecipe(
            user_id="user-a",
            surface_kind=SurfaceKind.NATIVE_AX,
            category="calendar",
            title="create calendar event",
            primitives=[primitive],
            receipt=receipt,
            confidence=0.91,
        )
    )

    assert len(store.find(user_id="user-a", surface_kind=SurfaceKind.NATIVE_AX, category="calendar")) == 1
    assert store.find(user_id="user-b", surface_kind=SurfaceKind.NATIVE_AX, category="calendar") == []
    assert store.find(user_id="user-a", surface_kind=SurfaceKind.BROWSER_DOM, category="calendar") == []
