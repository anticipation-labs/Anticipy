"""Owner onboarding writes the Action Engine's first memory mesh."""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_onboarding import OwnerOnboardingIn  # noqa: E402


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-onboard-"))
    core = ControlCore(data_dir=tmp)
    payload = {
        "source": "first_run",
        "owner_name": "Test Owner",
        "timezone": "America/Vancouver",
        "phone": "+15555550123",
        "email": "owner@example.test",
        "preferences": ["Ask before sending messages to real people.", "Never buy anything."],
        "people": [
            {"name": "Maya", "relationship": "wife", "channels": ["sms"], "notes": "school pickup changes"},
            {"name": "Sam", "relationship": "contractor", "channels": ["email"], "notes": "deck revisions"},
        ],
        "connections": [
            {"name": "Google Calendar", "status": "connected", "route": "api", "identifier": "calendar"},
            {"name": "Gmail", "status": "needs_auth", "route": "api", "identifier": "gmail.compose"},
            {"name": "Target", "status": "unknown", "route": "browser"},
        ],
        "stores": [
            {"name": "Target", "url": "https://www.target.com", "notes": "birthday gifts", "route": "browser"}
        ],
        "raw_notes": "Weekday afternoons are usually packed.",
    }
    await core.start()
    try:
        out = await core.owner_onboard(OwnerOnboardingIn.model_validate(payload))
        repeat = await core.owner_onboard(OwnerOnboardingIn.model_validate(payload))
        connected_payload = {
            **payload,
            "connections": [
                {"name": "Google Calendar", "status": "connected", "route": "api", "identifier": "calendar"},
                {"name": "Gmail", "status": "connected", "route": "api", "identifier": "gmail.compose"},
                {"name": "Target", "status": "unknown", "route": "browser"},
            ],
        }
        after_connect = await core.owner_onboard(OwnerOnboardingIn.model_validate(connected_payload))
    finally:
        await core.stop()

    profile = core.memory.profile.all()
    loops = core.memory.open_loops.all()
    profile_text = "\n".join(i.text for i in profile)
    loop_text = "\n".join(i.text for i in loops)
    serialized = json.dumps(out).lower()

    assert out["missing_connections"] == ["Gmail", "Target"], out
    assert "Owner identity" in profile_text and "America/Vancouver" in profile_text
    assert "Important person: Maya" in profile_text and "Important person: Sam" in profile_text
    assert "App connection: Google Calendar; status: connected; route: api" in profile_text
    assert "Common store/account: Target" in profile_text
    assert "Connect Gmail for Owner Action Engine" in loop_text
    assert "Connect Target for Owner Action Engine" in loop_text
    assert all(i.fields.get("action") == "connect_account" for i in loops)
    assert len(profile) == 10, [i.model_dump(mode="json") for i in profile]
    assert len(loops) == 2, [i.model_dump(mode="json") for i in loops]
    assert {w["memory_id"] for w in repeat["written"]} == {w["memory_id"] for w in out["written"]}, repeat
    assert repeat["missing_connections"] == ["Gmail", "Target"], repeat
    assert after_connect["missing_connections"] == ["Target"], after_connect
    visible = core.memory_open_loops()
    visible_text = "\n".join(i["text"] for i in visible["loops"])
    assert visible["count"] == 1, visible
    assert "Connect Gmail for Owner Action Engine" not in visible_text, visible
    assert "Connect Target for Owner Action Engine" in visible_text, visible
    assert all(i["status"] == "waiting" for i in visible["loops"]), visible

    gmail_loop = next(i for i in core.memory.open_loops.all() if "Gmail" in i.text)
    assert gmail_loop.status == "done", gmail_loop.model_dump(mode="json")
    gmail_connect = core.authorize_connection_loop(gmail_loop.id)
    assert gmail_connect["ok"] is True, gmail_connect
    assert gmail_connect["status"] == "mock", gmail_connect
    assert gmail_connect["tool"] == "Gmail.WriteDraftEmail", gmail_connect
    assert "connect URL" in gmail_connect["message"], gmail_connect

    target_loop = next(i for i in visible["loops"] if "Target" in i["text"])
    target_connect = core.authorize_connection_loop(target_loop["id"])
    assert target_connect["ok"] is True, target_connect
    assert target_connect["route"] == "browser", target_connect
    assert target_connect["status"] in {"needs_setup", "connected"}, target_connect

    done = core.resolve_memory_loop(gmail_loop.id)
    assert done["resolved"] is True and done["status"] == "done", done
    after_done = core.memory_open_loops()
    assert after_done["count"] == 1, after_done
    kinds = {e["kind"] for e in core.glassbox.entries()}
    assert "memory_loop_resolved" in kinds, kinds
    assert "connection_checked" in kinds, kinds
    assert "handoff" not in serialized
    assert len(out["written"]) == len(profile) + len(loops)
    print("PASS owner_onboarding: first-run setup writes profile mesh and connection loops")


if __name__ == "__main__":
    asyncio.run(main())
