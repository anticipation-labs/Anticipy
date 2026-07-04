"""Signed per-user PAIRING handshake (B12) — the hermetic PROOF that a valid signed pairing code
binds the browser hand to the RIGHT user's core, and a forged / expired / cross-secret one is
rejected. Closes the shared-cloud hole where the extension's unauthenticated GET /ws/token +
/ws/extension?token= (no ?user=) bound the hand to the OWNER core for every signed-in user.

Drives the REAL routes over HTTP/WS (TestClient), no Supabase, no model, no live Chrome:

  1. mint/verify pure-function battery — a valid code round-trips to its user; a wrong-secret
     forgery, a tampered signature, a swapped-payload code, an expired code, a bad prefix, and an
     empty code ALL verify to None (constant-time HMAC compare).
  2. POST /ws/pair (flag ON) — a valid code for USER_A returns A's OWN per-user browser_link token
     (== registry.core_for(A).browser_link.token); presenting that user+token on /ws/extension
     binds A's hand ONLY (default stays disconnected). A forged / expired / empty code -> 403.
  3. GET /ws/pair_code (flag ON) — mints a code that verifies back to the calling user.
  4. FLAG OFF is inert — with ANTICIPY_PER_USER_HANDS unset, both endpoints 404 even for a code
     that WOULD be valid, so today's single-owner behavior is untouched.
  5. PUBLIC-DEPLOY gate — with an owner token configured (a public deploy) + flag ON, /ws/pair is
     reachable with only the signed code (bypasses owner auth: a bad code -> 403, never 401), but
     the MINT endpoint /ws/pair_code still requires the signed-in caller (-> 401 without auth).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_per_user_pairing.py
"""
import os
import time

# --- hermetic env: free + deterministic; a FIXED HMAC secret; per-user hands ENABLED for the
# test process only (this does NOT flip the deploy flag — it lives in this process's env). ---
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ["ANTICIPY_TICK_SECONDS"] = "0"
os.environ["ANTICIPY_INBOUND_POLL_SECONDS"] = "0"
os.environ["ENGINE_INTERNAL_TOKEN"] = "test-engine-internal-secret-b12"
os.environ["ANTICIPY_PER_USER_HANDS"] = "1"
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)  # no owner token -> middleware open (local/suite)

from fastapi.testclient import TestClient  # noqa: E402
from anticipy_engine.main import app  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402
from anticipy_engine.core import pairing_codes as pc  # noqa: E402

USER_A = "11111111-1111-4111-8111-aaaaaaaaaaaa"

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------- (1) pure mint/verify battery
valid = pc.mint_pairing_code(USER_A)
check("valid code round-trips to its user", pc.verify_pairing_code(valid) == USER_A, str(valid))

# wrong-secret forgery: sign with a DIFFERENT secret, then verify under the real one -> None.
os.environ["ENGINE_INTERNAL_TOKEN"] = "attacker-guessed-a-different-secret"
forged = pc.mint_pairing_code(USER_A)
os.environ["ENGINE_INTERNAL_TOKEN"] = "test-engine-internal-secret-b12"
check("wrong-secret forgery rejected", pc.verify_pairing_code(forged) is None)

# tampered signature (last byte flipped) -> None.
_p = valid.rsplit(".", 1)[0]
_sig = valid.rsplit(".", 1)[1]
tampered = _p + "." + ("A" if _sig[0] != "A" else "B") + _sig[1:]
check("tampered signature rejected", pc.verify_pairing_code(tampered) is None)

# swapped payload (keep the signature, change the user id) -> None: the HMAC covers the payload.
other_payload = pc.mint_pairing_code("99999999-9999-4999-8999-cccccccccccc")
swapped = other_payload.rsplit(".", 1)[0] + "." + _sig
check("swapped-payload code rejected", pc.verify_pairing_code(swapped) is None)

# expired (minted 10s in the past with a 1s ttl) -> None even though the signature is valid.
expired = pc.mint_pairing_code(USER_A, ttl_seconds=1, now=time.time() - 10)
check("expired code rejected", pc.verify_pairing_code(expired) is None)
check("expired code has a VALID signature (only time killed it)",
      pc.verify_pairing_code(expired, now=time.time() - 10) == USER_A)

check("bad-prefix code rejected", pc.verify_pairing_code("nope." + valid) is None)
check("empty code rejected", pc.verify_pairing_code("") is None)
check("no-secret minting refuses",
      (lambda: (os.environ.__setitem__("ENGINE_INTERNAL_TOKEN", ""),
                pc.mint_pairing_code(USER_A) is None,
                os.environ.__setitem__("ENGINE_INTERNAL_TOKEN", "test-engine-internal-secret-b12"))[1])())

client = TestClient(app)

# ---------------------------------------------------------------- (2) POST /ws/pair binds the RIGHT core
core_A = registry.core_for(USER_A)
default_core = registry.default_core()
code_A = pc.mint_pairing_code(USER_A)
r = client.post("/ws/pair", json={"code": code_A})
check("valid claim -> 200", r.status_code == 200, r.text)
body = r.json() if r.status_code == 200 else {}
check("claim returns the target user id", body.get("user") == USER_A, str(body))
check("claim returns A's OWN per-user hand token",
      body.get("token") == core_A.browser_link.token, str(body))

# the returned user+token binds A's hand ONLY (default core stays disconnected).
with client.websocket_connect(f"/ws/extension?user={USER_A}&token={body.get('token')}") as wsA:
    wsA.send_json({"type": "ping"}); wsA.receive_json()  # round-trip => past attach()
    check("A's hand connected via the paired token", core_A.browser_link.connected is True)
    check("default/owner hand NOT connected (isolation)", default_core.browser_link.connected is False)
check("A's hand disconnects on close", core_A.browser_link.connected is False)

check("forged code -> 403", client.post("/ws/pair", json={"code": forged}).status_code == 403)
check("expired code -> 403", client.post("/ws/pair", json={"code": expired}).status_code == 403)
check("empty code -> 403", client.post("/ws/pair", json={"code": ""}).status_code == 403)

# ---------------------------------------------------------------- (3) GET /ws/pair_code mints a real code
rc = client.get("/ws/pair_code")
check("mint endpoint -> 200", rc.status_code == 200, rc.text)
minted = rc.json().get("code") if rc.status_code == 200 else None
check("minted code verifies to the calling user",
      pc.verify_pairing_code(minted) == registry.current_user(), str(minted))

# ---------------------------------------------------------------- (4) FLAG OFF is inert
os.environ["ANTICIPY_PER_USER_HANDS"] = "0"
check("flag off -> /ws/pair 404 (even a would-be-valid code)",
      client.post("/ws/pair", json={"code": pc.mint_pairing_code(USER_A)}).status_code == 404)
check("flag off -> /ws/pair_code 404", client.get("/ws/pair_code").status_code == 404)
os.environ["ANTICIPY_PER_USER_HANDS"] = "1"  # restore for the public-deploy sub-test

# ---------------------------------------------------------------- (5) PUBLIC-DEPLOY auth gate
# With an owner token set (a public deploy), the CLAIM endpoint must be reachable with ONLY the
# signed code (its HMAC is the auth) -> a bad code returns 403, NOT the middleware's 401. The MINT
# endpoint must still demand the signed-in caller -> 401 without any bearer.
os.environ["ANTICIPY_OWNER_API_TOKEN"] = "owner-secret-for-public-deploy"
try:
    claim = client.post("/ws/pair", json={"code": "apc1.bogus.0.bad"})
    check("public deploy: /ws/pair bypasses owner auth (bad code -> 403, not 401)",
          claim.status_code == 403, f"status={claim.status_code} body={claim.text}")
    good = client.post("/ws/pair", json={"code": pc.mint_pairing_code(USER_A)})
    check("public deploy: a VALID signed code still claims (-> 200)",
          good.status_code == 200, f"status={good.status_code} body={good.text}")
    mint_unauth = client.get("/ws/pair_code")
    check("public deploy: /ws/pair_code still requires the signed-in caller (-> 401)",
          mint_unauth.status_code == 401, f"status={mint_unauth.status_code} body={mint_unauth.text}")
finally:
    os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)

print("PER-USER PAIRING:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
import sys  # noqa: E402
sys.exit(1 if fails else 0)
