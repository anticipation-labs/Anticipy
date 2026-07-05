"""FRONT DOOR wiring proof — a brand-new, non-technical user self-onboards end to end.

Deterministic (stub model, mock hands). No live OAuth tap, no network. It proves the WIRING
at the contract level, both sides:

  ENGINE (through the REAL ControlCore, the same code the API routes call):
    1. The onboarding payload the /welcome page POSTs to /owner/onboard writes a SOURCED
       profile (every memory carries fields['source'] — nothing is unattributed) plus a
       'connect_account' open-loop per unconnected account, and returns each loop's
       memory_id (what the connect step needs).
    2. BROWSER-ONLY (Omar signed off 2026-07-04): the API-connect arm
       (authorize_connection_loop / /connections/authorize) was deleted. Onboarding still
       writes a connect_account loop per unconnected account; those loops now resolve
       through the browser flow, not an Arcade/OAuth authorize handshake.
    3. The SAME profile the onboarding write produced is readable back through the memory
       path the main app uses (memory.profile.all() / memory_open_loops()), so "the app
       reads what onboarding wrote" is proven, not assumed.

  APP SOURCE (static asserts, no bundler needed for these):
    Post Phase-Zero refactor: app/welcome/page.js and app/page.js are thin server wrappers
    that mount ONE client app, app/phase-zero/PhaseZeroApp.js, with a screen prop. The
    marketing front door is its WelcomeScreen. These asserts point at the real current files.
    4. The /welcome front door exists: it mounts the Phase-Zero client app, which renders the
       trust-first WelcomeScreen and still drives the read-only onboard recap (/api/onboard_scan).
    5. BROWSER-ONLY (Omar signed off 2026-07-04): the API-connect /connect page and the
       /api/connections/authorize proxy were DELETED — there is no "connect your calendar &
       email" API arm. The onboarding proxy (/api/owner/onboard) that forwards to the engine
       still exists and stays wired.
    6. Demo scaffolding is gone: the board's default profile is EMPTY_PROFILE (blank owner name,
       no example people — no Maya/Sam/Omar), and the demo scenario FIXTURES are env-gated
       (NEXT_PUBLIC_ANTICIPY_SHOW_FIXTURES) and OFF by default.

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

        # --- 2. BROWSER-ONLY (Omar signed off 2026-07-04): the API-connect arm
        #     (authorize_connection_loop / /connections/authorize) was deleted. Onboarding
        #     still writes the connect_account setup loops (asserted above); they now resolve
        #     through the browser flow, not an Arcade/OAuth authorize handshake. ---

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
    print("PASS frontdoor engine: /welcome -> sourced profile + connect loops (browser-only) -> readback")


def read(path: Path) -> str:
    assert path.exists(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def app_source_wiring():
    # --- 4. the front door exists: /welcome mounts the Phase-Zero client app + WelcomeScreen. ---
    # app/welcome/page.js is a thin server wrapper; the client marketing view lives in
    # app/phase-zero/PhaseZeroApp.js (WelcomeScreen), which also drives the read-only recap.
    welcome_wrap = read(APP / "welcome" / "page.js")
    assert "PhaseZeroApp" in welcome_wrap, "welcome page must mount the Phase-Zero app"
    assert 'screen="welcome"' in welcome_wrap, "welcome page must render the welcome screen"

    pz = read(APP / "phase-zero" / "PhaseZeroApp.js")
    assert '"use client"' in pz, "the Phase-Zero app must be a client component"
    assert "function WelcomeScreen" in pz, "the marketing front-door view (WelcomeScreen) must exist"
    # trust-first copy: the front door leads with the never-send-without-you promise.
    assert "never send anything without you" in pz.lower(), \
        "WelcomeScreen must open trust-first (I draft, you approve, I never send without you)"
    # the recap reward (read-only, invents nothing) is still driven from the app.
    assert "/api/onboard_scan" in pz, "the Phase-Zero app must call the read-only onboard recap"

    # --- 5. BROWSER-ONLY (Omar signed off 2026-07-04): the API-connect /connect page and the
    #     /api/connections/authorize proxy were DELETED. There is no "connect your calendar &
    #     email" API arm. The onboarding proxy that forwards to the engine still exists and
    #     stays wired; the /setup onboarding flow (PhaseZeroApp) is its caller. ---
    assert not (APP / "connect").exists(), "the API-connect /connect page must be gone (browser-only)"
    assert not (APP / "api" / "connections").exists(), \
        "the /api/connections/authorize proxy must be gone (browser-only)"
    onboard_route = read(APP / "api" / "owner" / "onboard" / "route.js")
    assert "/owner/onboard" in onboard_route, onboard_route

    # --- 6. demo scaffolding is gone: the board starts empty and invents no example people. ---
    # app/page.js is a thin wrapper onto PhaseZeroApp screen="board"; the real default state
    # lives in the Phase-Zero app (EMPTY_PROFILE), and the demo scenario FIXTURES are env-gated.
    home_wrap = read(APP / "page.js")
    assert "PhaseZeroApp" in home_wrap and 'screen="board"' in home_wrap, \
        "home page must mount the Phase-Zero board"
    # the board's default profile is EMPTY (no seeded owner, no example people).
    ep = re.search(r"const EMPTY_PROFILE\s*=\s*\{(.+?)\};", pz, re.S)
    assert ep, "could not find EMPTY_PROFILE"
    ep_block = ep.group(1)
    assert "Maya" not in ep_block and "Sam" not in ep_block, "EMPTY_PROFILE must not seed example people"
    assert "Omar" not in ep_block, "EMPTY_PROFILE must not seed an example owner name"
    # name is blank and people is an empty array (nothing invented on day one).
    nm = re.search(r'name:\s*("(.*?)"|\'(.*?)\')', ep_block)
    assert nm and (nm.group(2) or nm.group(3) or "") == "", "EMPTY_PROFILE.name must be blank"
    assert re.search(r"people:\s*\[\s*\]", ep_block), "EMPTY_PROFILE.people must be an empty array"
    assert "useState(EMPTY_PROFILE)" in pz, "the board must initialize from the empty profile"
    # demo scenario cards are gated behind an env flag and OFF by default (no auto-seeded demo).
    assert 'process.env.NEXT_PUBLIC_ANTICIPY_SHOW_FIXTURES === "1"' in pz, \
        "demo fixtures must be off unless NEXT_PUBLIC_ANTICIPY_SHOW_FIXTURES is explicitly set"
    assert "SHOW_FIXTURES ?" in pz, "the board must only append demo fixtures when the flag is on"

    print("PASS frontdoor app source: /welcome mounts WelcomeScreen, API-connect arm deleted (browser-only), board starts empty")


def main():
    asyncio.run(engine_wiring())
    app_source_wiring()
    print("PASS onboarding_frontdoor: a new user can onboard (browser-only; no API-connect arm) -> recap")


if __name__ == "__main__":
    main()
