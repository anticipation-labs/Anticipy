"""final/context — the ONE final context / memory learns-you layer (Phase 3).

Behind the live_memory facade, this package makes the assistant resolve references
and never re-ask a known fact:

  - reference_resolver.resolve_reference  — "my usual" -> the stored oat latte  (a)
  - reconcile.{reconcile,handle_retraction} — Mem0 ADD/UPDATE/DELETE/NOOP        (b)
  - dossier.PersonBook                    — two Sams -> disambiguate or ask      (c)
  - never_re_ask.NeverReAskLedger         — fill a known slot instead of asking  (d)

``ContextEngine`` is the facade the engine wires at intake (control_core).
"""

from .engine import ContextEngine

__all__ = ["ContextEngine"]
