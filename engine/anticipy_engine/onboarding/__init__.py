"""Onboarding — the first front-door slice of "it scrapes everything about you
and builds your profile."

The product promise: when a new person (or an entity the user cares about) comes
on board, Anticipy quietly reads the PUBLIC web about them and assembles a
structured profile it can reason over later — name, role, org, location, a few
key facts — each fact carrying its own source URL and a trust grade.

Trust is not an afterthought. It is built in from the browser-arm reliability
finding (see hands/browser_use_link.py): a live page read is the actor grading
its own homework, so FINE-grained extracted facts get flagged
`needs_cross_check=True` while COARSE whole-page reads are trusted a tier higher.
The profile carries that grade per fact so downstream consumers never mistake a
shaky pull for ground truth.

READ-ONLY public pages only. No login, no money, no writes — onboarding observes.
"""
from .profile_builder import (  # noqa: F401
    ProfileBuilder,
    ProfileFact,
    Profile,
    Source,
    build_profile,
)
