"""Two-user isolation — the hermetic PROOF that the product is genuinely per-user (B8).

Two distinct Supabase-style user ids, injected through the registry seam (the same seam the
owner_api_auth middleware drives via set_current_user -> current_core), resolve to two DISTINCT
ControlCores rooted at two DISTINCT per-user data_dirs under <base>/users/. From there we prove
three things end to end, with NO real Supabase call and NO model (throwaway base dir, stub brain):

  1. DATA isolation — user A's CARDS and MEMORY never appear for user B (nor for the default
     owner core), and vice-versa. We read through the real seams (``core.owner_cards()`` and the
     ``core.memory`` drawers), so this is the exact path the product surface reads.

  2. ACTION identity (fix #3) — each user's real-systems hand runs under THEIR identity:
     ``core.api_hand.user_id`` == that user's id, NOT the global ARCADE_USER_ID / owner. The
     default (owner) core still resolves to ARCADE_USER_ID, so the owner path is unchanged.

  3. The registry seam itself — binding the current user (as the HTTP middleware does) makes
     ``current_core()`` resolve to that user's core, and re-resolving a user is idempotent
     (one core per user, cached).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_two_user_isolation.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# --- hermetic environment (free + deterministic; nothing live leaks in) ---
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ["ANTICIPY_TICK_SECONDS"] = "0"
os.environ["ANTICIPY_INBOUND_POLL_SECONDS"] = "0"
# Pin a deterministic owner identity + a sentinel Arcade user so default_user() and the OWNER
# core's action identity are stable regardless of whatever .env.local happens to hold.
os.environ["ADMIN_EMAIL"] = "owner@anticipy.test"
ARCADE_SENTINEL = "arcade-owner-sentinel@anticipy.test"
os.environ["ARCADE_USER_ID"] = ARCADE_SENTINEL
_BASE = tempfile.mkdtemp(prefix="anticipy-two-user-")
os.environ["ANTICIPY_DATA_DIR"] = _BASE

# Import AFTER the env is pinned: main wires the registry (set_factory + register_default) at
# module load, exactly as the running engine does — so we test the REAL seam, not a mock of it.
from anticipy_engine import main as m  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402

# Two distinct Supabase-style user ids (UUID-shaped). These stand in for what
# verify_supabase_token would return for two signed-in users — no network needed, because the
# registry seam keys off the resolved user_id, which we inject directly.
USER_A = "11111111-1111-4111-8111-aaaaaaaaaaaa"
USER_B = "22222222-2222-4222-8222-bbbbbbbbbbbb"

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)


def _plant_card(core, card_id: str, title: str) -> None:
    """Land a durable owner card in THIS core's tree (what an ingest would persist), so we can
    prove owner_cards() reads only the calling core's own <data_dir>/owner_cards."""
    d = Path(core.data_dir) / "owner_cards"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{card_id}.json").write_text(
        json.dumps({"owner_card": {"id": card_id, "title": title}, "state": "open"}),
        encoding="utf-8",
    )


def _card_titles(core) -> set[str]:
    return {c.get("title") for c in core.owner_cards(limit=50)["cards"]}


def _history_texts(core) -> set[str]:
    return {i.text for i in core.memory.history.all()}


def main() -> int:
    base = Path(_BASE)

    # --- resolve two users through the registry seam -> two cores ---
    core_default = registry.core_for(registry.default_user())
    core_A = registry.core_for(USER_A)
    core_B = registry.core_for(USER_B)

    check("default user maps to the module-global core", core_default is m.core)
    check("three distinct cores (default / A / B)",
          len({id(core_default), id(core_A), id(core_B)}) == 3)
    check("re-resolving A returns the SAME cached core (one core per user)",
          registry.core_for(USER_A) is core_A)

    # --- distinct, per-user data dirs under <base>/users/, default base untouched ---
    dirs = {str(core_default.data_dir), str(core_A.data_dir), str(core_B.data_dir)}
    check("three distinct data_dirs", len(dirs) == 3, str(dirs))
    check("A's dir under <base>/users/", str(core_A.data_dir).startswith(str(base / "users")),
          str(core_A.data_dir))
    check("B's dir under <base>/users/", str(core_B.data_dir).startswith(str(base / "users")),
          str(core_B.data_dir))
    check("default core keeps the existing base dir", Path(core_default.data_dir) == base,
          str(core_default.data_dir))

    # --- the middleware binding seam: current_core() follows the bound user ---
    tok = registry.set_current_user(USER_A)
    try:
        check("set_current_user(A) -> current_core() is A's core", registry.current_core() is core_A)
    finally:
        registry.reset_current_user(tok)
    check("outside a bound request -> current_core() is the default core",
          registry.current_core() is core_default)

    # --- (1) CARD isolation: A's card is visible to A only ---
    _plant_card(core_A, "cardA1", "A only: renew passport")
    _plant_card(core_B, "cardB1", "B only: book dentist")
    a_titles, b_titles, d_titles = _card_titles(core_A), _card_titles(core_B), _card_titles(core_default)
    check("A sees A's card", "A only: renew passport" in a_titles, str(a_titles))
    check("B does NOT see A's card (no leak)", "A only: renew passport" not in b_titles, str(b_titles))
    check("owner/default does NOT see A's card (no leak)",
          "A only: renew passport" not in d_titles, str(d_titles))
    check("A does NOT see B's card (no leak)", "B only: book dentist" not in a_titles, str(a_titles))

    # --- (1) MEMORY isolation: A's memory is visible to A only ---
    core_A.memory.history.write_text("A-only memory: Maya prefers texts after lunch")
    core_B.memory.history.write_text("B-only memory: water the plants at 6pm")
    a_mem, b_mem, d_mem = _history_texts(core_A), _history_texts(core_B), _history_texts(core_default)
    check("A sees A's memory", "A-only memory: Maya prefers texts after lunch" in a_mem, str(a_mem))
    check("B does NOT see A's memory (no leak)",
          "A-only memory: Maya prefers texts after lunch" not in b_mem, str(b_mem))
    check("owner/default does NOT see A's memory (no leak)",
          "A-only memory: Maya prefers texts after lunch" not in d_mem, str(d_mem))
    check("A does NOT see B's memory (no leak)",
          "B-only memory: water the plants at 6pm" not in a_mem, str(a_mem))

    # --- on-disk: A's card file lives under A's tree, never under B's or the base root ---
    a_files = list((Path(core_A.data_dir) / "owner_cards").glob("*.json"))
    check("A's card is physically under A's tree",
          bool(a_files) and all(str(f).startswith(str(core_A.data_dir)) for f in a_files))
    check("A's card did NOT land in the DEFAULT base",
          list((base / "owner_cards").glob("*.json")) == [])

    # --- (2) ACTION identity: each user's hand runs under THEIR id, owner under ARCADE ---
    check("A's api_hand identity == user A", core_A.api_hand.user_id == USER_A,
          str(core_A.api_hand.user_id))
    check("B's api_hand identity == user B", core_B.api_hand.user_id == USER_B,
          str(core_B.api_hand.user_id))
    check("A's and B's hand identities differ",
          core_A.api_hand.user_id != core_B.api_hand.user_id)
    check("owner/default hand identity stays the ARCADE/owner id (unchanged)",
          core_default.api_hand.user_id == ARCADE_SENTINEL, str(core_default.api_hand.user_id))

    print("TWO-USER ISOLATION:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
    print(f"  base         : {base}")
    print(f"  user A dir   : {core_A.data_dir}  (hand={core_A.api_hand.user_id})")
    print(f"  user B dir   : {core_B.data_dir}  (hand={core_B.api_hand.user_id})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
