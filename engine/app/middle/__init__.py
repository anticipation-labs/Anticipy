"""Middle layer — Intent → Task dispatcher.

Listens on Supabase Realtime channel `intent.detected.{user_id}` for new
rows in `anticipy_intents_v2`. For each Intent that's a COMMIT (or a
fired STORE_AS_LATENT followup), runs the cascade:

   slot_resolver  — fill `slots.needs_memory` from anticipy_memory
                    (vector recall) and `slots.needs_inference` from
                    deterministic rules (date-from-day, sensible defaults).
   skill_router   — top-K skill candidates from skill_library via
                    vector search on intent_match_pattern. Hit returns
                    a parameterized recipe; miss triggers plan-from-scratch.
   policy         — decide fire / confirm-via-aevoy / refuse based on
                    irreversibility, financial cost, ambiguity.
   dispatcher     — INSERT Task into anticipy_tasks_v2; the executor
                    subscribed to task.dispatched.{user_id} picks it up.

Pure deterministic Python wherever possible — every LLM call here
should be considered a code smell. The cascade's LLM decisions all
happen in Pod A; the middle layer is rule-based.
"""

from .dispatcher import Dispatcher, DispatchResult
from .policy import PolicyDecision, PolicyDispatchAction, PolicyEngine
from .skill_router import SkillRouter, SkillRouteResult
from .slot_resolver import ResolvedSlots, SlotResolver

__all__ = [
    "Dispatcher",
    "DispatchResult",
    "PolicyDecision",
    "PolicyDispatchAction",
    "PolicyEngine",
    "ResolvedSlots",
    "SkillRouter",
    "SkillRouteResult",
    "SlotResolver",
]
