"""Universal user-surface runtime primitives.

This package is intentionally outside the frozen action/proactive/memory
paths. It gives the product layer a small vocabulary for surfaces,
receipts, and user-local recipes without turning Anticipy into a giant
global skills catalog.
"""

from .perception import choose_evidence_strategy
from .proof import ProofValidationError, validate_proof_receipt
from .recipes import RecipeStore
from .types import (
    ActionPrimitive,
    EvidenceKind,
    LearnedRecipe,
    PrimitiveKind,
    ProofReceipt,
    RiskMode,
    RuntimeDecision,
    SurfaceKind,
    SurfaceObservation,
)

__all__ = [
    "ActionPrimitive",
    "EvidenceKind",
    "LearnedRecipe",
    "PrimitiveKind",
    "ProofReceipt",
    "ProofValidationError",
    "RecipeStore",
    "RiskMode",
    "RuntimeDecision",
    "SurfaceKind",
    "SurfaceObservation",
    "choose_evidence_strategy",
    "validate_proof_receipt",
]
