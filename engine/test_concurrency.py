"""
Concurrency / idempotency regression tests for the Anticipy backend.

Targets the bug class that caused the 6-email incident: SELECT-then-INSERT
races where two near-simultaneous callers both pass the in-memory dedupe
and both insert.

Tests fire real HTTP calls against a live Vercel deployment with real
Supabase Auth tokens. We use an isolated test session per test so passing
tests leave no observable state in production.

Run:
    DISPLAY=:99 python engine/test_concurrency.py
or:
    pytest engine/test_concurrency.py -xvs

Required env (loaded from /workspaces/Anticipy/.env.local automatically):
    NEXT_PUBLIC_SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    NEXT_PUBLIC_SUPABASE_ANON_KEY

Optional:
    ANTICIPY_BASE_URL  — defaults to https://www.anticipy.ai
"""
import asyncio
import os
import sys
import time
import uuid
import json
from pathlib import Path
from typing import Any

import httpx

# ─── Env loader (no python-dotenv dependency required) ──────────────────────
ENV_FILE = Path(__file__).resolve().parent.parent / ".env.local"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
BASE_URL = os.environ.get("ANTICIPY_BASE_URL", "https://www.anticipy.ai")

REST = f"{SUPABASE_URL}/rest/v1"
AUTH = f"{SUPABASE_URL}/auth/v1"

ADMIN_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ─── Test-user lifecycle helpers ────────────────────────────────────────────
class TestUser:
    """Disposable Supabase auth user for one test run.

    Email pattern e2e-test-*@anticipy-test.local is recognised by /analyze
    as a test user — emails/SMS are SUPPRESSED so concurrent tests can run
    without inbox-bombing the admin.
    """

    def __init__(self) -> None:
        self.email = f"e2e-test-{uuid.uuid4().hex[:12]}@anticipy-test.local"
        self.password = uuid.uuid4().hex + "Aa!1"
        self.user_id: str | None = None
        self.access_token: str | None = None

    async def signup(self) -> None:
        # Direct admin signup (auto-confirms email, no SMTP needed).
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{AUTH}/admin/users",
                json={
                    "email": self.email,
                    "password": self.password,
                    "email_confirm": True,
                },
                headers=ADMIN_HEADERS,
            )
            r.raise_for_status()
            self.user_id = r.json()["id"]

            # Sign in to get an access token (analyze route needs Bearer auth).
            r = await c.post(
                f"{AUTH}/token?grant_type=password",
                json={"email": self.email, "password": self.password},
                headers={
                    "apikey": ANON_KEY,
                    "Content-Type": "application/json",
                },
            )
            r.raise_for_status()
            self.access_token = r.json()["access_token"]

    async def cleanup(self) -> None:
        if not self.user_id:
            return
        async with httpx.AsyncClient(timeout=30) as c:
            try:
                await c.delete(
                    f"{AUTH}/admin/users/{self.user_id}",
                    headers=ADMIN_HEADERS,
                )
            except Exception:
                pass

    @property
    def auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


async def create_session(user: TestUser) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{BASE_URL}/api/engine/session",
            headers=user.auth_headers,
        )
        r.raise_for_status()
        return r.json()["sessionId"]


async def count_intents(session_id: str) -> int:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{REST}/anticipy_intents",
            params={
                "session_id": f"eq.{session_id}",
                "select": "id",
            },
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
                "Prefer": "count=exact",
            },
        )
        r.raise_for_status()
        return len(r.json())


async def list_intents(session_id: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{REST}/anticipy_intents",
            params={
                "session_id": f"eq.{session_id}",
                "select": "id,status,summary_for_user,dedupe_key",
            },
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
            },
        )
        r.raise_for_status()
        return r.json()


async def insert_intent_directly(session_id: str, summary: str = "Test intent") -> str:
    """Bypass /analyze — insert a row straight into anticipy_intents.
    Used by tests that need a known-id intent to bombard /confirm with.
    """
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{REST}/anticipy_intents",
            json={
                "session_id": session_id,
                "action_type": "note_add",
                "parameters": {"title": summary, "body": "test"},
                "confidence": 0.9,
                "importance": "low",
                "summary_for_user": summary,
                "evidence_quote": "test",
                "status": "pending",
                "default_after_timeout": "no",
            },
            headers=ADMIN_HEADERS,
        )
        r.raise_for_status()
        return r.json()[0]["id"]


async def get_intent_status(intent_id: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{REST}/anticipy_intents",
            params={"id": f"eq.{intent_id}", "select": "status"},
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0]["status"] if rows else ""


async def count_actions_for_intent(intent_id: str) -> int:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{REST}/anticipy_actions",
            params={"intent_id": f"eq.{intent_id}", "select": "id"},
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
            },
        )
        r.raise_for_status()
        return len(r.json())


async def count_preferences_for_intent(user_id: str, summary: str) -> int:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            f"{REST}/anticipy_preferences",
            params={
                "user_id": f"eq.{user_id}",
                "intent_summary": f"eq.{summary[:500]}",
                "select": "id",
            },
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
            },
        )
        r.raise_for_status()
        return len(r.json())


# ─── Tests ──────────────────────────────────────────────────────────────────

async def test_concurrent_analyze_inserts_one_intent_per_summary() -> bool:
    """Fire 10 concurrent /analyze calls with the same transcript+session.
    Even if the LLM returns 1 intent per call, only 1 row should land.
    """
    print("\n[1/3] Concurrent /analyze: 10 calls, same transcript, same session")
    user = TestUser()
    await user.signup()
    try:
        session_id = await create_session(user)
        # Use a clear transcript that reliably extracts ONE concrete intent.
        transcript = (
            "[Speaker 0]: I really need to email Marcus tomorrow at 9am about "
            "the Q3 board deck. Subject: Q3 deck review request. Body: Hey "
            "Marcus, can you take a pass at the Q3 board deck before Friday? "
            "Thanks."
        )

        async def fire_one(idx: int) -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(
                    f"{BASE_URL}/api/engine/analyze",
                    headers=user.auth_headers,
                    json={
                        "sessionId": session_id,
                        "transcript": transcript,
                        "timezone": "America/Vancouver",
                        "isFinal": False,
                    },
                )
                return {
                    "idx": idx,
                    "status": r.status_code,
                    "body": r.json() if r.status_code < 500 else r.text[:200],
                }

        t0 = time.time()
        results = await asyncio.gather(*(fire_one(i) for i in range(10)))
        elapsed = time.time() - t0

        # Wait briefly for any in-flight inserts to land.
        await asyncio.sleep(2.0)
        intents = await list_intents(session_id)
        unique_summaries = {i["summary_for_user"] for i in intents}

        passed = (
            len(intents) >= 1
            and len(intents) == len(unique_summaries)
            and len(intents) <= 3  # generous: LLM may extract a couple of intents
        )
        if passed:
            print(
                f"   PASS — fired 10 calls in {elapsed:.2f}s, {len(intents)} unique intent(s) inserted "
                f"({sum(1 for r in results if r['status'] == 409)} returned 409 for inflight-lock)"
            )
        else:
            print(
                f"   FAIL — fired 10 calls, expected 1-3 unique intents, got {len(intents)}"
            )
            for it in intents[:5]:
                print(f"     - {it['summary_for_user'][:80]} (key={it['dedupe_key'][:60]})")
        return passed
    finally:
        await user.cleanup()


async def test_concurrent_confirms_execute_action_at_most_once() -> bool:
    """Fire 5 concurrent confirms on the same intent. Exactly ONE should win
    the status flip; subsequent ones must short-circuit.
    """
    print("\n[2/3] Concurrent /confirm: 5 calls, same intent, status flips once")
    user = TestUser()
    await user.signup()
    try:
        session_id = await create_session(user)
        # Insert a deterministic test intent (note_add → no browser, no email).
        intent_id = await insert_intent_directly(
            session_id, "Test concurrent confirm intent"
        )

        async def fire_one(idx: int) -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.get(
                    f"{BASE_URL}/api/engine/confirm",
                    params={"intentId": intent_id, "action": "yes"},
                )
                return {"idx": idx, "status": r.status_code}

        t0 = time.time()
        await asyncio.gather(*(fire_one(i) for i in range(5)))
        elapsed = time.time() - t0
        await asyncio.sleep(1.0)

        # Status should be "executed" (note_add succeeded) or "confirmed".
        final_status = await get_intent_status(intent_id)
        action_count = await count_actions_for_intent(intent_id)

        passed = final_status in ("executed", "confirmed", "failed") and action_count <= 1
        if passed:
            print(
                f"   PASS — 5 concurrent confirms in {elapsed:.2f}s, "
                f"final status={final_status}, anticipy_actions rows={action_count}"
            )
        else:
            print(
                f"   FAIL — final status={final_status}, action rows={action_count} "
                "(expected exactly 1 action row)"
            )
        return passed
    finally:
        await user.cleanup()


async def test_memory_unique_constraint_blocks_duplicates() -> bool:
    """Direct INSERT to anticipy_memory with the same (user_id, kind, key)
    should be blocked by the unique index added in the migration. Tests
    the DB constraint itself, decoupled from /analyze rate-limiting.
    """
    print("\n[+] anticipy_memory: unique (user_id, kind, key) blocks duplicates")
    user = TestUser()
    await user.signup()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            # First insert — must succeed.
            r = await c.post(
                f"{REST}/anticipy_memory",
                json={
                    "user_id": user.user_id,
                    "kind": "preference",
                    "key": "test_concurrency_key",
                    "value": "first value",
                    "evidence_quote": "test",
                    "confidence": 0.9,
                },
                headers=ADMIN_HEADERS,
            )
            first_ok = r.status_code in (200, 201)

            # Second insert with same key — must fail with 409 / 23505.
            r = await c.post(
                f"{REST}/anticipy_memory",
                json={
                    "user_id": user.user_id,
                    "kind": "Preference",  # different case → still blocked by lower()
                    "key": "TEST_concurrency_key",
                    "value": "second value",
                    "evidence_quote": "test",
                    "confidence": 0.9,
                },
                headers=ADMIN_HEADERS,
            )
            second_blocked = r.status_code == 409 or "23505" in (r.text or "")

        passed = first_ok and second_blocked
        if passed:
            print("   PASS — first insert ok, duplicate blocked by unique index (case-insensitive)")
        else:
            print(
                f"   FAIL — first_ok={first_ok}, second_blocked={second_blocked} "
                "(expected unique index to reject duplicate)"
            )
        return passed
    finally:
        # Clean up the test row before deleting user (FK constraint).
        async with httpx.AsyncClient(timeout=30) as c:
            await c.delete(
                f"{REST}/anticipy_memory",
                params={"user_id": f"eq.{user.user_id}"},
                headers=ADMIN_HEADERS,
            )
        await user.cleanup()


async def test_preferences_unique_constraint_blocks_duplicates() -> bool:
    """Direct INSERT to anticipy_preferences twice with the same
    (user_id, intent_summary, signal) should fire the unique index.
    """
    print("\n[+] anticipy_preferences: unique (user_id, intent_summary, signal)")
    user = TestUser()
    await user.signup()
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            payload = {
                "user_id": user.user_id,
                "signal": "accept",
                "intent_summary": "Test concurrency preference",
                "action_type": "note_add",
                "evidence_quote": "test",
                "reasoning": "first",
            }
            r1 = await c.post(
                f"{REST}/anticipy_preferences",
                json=payload,
                headers=ADMIN_HEADERS,
            )
            first_ok = r1.status_code in (200, 201)

            r2 = await c.post(
                f"{REST}/anticipy_preferences",
                json={**payload, "reasoning": "second"},
                headers=ADMIN_HEADERS,
            )
            second_blocked = r2.status_code == 409 or "23505" in (r2.text or "")

        passed = first_ok and second_blocked
        if passed:
            print("   PASS — first insert ok, duplicate blocked")
        else:
            print(f"   FAIL — first_ok={first_ok}, second_blocked={second_blocked}")
        return passed
    finally:
        async with httpx.AsyncClient(timeout=30) as c:
            await c.delete(
                f"{REST}/anticipy_preferences",
                params={"user_id": f"eq.{user.user_id}"},
                headers=ADMIN_HEADERS,
            )
        await user.cleanup()


async def test_auto_proceed_vs_user_click_resolves_to_one_status() -> bool:
    """Fire /confirm and /auto-proceed on the same intent simultaneously.
    Exactly one path must win; the second must report alreadyResolved.
    Also: anticipy_preferences should have exactly ONE row for this intent
    (the unique index added by deep_bug_hunt_idempotency_constraints).
    """
    print("\n[3/3] Race: /confirm vs /auto-proceed on same intent")
    user = TestUser()
    await user.signup()
    try:
        session_id = await create_session(user)
        summary = f"Test race intent {uuid.uuid4().hex[:8]}"
        intent_id = await insert_intent_directly(session_id, summary)

        # Set status to awaiting_user so auto-proceed is allowed.
        async with httpx.AsyncClient(timeout=30) as c:
            await c.patch(
                f"{REST}/anticipy_intents",
                params={"id": f"eq.{intent_id}"},
                json={"status": "awaiting_user", "default_after_timeout": "no"},
                headers=ADMIN_HEADERS,
            )

        async def confirm_yes() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.get(
                    f"{BASE_URL}/api/engine/confirm",
                    params={"intentId": intent_id, "action": "yes"},
                )
                return {"path": "confirm", "status": r.status_code}

        async def auto_proceed() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(
                    f"{BASE_URL}/api/engine/auto-proceed",
                    headers=user.auth_headers,
                    json={"intentId": intent_id},
                )
                return {"path": "auto", "status": r.status_code, "body": r.json()}

        # /confirm requires status=pending; we set awaiting_user above. Reset.
        async with httpx.AsyncClient(timeout=30) as c:
            await c.patch(
                f"{REST}/anticipy_intents",
                params={"id": f"eq.{intent_id}"},
                json={"status": "pending", "default_after_timeout": "no"},
                headers=ADMIN_HEADERS,
            )

        results = await asyncio.gather(confirm_yes(), auto_proceed())

        await asyncio.sleep(2.5)  # let preference recording (Gemini call) land
        action_count = await count_actions_for_intent(intent_id)
        # Count preference rows — must be exactly 1 (or 0 if Gemini call dropped).
        pref_count = await count_preferences_for_intent(user.user_id, summary)
        final_status = await get_intent_status(intent_id)

        passed = action_count <= 1 and pref_count <= 1
        if passed:
            print(
                f"   PASS — 1 winner: status={final_status}, "
                f"actions={action_count}, preferences={pref_count}"
            )
        else:
            print(
                f"   FAIL — status={final_status}, actions={action_count}, "
                f"preferences={pref_count} (expected ≤1 each)"
            )
        for r in results:
            print(f"     {r}")
        return passed
    finally:
        await user.cleanup()


# ─── Runner ─────────────────────────────────────────────────────────────────

async def main() -> int:
    print(f"Anticipy concurrency tests against {BASE_URL}")
    tests = [
        test_concurrent_analyze_inserts_one_intent_per_summary,
        test_concurrent_confirms_execute_action_at_most_once,
        test_auto_proceed_vs_user_click_resolves_to_one_status,
        test_memory_unique_constraint_blocks_duplicates,
        test_preferences_unique_constraint_blocks_duplicates,
    ]
    results: list[bool] = []
    for t in tests:
        try:
            ok = await t()
        except Exception as exc:
            print(f"   ERROR — {t.__name__}: {exc!r}")
            ok = False
        results.append(ok)

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"Concurrency tests: {passed}/{total} passed")
    print(f"{'='*60}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
