"""Endpoint test: GET /readiness — the guided connect-your-accounts checklist.

This is the HTTP surface the app's "Connect your accounts" page reads. It reports,
for each capability that turns an owner action LIVE, whether it is connected or still
needs connecting, plus an honest one-liner of what to do. It exposes only the
PRESENCE/ABSENCE of config — NEVER a secret value.

BROWSER-ONLY (Omar signed off 2026-07-04): the API-connect arm (Arcade/OAuth "connect
your calendar & email") is deleted, so the checklist no longer carries a google_arcade
row — the browser hand + comms line are the live capabilities it reports.

Asserts, against ONE booted engine:
  - default (mock) env -> all three capabilities (twilio, browser_bridge,
    apple_signing) report status "needs_connect", each with a non-empty
    what_to_do, overall "needs_connect".
  - the shape is stable: {overall, live_count, total, capabilities:[{capability,
    label, status, what_to_do}]} and status is always live|needs_connect.
  - presence flips the status: with live channels + Twilio creds + owner phone,
    and APPLE_DEVELOPER_ID set, those two flip to "live"; NONE of the secret
    VALUES appear anywhere in the response.
  - it is owner-gated: with ANTICIPY_OWNER_API_TOKEN set, an anonymous GET is 401;
    the same GET with the token succeeds.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_readiness.py
"""
import importlib
import os
import tempfile

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-readiness-")
# Force the browser bridge probe deterministically UNAVAILABLE (path does not exist),
# so this test never depends on whether engine/.bu-venv happens to be installed in CI.
os.environ["ANTICIPY_BROWSERUSE_PYTHON"] = "/nonexistent/anticipy/bridge/python"

CAPS = {"twilio", "browser_bridge", "apple_signing"}
SECRETS = {
    "ARCADE_API_KEY": "SUPERSECRET_ARC_xyz",
    "TWILIO_ACCOUNT_SID": "ACtotallysecret123",
    "TWILIO_AUTH_TOKEN": "tok_super_secret_abc",
    "TWILIO_FROM": "+15550000000",
    "OWNER_PHONE": "+15551112222",
    "APPLE_DEVELOPER_ID": "Developer ID Application: Secret Person (SECRETTEAM)",
}


def _check_shape(data, fails):
    if data.get("overall") not in {"all_live", "needs_connect"}:
        fails.append(f"overall must be all_live|needs_connect: {data.get('overall')}")
    caps = data.get("capabilities")
    if not isinstance(caps, list):
        fails.append(f"capabilities must be a list: {caps!r}")
        return {}
    by = {}
    for cap in caps:
        for field in ("capability", "label", "status", "what_to_do"):
            if not cap.get(field):
                fails.append(f"capability missing {field}: {cap}")
        if cap.get("status") not in {"live", "needs_connect"}:
            fails.append(f"status must be live|needs_connect: {cap}")
        by[cap.get("capability")] = cap
    if set(by) != CAPS:
        fails.append(f"capabilities must be exactly {CAPS}, got {set(by)}")
    if data.get("total") != len(caps):
        fails.append(f"total must equal capability count: {data.get('total')} vs {len(caps)}")
    live = sum(1 for c in caps if c.get("status") == "live")
    if data.get("live_count") != live:
        fails.append(f"live_count must equal live capabilities: {data.get('live_count')} vs {live}")
    return by


def _boot_client():
    """Re-import main fresh so a per-scenario environment (live creds, owner token)
    is read at construction time — the engine reads env at startup."""
    import anticipy_engine.main as main_mod

    main_mod = importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    return TestClient(main_mod.app), main_mod


def main():
    fails = []

    # (1) default mock env -> everything needs_connect, honest what_to_do each.
    client, _ = _boot_client()
    with client:
        r = client.get("/readiness")
        if r.status_code != 200:
            fails.append(f"default GET /readiness should be 200: {r.status_code} {r.text}")
        data = r.json()
        by = _check_shape(data, fails)
        for name in CAPS:
            if by.get(name, {}).get("status") != "needs_connect":
                fails.append(f"{name} should be needs_connect in mock env: {by.get(name)}")
        if data.get("overall") != "needs_connect":
            fails.append(f"mock env overall should be needs_connect: {data.get('overall')}")

    # (2) presence flips status; NO secret value leaks into the response.
    saved = {k: os.environ.get(k) for k in (*SECRETS, "ANTICIPY_HANDS_MODE", "ANTICIPY_CHANNELS_MODE")}
    try:
        os.environ.update(SECRETS)
        os.environ["ANTICIPY_HANDS_MODE"] = "live"
        os.environ["ANTICIPY_CHANNELS_MODE"] = "live"
        client, _ = _boot_client()
        with client:
            data = client.get("/readiness").json()
            by = _check_shape(data, fails)
            for name in ("twilio", "apple_signing"):
                if by.get(name, {}).get("status") != "live":
                    fails.append(f"{name} should be live with creds present: {by.get(name)}")
            import json as _json

            blob = _json.dumps(data)
            for label, value in SECRETS.items():
                if value in blob:
                    fails.append(f"SECRET LEAK: {label} value appeared in /readiness output")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # (3) owner-gated: token set -> anonymous 401, with token 200.
    os.environ["ANTICIPY_OWNER_API_TOKEN"] = "test-owner-token-readiness"
    try:
        client, _ = _boot_client()
        with client:
            anon = client.get("/readiness")
            if anon.status_code != 401:
                fails.append(f"with token set, anonymous /readiness must be 401: {anon.status_code}")
            ok = client.get("/readiness", headers={"x-anticipy-owner-token": "test-owner-token-readiness"})
            if ok.status_code != 200:
                fails.append(f"with token header, /readiness must be 200: {ok.status_code} {ok.text}")
    finally:
        os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)

    if fails:
        print("FAIL test_readiness:")
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print("PASS test_readiness: /readiness reports per-capability connect status (presence-only), owner-gated")


if __name__ == "__main__":
    main()
