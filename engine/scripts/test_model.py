"""Room 5 test: the model wire holds (swappable, cost-tiered, stub by default).

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_model.py
"""
from anticipy_engine.model import ModelClient, Tier, think

# Default (no endpoint configured) => deterministic stub, no network.
default = ModelClient(endpoint=None)
assert default.mode == "stub"

out = think("What should I do about the 3pm meeting?")
assert isinstance(out, str) and out, "think() must return text"
assert "3pm meeting" in out, "stub should echo the prompt content"

# Cost discipline: tier is honored and routable.
cheap = think("tiny", tier=Tier.CHEAP)
smart = think("tiny", tier=Tier.SMART)
assert "cheap" in cheap and "smart" in smart and cheap != smart

# Swappable: pointing at our endpoint flips the mode (real path, not exercised here).
swapped = ModelClient(endpoint="https://model.anticipy.internal/v1/think")
assert swapped.mode == "endpoint"

print("PASS room 5: model wire")
print("  mode:", default.mode, "| think() ->", repr(out))
print("  tiers:", repr(cheap), "/", repr(smart))
