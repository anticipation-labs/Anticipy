"""
Tests for the per-provider rate-limit infrastructure in app.models.

Three pieces of plumbing:

  - `_await_throttle(provider, min_interval)` — blocks until at least
    `min_interval` seconds have passed since the last call to that provider.
  - `provider_slot(provider, min_interval)` — async context manager that
    gates concurrent callers via a per-provider Semaphore(1) AND honors
    the min_interval throttle inside the slot. Different providers run
    independently.
  - `effective_layer_timeout_seconds(base, expected_concurrent)` — pads
    a layer's asyncio.wait_for budget to cover the queue wait imposed by
    the throttle when N concurrent callers fan out via asyncio.gather.

These tests don't hit any real API — they exercise the spacing math directly.

Each test uses asyncio.run so it works under both `python test_models.py`
and `python -m pytest test_models.py` (with conftest.py providing the
asyncio_mode=auto config — but plain sync wrappers are kept for safety).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Test env must be set before importing app.config (which validates it).
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",  # static valid Fernet key for tests
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app import models  # noqa: E402
from app.models import effective_layer_timeout_seconds, provider_slot  # noqa: E402


def _reset_throttle_state() -> None:
    models._throttle_locks.clear()
    models._throttle_last_call.clear()
    models._provider_semaphores.clear()


async def _fire_n_calls(provider: str, n: int, min_interval: float) -> list[float]:
    """Fire n throttled calls back-to-back, return wall-clock timestamps."""
    timestamps: list[float] = []

    async def one() -> None:
        await models._await_throttle(provider, min_interval)
        timestamps.append(time.monotonic())

    await asyncio.gather(*(one() for _ in range(n)))
    return timestamps


async def _async_test_throttle_spaces_calls() -> None:
    """5 calls at 1s spacing should take ~4s and each gap >= ~1s."""
    _reset_throttle_state()
    start = time.monotonic()
    ts = await _fire_n_calls("mistral", 5, 1.0)
    elapsed = time.monotonic() - start

    assert len(ts) == 5
    # Gaps between consecutive completions must respect the interval.
    gaps = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    for i, g in enumerate(gaps):
        assert g >= 0.95, f"gap {i} = {g:.3f}s, expected >= 0.95s"
    # Total wall clock for 5 calls @ 1s spacing should be roughly 4s.
    assert 3.8 <= elapsed <= 6.0, f"elapsed={elapsed:.2f}s outside [3.8, 6.0]"
    print(f"PASS test_throttle_spaces_calls: 5 calls in {elapsed:.2f}s, gaps={[f'{g:.2f}' for g in gaps]}")


async def _async_test_zero_interval_is_no_throttle() -> None:
    """Provider with min_interval_seconds=0 should not block."""
    _reset_throttle_state()
    start = time.monotonic()
    await _fire_n_calls("gemini", 10, 0.0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, f"zero-interval throttle took {elapsed:.3f}s, expected near-zero"
    print(f"PASS test_zero_interval_is_no_throttle: 10 calls in {elapsed:.4f}s")


async def _async_test_different_providers_independent() -> None:
    """A slow provider should not block fast calls to a different provider."""
    _reset_throttle_state()

    # Pre-poison mistral so the next call would have to wait 2s, then verify
    # gemini calls fire instantly anyway.
    models._throttle_last_call["mistral"] = time.monotonic()

    start = time.monotonic()
    await _fire_n_calls("gemini", 5, 0.0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, f"gemini blocked on mistral state: {elapsed:.3f}s"
    print(f"PASS test_different_providers_independent: gemini ran in {elapsed:.4f}s while mistral was throttled")


async def _async_test_burst_then_steady() -> None:
    """First call goes through immediately; subsequent calls space out."""
    _reset_throttle_state()
    start = time.monotonic()
    await models._await_throttle("mistral", 1.2)
    first_done = time.monotonic() - start
    await models._await_throttle("mistral", 1.2)
    second_done = time.monotonic() - start

    assert first_done < 0.05, f"first call delayed: {first_done:.3f}s"
    assert second_done >= 1.15, f"second call did not wait: {second_done:.3f}s"
    print(f"PASS test_burst_then_steady: first={first_done:.4f}s, second={second_done:.4f}s")


async def _async_test_effective_timeout_with_throttle() -> None:
    """When MODEL_CHAIN[0].min_interval > 0 and N concurrent callers fan out,
    the effective timeout pads by (N-1) * min_interval."""
    saved = list(models.MODEL_CHAIN)
    try:
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.append({
            "name": "mistral",
            "min_interval_seconds": 1.2,
            "base_url": "x", "api_key": "x", "model": "x",
            "cost_input": 0.0, "cost_output": 0.0,
        })
        result = effective_layer_timeout_seconds(8.0, expected_concurrent_calls=3)
        # 8 + (3-1) * 1.2 = 10.4
        assert abs(result - 10.4) < 1e-9, f"expected 10.4, got {result}"
        # Single-caller path: no extra time.
        assert effective_layer_timeout_seconds(8.0, expected_concurrent_calls=1) == 8.0
        # Five callers: 8 + 4 * 1.2 = 12.8
        result5 = effective_layer_timeout_seconds(8.0, expected_concurrent_calls=5)
        assert abs(result5 - 12.8) < 1e-9, f"expected 12.8, got {result5}"
    finally:
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.extend(saved)
    print("PASS test_effective_timeout_with_throttle: 10.4s pad applied for 3-way gather at 1.2s spacing")


async def _async_test_effective_timeout_no_throttle() -> None:
    """When MODEL_CHAIN[0].min_interval == 0, the base timeout is unchanged."""
    saved = list(models.MODEL_CHAIN)
    try:
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.append({
            "name": "gemini",
            "min_interval_seconds": 0.0,
            "base_url": "x", "api_key": "x", "model": "x",
            "cost_input": 0.0, "cost_output": 0.0,
        })
        assert effective_layer_timeout_seconds(8.0, expected_concurrent_calls=3) == 8.0
        assert effective_layer_timeout_seconds(20.0, expected_concurrent_calls=10) == 20.0

        # Empty MODEL_CHAIN also returns base unchanged.
        models.MODEL_CHAIN.clear()
        assert effective_layer_timeout_seconds(8.0, expected_concurrent_calls=3) == 8.0
    finally:
        models.MODEL_CHAIN.clear()
        models.MODEL_CHAIN.extend(saved)
    print("PASS test_effective_timeout_no_throttle: base timeout unchanged when interval=0")


async def _async_test_provider_slot_serializes_concurrent() -> None:
    """3 concurrent slot acquires on the SAME provider serialize at min_interval
    spacing; 3 acquires on DIFFERENT providers run in parallel.
    """
    _reset_throttle_state()

    finish_times: list[tuple[str, float]] = []
    start = time.monotonic()

    async def acquire(provider: str, interval: float, label: str) -> None:
        async with provider_slot(provider, interval):
            # Tiny "API call" — record completion time immediately.
            finish_times.append((label, time.monotonic() - start))

    # Fan out 3 calls to the same provider with min_interval=1.0. Only one
    # is in-flight at a time. Completions should be ~0s, ~1s, ~2s.
    await asyncio.gather(
        acquire("mistral", 1.0, "k1"),
        acquire("mistral", 1.0, "k2"),
        acquire("mistral", 1.0, "k3"),
    )
    same_provider_finishes = sorted(t for label, t in finish_times if label.startswith("k"))
    assert len(same_provider_finishes) == 3
    assert same_provider_finishes[0] < 0.1, f"first mistral finish: {same_provider_finishes[0]:.3f}s"
    assert 0.95 <= same_provider_finishes[1] <= 1.3, (
        f"second mistral finish: {same_provider_finishes[1]:.3f}s, expected ~1s")
    assert 1.95 <= same_provider_finishes[2] <= 2.4, (
        f"third mistral finish: {same_provider_finishes[2]:.3f}s, expected ~2s")

    # Now reset and fan out 3 calls to DIFFERENT providers — they should
    # all complete near-instantly because the per-provider semaphores are
    # independent.
    _reset_throttle_state()
    finish_times = []
    start = time.monotonic()
    await asyncio.gather(
        acquire("p1", 1.0, "p1"),
        acquire("p2", 1.0, "p2"),
        acquire("p3", 1.0, "p3"),
    )
    diff_provider_finishes = sorted(t for label, t in finish_times if label.startswith("p"))
    assert len(diff_provider_finishes) == 3
    for i, t in enumerate(diff_provider_finishes):
        assert t < 0.15, f"different-provider call {i} took {t:.3f}s, expected near-zero"
    print(
        "PASS test_provider_slot_serializes_concurrent: same-provider 3-way ran "
        f"at {same_provider_finishes[0]:.2f}s/{same_provider_finishes[1]:.2f}s/"
        f"{same_provider_finishes[2]:.2f}s; different-providers ran in parallel"
    )


# --- pytest-style sync wrappers ---------------------------------------------
# Existing tests are async functions; pytest without auto-mode wraps them as
# coroutines and complains. These sync wrappers run the coroutine via
# asyncio.run so the pytest invocation in the task instructions works without
# a separate conftest configuration.


def test_throttle_spaces_calls() -> None:
    asyncio.run(_async_test_throttle_spaces_calls())


def test_zero_interval_is_no_throttle() -> None:
    asyncio.run(_async_test_zero_interval_is_no_throttle())


def test_different_providers_independent() -> None:
    asyncio.run(_async_test_different_providers_independent())


def test_burst_then_steady() -> None:
    asyncio.run(_async_test_burst_then_steady())


def test_effective_timeout_with_throttle() -> None:
    asyncio.run(_async_test_effective_timeout_with_throttle())


def test_effective_timeout_no_throttle() -> None:
    asyncio.run(_async_test_effective_timeout_no_throttle())


def test_provider_slot_serializes_concurrent() -> None:
    asyncio.run(_async_test_provider_slot_serializes_concurrent())


async def main() -> None:
    await _async_test_throttle_spaces_calls()
    await _async_test_zero_interval_is_no_throttle()
    await _async_test_different_providers_independent()
    await _async_test_burst_then_steady()
    await _async_test_effective_timeout_with_throttle()
    await _async_test_effective_timeout_no_throttle()
    await _async_test_provider_slot_serializes_concurrent()
    print("\nAll throttle/timeout/slot tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
