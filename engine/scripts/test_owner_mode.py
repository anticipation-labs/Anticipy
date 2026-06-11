"""Owner Action Engine intake test.

The product input is not clean commands. This pins the first operating contract:
all owner doors feed the same messy transcript path, useless lines are ignored,
useful lines become durable action cards, and no card uses a special pass-off
mode instead of a real route/status.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_mode import OwnerMode  # noqa: E402


NOISY_DAY = """
[08:02] Omar: yeah okay no the coffee machine is being weird again and I do not care.
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[08:05] Omar: oh sure, I'll just clone myself, that'll fix the schedule.
[09:12] Sam needs the revised decking before Friday; I told him I'd send it.
[09:15] Omar: anyway the blue cup is on the counter, whatever.
[11:22] Omar: that water-table thing for Leila's birthday, put it in the cart if you find it, don't buy it.
[13:00] Omar: My wife Maya prefers texts after lunch.
[16:10] Omar: this whole week is ridiculous, lol.
"""


def signature(result):
    return [
        (c.title, c.disposition, c.route, c.action, c.args.get("person"), c.args.get("kind"))
        for c in result.cards
    ]


async def control_core_check():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-owner-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        out = await core.owner_ingest("mp3", NOISY_DAY)
    finally:
        await core.stop()

    owner_loops = [i for i in core.memory.open_loops.all() if i.fields.get("owner_card_id")]
    owner_profile = [i for i in core.memory.profile.all() if i.fields.get("owner_card_id")]
    assert len(out["cards"]) == 4, out
    assert len(owner_loops) == 3, [i.model_dump(mode="json") for i in owner_loops]
    assert len(owner_profile) == 1, [i.model_dump(mode="json") for i in owner_profile]
    assert {i.fields["route"] for i in owner_loops} == {"api", "voice_text", "browser"}
    assert all(i.fields["action"] for i in owner_loops)
    assert "handoff" not in json.dumps(out).lower()


def main():
    mode = OwnerMode()
    sources = ["pay_to_try", "start_listening", "mp3", "transcript"]
    results = [mode.ingest(NOISY_DAY, source=s) for s in sources]
    expected = signature(results[0])
    for result in results[1:]:
        assert signature(result) == expected, (result.source, signature(result), expected)

    cards = results[0].cards
    assert len(cards) == 4, [c.model_dump(mode="json") for c in cards]
    assert results[0].ignored_line_count >= 3
    assert any(c.action == "create_calendar_or_reminder" and c.route == "api" for c in cards)
    assert any(c.action == "draft_or_confirm_message" and c.args.get("person") == "Sam" for c in cards)
    assert any(c.action == "find_or_cart_without_purchase" and c.route == "browser" for c in cards)
    assert any(c.action == "write_profile_memory" and c.route == "memory" for c in cards)
    assert not any("clone myself" in c.source_text.lower() for c in cards)
    assert "handoff" not in json.dumps([c.model_dump(mode="json") for c in cards]).lower()

    asyncio.run(control_core_check())
    print("PASS owner_mode: noisy owner transcript -> shared durable action cards")


if __name__ == "__main__":
    main()
