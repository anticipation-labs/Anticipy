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
    await core.start()
    try:
        out = await core.owner_onboard(OwnerOnboardingIn.model_validate({
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
        }))
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
    assert all(i.status == "waiting" for i in loops)
    assert all(i.fields.get("action") == "connect_account" for i in loops)
    assert "handoff" not in serialized
    assert len(out["written"]) == len(profile) + len(loops)
    print("PASS owner_onboarding: first-run setup writes profile mesh and connection loops")


if __name__ == "__main__":
    asyncio.run(main())
