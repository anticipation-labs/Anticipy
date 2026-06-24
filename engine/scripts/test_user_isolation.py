"""Per-user data isolation — the load-bearing proof.

Today there is ONE global brain. This test proves the new registry gives each SIGNED-IN
user their OWN ControlCore (own data_dir -> own cards, memory, goals, permissions, vault),
so one user's data can NEVER appear for another user, and neither appears for the
DEFAULT/owner.

It drives the REAL HTTP path (TestClient -> the owner_api_auth middleware -> the per-user
contextvar -> current_core() in the handlers), authenticating user A and user B with
DISTINCT Supabase-style bearers (we stub verify_supabase_token so no network/secret is
needed). The assertions:

  1. With a token configured, an anonymous request is 401 (the gate still holds).
  2. User A ingests a transcript that creates owner cards + a calendar reminder + memory.
  3. User B's /owner/cards, /memory/history, /memory/open-loops, /status all show ZERO of
     user A's work (counts are 0 / empty).
  4. The DEFAULT (owner-token) caller also sees NONE of user A's work.
  5. On disk: user A's data lives under <base>/users/<A>/, user B under <base>/users/<B>/,
     and the DEFAULT base dir is untouched by either user's ingest — three separate trees.
  6. The cores are three distinct objects with three distinct data_dirs.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_user_isolation.py
"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
# Pin a known owner identity so default_user() is deterministic regardless of .env.local.
os.environ["ADMIN_EMAIL"] = "owner@anticipy.test"
_BASE = tempfile.mkdtemp(prefix="anticipy-isolation-")
os.environ["ANTICIPY_DATA_DIR"] = _BASE

# An owner API token must be set so the auth gate is ACTIVE and the Supabase-user branch is
# the only way A/B authenticate as themselves (mirrors the real public deploy).
OWNER_TOKEN = "owner-token-isolation-xyz"
os.environ["ANTICIPY_OWNER_API_TOKEN"] = OWNER_TOKEN

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine import main as m  # noqa: E402
from anticipy_engine.core import auth as auth_mod  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402

# Stub the Supabase verifier: map our two fake JWT-shaped bearers to two distinct users.
# The middleware only calls this for tokens with exactly two dots (JWT shape), and the
# opaque OWNER_TOKEN has none, so the owner-token path is unaffected.
_USERS = {
    "jwt.userA.sig": {"user_id": "user-A-uuid-1111", "email": "a@example.com"},
    "jwt.userB.sig": {"user_id": "user-B-uuid-2222", "email": "b@example.com"},
}


def _fake_verify(token, now=None):
    return _USERS.get(token)


auth_mod.verify_supabase_token = _fake_verify

A_HEADERS = {"authorization": "Bearer jwt.userA.sig"}
B_HEADERS = {"authorization": "Bearer jwt.userB.sig"}
OWNER_HEADERS = {"x-anticipy-owner-token": OWNER_TOKEN}

# A transcript that, on the stub brain, produces a calendar reminder card + a memory write +
# an open loop — concrete, countable artifacts we can look for leaking across users.
A_TRANSCRIPT = (
    "[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.\n"
    "[13:00] My wife Maya prefers texts after lunch.\n"
)


def _cards(client, headers):
    r = client.get("/owner/cards?limit=50", headers=headers)
    assert r.status_code == 200, (headers, r.status_code, r.text)
    return r.json()["cards"]


def _status(client, headers):
    r = client.get("/status", headers=headers)
    assert r.status_code == 200, (headers, r.status_code, r.text)
    return r.json()


def _history(client, headers):
    r = client.get("/memory/history", headers=headers)
    assert r.status_code == 200, (headers, r.status_code, r.text)
    return r.json()["items"]


def _files(p: Path, pattern: str) -> list:
    return list(p.glob(pattern)) if p.exists() else []


def main():
    base = Path(_BASE)
    with TestClient(m.app) as client:
        # --- 0) the gate still holds: anonymous is rejected when a token is configured ---
        anon = client.get("/owner/cards")
        assert anon.status_code == 401, anon.text

        # Sanity: three distinct cores / data_dirs (resolve through the public seam).
        core_default = registry.core_for(registry.default_user())
        core_A = registry.core_for("user-A-uuid-1111")
        core_B = registry.core_for("user-B-uuid-2222")
        assert core_default is m.core, "default user must map to the module-global core"
        assert len({id(core_default), id(core_A), id(core_B)}) == 3, "cores must be distinct"
        dirs = {str(core_default.data_dir), str(core_A.data_dir), str(core_B.data_dir)}
        assert len(dirs) == 3, f"data_dirs must be distinct: {dirs}"
        assert str(core_A.data_dir).startswith(str(base / "users")), core_A.data_dir
        assert str(core_B.data_dir).startswith(str(base / "users")), core_B.data_dir
        assert Path(core_default.data_dir) == base, core_default.data_dir

        # --- baseline: everyone starts empty ---
        assert _cards(client, A_HEADERS) == []
        assert _cards(client, B_HEADERS) == []
        assert _cards(client, OWNER_HEADERS) == []

        # --- 1) USER A ingests a real transcript (creates cards + memory + open loop) ---
        ingest = client.post(
            "/owner/ingest",
            headers=A_HEADERS,
            json={"source": "typed", "text": A_TRANSCRIPT, "execute_actions": True,
                  "meta": {"test": "isolation_A"}},
        )
        assert ingest.status_code == 200, ingest.text
        a_cards = ingest.json()["cards"]
        assert a_cards, "user A's ingest must produce at least one card"
        a_card_ids = {c["id"] for c in a_cards}

        # User A sees their own cards + memory. The transcript creates owner cards AND at
        # least one memory artifact (an open loop and/or a history entry) — assert A has SOME
        # memory state (drawer-agnostic), since the brain may file the reminder as an open loop
        # rather than a history line.
        a_cards_get = _cards(client, A_HEADERS)
        assert {c["id"] for c in a_cards_get} == a_card_ids, "A must see A's cards"
        a_status = _status(client, A_HEADERS)
        a_memory_signal = (a_status["history_count"] + a_status["open_loop_count"])
        assert a_memory_signal >= 1, f"A must have some memory state (history or loops): {a_status}"

        # --- 2) USER B sees ZERO of A's cards / memory / loops ---
        b_cards = _cards(client, B_HEADERS)
        assert b_cards == [], f"LEAK: user B sees user A's cards: {b_cards}"
        assert not (a_card_ids & {c["id"] for c in b_cards}), "LEAK: shared card ids A/B"
        b_status = _status(client, B_HEADERS)
        assert b_status["history_count"] == 0, f"LEAK: B history not empty: {b_status}"
        assert b_status["open_loop_count"] == 0, f"LEAK: B open loops not empty: {b_status}"
        assert _history(client, B_HEADERS) == [], "LEAK: B sees A's memory history"
        b_loops = client.get("/memory/open-loops?limit=50", headers=B_HEADERS).json()["loops"]
        assert b_loops == [], f"LEAK: B sees A's open loops: {b_loops}"

        # --- 3) the DEFAULT / owner caller sees NONE of A's work either ---
        owner_cards = _cards(client, OWNER_HEADERS)
        assert owner_cards == [], f"LEAK: owner/default sees user A's cards: {owner_cards}"
        owner_status = _status(client, OWNER_HEADERS)
        assert owner_status["history_count"] == 0, f"LEAK: owner history not empty: {owner_status}"
        assert owner_status["open_loop_count"] == 0, f"LEAK: owner open loops not empty: {owner_status}"
        assert _history(client, OWNER_HEADERS) == [], "LEAK: owner sees A's memory history"

        # --- 4) on-disk separation: A's tree has cards, B's + default base do not ---
        a_dir = Path(core_A.data_dir)
        b_dir = Path(core_B.data_dir)
        a_card_files = _files(a_dir / "owner_cards", "*.json")
        assert a_card_files, f"user A's cards must be on disk under {a_dir}"
        # The DEFAULT base must have NO owner_cards from A (its only subtree touched is users/).
        default_card_files = _files(base / "owner_cards", "*.json")
        assert default_card_files == [], f"LEAK: A's cards landed in the DEFAULT base: {default_card_files}"
        b_card_files = _files(b_dir / "owner_cards", "*.json")
        assert b_card_files == [], f"LEAK: A's cards visible in B's tree: {b_card_files}"
        # A's card files are physically under A's dir, never under B's or the base root.
        for f in a_card_files:
            assert str(f).startswith(str(a_dir)), f

        # --- 5) USER B does their OWN ingest; A's data is STILL only A's ---
        b_ingest = client.post(
            "/owner/ingest",
            headers=B_HEADERS,
            json={"source": "typed", "text": "[09:00] remind me to water the plants at 6pm.",
                  "execute_actions": True, "meta": {"test": "isolation_B"}},
        )
        assert b_ingest.status_code == 200, b_ingest.text
        b_card_ids = {c["id"] for c in b_ingest.json()["cards"]}
        # B now has its own cards, and A's set is disjoint from B's; A still only sees A's.
        a_after = {c["id"] for c in _cards(client, A_HEADERS)}
        b_after = {c["id"] for c in _cards(client, B_HEADERS)}
        assert a_after == a_card_ids, f"A's cards changed after B ingested: {a_after}"
        assert not (a_after & b_after), f"LEAK: A and B share cards after both ingested: {a_after & b_after}"

        print("PASS user_isolation: per-user ControlCore — A's cards/memory/loops never appear "
              "for B or the owner; three separate data_dirs proven on disk")
        print(f"  default base : {base}")
        print(f"  user A dir   : {a_dir}  (cards on disk: {len(a_card_files)})")
        print(f"  user B dir   : {b_dir}")
        print(f"  A card ids   : {sorted(a_card_ids)}  (A memory signal: {a_memory_signal})")
        print(f"  B sees cards : {b_cards}  status(history={b_status['history_count']}, loops={b_status['open_loop_count']})  (all 0 == isolated)")
        print(f"  owner sees   : {owner_cards}  status(history={owner_status['history_count']}, loops={owner_status['open_loop_count']})  (all 0 == isolated)")


if __name__ == "__main__":
    main()
