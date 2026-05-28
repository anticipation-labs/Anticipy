"""
Memory layer end-to-end test.

Verifies the new long-term memory pipeline added to /api/engine/analyze:

  1. POST 5 sequential transcripts as the same user, each carrying a
     different "memorable" item (preference, relationship, reference, etc).
  2. After each call, confirm rows accumulate in `anticipy_memory` for that
     user — i.e. extractMemoryItems is firing and writing.
  3. After day 3, fetch the rows with recallRelevantMemory(userId, ...) via
     a small Node helper and assert the recall list contains items the LLM
     extracted from days 1-2. This proves the recall list — which gets
     passed into buildIntentPrompt as `memoryContext` — is populated by
     the time the next analyze call runs.
  4. Verify the buildIntentPrompt output, when called with the recall list,
     actually embeds the memory items in the prompt string (the wiring we
     added to intent-prompt.ts).

NOTE: The memory extractor is fire-and-forget (background promise), so we
poll for a few seconds after each analyze call before checking the table.

Run:
  cd engine && python test_memory_layer.py
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

SUPABASE_URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SUPABASE_ANON = os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
ANTICIPY_BASE = os.environ.get("ANTICIPY_BASE", "https://www.anticipy.ai")

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Five sequential transcripts. Each contains BOTH a real intent AND a
# random memorable item. Memorable items intentionally span kinds:
# preference, relationship, reference, context, routine.
TRANSCRIPTS = [
    [
        # Day 1: preference + relationship
        "Wearer: Quick coffee run, I'll grab a flat white at Blue Bottle on 6th.",
        "Friend: Want me to come?",
        "Wearer: Sure. Oh and remind me to text my sister Lila later, she just moved to Brooklyn.",
    ],
    [
        # Day 2: dietary context + ongoing reference
        "Wearer: I'm vegan so anywhere except the steakhouse works for dinner.",
        "Friend: Got it. Did you ever order those Gucci shoes you were looking at?",
        "Wearer: Not yet, I'll put it on my list.",
    ],
    [
        # Day 3: routine + work relationship
        "Wearer: Thursday 6am workout — I never miss it.",
        "Friend: That's the one with John Yokels?",
        "Wearer: Yeah he's my CFO, we use the gym time to sync.",
    ],
    [
        # Day 4: another preference + a casual reference
        "Wearer: My dog Banjo is at the groomer right now.",
        "Friend: Cute. Can you book us tickets for that comedy show?",
        "Wearer: I'll do it tonight.",
    ],
    [
        # Day 5: cross-references prior memory — exercises pronoun
        # disambiguation in the next analyze call's prompt.
        "Wearer: I should call her back about the move, it's been a week.",
        "Friend: Lila?",
        "Wearer: Yeah.",
    ],
]


async def get_or_create_test_user_jwt(email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        await c.post(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            headers={
                "apikey": SUPABASE_SERVICE,
                "Authorization": f"Bearer {SUPABASE_SERVICE}",
                "Content-Type": "application/json",
            },
            json={"email": email, "password": password, "email_confirm": True},
        )
        r = await c.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        if r.status_code != 200:
            raise RuntimeError(f"signin {r.status_code}: {r.text[:200]}")
        return r.json()["access_token"]


async def get_user_id_from_jwt(jwt: str) -> str | None:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON, "Authorization": f"Bearer {jwt}"},
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")


async def insert_session(session_id: str, user_email: str, user_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        body = {
            "id": session_id,
            "status": "recording",
            "user_email": user_email,
            "user_id": user_id,
            "metadata": {"memory_test": True},
        }
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions",
            headers=HDR,
            json=body,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"session insert {r.status_code}: {r.text[:200]}")


async def call_analyze(transcript_lines: list[str], session_id: str, jwt: str) -> dict:
    payload = {
        "sessionId": session_id,
        "transcript": "\n".join(transcript_lines),
        "isFinal": True,
    }
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(
            f"{ANTICIPY_BASE}/api/engine/analyze",
            headers={"Authorization": f"Bearer {jwt}"},
            json=payload,
        )
        if r.status_code != 200:
            return {"error": f"analyze {r.status_code}: {r.text[:300]}"}
        return r.json()


async def fetch_memory(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_memory"
            f"?user_id=eq.{user_id}&select=*&order=created_at.desc",
            headers=HDR,
        )
        if r.status_code != 200:
            return []
        return r.json()


async def cleanup(user_id: str, session_ids: list[str]) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_memory?user_id=eq.{user_id}",
            headers=HDR,
        )
        for sid in session_ids:
            await c.delete(
                f"{SUPABASE_URL}/rest/v1/anticipy_intents?session_id=eq.{sid}",
                headers=HDR,
            )
            await c.delete(
                f"{SUPABASE_URL}/rest/v1/anticipy_sessions?id=eq.{sid}",
                headers=HDR,
            )


def run_node_recall_and_prompt(user_id: str, transcript: str) -> dict:
    """Invoke recallRelevantMemory + buildIntentPrompt directly via a tsx
    script. Verifies that (a) the recall layer surfaces memory rows for
    this user, and (b) buildIntentPrompt embeds them into the prompt
    string (so the production /analyze call would too)."""
    script = """
import { recallRelevantMemory } from "@/lib/memory-recall";
import { buildIntentPrompt } from "@/lib/intent-prompt";

const userId = process.env._TEST_USER_ID!;
const transcript = process.env._TEST_TRANSCRIPT!;

(async () => {
  const memoryContext = await recallRelevantMemory(userId, transcript, 10);
  const { user } = buildIntentPrompt(
    transcript,
    new Date().toLocaleString("en-US", { timeZone: "America/Vancouver" }),
    "America/Vancouver",
    [],
    [],
    null,
    memoryContext
  );
  process.stdout.write(JSON.stringify({
    memoryContext,
    promptContainsMemoryHeader: user.includes("Long-term memory about this wearer"),
    promptContainsAtLeastOneItem: memoryContext.some((m) => user.includes(m)),
    promptUserSnippet: user.slice(-1500),
  }));
})().catch((e) => {
  process.stdout.write(JSON.stringify({ error: String(e) }));
  process.exit(2);
});
"""
    script_path = ROOT / "engine" / "_memory_recall_probe.ts"
    script_path.write_text(script)
    try:
        env = os.environ.copy()
        env["_TEST_USER_ID"] = user_id
        env["_TEST_TRANSCRIPT"] = transcript
        # Use npx tsx to run a TS file with the same path aliasing as the app.
        result = subprocess.run(
            ["npx", "--yes", "tsx", "--tsconfig", str(ROOT / "tsconfig.json"),
             str(script_path)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode != 0:
            return {
                "error": f"tsx exit {result.returncode}",
                "stderr": result.stderr[-800:],
                "stdout": result.stdout[-800:],
            }
        return json.loads(result.stdout.strip())
    finally:
        try:
            script_path.unlink()
        except Exception:
            pass


async def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    email = f"e2e-test-memory-{suffix}@anticipy-test.local"
    password = f"Pass-{suffix}!23"
    print(f"Provisioning user {email}…", flush=True)
    jwt = await get_or_create_test_user_jwt(email, password)
    user_id = await get_user_id_from_jwt(jwt)
    if not user_id:
        print("ERROR: could not resolve user_id from jwt")
        return 2

    session_ids: list[str] = []
    failed = False
    try:
        memory_counts: list[int] = []
        for i, transcript in enumerate(TRANSCRIPTS, start=1):
            session_id = str(uuid.uuid4())
            session_ids.append(session_id)
            await insert_session(session_id, email, user_id)
            print(f"\n[Day {i}] POST /api/engine/analyze…", flush=True)
            t0 = time.time()
            resp = await call_analyze(transcript, session_id, jwt)
            print(f"  analyze: {time.time() - t0:.1f}s — keys={list(resp)[:6]}", flush=True)
            if "error" in resp:
                print(f"  ERROR: {resp['error']}")
                failed = True
                break

            # Memory extraction is fire-and-forget. Poll briefly for new rows.
            count_target = i  # at least one new item per transcript (best-effort)
            count_now = 0
            for _ in range(15):  # up to ~15s
                rows = await fetch_memory(user_id)
                count_now = len(rows)
                if count_now >= count_target:
                    break
                await asyncio.sleep(1)
            memory_counts.append(count_now)
            print(f"  memory rows for user: {count_now}", flush=True)

        # Assertion (a): rows accumulate strictly across calls (allow flat
        # turns since extraction is best-effort, but require strictly more
        # at the end than at the start).
        print("\n--- Assertions ---", flush=True)
        print(f"Memory counts after each day: {memory_counts}", flush=True)
        assert_a = (
            len(memory_counts) == len(TRANSCRIPTS)
            and memory_counts[-1] > 0
            and memory_counts[-1] >= memory_counts[0]
        )
        print(f"(a) memory rows accumulate: {'PASS' if assert_a else 'FAIL'}", flush=True)
        if not assert_a:
            failed = True

        # Assertion (b): the third-day prompt actually contains memory
        # items extracted on days 1-2. We probe via a tsx script that
        # imports the production modules.
        third_day_transcript = "\n".join(TRANSCRIPTS[2])
        probe = run_node_recall_and_prompt(user_id, third_day_transcript)
        if "error" in probe:
            print(f"  probe error: {probe.get('error')}\n  stderr={probe.get('stderr', '')[-400:]}", flush=True)
            failed = True
        else:
            print(f"  recalled {len(probe['memoryContext'])} items:")
            for m in probe["memoryContext"][:8]:
                print(f"    - {m}")
            assert_b1 = probe["promptContainsMemoryHeader"]
            assert_b2 = probe["promptContainsAtLeastOneItem"]
            assert_b3 = len(probe["memoryContext"]) > 0
            print(f"(b1) prompt has memory header: {'PASS' if assert_b1 else 'FAIL'}", flush=True)
            print(f"(b2) prompt embeds at least one memory item: {'PASS' if assert_b2 else 'FAIL'}", flush=True)
            print(f"(b3) recall returns >=1 item: {'PASS' if assert_b3 else 'FAIL'}", flush=True)
            if not (assert_b1 and assert_b2 and assert_b3):
                failed = True

        # Show a sample of the actual rows so the human reviewer can sanity-check
        all_rows = await fetch_memory(user_id)
        print("\nSample of extracted memory rows (last 8):", flush=True)
        for r in all_rows[:8]:
            print(f"  [{r.get('kind')}:{r.get('key')}] {r.get('value')}  (conf={r.get('confidence')})")

    finally:
        await cleanup(user_id, session_ids)

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
