from __future__ import annotations

from .types import EvidenceKind, PrimitiveKind, SurfaceKind


_EVIDENCE_ORDER: dict[SurfaceKind, tuple[EvidenceKind, ...]] = {
    SurfaceKind.BROWSER_DOM: (
        EvidenceKind.DOM_SNAPSHOT,
        EvidenceKind.CDP_TARGET,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.VISION_ANSWER,
    ),
    SurfaceKind.BROWSER_CANVAS: (
        EvidenceKind.SCREENSHOT,
        EvidenceKind.VISION_ANSWER,
        EvidenceKind.DOM_SNAPSHOT,
    ),
    SurfaceKind.NATIVE_AX: (
        EvidenceKind.AX_TREE,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.VISION_ANSWER,
    ),
    SurfaceKind.TERMINAL: (
        EvidenceKind.TERMINAL_BUFFER,
        EvidenceKind.SCREENSHOT,
        EvidenceKind.VISION_ANSWER,
    ),
    SurfaceKind.FILE_SYSTEM: (
        EvidenceKind.FILE_STATE,
        EvidenceKind.AX_TREE,
    ),
    SurfaceKind.NOTIFICATION: (
        EvidenceKind.NOTIFICATION_RECORD,
        EvidenceKind.PROVIDER_CALLBACK,
    ),
    SurfaceKind.UNKNOWN: (
        EvidenceKind.SCREENSHOT,
        EvidenceKind.VISION_ANSWER,
    ),
}


def choose_evidence_strategy(
    surface_kind: SurfaceKind,
    primitive: PrimitiveKind = PrimitiveKind.READ,
    hostile_or_canvas_only: bool = False,
) -> list[EvidenceKind]:
    """Return the bounded proof ladder for a surface action.

    DOM is preferred when it represents the product state. Canvas and
    hostile surfaces move screenshot plus vision to the front because
    the DOM is usually a shell that does not prove the user's actual
    visible result.
    """

    if hostile_or_canvas_only and surface_kind == SurfaceKind.BROWSER_DOM:
        return [
            EvidenceKind.SCREENSHOT,
            EvidenceKind.VISION_ANSWER,
            EvidenceKind.DOM_SNAPSHOT,
        ]
    order = list(_EVIDENCE_ORDER.get(surface_kind, _EVIDENCE_ORDER[SurfaceKind.UNKNOWN]))
    if primitive in {PrimitiveKind.VERIFY, PrimitiveKind.DECLINE}:
        return [kind for kind in order if kind != EvidenceKind.ENGINE_LOG]
    return order
