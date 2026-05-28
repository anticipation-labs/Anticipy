from __future__ import annotations

import json
import os
from pathlib import Path

from .proof import validate_proof_receipt
from .types import (
    ActionPrimitive,
    EvidenceKind,
    LearnedRecipe,
    PrimitiveKind,
    ProofReceipt,
    RiskMode,
    SurfaceKind,
)


class RecipeStore:
    """Small per-user recipe store.

    This deliberately does not load a global app catalog. It only returns
    recipes learned from receipts for the current user and matching
    surface/category.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.path.expanduser("~/.anticipy/surface_recipes"))

    def path_for(self, user_id: str) -> Path:
        safe = "".join(ch for ch in user_id if ch.isalnum() or ch in ("-", "_")) or "user"
        return self.root / f"{safe}.jsonl"

    def learn(self, recipe: LearnedRecipe) -> None:
        validate_proof_receipt(recipe.receipt)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path_for(recipe.user_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(recipe.to_json(), sort_keys=True) + "\n")

    def find(
        self,
        *,
        user_id: str,
        surface_kind: SurfaceKind,
        category: str,
        min_confidence: float = 0.7,
        limit: int = 5,
    ) -> list[LearnedRecipe]:
        rows: list[LearnedRecipe] = []
        path = self.path_for(user_id)
        if not path.exists():
            return []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                raw = json.loads(line)
                if raw.get("surface_kind") != surface_kind.value:
                    continue
                if raw.get("category") != category:
                    continue
                if float(raw.get("confidence", 0)) < min_confidence:
                    continue
                rows.append(_recipe_from_json(raw))
            except Exception:
                continue
        rows.sort(key=lambda r: (r.confidence, r.updated_at), reverse=True)
        return rows[:limit]


def _primitive_from_json(raw: dict) -> ActionPrimitive:
    return ActionPrimitive(
        primitive=PrimitiveKind(raw["primitive"]),
        surface_kind=SurfaceKind(raw["surface_kind"]),
        target=raw["target"],
        args=dict(raw.get("args") or {}),
        max_wait_seconds=float(raw.get("max_wait_seconds", 30.0)),
        risk_mode=RiskMode(raw.get("risk_mode", "ask_first")),
    )


def _receipt_from_json(raw: dict) -> ProofReceipt:
    return ProofReceipt(
        evidence_kind=EvidenceKind(raw["evidence_kind"]),
        surface_kind=SurfaceKind(raw["surface_kind"]),
        target=raw["target"],
        summary=raw["summary"],
        confidence=float(raw.get("confidence", 1.0)),
        artifact_path=raw.get("artifact_path"),
        observed_state=dict(raw.get("observed_state") or {}),
        metadata=dict(raw.get("metadata") or {}),
        timestamp=float(raw.get("timestamp", 0.0)),
    )


def _recipe_from_json(raw: dict) -> LearnedRecipe:
    return LearnedRecipe(
        user_id=raw["user_id"],
        surface_kind=SurfaceKind(raw["surface_kind"]),
        category=raw["category"],
        title=raw["title"],
        primitives=[_primitive_from_json(p) for p in raw.get("primitives", [])],
        receipt=_receipt_from_json(raw["receipt"]),
        confidence=float(raw.get("confidence", 0.0)),
        updated_at=float(raw.get("updated_at", 0.0)),
    )
