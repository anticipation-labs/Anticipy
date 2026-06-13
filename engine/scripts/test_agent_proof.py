"""Proof helper tests.

Pins the target-agnostic multi-read artifact discipline used by WebVoyager cart
proof and future browser/API artifact read-back paths.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_agent_proof.py
"""
import asyncio

from anticipy_engine.agent.proof import confirm_stable_artifact


async def test_stable_reads_accept_best_observation():
    reads = [
        ({"url": "https://store.test/cart", "ok": True, "score": 1}, "shot-1"),
        ({"url": "https://store.test/cart", "ok": True, "score": 3}, "shot-2"),
        ({"url": "https://store.test/cart", "ok": True, "score": 2}, None),
    ]
    slept = []

    async def read_once():
        return reads.pop(0)

    async def fake_sleep(seconds):
        slept.append(seconds)

    proof = await confirm_stable_artifact(
        read_once,
        lambda out: bool(out.get("ok")),
        score=lambda out: out.get("score", 0),
        reads=3,
        delay_seconds=0.25,
        sleep=fake_sleep,
    )

    assert proof.confirmed is True, proof
    assert proof.reads == 3, proof
    assert proof.failed_read_index is None, proof
    assert proof.observation["score"] == 3, proof
    assert proof.shot == "shot-2", proof
    assert slept == [0.25, 0.25], slept
    print("PASS stable artifact: every read verified; best observation retained")


async def test_flicker_rejects_first_failed_read():
    reads = [
        ({"url": "https://store.test/cart", "ok": True, "score": 5}, "shot-good"),
        ({"url": "https://store.test/cart", "ok": False, "score": 0}, "shot-lost"),
        ({"url": "https://store.test/cart", "ok": True, "score": 5}, "shot-late"),
    ]

    async def read_once():
        return reads.pop(0)

    async def fake_sleep(_seconds):
        return None

    proof = await confirm_stable_artifact(
        read_once,
        lambda out: bool(out.get("ok")),
        score=lambda out: out.get("score", 0),
        reads=3,
        delay_seconds=0.1,
        sleep=fake_sleep,
    )

    assert proof.confirmed is False, proof
    assert proof.reads == 2, proof
    assert proof.failed_read_index == 1, proof
    assert proof.observation["ok"] is False, proof
    assert proof.shot == "shot-lost", proof
    assert len(reads) == 1, "must stop at the first failed delayed read"
    print("PASS flicker artifact: later disappearance rejects stale success")


async def test_reader_exception_fails_closed():
    calls = 0

    async def read_once():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("observer died")
        return {"ok": True}, None

    async def fake_sleep(_seconds):
        return None

    proof = await confirm_stable_artifact(
        read_once,
        lambda out: bool(out.get("ok")),
        reads=3,
        delay_seconds=0.1,
        sleep=fake_sleep,
    )

    assert proof.confirmed is False, proof
    assert proof.reads == 2, proof
    assert proof.failed_read_index == 1, proof
    assert proof.observation == {}, proof
    print("PASS observer exception: proof fails closed")


async def main():
    await test_stable_reads_accept_best_observation()
    await test_flicker_rejects_first_failed_read()
    await test_reader_exception_fails_closed()
    print("ALL AGENT PROOF TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
