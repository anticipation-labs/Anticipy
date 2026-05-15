"""Dispatcher — emits Task to anticipy_tasks_v2.

After slot resolution + skill routing + policy, the dispatcher writes
the Task row to Supabase. The executor app subscribed to Realtime
channel `task.dispatched.{user_id}` picks it up automatically.

For policy.action == REFUSE, no row is written (Pod A already
recorded the Intent; nothing more to do).

For policy.action == AEVOY_CONFIRM, the Task is written but with
`aevoy_confirmation_required=true` so the executor blocks until the
[ANTICIPY-Q] reply arrives.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Optional

from app.middle.policy import PolicyDecision, PolicyDispatchAction
from app.middle.skill_router import SkillRouteResult
from app.middle.slot_resolver import ResolvedSlots
from app.proactive.intent_extraction import TypedIntent

_logger = logging.getLogger("anticipy.middle.dispatcher")


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _substitute_placeholders(step: dict, params: dict) -> dict:
    """Replace {{slot_name}} in step values + target_refs with values
    from params. Leaves unresolved placeholders in place so the
    executor can detect missing slots.
    """
    out = dict(step)
    for k in ("value", "target_ref"):
        v = out.get(k)
        if isinstance(v, str) and "{{" in v:
            out[k] = _PLACEHOLDER_RE.sub(
                lambda m: str(params.get(m.group(1), m.group(0))),
                v,
            )
    return out


@dataclass(frozen=True, slots=True)
class DispatchResult:
    dispatched: bool
    task_id: Optional[str]
    reason: str


class Dispatcher:
    """Writes anticipy_tasks_v2 rows. Realtime publication on the table
    handles the channel push.
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

    def dispatch(
        self,
        intent: TypedIntent,
        slots: ResolvedSlots,
        route: SkillRouteResult,
        policy: PolicyDecision,
    ) -> DispatchResult:
        if policy.action == PolicyDispatchAction.REFUSE:
            return DispatchResult(dispatched=False, task_id=None, reason=policy.reason)

        sb = self._ensure_supabase()
        if sb is None:
            return DispatchResult(
                dispatched=False, task_id=None, reason="supabase_unavailable"
            )

        task_id = str(uuid.uuid4())
        merged_params = slots.merged()
        # Substitute {{slot_name}} placeholders in the recipe steps from
        # merged params. Bootstrap recipes (in skill_library.selector_chain
        # .steps) use {{url}}/{{day}}/etc. placeholders that the dispatcher
        # fills here. Walks step values + target_refs.
        raw_steps = (
            route.top_candidates[0].selector_chain.get("steps", [])
            if route.top_candidates
            else []
        )
        recipe_steps = [_substitute_placeholders(step, merged_params) for step in raw_steps]
        row = {
            "task_id": task_id,
            "intent_id": intent.intent_id,
            "user_id": intent.user_id,
            "skill_id": route.proposed_skill_id,
            "parameters": merged_params,
            "recipe_steps": recipe_steps,
            "global_postcondition": (
                {
                    "verifier": route.top_candidates[0].postcondition_spec,
                    "spec": {},
                }
                if route.top_candidates
                else None
            ),
            "rollback_spec": (
                {"compensate": f"skills/{route.proposed_skill_id}/compensate.py", "spec": {}}
                if route.proposed_skill_id
                else None
            ),
            "rehearsal_required": policy.rehearsal_required,
            "irreversible": policy.irreversible,
            "aevoy_confirmation_required": policy.aevoy_confirmation_required,
        }
        try:
            sb.table("anticipy_tasks_v2").insert(row).execute()
            _logger.info(
                "dispatched task %s for intent %s (skill=%s, action=%s)",
                task_id,
                intent.intent_id,
                route.proposed_skill_id,
                policy.action.value,
            )
            return DispatchResult(dispatched=True, task_id=task_id, reason=policy.reason)
        except Exception as e:
            _logger.error("dispatch insert failed: %s", e)
            return DispatchResult(dispatched=False, task_id=None, reason=f"insert_failed:{e}")
