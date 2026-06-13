"""Public backend path test: messy input -> memory -> cards -> safe execution.

This is the product contract in one HTTP story:
  - typed/upload/listening text enters the same owner ingest endpoint
  - safe tasks execute with durable receipts
  - human-impacting tasks pause in /pending and resume through /resolve
  - memory context can unlock a browser/cart-only task
  - money/check-out requests are blocked and never become executable goals

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_public_backend_path.py
"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-public-backend-")

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine.main import app, core  # noqa: E402


TRANSCRIPT = """
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[09:12] Sam needs the revised decking before Friday; I told him I'd send it.
[10:17] Was comparing spiral notebooks at Staples; liked the 5x8 recycled notebook pack.
[10:22] That notebook size I liked at Staples, cart one pack so I can check shipping later, no buying.
[13:00] My wife Maya prefers texts after lunch.
[16:31] order the replacement filter today and just pay whatever it costs.
"""


def _record(card_id: str) -> dict:
    path = Path(os.environ["ANTICIPY_DATA_DIR"]) / "owner_cards" / f"{card_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _cards_by_action(cards: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for card in cards:
        out.setdefault(card["action"], []).append(card)
    return out


def main():
    with TestClient(app) as client:
        status = client.get("/status")
        assert status.status_code == 200, status.text
        channels = status.json()["channels"]
        assert channels["mode"] in {"mock", "live"}, channels
        assert channels["status"] in {
            "mock",
            "ready_to_enable",
            "missing_twilio",
            "missing_owner_contact",
            "live_ready",
        }, channels
        assert channels["inbound"]["status"] in {
            "mock",
            "ready_to_enable",
            "missing_twilio",
            "missing_owner_contact",
            "disabled",
            "live_ready",
        }, channels
        assert channels["inbound"]["label"], channels
        assert "TWILIO_AUTH_TOKEN" not in json.dumps(channels), channels
        readiness = status.json()["readiness"]
        assert readiness["overall"] in {"ready", "needs_setup", "local_mock"}, readiness
        for key in ("app_input", "proactive_engine", "memory", "browser", "api_hands",
                    "voice_text", "approvals", "money_wall", "owner_api"):
            assert key in readiness["items"], readiness
            assert readiness["items"][key]["state"], readiness["items"][key]
            assert readiness["items"][key]["label"], readiness["items"][key]
        assert readiness["items"]["money_wall"]["state"] == "ready", readiness
        assert readiness["items"]["voice_text"]["state"] in {
            "mock",
            "ready_to_enable",
            "setup",
            "ready",
        }, readiness
        assert "TWILIO_AUTH_TOKEN" not in json.dumps(readiness), readiness

        res = client.post(
            "/owner/ingest",
            json={
                "source": "typed",
                "text": TRANSCRIPT,
                "execute_actions": True,
                "meta": {"test": "public_backend_path"},
            },
        )
        assert res.status_code == 200, res.text
        out = res.json()

        cards = out["cards"]
        by_action = _cards_by_action(cards)
        assert out["ignored_line_count"] >= 1, out

        # Safe local/API work finished and wrote proof into a durable card record.
        pickup = by_action["create_calendar_or_reminder"][0]
        pickup_record = _record(pickup["id"])
        assert pickup["status"] == "done", pickup
        assert pickup_record["state"] == "done", pickup_record
        assert pickup_record["steps"], pickup_record
        assert pickup_record["proof"], pickup_record
        assert any(p["type"] == "memory_write" for p in pickup["proof"]), pickup
        assert any(p["type"] == "memory_read_back" for p in pickup["proof"]), pickup
        assert any(p["type"] == "engine_execution" for p in pickup["proof"]), pickup

        # The memory line is not a task, but it must be captured so the later
        # vague browser task can resolve the store/item without inventing them.
        browser = by_action["find_or_cart_without_purchase"][0]
        browser_record = _record(browser["id"])
        assert browser["status"] == "done", browser
        assert browser_record["state"] == "done", browser_record
        assert browser_record["steps"][0]["intent"] == "browse_task", browser_record
        resolution = browser_record["steps"][0]["args"]["memory_resolution"]
        assert resolution["site"] == "https://www.staples.com", resolution
        assert "notebook" in resolution["item"].lower(), resolution
        memory_receipts = [p for p in browser["proof"] if p.get("type") == "memory_resolution"]
        assert memory_receipts, browser
        assert memory_receipts[0]["site"] == "https://www.staples.com", memory_receipts
        assert "notebook" in memory_receipts[0]["item"].lower(), memory_receipts

        # Human-impacting communication pauses in /pending, then /resolve resumes
        # the exact paused goal and writes the result back onto the durable card.
        message = by_action["draft_or_confirm_message"][0]
        ask_id = message["execution"]["ask_id"]
        assert message["status"] == "waiting" and ask_id, message
        pending = client.get("/pending")
        assert pending.status_code == 200, pending.text
        pending_items = pending.json()["pending"]
        assert any(p["ask_id"] == ask_id and p["goal_id"] == message["execution"]["goal_id"]
                   for p in pending_items), pending_items
        data_dir = Path(os.environ["ANTICIPY_DATA_DIR"])
        card_count_before_replay = len(list((data_dir / "owner_cards").glob("*.json")))
        goal_count_before_replay = len(list((data_dir / "goals").glob("*.json")))
        pending_count_before_replay = len(pending_items)
        replay = client.post(
            "/owner/ingest",
            json={
                "source": "typed",
                "text": TRANSCRIPT,
                "execute_actions": True,
                "meta": {"test": "public_backend_path_replay"},
            },
        )
        assert replay.status_code == 200, replay.text
        replay_cards = replay.json()["cards"]
        assert {c["id"] for c in replay_cards} == {c["id"] for c in cards}, replay_cards
        assert len(list((data_dir / "owner_cards").glob("*.json"))) == card_count_before_replay
        assert len(list((data_dir / "goals").glob("*.json"))) == goal_count_before_replay
        assert len(client.get("/pending").json()["pending"]) == pending_count_before_replay
        protected_loops = client.get("/memory/open-loops?limit=20")
        assert protected_loops.status_code == 200, protected_loops.text
        protected_loop = next(
            i for i in protected_loops.json()["loops"]
            if i["fields"].get("owner_card_id") == message["id"]
        )
        refused = client.post("/memory/open-loops/resolve", json={"id": protected_loop["id"], "status": "done"})
        assert refused.status_code == 400, refused.text

        approved = client.post("/resolve", json={"ask_id": ask_id, "approved": True})
        assert approved.status_code == 200, approved.text
        approved_out = approved.json()
        assert approved_out["approved"] is True and approved_out["state"] == "done", approved_out
        message_record = _record(message["id"])
        assert message_record["state"] == "done", message_record
        assert message_record["resolution"] == {"ask_id": ask_id, "approved": True}, message_record
        assert message_record["proof"], message_record
        message_args = message_record["steps"][0]["args"]
        assert message_args["to"] == "Sam", message_args
        assert "Sam needs the revised decking" in message_args["body"], message_args
        assert "Sarah" not in json.dumps(message_record["steps"]), message_record["steps"]

        durable = client.get("/owner/cards?limit=20")
        assert durable.status_code == 200, durable.text
        durable_cards = durable.json()["cards"]
        durable_message = next(c for c in durable_cards if c["id"] == message["id"])
        assert durable_message["status"] == "done", durable_message
        assert durable_message["execution"]["goal_state"] == "done", durable_message
        assert durable_message["execution"]["ask_id"] is None, durable_message
        assert any(p["type"] == "resolution" and p["decision"] == "approved"
                   for p in durable_message["proof"]), durable_message
        durable_browser = next(c for c in durable_cards if c["id"] == browser["id"])
        assert any(p.get("type") == "memory_resolution" and p.get("site") == "https://www.staples.com"
                   for p in durable_browser["proof"]), durable_browser

        # A lower-level model/planner risk cannot bypass the owner approval rail.
        # The top-level request is safe enough to plan, but the planned send step is
        # ask_human; product core must surface it as pending and resume the exact
        # planned goal only after approval.
        from anticipy_engine.core.gateway import default_stub
        old_stub = core.gateway._stub

        def planned_high_risk(task, tier, caller):
            if caller == "plan":
                return json.dumps({
                    "steps": [{
                        "intent": "send_email",
                        "args": {"to": "Jordan", "subject": "Packet", "body": "Prepared packet."},
                        "risk": "ask_human",
                    }],
                })
            return default_stub(task, tier, caller)

        core.gateway._stub = planned_high_risk
        try:
            lower_gate = client.post(
                "/event",
                json={"source": "app", "text": "Prepare the project packet", "meta": {"test": "planner_risk"}},
            )
            assert lower_gate.status_code == 200, lower_gate.text
            lower_out = lower_gate.json()
            assert lower_out["decision"] == "ask" and lower_out["ask_id"], lower_out
            lower_goal = core.store.load(lower_out["goal_id"])
            assert lower_goal.state.value == "waiting", lower_goal
            assert lower_goal.steps[0].state.value == "needs_human", lower_goal.steps[0]
            assert not lower_goal.steps[0].args.get("approved"), lower_goal.steps[0]
            lower_pending = client.get("/pending").json()["pending"]
            assert any(p["ask_id"] == lower_out["ask_id"] for p in lower_pending), lower_pending
            lower_approved = client.post("/resolve", json={"ask_id": lower_out["ask_id"], "approved": True})
            assert lower_approved.status_code == 200, lower_approved.text
            lower_approved_out = lower_approved.json()
            assert lower_approved_out["approved"] is True and lower_approved_out["state"] == "done", lower_approved_out
            lower_done = core.store.load(lower_out["goal_id"])
            assert lower_done.state.value == "done", lower_done
            assert lower_done.steps[0].args["approved"] is True, lower_done.steps[0]
        finally:
            core.gateway._stub = old_stub

        still_pending = client.get("/pending").json()["pending"]
        assert all(p["ask_id"] != ask_id for p in still_pending), still_pending

        # Remember cards are real memory writes with read-back proof, not loose notes.
        remembered = by_action["write_profile_memory"][0]
        remembered_record = _record(remembered["id"])
        assert remembered["status"] == "done", remembered
        assert remembered_record["state"] == "done", remembered_record
        assert remembered_record["proof"].get("read_back"), remembered_record

        # Money is the hard wall: no pending ask id that can be approved into
        # payment, no orchestrator goal file, no steps, no proof.
        blocked = by_action["prepare_purchase_path_without_payment"][0]
        blocked_record = _record(blocked["id"])
        assert blocked["status"] == "blocked", blocked
        assert blocked["execution"]["goal_id"] is None and blocked["execution"]["ask_id"] is None, blocked
        assert blocked_record["state"] == "blocked", blocked_record
        assert not blocked_record["steps"] and not blocked_record["proof"], blocked_record
        assert not (Path(os.environ["ANTICIPY_DATA_DIR"]) / "goals" / f"{blocked['id']}.json").exists()

        owner_loop_status = {
            i.fields["owner_card_id"]: i.status
            for i in core.memory.open_loops.all()
            if i.fields.get("owner_card_id")
        }
        assert owner_loop_status[pickup["id"]] == "done", owner_loop_status
        assert owner_loop_status[browser["id"]] == "done", owner_loop_status
        assert owner_loop_status[message["id"]] == "done", owner_loop_status
        assert owner_loop_status[blocked["id"]] == "blocked", owner_loop_status
        raw_loop_status = {
            i.text: i.status
            for i in core.memory.open_loops.all()
            if not i.fields.get("owner_card_id")
        }
        assert raw_loop_status.get(pickup["source_text"]) == "open", raw_loop_status
        assert raw_loop_status.get(message["source_text"]) == "done", raw_loop_status
        assert raw_loop_status.get(blocked["source_text"]) == "blocked", raw_loop_status

        active_loops = client.get("/memory/open-loops?limit=20")
        assert active_loops.status_code == 200, active_loops.text
        visible_loops = active_loops.json()["loops"]
        visible_text = "\n".join(i["text"] for i in visible_loops)
        assert pickup["source_text"] in visible_text, visible_loops
        assert message["source_text"] not in visible_text, visible_loops
        assert blocked["source_text"] not in visible_text, visible_loops
        stale = core.memory.open_loops.write_text(
            "Already-fired transcript noise should not look active",
            fields={"task": "Already-fired transcript noise should not look active", "fired_at": 123.0},
            status="open",
        )
        visible_after_stale = client.get("/memory/open-loops?limit=100").json()["loops"]
        assert all(i["id"] != stale.id for i in visible_after_stale), visible_after_stale
        active_count = client.get("/memory/open-loops?limit=0").json()["count"]
        status_after_stale = client.get("/status").json()
        assert status_after_stale["open_loop_count"] == active_count, status_after_stale

        onboarding = client.post("/owner/onboard", json={
            "source": "public_backend_path",
            "connections": [
                {"name": "Gmail", "status": "needs_auth", "route": "api"},
            ],
        })
        assert onboarding.status_code == 200, onboarding.text
        setup_loop = next(i for i in client.get("/memory/open-loops?limit=20").json()["loops"]
                          if i["text"] == "Connect Gmail for Owner Action Engine")
        connect = client.post("/connections/authorize", json={"id": setup_loop["id"]})
        assert connect.status_code == 200, connect.text
        connect_out = connect.json()
        assert connect_out["status"] == "mock", connect_out
        assert connect_out["tool"] == "Gmail.SendEmail", connect_out
        closed = client.post("/memory/open-loops/resolve", json={"id": setup_loop["id"], "status": "done"})
        assert closed.status_code == 200, closed.text
        assert closed.json()["resolved"] is True, closed.text
        after_closed = client.get("/memory/open-loops?limit=20").json()["loops"]
        assert not any(i["id"] == setup_loop["id"] for i in after_closed), after_closed

        receipt_feed = client.get("/glassbox?limit=80")
        assert receipt_feed.status_code == 200, receipt_feed.text
        summaries = [e["summary"] for e in receipt_feed.json()["entries"]]
        assert any("processed" in s and "cards" in s for s in summaries), summaries
        assert any("waiting for you" in s and "Sam" in s for s in summaries), summaries
        assert any("hard wall: money" in s for s in summaries), summaries
        assert any("connection Gmail: mock" in s for s in summaries), summaries

    print("PASS public_backend_path: messy input -> memory -> safe actions, pending approval, receipts, money wall")


if __name__ == "__main__":
    main()
