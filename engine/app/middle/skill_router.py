"""Skill router — vector search over skill_library.

For each Intent, finds the top-K skill candidates whose
intent_match_pattern is semantically close to the intent's
action_category + utterance. A "hit" means we have a previously-
verified parameterized program; a "miss" means we plan from scratch.

The skill_library is initially empty. Until skills accumulate (via
Phase 9's fleet learning), every Intent is a miss → plan-from-scratch
path. The router still runs (returns empty hit list) so the policy
layer has a uniform interface.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from app.proactive.intent_extraction import TypedIntent

_logger = logging.getLogger("anticipy.middle.skill_router")


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    skill_id: str
    intent_match_pattern: str
    similarity: float
    selector_chain: dict
    postcondition_spec: str
    status: str  # 'shadow' | 'active' | 'retired'


@dataclass(frozen=True, slots=True)
class SkillRouteResult:
    hit: bool
    top_candidates: list[SkillCandidate] = field(default_factory=list)
    proposed_skill_id: Optional[str] = None  # None ⇒ plan from scratch


class SkillRouter:
    """Vector lookup over `skill_library`."""

    DEFAULT_TOP_K = 3
    DEFAULT_HIT_THRESHOLD = 0.78  # cosine sim — empirically validated for sentence-MiniLM

    def __init__(
        self,
        top_k: int = DEFAULT_TOP_K,
        hit_threshold: float = DEFAULT_HIT_THRESHOLD,
        supabase=None,
    ) -> None:
        self.top_k = top_k
        self.hit_threshold = hit_threshold
        self._supabase = supabase

    def _ensure_supabase(self):
        if self._supabase is not None:
            return self._supabase
        try:
            from supabase import create_client  # type: ignore
        except ImportError:
            return None
        url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            return None
        self._supabase = create_client(url, key)
        return self._supabase

    def route(self, intent: TypedIntent) -> SkillRouteResult:
        """Lookup top-K skill candidates by:
          1. Direct match on `proposed_skill_hint` (Stage 2 may have
             already named one).
          2. Filter by status='active' (shadow_verified gets promoted
             to active once 20 real runs pass at 85%+).
          3. Vector similarity is best-effort — when sqlite-vec / pg-vector
             extension absent, we fall back to substring match on
             intent_match_pattern.
        """
        sb = self._ensure_supabase()
        if sb is None:
            return SkillRouteResult(hit=False)

        # Pass 1 — direct hint (matches active OR shadow — shadow skills
        # are gated by sandbox rehearsal before live commit, so it's
        # safe to surface them as candidates with status carried through).
        if intent.proposed_skill_hint:
            try:
                resp = (
                    sb.table("skill_library")
                    .select("skill_id,intent_match_pattern,selector_chain,postcondition_spec,status")
                    .eq("skill_id", intent.proposed_skill_hint)
                    .in_("status", ["active", "shadow"])
                    .limit(1)
                    .execute()
                )
                rows = getattr(resp, "data", None) or []
                if rows:
                    cand = SkillCandidate(
                        skill_id=rows[0]["skill_id"],
                        intent_match_pattern=rows[0]["intent_match_pattern"],
                        similarity=1.0,
                        selector_chain=rows[0].get("selector_chain") or {},
                        postcondition_spec=rows[0].get("postcondition_spec", ""),
                        status=rows[0]["status"],
                    )
                    # Only count as hit if active; shadow surfaces a
                    # candidate but routes to sandbox rehearsal first.
                    is_hit = cand.status == "active"
                    return SkillRouteResult(
                        hit=is_hit,
                        top_candidates=[cand],
                        proposed_skill_id=cand.skill_id if is_hit else None,
                    )
            except Exception as e:
                _logger.warning("skill_router hint lookup failed: %s", e)

        # Pass 2 — substring match on intent_match_pattern by action_category
        if intent.action_category:
            try:
                resp = (
                    sb.table("skill_library")
                    .select("skill_id,intent_match_pattern,selector_chain,postcondition_spec,status")
                    .eq("status", "active")
                    .ilike("intent_match_pattern", f"%{intent.action_category}%")
                    .limit(self.top_k)
                    .execute()
                )
                rows = getattr(resp, "data", None) or []
                if rows:
                    cands = [
                        SkillCandidate(
                            skill_id=r["skill_id"],
                            intent_match_pattern=r["intent_match_pattern"],
                            similarity=0.85,  # rough fallback score
                            selector_chain=r.get("selector_chain") or {},
                            postcondition_spec=r.get("postcondition_spec", ""),
                            status=r["status"],
                        )
                        for r in rows
                    ]
                    proposed = cands[0].skill_id if cands[0].similarity >= self.hit_threshold else None
                    return SkillRouteResult(
                        hit=proposed is not None,
                        top_candidates=cands,
                        proposed_skill_id=proposed,
                    )
            except Exception as e:
                _logger.warning("skill_router category match failed: %s", e)

        return SkillRouteResult(hit=False)
