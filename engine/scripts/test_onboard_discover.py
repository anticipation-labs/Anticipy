"""Slice 1 (engine): the /onboard/discover ingest path writes the per-person mesh from a scan.

Proves core.onboard_discover (what POST /onboard/discover calls) turns a logged-in-Chrome
connection scan into the mesh via the SAME build_onboarding_plan path typed onboarding uses:
each discovered logged-in service -> a profile card + a 'Connect X' open-loop, and a service
Anticipy already holds a vault token for -> connected (no Connect loop). No Chrome, no network.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboard_discover.py
"""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ["ANTICIPY_VAULT_KEY"] = "test-master-key-do-not-use-in-prod"

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.hands.token_vault import ROUTE_API  # noqa: E402

DISCOVERED = [
    {"service": "Gmail", "logged_in": True, "identifier": "owner@gmail.com",
     "url": "https://mail.google.com"},
    {"service": "Google Calendar", "logged_in": True},
    {"service": "Cosmolex", "logged_in": True, "url": "https://app.cosmolex.com"},  # niche CRM -> browser
    {"service": "Gmail", "logged_in": True},      # duplicate -> deduped
    {"service": "Reddit", "logged_in": False},    # logged out -> skipped
]


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-discover-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.onboard_discover(DISCOVERED, source="chrome_scrape")
        # no vault tokens yet -> all three discovered services are needs_auth -> Connect loops
        assert out["discovered_count"] == 5, out
        names = [c["name"] for c in out["connections"]]
        assert names == ["Gmail", "Google Calendar", "Cosmolex"], names
        assert set(out["missing_connections"]) == {"Gmail", "Google Calendar", "Cosmolex"}, out["missing_connections"]

        loop_text = "\n".join(i.text for i in core.memory.open_loops.all())
        assert "Connect Gmail for Owner Action Engine" in loop_text, loop_text
        assert "Connect Cosmolex for Owner Action Engine" in loop_text, loop_text
        profile_text = "\n".join(i.text for i in core.memory.profile.all())
        assert "App connection: Google Calendar; status: needs_auth; route: api" in profile_text, profile_text
        assert "App connection: Cosmolex; status: needs_auth; route: browser" in profile_text, profile_text

        # the real scrape is glass-boxed so the reality gate can read it back as PROOF it fired
        ob = [e for e in core.glassbox.entries() if e["kind"] == "onboard_discover"]
        assert len(ob) == 1, ("a real scan with connections logs exactly one onboard_discover", ob)
        assert ob[0]["data"]["discovered_count"] == 5, ob[0]["data"]
        assert ob[0]["data"]["connected_count"] == 0, ob[0]["data"]  # no vault tokens yet
        assert {c["name"] for c in ob[0]["data"]["connections"]} == {"Gmail", "Google Calendar", "Cosmolex"}, ob[0]["data"]

        # now Anticipy holds a Gmail token -> a re-scan marks Gmail connected (no Connect loop)
        uid = core.api_hand.user_id
        core.token_vault.store_token(uid, "gmail", "arc_FAKE-tok", route=ROUTE_API)
        out2 = await core.onboard_discover(DISCOVERED, source="chrome_scrape")
        assert set(out2["missing_connections"]) == {"Google Calendar", "Cosmolex"}, out2["missing_connections"]
        gmail = [c for c in out2["connections"] if c["name"] == "Gmail"][0]
        assert gmail["status"] == "connected", gmail

        # the gmail-token re-scan also logged (connected_count now 1) -> two real scrapes so far
        ob = [e for e in core.glassbox.entries() if e["kind"] == "onboard_discover"]
        assert len(ob) == 2 and ob[-1]["data"]["connected_count"] == 1, [e["data"] for e in ob]

        # defenses (skeptic-found): a non-list scalar -> empty (no crash); an oversized list is capped
        scalar = await core.onboard_discover(12345)
        assert scalar["discovered_count"] == 0 and scalar["connections"] == [], scalar
        # an EMPTY/no-op scan must NOT look like an onboarding event (honesty: no false proof)
        ob_after_empty = [e for e in core.glassbox.entries() if e["kind"] == "onboard_discover"]
        assert len(ob_after_empty) == 2, ("empty scan must log no onboard_discover", len(ob_after_empty))
        big = [{"service": f"svc{i}", "logged_in": True} for i in range(500)]
        capped = await core.onboard_discover(big)
        assert capped["discovered_count"] == 100, capped["discovered_count"]
    finally:
        await core.stop()

    print("PASS: /onboard/discover ingest writes the per-person mesh from a Chrome scan")
    print("  discovered logged-in services -> Connect loops; held vault token -> connected")


if __name__ == "__main__":
    asyncio.run(main())
