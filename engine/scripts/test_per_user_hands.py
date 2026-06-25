"""Per-user HANDS routing (Step 4) — the load-bearing proof that each signed-in user pilots their OWN
Chrome, not a shared/owner one. Drives the REAL /ws/extension WebSocket route (not a stub): a user
connects with ?user=<id>&token=<their core's token> and the WS binds to THAT user's core.browser_link.

Proves: 3 distinct cores -> 3 distinct browser_links with distinct tokens; user A's WS connects A's hand
ONLY (B's + default stay disconnected); A's token cannot bind user B (cross-user rejected). Pairs with
test_user_isolation (per-user DATA) to give per-user hands+data.
"""
import os
os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from fastapi.testclient import TestClient  # noqa: E402
from anticipy_engine.main import app  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402

fails = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)

A = registry.core_for("userA")
B = registry.core_for("userB")
D = registry.default_core()
check("3 distinct per-user cores", len({id(A), id(B), id(D)}) == 3)
check("3 distinct browser_links", len({id(A.browser_link), id(B.browser_link), id(D.browser_link)}) == 3)
tokA, tokB, tokD = A.browser_link.token, B.browser_link.token, D.browser_link.token
check("per-user hand tokens all differ", len({tokA, tokB, tokD}) == 3)

client = TestClient(app)

# A connects with A's id + A's token -> binds A's hand ONLY
with client.websocket_connect(f"/ws/extension?user=userA&token={tokA}") as wsA:
    wsA.send_json({"type": "ping"}); wsA.receive_json()  # round-trip => handler is past attach()
    check("A's hand connected", A.browser_link.connected is True, "A not connected")
    check("B's hand NOT connected (isolation)", B.browser_link.connected is False)
    check("default hand NOT connected (isolation)", D.browser_link.connected is False)
check("A's hand disconnects on close", A.browser_link.connected is False)

# cross-user: user=userB presenting A's token must be rejected (and must NOT connect B)
rejected = False
try:
    with client.websocket_connect(f"/ws/extension?user=userB&token={tokA}") as ws:
        ws.send_json({"type": "ping"}); ws.receive_json()
except Exception:
    rejected = True
check("cross-user token rejected (B not piloted by A's token)", rejected and B.browser_link.connected is False,
      f"rejected={rejected} B.connected={B.browser_link.connected}")

# B connects correctly with B's own token -> binds B's hand only
with client.websocket_connect(f"/ws/extension?user=userB&token={tokB}") as wsB:
    wsB.send_json({"type": "ping"}); wsB.receive_json()
    check("B's hand connected with B's own token", B.browser_link.connected is True)
    check("A's hand still NOT connected while B is", A.browser_link.connected is False)

print("PER-USER HANDS:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
import sys
sys.exit(1 if fails else 0)
