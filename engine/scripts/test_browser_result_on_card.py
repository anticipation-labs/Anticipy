"""GATE F — the browser round-trip result must LAND on the durable owner card.

The centerpiece browser path flips the card to 'running' on YES (in
_resolve_browser_card_record), runs the agent (_run_browser_and_confirm), and
texts the owner — but it NEVER wrote the found result/screenshot/URL back onto
the durable card record and skipped persisting it. So the board was stranded at
'running' forever, with no receipt — unlike the API arm, whose proof rides the
card. This test pins the fix: after a (mock-hands) browser run, the card record
carries a browser receipt (url + screenshot flag + answer) and a terminal state.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_result_on_card.py
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.owner_mode import OwnerTaskCard  # noqa: E402


class _MockBrowseResult:
    """Mirrors browser_use_link.BrowseReadResult's read-back contract (no real browser)."""
    def __init__(self, *, success, result, url, screenshot, screenshot_path=None):
        self.success = success
        self.result = result
        self.url = url
        self.screenshot = screenshot
        self.screenshot_path = screenshot_path


def _record(data_dir: Path, card_id: str) -> dict:
    return json.loads((data_dir / "owner_cards" / f"{card_id}.json").read_text(encoding="utf-8"))


def _seed_browser_card(core: ControlCore, data_dir: Path, ask_id: str, task: str, url: str) -> None:
    """Seed a browser_action card record + pending exactly as owner_ingest would,
    then leave it for resolve(YES) to drive."""
    (data_dir / "owner_cards").mkdir(parents=True, exist_ok=True)
    card = OwnerTaskCard(
        id=ask_id, source="typed", line_no=1, source_text=task,
        title=f"Look this up for you: {task[:70]}", disposition="ask", route="browser",
        action="browser_action", args={"task_text": task, "start_url": url}, confidence=0.8,
        reason="I'll handle this on the web once you say yes",
        execution={"decision": "ask", "goal_id": ask_id, "ask_id": ask_id, "goal_state": "waiting"},
    )
    record = {"id": ask_id, "state": "waiting", "proof": [], "steps": [],
              "source_text": task, "owner_card": card.model_dump(mode="json")}
    (data_dir / "owner_cards" / f"{ask_id}.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    core.proactive.pending[ask_id] = {
        "goal_id": ask_id, "action": task, "reason": "browser task — confirm before I look",
        "category": "browser_action", "browser_task": task, "browser_url": url}
    core.proactive._persist_pending()


async def _run_case(success: bool):
    data_dir = Path(tempfile.mkdtemp(prefix="anticipy-browser-card-"))
    core = ControlCore(data_dir=data_dir)
    await core.start()
    sent = []
    core.text_channel.send = lambda to, msg: sent.append(msg)  # never really text in a test

    ask_id = "br_test_resultoncard_" + ("ok" if success else "fail")
    task = "find the cheapest USB-C cable and add it to the cart"
    url = "https://demowebshop.tricentis.com"
    _seed_browser_card(core, data_dir, ask_id, task, url)

    answer = "Added a 6ft USB-C cable to the cart ($8.99). Stopped before checkout." if success else ""

    # Monkeypatch the real browser arm with an honest mock result (a successful
    # cart-prep with a screenshot, or an honest failure). browse_act is imported
    # INSIDE _run_browser_and_confirm, so patch it on the source module.
    import anticipy_engine.hands.browser_use_link as L
    L.browse_act = lambda t, url=None, max_steps=16: _MockBrowseResult(
        success=success, result=answer,
        url=("https://demowebshop.tricentis.com/cart" if success else url),
        screenshot=success, screenshot_path=("/tmp/anticipy-shot.png" if success else None))

    try:
        # resolve(YES) does two things for a browser_action: flips the card to 'running'
        # (_resolve_browser_card_record) and kicks _run_browser_and_confirm as a fire-and-forget
        # task. We exercise that SAME pair deterministically (awaiting the run instead of racing a
        # create_task), so the test pins the result-on-card write without depending on the engine's
        # long-lived background loops finishing.
        core._resolve_browser_card_record(ask_id, approved=True)
        running = _record(data_dir, ask_id)
        assert running["state"] == "running", ("YES must first flip the card to running", running)
        await core._run_browser_and_confirm(task, url, ask_id)
    finally:
        await core.stop()

    return _record(data_dir, ask_id), sent


async def _run_demo_amazon_rearm_case():
    old_demo = os.environ.get("ANTICIPY_DEMO_AMAZON_RETURN")
    os.environ["ANTICIPY_DEMO_AMAZON_RETURN"] = "1"
    data_dir = Path(tempfile.mkdtemp(prefix="anticipy-amz-demo-card-"))
    core = ControlCore(data_dir=data_dir)
    await core.start()
    core.text_channel.send = lambda to, msg: None
    task = core._demo_amazon_return_task()
    ask_id = core._demo_amazon_return_ask_id()
    url = "https://www.amazon.ca/gp/css/order-history"
    try:
        _seed_browser_card(core, data_dir, ask_id, task, url)
        duplicate_ask_id = core._browser_action_ask_id(
            "please do the Amazon return about the security camera light", "transcript")
        _seed_browser_card(
            core,
            data_dir,
            duplicate_ask_id,
            "please do the Amazon return about the security camera light",
            url,
        )
        core._resolve_browser_card_record(ask_id, approved=True)
        core._land_browser_result_on_card(
            ask_id,
            success=True,
            answer="Opened your Amazon return for the security camera — stopped at Continue.",
            url="https://www.amazon.ca/spr/returns/cart?orderId=123",
            screenshot=True,
        )
        rec = _record(data_dir, ask_id)
        assert rec["state"] == "waiting", ("demo card must re-arm to waiting", rec)
        assert rec["owner_card"]["status"] == "waiting", rec["owner_card"]
        assert rec["owner_card"]["execution"]["goal_state"] == "waiting", rec["owner_card"]["execution"]
        assert rec["owner_card"]["execution"]["ask_id"] == ask_id, rec["owner_card"]["execution"]
        assert rec["browser_result"]["success"] is False, rec["browser_result"]
        assert rec["browser_result"]["last_success"] is True, rec["browser_result"]
        assert ask_id in core.proactive.pending, core.proactive.pending

        # Heal stale non-waiting records from older runs when the board reloads.
        for stale_state in ("failed", "open"):
            rec["state"] = stale_state
            rec["owner_card"]["status"] = stale_state
            (data_dir / "owner_cards" / f"{ask_id}.json").write_text(
                json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")
            cards = core.owner_cards(limit=10)["cards"]
            healed = next(c for c in cards if c["id"] == ask_id)
            assert all(c["id"] != duplicate_ask_id for c in cards), cards
            assert healed["status"] == "waiting", healed
            assert healed["execution"]["ask_id"] == ask_id, healed["execution"]
            healed_rec = _record(data_dir, ask_id)
            assert healed_rec["state"] == "waiting", healed_rec
            assert ask_id in core.proactive.pending, core.proactive.pending
            rec = healed_rec
        return rec
    finally:
        await core.stop()
        if old_demo is None:
            os.environ.pop("ANTICIPY_DEMO_AMAZON_RETURN", None)
        else:
            os.environ["ANTICIPY_DEMO_AMAZON_RETURN"] = old_demo


async def main():
    # --- success: a real cart-prep result must land on the card ---
    rec, sent = await _run_case(success=True)
    assert rec["state"] == "done", ("success run must mark the card done", rec)
    proof = rec.get("proof")
    assert isinstance(proof, dict) and proof.get("type") == "browser_receipt", ("no browser receipt on card", rec)
    assert proof.get("url") == "https://demowebshop.tricentis.com/cart", proof
    assert proof.get("screenshot") is True, ("screenshot flag did not land", proof)
    assert proof.get("screenshot_path") == "/tmp/anticipy-shot.png", proof
    assert "USB-C cable" in (proof.get("answer") or ""), proof
    # the receipt also rides the card body's execution block (board reads it there)
    oc = rec["owner_card"]
    assert oc["status"] == "done", oc
    assert oc["execution"]["proof"]["type"] == "browser_receipt", oc["execution"]
    # the owner was actually texted the result
    assert any("USB-C cable" in m for m in sent), sent
    print("PASS browser-result-on-card: success run -> card carries url + screenshot + answer, state=done")

    # --- failure: an honest failure also lands (no stranded 'running', no faked proof) ---
    rec2, sent2 = await _run_case(success=False)
    assert rec2["state"] == "failed", ("failed run must not be stranded at running", rec2)
    proof2 = rec2.get("proof")
    assert proof2.get("type") == "browser_receipt" and proof2.get("screenshot") is False, proof2
    assert (proof2.get("answer") or "") == "", proof2
    assert rec2["owner_card"]["status"] == "failed", rec2["owner_card"]
    print("PASS browser-result-on-card: failure run -> card=failed, honest receipt (no faked screenshot/answer)")

    await _run_demo_amazon_rearm_case()
    print("PASS browser-result-on-card: demo Amazon return card re-arms, heals stale state, and suppresses duplicates")

    print("ALL browser-result-on-card TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
