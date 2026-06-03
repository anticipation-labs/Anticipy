"""Room 5: the model wire.

One ``think()`` call, reached through OUR OWN endpoint (swappable, so we control
cost and can change models without touching callers). The app never calls a
provider directly — only the engine, only through here. Cost discipline lives
here too: cheap tier for easy steps, smart tier only for hard reasoning.
"""
from .client import ModelClient, Tier, think  # noqa: F401
