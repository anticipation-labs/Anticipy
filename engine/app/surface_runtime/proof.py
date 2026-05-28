from __future__ import annotations

from .types import EvidenceKind, ProofReceipt, SurfaceKind


VISIBLE_EVIDENCE = {
    EvidenceKind.DOM_SNAPSHOT,
    EvidenceKind.CDP_TARGET,
    EvidenceKind.AX_TREE,
    EvidenceKind.SCREENSHOT,
    EvidenceKind.VISION_ANSWER,
    EvidenceKind.TERMINAL_BUFFER,
    EvidenceKind.FILE_STATE,
    EvidenceKind.NOTIFICATION_RECORD,
}


class ProofValidationError(ValueError):
    pass


def validate_proof_receipt(
    receipt: ProofReceipt,
    *,
    required_surface: SurfaceKind | None = None,
    allow_provider_callback: bool = False,
) -> ProofReceipt:
    """Validate that a receipt came from the user's real surface.

    Engine logs can help debugging, but they never prove completion.
    Provider callbacks are accepted only for notification-delivery
    receipts, not for browser/native/canvas task completion.
    """

    if required_surface and receipt.surface_kind != required_surface:
        raise ProofValidationError(
            f"wrong surface: {receipt.surface_kind.value}, expected {required_surface.value}"
        )
    if receipt.evidence_kind == EvidenceKind.ENGINE_LOG:
        raise ProofValidationError("engine logs are not proof receipts")
    if receipt.evidence_kind == EvidenceKind.PROVIDER_CALLBACK and not allow_provider_callback:
        raise ProofValidationError("provider callback cannot prove visible user-surface state")
    if receipt.evidence_kind not in VISIBLE_EVIDENCE and not (
        allow_provider_callback and receipt.evidence_kind == EvidenceKind.PROVIDER_CALLBACK
    ):
        raise ProofValidationError(f"unsupported evidence kind: {receipt.evidence_kind.value}")
    if receipt.confidence < 0.75:
        raise ProofValidationError(f"receipt confidence too low: {receipt.confidence}")
    if not receipt.summary.strip():
        raise ProofValidationError("receipt summary is empty")
    return receipt
