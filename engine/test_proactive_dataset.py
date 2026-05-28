"""
Score the production /api/engine/analyze pipeline against the
50-scenario dataset at /workspaces/Anticipy/engine/data/proactive_e2e.jsonl.

For every scenario we:
  1. POST the transcript to https://www.anticipy.ai/api/engine/analyze with a
     test-domain Supabase JWT (so the analyze route's email-skip kicks in
     and admin gets no inbox spam).
  2. Read back the rows that landed in anticipy_intents.
  3. Hand transcript + ground truth + extracted intents to a Gemini judge,
     which returns matched/missed/false-positive/spurious counts.
  4. Score precision/recall and pass/fail (recall == 1, fp == 0, spurious == 0).

This is the voice→intent half ONLY (no extension drive-through). The action
half lives in test_e2e_voice_action.py and runs against a smaller, generated
slice. Splitting concerns keeps this file fast enough for nightly CI.

Run:
    python /workspaces/Anticipy/engine/test_proactive_dataset.py             # all 50
    python /workspaces/Anticipy/engine/test_proactive_dataset.py 10          # first 10
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env.local"
DATASET = Path(__file__).resolve().parent / "data" / "proactive_e2e.jsonl"

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
GEMINI_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

HDR = {
    "apikey": SUPABASE_SERVICE,
    "Authorization": f"Bearer {SUPABASE_SERVICE}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ---------------------------------------------------------------------------
# Auth (mirrors test_e2e_voice_action.py — same flow as the /engine page)
# ---------------------------------------------------------------------------


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


async def insert_session(session_id: str, user_email: str, user_id: str | None) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        body = {
            "id": session_id,
            "status": "recording",
            "user_email": user_email,
            "metadata": {"e2e_test": True, "dataset": "proactive_e2e"},
        }
        if user_id:
            body["user_id"] = user_id
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions",
            headers=HDR,
            json=body,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"session insert {r.status_code}: {r.text[:200]}")


async def cleanup_session(session_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as c:
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents?session_id=eq.{session_id}",
            headers=HDR,
        )
        await c.delete(
            f"{SUPABASE_URL}/rest/v1/anticipy_sessions?id=eq.{session_id}",
            headers=HDR,
        )


# ---------------------------------------------------------------------------
# /api/engine/analyze + intent fetch
# ---------------------------------------------------------------------------


async def call_analyze(transcript_lines: list[str], session_id: str, jwt: str) -> dict:
    payload = {
        "sessionId": session_id,
        "transcript": "\n".join(transcript_lines),
        "isFinal": True,
    }
    async with httpx.AsyncClient(timeout=240) as c:
        r = await c.post(
            f"{ANTICIPY_BASE}/api/engine/analyze",
            headers={"Authorization": f"Bearer {jwt}"},
            json=payload,
        )
        if r.status_code != 200:
            return {"error": f"analyze {r.status_code}: {r.text[:300]}"}
        return r.json()


async def get_session_intents(session_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/anticipy_intents"
            f"?session_id=eq.{session_id}&select=*&order=created_at",
            headers=HDR,
        )
        if r.status_code != 200:
            return []
        return r.json()


# ---------------------------------------------------------------------------
# LLM judge (matched / missed / false_positive / spurious)
# ---------------------------------------------------------------------------


JUDGE_SYSTEM = """You judge whether a proactive intent-extraction system did the right thing.

You see:
- The conversation transcript
- The list of EXPECTED intents (ground truth — the system SHOULD have extracted these)
- The list of NOISE items (the system should NOT have extracted these)
- The list of EXTRACTED intents (what the system actually produced)

For EACH expected intent, decide if it has a clear match in extracted (ignoring phrasing differences).
For EACH noise item, decide if extracted contains anything that corresponds (i.e. a false positive).
For EACH extracted intent that doesn't correspond to any expected OR noise item, count it as 'spurious'.

Return JSON:
{
  "matched_expected": <int>,
  "missed_expected": <int>,
  "false_positives_on_noise": <int>,
  "spurious_extra": <int>,
  "details": [
    {"kind": "matched", "expected": "<>", "extracted": "<>"},
    {"kind": "missed", "expected": "<>"},
    {"kind": "false_positive", "noise": "<>", "extracted": "<>"},
    {"kind": "spurious", "extracted": "<>"}
  ]
}

Rules:
- Match by INTENT, not exact wording. "email Sarah about Friday" matches "Send email to Sarah re: Friday meeting".
- A retracted item that was extracted (e.g. agent extracted 'cancel picnic if rains' even though the user retracted it) IS a false positive on noise.
- Quantity matters: if expected has 3 items and extracted has 1, that's 1 matched + 2 missed.
- Delegations to other people that the system extracted as wearer-actions are false positives on noise.
"""


async def judge_extraction(
    transcript: list[str],
    expected: list[str],
    noise: list[str],
    extracted: list[str],
) -> dict:
    payload = {
        "transcript": "\n".join(transcript),
        "expected_intents": expected,
        "noise_should_NOT_act_on": noise,
        "extracted_intents": extracted,
    }
    body = {
        "system_instruction": {"parts": [{"text": JUDGE_SYSTEM}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(payload, indent=2)}]}
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    last_err: str | None = None
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
                if r.status_code != 200:
                    last_err = f"judge {r.status_code}: {r.text[:200]}"
                    await asyncio.sleep(2)
                    continue
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                t = txt.strip()
                if t.startswith("```"):
                    t = t.split("\n", 1)[1] if "\n" in t else t
                    if t.endswith("```"):
                        t = t.rsplit("```", 1)[0]
                try:
                    return json.loads(t)
                except json.JSONDecodeError:
                    s, e = txt.find("{"), txt.rfind("}")
                    if s >= 0 and e > s:
                        return json.loads(txt[s : e + 1])
                    raise
        except Exception as e:
            last_err = f"judge: {type(e).__name__}: {e}"
            await asyncio.sleep(2)
    return {"error": last_err or "judge exhausted"}


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------


def score_scenario(scenario: dict, judgment: dict) -> dict:
    expected_n = len(scenario["expected_intents"])
    noise_n = len(scenario["noise_should_NOT_act_on"])
    matched = judgment.get("matched_expected", 0)
    missed = judgment.get("missed_expected", 0)
    fp = judgment.get("false_positives_on_noise", 0)
    spurious = judgment.get("spurious_extra", 0)

    pp = matched + fp + spurious
    precision = (matched / pp) if pp else (1.0 if expected_n == 0 else 0.0)
    recall = (matched / expected_n) if expected_n else (1.0 if (fp + spurious) == 0 else 0.0)
    passed = (missed == 0) and (fp == 0) and (spurious == 0)

    return {
        "name": scenario["name"],
        "difficulty": scenario.get("difficulty", "?"),
        "pattern_id": scenario.get("pattern_id", "?"),
        "expected_n": expected_n,
        "noise_n": noise_n,
        "matched": matched,
        "missed": missed,
        "false_positives_on_noise": fp,
        "spurious_extra": spurious,
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "passed": passed,
    }


# ---------------------------------------------------------------------------
# Per-scenario runner
# ---------------------------------------------------------------------------


async def run_scenario(
    scenario: dict, user_email: str, user_id: str | None, jwt: str
) -> dict:
    session_id = str(uuid.uuid4())
    name = scenario["name"]
    print(f"\n=== {name} (d={scenario.get('difficulty', '?')}) ===", flush=True)
    print(
        f"  session={session_id[:8]} "
        f"lines={len(scenario['transcript'])} "
        f"exp={len(scenario['expected_intents'])} "
        f"noise={len(scenario['noise_should_NOT_act_on'])}",
        flush=True,
    )

    try:
        await insert_session(session_id, user_email, user_id)
    except Exception as e:
        return {"scenario": scenario, "error": f"session-insert: {e}", "passed": False}

    try:
        t0 = time.time()
        analyze_resp = await call_analyze(scenario["transcript"], session_id, jwt)
        dt = time.time() - t0
        if "error" in analyze_resp:
            print(f"  [analyze ERROR] {analyze_resp['error']}", flush=True)
            return {"scenario": scenario, "error": analyze_resp["error"], "passed": False}

        await asyncio.sleep(2)  # let the INSERT land
        intents = await get_session_intents(session_id)
        extracted = [i.get("summary_for_user") or "" for i in intents]
        print(f"  analyze: {dt:.1f}s, {len(extracted)} intents", flush=True)
        for s in extracted:
            print(f"    · {s[:140]}", flush=True)

        judgment = await judge_extraction(
            scenario["transcript"],
            scenario["expected_intents"],
            scenario["noise_should_NOT_act_on"],
            extracted,
        )
        if "error" in judgment:
            print(f"  [judge ERROR] {judgment['error']}", flush=True)
            return {"scenario": scenario, "error": judgment["error"], "passed": False}

        score = score_scenario(scenario, judgment)
        tag = "PASS" if score["passed"] else "FAIL"
        print(
            f"  {tag}: matched={score['matched']}/{score['expected_n']} "
            f"missed={score['missed']} fp={score['false_positives_on_noise']} "
            f"spurious={score['spurious_extra']} "
            f"(p={score['precision']} r={score['recall']})",
            flush=True,
        )
        if not score["passed"]:
            for d in (judgment.get("details") or [])[:6]:
                print(f"    {d}", flush=True)

        return {
            "scenario": scenario,
            "session_id": session_id,
            "extracted": extracted,
            "judgment": judgment,
            "score": score,
            "passed": score["passed"],
            "elapsed_s": round(dt, 2),
        }
    finally:
        try:
            await cleanup_session(session_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_dataset(limit: int | None = None) -> list[dict]:
    scenarios: list[dict] = []
    with DATASET.open() as f:
        for line in f:
            line = line.strip()
            if line:
                scenarios.append(json.loads(line))
    if limit is not None:
        scenarios = scenarios[:limit]
    return scenarios


async def main(limit: int | None = None, concurrency: int = 4) -> int:
    scenarios = load_dataset(limit=limit)
    if not scenarios:
        print(f"FAIL: no scenarios in {DATASET}", flush=True)
        return 1

    user_email = f"e2e-test-{uuid.uuid4().hex[:8]}@anticipy-test.local"
    user_pw = f"E2eTest!{uuid.uuid4().hex[:12]}"
    print(f"Dataset test — {len(scenarios)} scenarios from {DATASET}")
    print(f"  user_email={user_email}")
    print(f"  target={ANTICIPY_BASE}/api/engine/analyze")
    print(f"  concurrency={concurrency}")

    print("\nProvisioning Supabase Auth user…", flush=True)
    try:
        jwt = await get_or_create_test_user_jwt(user_email, user_pw)
    except Exception as e:
        print(f"FAIL: auth provisioning: {e}")
        return 1
    user_id = await get_user_id_from_jwt(jwt)
    print(f"  jwt_len={len(jwt)} user_id={user_id}")

    sem = asyncio.Semaphore(concurrency)
    runs: list[dict] = []

    async def go(sc: dict) -> None:
        async with sem:
            try:
                r = await run_scenario(sc, user_email, user_id, jwt)
            except Exception as e:
                r = {"scenario": sc, "error": f"{type(e).__name__}: {e}", "passed": False}
            runs.append(r)

    await asyncio.gather(*[go(sc) for sc in scenarios])

    n = len(runs) or 1
    pass_n = sum(1 for r in runs if r.get("passed"))
    by_diff: Counter[str] = Counter()
    pass_diff: Counter[str] = Counter()
    by_pattern: Counter[str] = Counter()
    pass_pattern: Counter[str] = Counter()
    for r in runs:
        d = r["scenario"].get("difficulty", "?")
        p = r["scenario"].get("pattern_id", "?")
        by_diff[d] += 1
        by_pattern[p] += 1
        if r.get("passed"):
            pass_diff[d] += 1
            pass_pattern[p] += 1

    print("\n" + "=" * 70)
    print(f"DATASET RESULT: {pass_n}/{n} ({100 * pass_n / n:.0f}%)")
    print("=" * 70)
    for d in ("easy", "medium", "hard", "brutal"):
        if by_diff[d]:
            print(f"  difficulty={d:<7} pass={pass_diff[d]}/{by_diff[d]}")
    print()

    # Per-scenario one-liners, sorted worst-to-best (failed first, then by
    # most spurious + missed) so the operator sees the badness up front.
    def badness(r: dict) -> int:
        s = r.get("score") or {}
        return (
            (0 if r.get("passed") else 1) * 1000
            + s.get("missed", 0) * 10
            + s.get("false_positives_on_noise", 0) * 5
            + s.get("spurious_extra", 0) * 2
        )

    runs_sorted = sorted(runs, key=badness, reverse=True)
    for r in runs_sorted:
        s = r.get("score") or {}
        sc = r["scenario"]
        v = "PASS" if r.get("passed") else "FAIL"
        if r.get("error"):
            print(
                f"  {v} {sc['name']:<46} d={sc.get('difficulty', '?'):<6} "
                f"ERROR: {r['error'][:80]}"
            )
        else:
            print(
                f"  {v} {sc['name']:<46} d={sc.get('difficulty', '?'):<6} "
                f"m={s.get('matched', 0)}/{s.get('expected_n', 0)} "
                f"miss={s.get('missed', 0)} "
                f"fp={s.get('false_positives_on_noise', 0)} "
                f"sp={s.get('spurious_extra', 0)} "
                f"p={s.get('precision', 0)} r={s.get('recall', 0)}"
            )

    out = Path("/tmp/proactive_dataset_detail.json")
    out.write_text(
        json.dumps(
            [
                {
                    "name": r["scenario"]["name"],
                    "pattern_id": r["scenario"].get("pattern_id"),
                    "difficulty": r["scenario"].get("difficulty"),
                    "passed": r.get("passed", False),
                    "error": r.get("error"),
                    "extracted": r.get("extracted", []),
                    "expected": r["scenario"].get("expected_intents", []),
                    "noise": r["scenario"].get("noise_should_NOT_act_on", []),
                    "score": r.get("score", {}),
                    "judgment_details": (r.get("judgment") or {}).get("details", []),
                    "elapsed_s": r.get("elapsed_s"),
                }
                for r in runs
            ],
            indent=2,
        )
    )
    print(f"\nDetail: {out}")
    return 0 if pass_n == n else 1


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    raise SystemExit(asyncio.run(main(limit=limit)))
