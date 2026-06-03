"""Room 9 test: action layer — gate + connector/browser adapter seams.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_actions.py
"""
from anticipy_engine.actions import ActionLayer, BrowserAdapter, ConnectorAdapter
from anticipy_engine.actions.base import ActionAdapter
from anticipy_engine.shared.schema import ActionRequest

layer = ActionLayer()

# low risk + connector path -> gate says ACT -> connector stub runs
low = ActionRequest(intent="add calendar hold", risk="low", path="connector")
out = layer.handle(low)
assert out["decision"] == "act"
assert out["result"]["stub"] is True and out["result"]["path"] == "connector"

# needs_confirm -> gate says CONFIRM -> not executed (result None)
confirm = ActionRequest(intent="send email", risk="needs_confirm", path="connector")
out2 = layer.handle(confirm)
assert out2["decision"] == "confirm" and out2["result"] is None

# ask_human -> ESCALATE
esc = ActionRequest(intent="wire money", risk="ask_human", path="browser")
assert layer.handle(esc)["decision"] == "escalate"

# both adapters share the interface; connector vendor is TBD
assert issubclass(ConnectorAdapter, ActionAdapter) and issubclass(BrowserAdapter, ActionAdapter)
assert ConnectorAdapter.vendor is None

print("PASS room 9: action layer (gate + connector/browser seams)")
print("  low/connector ->", out["decision"], out["result"]["note"])
print("  needs_confirm ->", out2["decision"], "(gated, not executed)")
print("  ask_human     ->", "escalate")
