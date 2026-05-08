"""
Preference learning + check-in end-to-end probe.

Covers the new wiring added in this PR:

  1. Schema: anticipy_preferences exists; anticipy_intents.status accepts
     'awaiting_user' / 'auto_proceeded'; default_after_timeout column exists.
  2. recordPreferenceSignal writes a row with a Gemini-generated reasoning
     sentence on confirm/reject signals.
  3. recallUserPreferences reads them back, diversifies across signals,
     and formats them as `[signal:action_type] reasoning` strings.
  4. buildIntentPrompt embeds the recalled preferences into the prompt
     under the new "Personal preferences" header.
  5. /api/engine/auto-proceed flips an awaiting_user intent to
     auto_proceeded and records the auto_proceed signal.

Run:
  cd engine && python test_preferences.py

Environment: needs the same .env.local the analyze route uses
(NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GOOGLE_API_KEY).
ANTICIPY_BASE controls which deployment we hit; defaults to prod.
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
            "metadata": {"preferences_test": True},
        }
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions",
            headers=HDR,
            json=body,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"session insert {r.status_code}: {r.text[:200]}")


async def insert_intent(
    session_id: str,
    action_type: str,
    summary: str,
    evidence: str,
    status: str = "pending",
    default_after_timeout: str | None = None,
    execution_result: str | None = None,
) -> str:
    body = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "action_type": action_type,
        "parameters": {},
        "confidence": 0.85,
        "importance": "standard",
        "summary_for_user": summary,
        "evidence_quote": evidence,
        "status": status,
    }
    if default_after_timeout is not None:
        body["default_after_timeout"] = default_after_timeout
    if execution_result is not None:
        body["execution_result"] = execution_result
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents",
            headers=HDR,
            json=body,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"intent insert {r.status_code}: {r.text[:200]}")
        rows = r.json()
        return rows[0]["id"] if rows else body["id"]


async def fetch_preferences(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_preferences"
            f"?user_id=eq.{user_id}&select=*&order=created_at.desc",
            headers=HDR,
        )
        if r.status_code != 200:
            return []
        return r.json()


async def fetch_intent(intent_id: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents"
            f"?id=eq.{intent_id}&select=*",
            headers=HDR,
        )
        if r.status_code != 200 or not r.json():
            return None
        return r.json()[0]


async def call_confirm(intent_id: str, action: str) -> int:
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as c:
        r = await c.get(
            f"{ANTICIPY_BASE}/api/engine/confirm"
            f"?intentId={intent_id}&action={action}"
        )
        return r.status_code


async def call_auto_proceed(intent_id: str, jwt: str) -> tuple[int, dict]:
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            f"{ANTICIPY_BASE}/api/engine/auto-proceed",
            headers={"Authorization": f"Bearer {jwt}"},
            json={"intentId": intent_id},
        )
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:200]}


async def cleanup(user_id: str, session_ids: list[str]) -> None:
    async with httpx.AsyncClient(timeout=20) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_preferences?user_id=eq.{user_id}",
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


def run_node_recall_and_prompt(user_id: str) -> dict:
    """Invoke recallUserPreferences + buildIntentPrompt directly via tsx."""
    script = """
import { recallUserPreferences } from "@/lib/preference-recall";
import { buildIntentPrompt } from "@/lib/intent-prompt";

const userId = process.env._TEST_USER_ID!;

(async () => {
  const preferenceContext = await recallUserPreferences(userId, 15);
  const { user } = buildIntentPrompt(
    "Wearer: book me a meeting at 7am tomorrow.",
    new Date().toLocaleString("en-US", { timeZone: "America/Vancouver" }),
    "America/Vancouver",
    [],
    [],
    null,
    [],
    preferenceContext
  );
  process.stdout.write(JSON.stringify({
    preferenceContext,
    promptContainsHeader: user.includes("Personal preferences"),
    promptContainsAtLeastOneItem:
      preferenceContext.length > 0 &&
      preferenceContext.some((p) => user.includes(p)),
    promptUserSnippet: user.slice(-1800),
  }));
})().catch((e) => {
  process.stdout.write(JSON.stringify({ error: String(e) }));
  process.exit(2);
});
"""
    script_path = ROOT / "engine" / "_pref_recall_probe.ts"
    script_path.write_text(script)
    try:
        env = os.environ.copy()
        env["_TEST_USER_ID"] = user_id
        result = subprocess.run(
            [
                "npx", "--yes", "tsx",
                "--tsconfig", str(ROOT / "tsconfig.json"),
                str(script_path),
            ],
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
    email = f"e2e-test-prefs-{suffix}@anticipy-test.local"
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
        # ── 1. Schema check: confirm new column + new statuses are accepted ──
        print("\n[1/5] Schema check: insert intent with awaiting_user + default_after_timeout…", flush=True)
        sid = str(uuid.uuid4())
        session_ids.append(sid)
        await insert_session(sid, email, user_id)
        awaiting_id = await insert_intent(
            sid,
            "subscribe_newsletter",
            "Subscribe you to the NYT.",
            "I'd love to read the NYT every day.",
            status="awaiting_user",
            default_after_timeout="no",
            execution_result="About to subscribe to the NYT — confirm?",
        )
        row = await fetch_intent(awaiting_id)
        if not row or row.get("status") != "awaiting_user" or row.get("default_after_timeout") != "no":
            print(f"  FAIL — schema row missing fields: {row}")
            failed = True
        else:
            print("  OK — awaiting_user / default_after_timeout=no persisted.")

        # ── 2. Confirm endpoint: reject path records a 'reject' preference ──
        print("\n[2/5] Confirm 'no' path → record reject preference…", flush=True)
        reject_intent_id = await insert_intent(
            sid,
            "book_meeting_morning",
            "Book a 7am meeting tomorrow with Sarah.",
            "Book me a meeting at 7am tomorrow with Sarah.",
            status="pending",
        )
        status_code = await call_confirm(reject_intent_id, "no")
        print(f"  /api/engine/confirm returned {status_code}.")
        # Wait briefly for the fire-and-forget Gemini summarization.
        await asyncio.sleep(6)
        prefs = await fetch_preferences(user_id)
        reject_rows = [p for p in prefs if p.get("signal") == "reject"]
        if not reject_rows:
            print(f"  FAIL — no reject row in anticipy_preferences (got {len(prefs)} rows total).")
            failed = True
        else:
            r0 = reject_rows[0]
            print(f"  OK — reject row written. action={r0.get('action_type')!r} reasoning={r0.get('reasoning')!r}")

        # ── 3. Confirm endpoint: accept path records an 'accept' preference ──
        print("\n[3/5] Confirm 'yes' path → record accept preference…", flush=True)
        accept_intent_id = await insert_intent(
            sid,
            "remind_followup_email",
            "Remind you to email the proposal to Joe.",
            "Remind me to email the proposal to Joe later.",
            status="pending",
        )
        status_code = await call_confirm(accept_intent_id, "yes")
        print(f"  /api/engine/confirm returned {status_code}.")
        await asyncio.sleep(6)
        prefs = await fetch_preferences(user_id)
        accept_rows = [p for p in prefs if p.get("signal") == "accept"]
        if not accept_rows:
            print(f"  FAIL — no accept row.")
            failed = True
        else:
            a0 = accept_rows[0]
            print(f"  OK — accept row written. action={a0.get('action_type')!r} reasoning={a0.get('reasoning')!r}")

        # ── 4. /api/engine/auto-proceed flips awaiting_user → auto_proceeded ──
        print("\n[4/5] auto-proceed endpoint flips awaiting_user → auto_proceeded…", flush=True)
        sc, body = await call_auto_proceed(awaiting_id, jwt)
        print(f"  /api/engine/auto-proceed returned {sc}: {body}")
        await asyncio.sleep(4)
        row = await fetch_intent(awaiting_id)
        if not row or row.get("status") != "auto_proceeded":
            print(f"  FAIL — intent status is {row.get('status') if row else None}, expected auto_proceeded.")
            failed = True
        else:
            print(f"  OK — status={row.get('status')}.")
        prefs = await fetch_preferences(user_id)
        auto_rows = [p for p in prefs if p.get("signal") == "auto_proceed"]
        if not auto_rows:
            print(f"  FAIL — no auto_proceed row.")
            failed = True
        else:
            print(f"  OK — auto_proceed row written. reasoning={auto_rows[0].get('reasoning')!r}")

        # ── 5. recall + buildIntentPrompt embed the reasoning lines ──
        print("\n[5/5] recallUserPreferences + buildIntentPrompt…", flush=True)
        out = run_node_recall_and_prompt(user_id)
        if "error" in out:
            print(f"  FAIL — tsx probe error: {out}")
            failed = True
        else:
            print(f"  preferenceContext ({len(out.get('preferenceContext', []))} lines):")
            for line in out.get("preferenceContext", [])[:6]:
                print(f"    - {line}")
            if not out.get("preferenceContext"):
                print("  FAIL — preferenceContext empty after writes.")
                failed = True
            elif not out.get("promptContainsHeader"):
                print("  FAIL — prompt missing 'Personal preferences' header.")
                failed = True
            elif not out.get("promptContainsAtLeastOneItem"):
                print("  FAIL — prompt has header but doesn't embed any reasoning line.")
                failed = True
            else:
                print("  OK — header present and at least one reasoning line embedded.")

        print("\n" + ("FAILED" if failed else "PASSED"))
        return 1 if failed else 0
    finally:
        await cleanup(user_id, session_ids)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
