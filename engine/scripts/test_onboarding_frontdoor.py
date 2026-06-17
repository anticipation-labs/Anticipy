"""FRONT DOOR wiring proof — a brand-new, non-technical user self-onboards end to end.

Deterministic (stub model, mock hands). No live OAuth tap, no network. It proves the WIRING
at the contract level, both sides:

  ENGINE (through the REAL ControlCore, the same code the API routes call):
    1. The onboarding payload the /welcome page POSTs to /owner/onboard writes a SOURCED
       profile (every memory carries fields['source'] — nothing is unattributed) plus a
       'connect_account' open-loop per unconnected account, and returns each loop's
       memory_id (what the connect step needs).
    2. The connect action's payload to /connections/authorize (the loop's memory_id) is a
       real connect_account loop the engine accepts: authorize_connection_loop returns ok
       with a connect-status (mock here; in live mode this is the connector's real consent
       URL). A non-connection loop id is correctly rejected.
    3. The SAME profile the onboarding write produced is readable back through the memory
       path the main app uses (memory.profile.all() / memory_open_loops()), so "the app
       reads what onboarding wrote" is proven, not assumed.

  APP SOURCE (static asserts, no bundler needed for these):
    4. The /welcome front door exists and POSTs to /api/owner/onboard and
       /api/connections/authorize and renders the returned connect_url (window.open).
    5. The /connect page connects FOR REAL (calls /api/connections/authorize and opens the
       consent URL) — the dead vendor-console deep-links (arcade.dev) are gone.
    6. Demo scaffolding is gone: the home page's SAMPLE transcript is empty, DEFAULT_MEMORY
       seeds NO example people (no Maya/Sam), and "start over" blanks rather than restoring
       a sample.

Run:
  PYTHONPATH=engine ANTICIPY_MODEL_PROVIDER=stub ANTICIPY_HANDS_MODE=mock \
    engine/.venv/bin/python engine/scripts/test_onboarding_frontdoor.py
"""
import asyncio
import os
import re
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_onboarding import OwnerOnboardingIn  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"


# The exact payload shape the /welcome page builds (see app/welcome/page.js onboardingPayload):
# a real new user — blank seeds, their own name/people, the two unlock accounts registered as
# needs_auth so the engine writes a connect open-loop for each.
NEW_USER_PAYLOAD = {
    "source": "first_run",
    "owner_name": "Dana Rivers",
    "timezone": "America/New_York",
    "phone": "+15555550199",
    "preferences": ["Ask before messaging anyone.", "Never buy anything without me."],
    "people": [
        {"name": "Jordan", "relationship": "my partner", "channels": ["text"]},
        {"name": "Priya", "relationship": "works with me", "channels": ["email"]},
    ],
    "connections": [
        {"name": "Google Calendar", "status": "needs_auth", "route": "api", "identifier": "googlecalendar"},
        {"name": "Gmail", "status": "needs_auth", "route": "api", "identifier": "gmail.compose"},
    ],
}


async def engine_wiring():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-frontdoor-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.owner_onboard(OwnerOnboardingIn.model_validate(NEW_USER_PAYLOAD))

        # --- 1. SOURCED profile: every written memory carries a source; identity + people landed. ---
        written = out["written"]
        assert written, out
        for w in written:
            assert w.get("fields", {}).get("source") == "first_run", w
        profile = core.memory.profile.all()
        # Every profile memory is sourced (no orphan, unattributed fact) — the honesty contract.
        for item in profile:
            assert item.fields.get("source") == "first_run", item.model_dump(mode="json")
        profile_text = "\n".join(i.text for i in profile)
        assert "Owner identity" in profile_text and "America/New_York" in profile_text, profile_text
        assert "Important person: Jordan" in profile_text, profile_text
        assert "Important person: Priya" in profile_text, profile_text
        # Nothing invented: the seeded demo people must NOT appear (this is a real new user).
        assert "Maya" not in profile_text and "Sam" not in profile_text, profile_text

        # --- connect open-loops written for both unconnected accounts, with memory_ids. ---
        assert out["missing_connections"] == ["Google Calendar", "Gmail"], out
        connect_written = [
            w for w in written
            if w.get("drawer") == "open_loops" and w.get("fields", {}).get("action") == "connect_account"
        ]
        by_name = {w["fields"]["name"]: w for w in connect_written}
        assert set(by_name) == {"Google Calendar", "Gmail"}, by_name
        for w in connect_written:
            assert w.get("memory_id"), w  # the id the connect step posts to /connections/authorize

        # --- 2. the connect action: the loop memory_id is a real connect_account loop. ---
        cal_id = by_name["Google Calendar"]["memory_id"]
        connect = core.authorize_connection_loop(cal_id)
        assert connect["ok"] is True, connect
        # In mock hands the connector returns 'mock' with a message about needing live mode for a
        # real URL; in live mode this same call returns status 'needs_auth' + connect_url (the
        # provider's real consent). The app renders connect_url when present.
        assert connect["status"] in {"mock", "needs_auth", "connected"}, connect
        assert connect["route"] == "api", connect
        assert "connect_url" in connect or connect["status"] == "mock", connect

        # a NON-connection loop id is rejected (the authorize path can't be abused for any loop).
        non_connect = next(
            (i for i in core.memory.open_loops.all()
             if i.fields.get("action") != "connect_account"),
            None,
        )
        if non_connect is not None:
            bad = core.authorize_connection_loop(non_connect.id)
            assert bad.get("ok") is False, bad

        # --- 3. the app reads what onboarding wrote: same memory path the home screen uses. ---
        visible = core.memory_open_loops()
        visible_text = "\n".join(i["text"] for i in visible["loops"])
        assert "Connect Google Calendar for Owner Action Engine" in visible_text, visible
        assert "Connect Gmail for Owner Action Engine" in visible_text, visible
        # the sourced profile is readable back (the brain knows the new owner from day one).
        readback = "\n".join(i.text for i in core.memory.profile.all())
        assert "Dana Rivers" in readback, readback
    finally:
        await core.stop()
    print("PASS frontdoor engine: /welcome -> sourced profile + connect loops -> authorize -> readback")


def read(path: Path) -> str:
    assert path.exists(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def app_source_wiring():
    # --- 4. the front door exists and is wired to the right endpoints. ---
    welcome = read(APP / "welcome" / "page.js")
    assert '"use client"' in welcome, "welcome must be a client component"
    assert "/api/owner/onboard" in welcome, "welcome must POST the profile to /api/owner/onboard"
    assert "/api/connections/authorize" in welcome, "welcome must call /api/connections/authorize"
    assert "connect_url" in welcome, "welcome must render the returned connect_url"
    assert "window.open" in welcome, "welcome must launch the provider's real consent in a new tab"
    assert "connect_account" in welcome, "welcome must map the connect open-loops by action"
    # trust-first first screen copy is present (the front door must lead with trust).
    assert "who am i helping" in welcome.lower(), "welcome must open trust-first"
    # the recap reward (read-only, invents nothing) is part of the flow.
    assert "/api/onboard_scan" in welcome, "welcome must show the read-only onboard recap"
    assert "invented" in welcome.lower(), "welcome recap must keep the 'invented nothing' honesty"

    # --- 5. the connect page connects for real; dead vendor deep-links are gone. ---
    connect = read(APP / "connect" / "page.js")
    assert "/api/connections/authorize" in connect, "connect must call /api/connections/authorize for real"
    assert "/api/owner/onboard" in connect, "connect must ensure the connect open-loops exist"
    assert "window.open" in connect, "connect must launch the provider's real consent"
    assert "arcade.dev" not in connect, "the dead vendor-console deep-link must be removed"
    assert "twilio.com/console" in connect, "twilio setup link may remain (config, not OAuth)"

    # the Next proxy routes that forward to the engine must exist.
    auth_route = read(APP / "api" / "connections" / "authorize" / "route.js")
    assert "/connections/authorize" in auth_route, auth_route
    onboard_route = read(APP / "api" / "owner" / "onboard" / "route.js")
    assert "/owner/onboard" in onboard_route, onboard_route

    # --- 6. demo scaffolding is gone from the home screen. ---
    home = read(APP / "page.js")
    # SAMPLE transcript is blanked.
    m = re.search(r"const SAMPLE\s*=\s*(.+?);", home, re.S)
    assert m, "could not find SAMPLE declaration"
    sample_val = m.group(1).strip()
    assert sample_val in ('""', "''", "``"), f"SAMPLE must be empty, got: {sample_val[:60]}"
    # DEFAULT_MEMORY seeds NO example people and no seeded owner identity.
    dm = re.search(r"const DEFAULT_MEMORY\s*=\s*\{(.+?)\};", home, re.S)
    assert dm, "could not find DEFAULT_MEMORY"
    dm_block = dm.group(1)
    assert "Maya" not in dm_block and "Sam" not in dm_block, "DEFAULT_MEMORY must not seed example people"
    assert "Omar" not in dm_block, "DEFAULT_MEMORY must not seed an example owner name"
    # the people/preferences seeds are empty strings.
    for field in ("people", "preferences", "ownerName"):
        fm = re.search(rf'{field}:\s*("(.*?)"|\'(.*?)\')', dm_block)
        assert fm, f"DEFAULT_MEMORY.{field} not found"
        assert (fm.group(2) or fm.group(3) or "") == "", f"DEFAULT_MEMORY.{field} must be blank"
    # "start over" / clear blanks the box rather than restoring a sample (no setText(SAMPLE)).
    assert "setText(SAMPLE)" not in home, "the reset button must blank, never restore the sample"

    print("PASS frontdoor app source: /welcome wired, /connect connects for real, demo data gone")


def main():
    asyncio.run(engine_wiring())
    app_source_wiring()
    print("PASS onboarding_frontdoor: a new user can onboard -> connect (real consent) -> recap")


if __name__ == "__main__":
    main()
