"""Slot resolver — fills `slots.needs_memory` and `slots.needs_inference`.

Takes an Intent's slot manifest and:
  - For each `needs_memory` slot, queries `anticipy_memory` via vector
    recall (semantic search over the wearer's accumulated knowledge).
  - For each `needs_inference` slot, applies deterministic rules
    (date-from-day, default duration, default location).

Returns a ResolvedSlots object with everything that could be filled,
plus a list of slots that REMAIN unresolved (router/policy uses this
to decide whether to ask via Aevoy).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from app.proactive.intent_extraction import IntentSlots, TypedIntent

_logger = logging.getLogger("anticipy.middle.slot_resolver")

# Sensible defaults applied for needs_inference slots when no specific
# rule matches.
_DEFAULTS: dict[str, Any] = {
    "duration_min": 60,
    "duration_default": 60,
    "party_size": 2,
    "urgency": "normal",
    "location_default": None,  # left None → caller decides
}


@dataclass(frozen=True, slots=True)
class ResolvedSlots:
    filled: dict[str, Any]
    resolved_from_memory: dict[str, Any] = field(default_factory=dict)
    resolved_by_inference: dict[str, Any] = field(default_factory=dict)
    still_unresolved: list[str] = field(default_factory=list)

    def merged(self) -> dict[str, Any]:
        out = dict(self.filled)
        out.update(self.resolved_from_memory)
        out.update(self.resolved_by_inference)
        return out


class SlotResolver:
    """Slot resolver. Vector recall over anticipy_memory + deterministic
    inference rules.
    """

    def __init__(self, supabase=None) -> None:
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

    def resolve(self, intent: TypedIntent) -> ResolvedSlots:
        slots = intent.slots
        from_mem = self._resolve_from_memory(intent.user_id, slots)
        by_inf = self._resolve_by_inference(slots, from_mem)
        unresolved: list[str] = []
        for slot in slots.needs_memory:
            if slot not in from_mem:
                unresolved.append(slot)
        for slot in slots.needs_inference:
            if slot not in by_inf:
                unresolved.append(slot)
        # Ambiguous slots are always unresolved unless inference picked
        # them up.
        for slot in slots.ambiguous:
            if slot not in by_inf and slot not in from_mem:
                unresolved.append(slot)
        return ResolvedSlots(
            filled=dict(slots.filled),
            resolved_from_memory=from_mem,
            resolved_by_inference=by_inf,
            still_unresolved=sorted(set(unresolved)),
        )

    def _resolve_from_memory(
        self, user_id: str, slots: IntentSlots
    ) -> dict[str, Any]:
        """Look up each `needs_memory` slot in anticipy_memory.

        Strategy:
          - For "wearer_*" slots → look up `kind=preference` rows.
          - For contact-shaped slots → `kind=contact`.
          - For habit-shaped slots → `kind=habit`.
          - For everything else → free text key match by slot name.
        """
        sb = self._ensure_supabase()
        if sb is None or not slots.needs_memory:
            return {}

        out: dict[str, Any] = {}
        try:
            for slot in slots.needs_memory:
                kind = self._infer_memory_kind(slot)
                resp = (
                    sb.table("anticipy_memory")
                    .select("kind,key,value,confidence")
                    .eq("user_id", user_id)
                    .eq("kind", kind)
                    .ilike("key", f"%{slot}%")
                    .order("confidence", desc=True)
                    .limit(1)
                    .execute()
                )
                rows = getattr(resp, "data", None) or []
                if rows:
                    out[slot] = rows[0]["value"]
        except Exception as e:
            _logger.warning("slot resolver memory lookup failed: %s", e)
        return out

    @staticmethod
    def _infer_memory_kind(slot_name: str) -> str:
        if slot_name.endswith("_email") or slot_name.endswith("_phone"):
            return "contact"
        if slot_name.startswith("wearer_") or "_default" in slot_name:
            return "preference"
        if slot_name in {"brand", "preferred_retailer", "favorite_coffee_spot"}:
            return "habit"
        return "preference"

    def _resolve_by_inference(
        self,
        slots: IntentSlots,
        from_mem: dict[str, Any],
    ) -> dict[str, Any]:
        """Deterministic inference. Date-from-day, defaults, etc."""
        out: dict[str, Any] = {}

        # date — derive from "day" slot if filled
        if "date" in slots.needs_inference:
            day_label = slots.filled.get("day") or from_mem.get("day")
            iso_date = self._day_label_to_iso(day_label)
            if iso_date is not None:
                out["date"] = iso_date

        # duration_default / duration_min
        for slot in ("duration_min", "duration_default"):
            if slot in slots.needs_inference and slot in _DEFAULTS:
                out[slot] = _DEFAULTS[slot]

        # location_default — leave to caller; only emit when explicitly None-OK
        # (downstream skill verifier decides whether to require a real location).

        # urgency
        if "urgency" in slots.needs_inference:
            out["urgency"] = _DEFAULTS["urgency"]

        return out

    @staticmethod
    def _day_label_to_iso(day_label: Optional[str]) -> Optional[str]:
        """Convert "Thursday", "next Monday", "tomorrow" -> ISO date.

        Anchor: today (system clock). Not timezone-aware — assumed local.
        """
        if not day_label:
            return None
        today = date.today()
        label = day_label.strip().lower()

        if label == "today":
            return today.isoformat()
        if label == "tomorrow":
            return (today + timedelta(days=1)).isoformat()
        if label == "yesterday":
            return (today - timedelta(days=1)).isoformat()

        weekdays = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        next_prefix = "next "
        target_label = label[len(next_prefix):] if label.startswith(next_prefix) else label
        if target_label in weekdays:
            target_idx = weekdays.index(target_label)
            today_idx = today.weekday()
            offset = (target_idx - today_idx) % 7
            # "next X" always means strictly future; bare "X" means
            # the soonest occurrence (today included only if X == today).
            if label.startswith(next_prefix) and offset == 0:
                offset = 7
            elif offset == 0:
                offset = 7
            return (today + timedelta(days=offset)).isoformat()

        # "next week" etc. — leave to caller for now
        return None
