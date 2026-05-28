"""Per-user action recipe storage.

Records successful primitive sequences after the engine completes a task and
retrieves them for similar future tasks. Lightweight, account-scoped, NOT a
global skills library.

Storage: ~/.anticipy/v7/recipes/<account_id>/<device_id>/recipes.jsonl
Each line is one Recipe JSON object (see Recipe.to_dict).

Concurrency: a module-level lock guards reads/writes. Append-only for new
recipes; updates rewrite the file in place under lock. Corrupt lines are
skipped rather than crashing callers.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Module-level lock. Typically one (account_id, device_id) per process, so a
# single lock is fine and avoids per-scope fan-out.
_LOCK = threading.Lock()

# A recipe gets deprioritized in recall when it has this many or more recent
# failures (where "recent" is defined as failures within RECENT_FAIL_WINDOW
# seconds). Keeps a one-off failure from killing an otherwise-good recipe.
DEPRIORITIZE_FAIL_COUNT = 3
RECENT_FAIL_WINDOW = 60 * 60 * 24 * 30  # 30 days


def _root() -> Path:
    """Base directory for scoped recipe storage."""
    raw = os.environ.get("ANTICIPY_V7_RECIPES_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "recipes"


def _safe_id(s: str) -> str:
    """Filesystem-safe id. Strips path separators and oddballs."""
    s = (s or "").strip()
    if not s:
        return "unknown"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s[:128] or "unknown"


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lowercased alphanumeric tokens, 2+ chars."""
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) >= 2}


def _token_overlap(a: str, b: str) -> float:
    """Simple Jaccard similarity on token sets, in [0.0, 1.0]."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    if not inter:
        return 0.0
    union = len(ta | tb)
    return inter / union


@dataclass
class Recipe:
    """One successful primitive sequence remembered for reuse."""

    recipe_id: str
    intent_summary: str
    surface_key: str
    primitives: list[dict[str, Any]]
    success_proof_ref: str
    learned_at: float
    success_count: int = 1
    intent_embedding: Optional[list[float]] = None
    failed_uses: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        emb = self.intent_embedding
        return {
            "recipe_id": self.recipe_id,
            "intent_summary": self.intent_summary,
            "intent_embedding": list(emb) if emb is not None else None,
            "surface_key": self.surface_key,
            "primitives": [dict(p) for p in (self.primitives or [])],
            "success_proof_ref": self.success_proof_ref,
            "learned_at": float(self.learned_at),
            "success_count": int(self.success_count),
            "failed_uses": [dict(f) for f in (self.failed_uses or [])],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Recipe":
        emb = d.get("intent_embedding")
        return cls(
            recipe_id=str(d.get("recipe_id") or ""),
            intent_summary=str(d.get("intent_summary") or ""),
            surface_key=str(d.get("surface_key") or ""),
            primitives=list(d.get("primitives") or []),
            success_proof_ref=str(d.get("success_proof_ref") or ""),
            learned_at=float(d.get("learned_at") or 0.0),
            success_count=int(d.get("success_count") or 1),
            intent_embedding=list(emb) if isinstance(emb, list) else None,
            failed_uses=list(d.get("failed_uses") or []),
        )

    def recent_fail_count(self, now: Optional[float] = None) -> int:
        """Count failures within the recent window."""
        now = now if now is not None else time.time()
        cutoff = now - RECENT_FAIL_WINDOW
        count = 0
        for f in self.failed_uses or []:
            try:
                if float(f.get("at") or 0.0) >= cutoff:
                    count += 1
            except (TypeError, ValueError):
                continue
        return count


class RecipeStore:
    """Account/device scoped action recipe storage.

    Construct one per (account_id, device_id) pair. Construction is cheap;
    the storage file is created lazily on first write.
    """

    def __init__(self, account_id: str, device_id: str) -> None:
        self.account_id = _safe_id(account_id)
        self.device_id = _safe_id(device_id)
        self._dir = _root() / self.account_id / self.device_id
        self._path = self._dir / "recipes.jsonl"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def dir(self) -> Path:
        return self._dir

    # ----- low-level disk -----

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[Recipe]:
        if not self._path.exists():
            return []
        out: list[Recipe] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(Recipe.from_dict(json.loads(line)))
                except Exception:
                    # Skip corrupt line, do not crash callers.
                    continue
        except Exception:
            return []
        return out

    def _write_all(self, recipes: list[Recipe]) -> None:
        self._ensure_dir()
        tmp = self._path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in recipes:
                fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
        os.replace(tmp, self._path)

    def _append(self, recipe: Recipe) -> None:
        self._ensure_dir()
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(recipe.to_dict(), ensure_ascii=False) + "\n")

    # ----- public API -----

    def record(
        self,
        intent_summary: str,
        surface_key: str,
        primitives: list[dict[str, Any]],
        success_proof_ref: str,
        *,
        intent_embedding: Optional[list[float]] = None,
    ) -> Recipe:
        """Persist a successful primitive sequence.

        Always appends a NEW recipe rather than deduping; the dispatcher
        uses increment_success when reusing an existing one. Treating each
        successful run as a new candidate lets recall surface different
        primitive paths for the same intent.
        """
        recipe = Recipe(
            recipe_id=f"rec-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
            intent_summary=str(intent_summary or "")[:512],
            surface_key=str(surface_key or "")[:256],
            primitives=[dict(p) for p in (primitives or [])],
            success_proof_ref=str(success_proof_ref or ""),
            learned_at=time.time(),
            success_count=1,
            intent_embedding=(
                list(intent_embedding)
                if intent_embedding is not None
                else None
            ),
            failed_uses=[],
        )
        with _LOCK:
            self._append(recipe)
        return recipe

    def recall(
        self,
        intent_summary: str,
        surface_key: str,
        top_k: int = 3,
    ) -> list[Recipe]:
        """Return up to top_k recipes for similar intent on the same surface.

        Exact surface_key match required (case-insensitive). Ranks by
        token-overlap similarity on intent_summary + log-scaled
        success_count bonus, minus a penalty when recent failures hit
        DEPRIORITIZE_FAIL_COUNT. Recency is the tie-breaker.
        """
        if top_k <= 0:
            return []
        wanted_surface = str(surface_key or "").strip().lower()
        if not wanted_surface:
            return []

        with _LOCK:
            recipes = self._read_all()

        from math import log1p
        now = time.time()
        scored: list[tuple[float, float, Recipe]] = []
        for r in recipes:
            if r.surface_key.strip().lower() != wanted_surface:
                continue
            sim = _token_overlap(intent_summary, r.intent_summary)
            success_bonus = 0.05 * log1p(max(0, r.success_count - 1))
            recent_fails = r.recent_fail_count(now=now)
            fail_penalty = 0.0
            if recent_fails >= DEPRIORITIZE_FAIL_COUNT:
                fail_penalty = 0.5 + 0.05 * (
                    recent_fails - DEPRIORITIZE_FAIL_COUNT
                )
            score = sim + success_bonus - fail_penalty
            scored.append((score, r.learned_at, r))

        if not scored:
            return []
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return [r for _score, _ts, r in scored[:top_k]]

    def increment_success(self, recipe_id: str) -> bool:
        """Bump success_count after a recipe was reused successfully.

        Returns True if the recipe was found and updated, False otherwise.
        """
        rid = str(recipe_id or "").strip()
        if not rid:
            return False
        with _LOCK:
            recipes = self._read_all()
            changed = False
            for r in recipes:
                if r.recipe_id == rid:
                    r.success_count = int(r.success_count) + 1
                    changed = True
                    break
            if changed:
                self._write_all(recipes)
        return changed

    def mark_failed(self, recipe_id: str, reason: str) -> bool:
        """Add a failure record to a recipe.

        Returns True if the recipe was found and updated, False otherwise.
        """
        rid = str(recipe_id or "").strip()
        if not rid:
            return False
        entry = {
            "at": time.time(),
            "reason": str(reason or "")[:512],
        }
        with _LOCK:
            recipes = self._read_all()
            changed = False
            for r in recipes:
                if r.recipe_id == rid:
                    r.failed_uses = list(r.failed_uses or []) + [entry]
                    changed = True
                    break
            if changed:
                self._write_all(recipes)
        return changed

    def prune(self, older_than_days: int = 180) -> int:
        """Drop stale, rarely-used recipes.

        Pruned when learned_at is older than `older_than_days` AND
        success_count <= 1, OR when recent_fail_count hits
        DEPRIORITIZE_FAIL_COUNT and success_count <= 1. Returns count
        removed.
        """
        if older_than_days <= 0:
            return 0
        now = time.time()
        cutoff = now - (older_than_days * 86400)
        removed = 0
        with _LOCK:
            recipes = self._read_all()
            kept: list[Recipe] = []
            for r in recipes:
                stale = r.learned_at < cutoff and r.success_count <= 1
                useless = (
                    r.recent_fail_count(now=now) >= DEPRIORITIZE_FAIL_COUNT
                    and r.success_count <= 1
                )
                if stale or useless:
                    removed += 1
                    continue
                kept.append(r)
            if removed:
                self._write_all(kept)
        return removed

    def all_recipes(self) -> list[Recipe]:
        """Return every recipe on disk. Useful for diagnostics and tests."""
        with _LOCK:
            return self._read_all()
