"""Anticipy universal action loop.

One orchestrator that drives ANY web surface by reading the DOM
accessibility tree plus a screenshot, asking the vision model for the
next concrete action, dispatching that action over CDP against an
Anticipy-owned background tab, observing the result, and repeating
until the goal is satisfied or the wall-clock deadline expires. No
per-app recipes, no hardcoded skill library, no per-domain branches.
Calendar, Salesforce, Slack, a law firm's bespoke matter portal all
get the same treatment.

This wraps the existing DSv4SkillRunner (the Ralph Loop at
``engine/app/action_engine/dsv4_skill_runner.py``) plus the existing
generic CDP dispatcher (``engine/app/action_engine/cdp_dispatcher.py``)
and the Anticipy-owned background-window tab ownership it already
implements via ``Target.createTarget(background=True)``. No frozen
file is touched; this layer is additive.
"""

from .action_loop import run_until_done

__all__ = ["run_until_done"]
