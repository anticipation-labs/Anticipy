"""Proactive helpers and legacy loop scaffold.

The product proactive spine is `anticipy_engine.core.proactive.ProactiveEngine`.
This package holds supporting pieces such as triage, harm-line, decider,
triggering, follow-up, anticipation, and shared contracts.

`anticipy_engine.proactive.engine.ProactiveEngine` is retained as a legacy
scaffold; do not treat it as the running product engine.
"""
from .engine import ProactiveEngine  # noqa: F401
