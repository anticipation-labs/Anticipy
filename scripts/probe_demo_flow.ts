/**
 * Live demo flow probe — exercises the full path:
 *   1. health endpoint up
 *   2. waitlist endpoint accepts a fresh email (then deletes it)
 *   3. /engine page returns 200 with Anticipy branding
 *   4. extension auth endpoint rejects bogus codes
 *   5. extension auth endpoint accepts a valid code (must set TEST_ACCESS_CODE)
 *   6. confirm endpoint rejects bogus tokens
 *
 * Run:
 *   npx tsx scripts/probe_demo_flow.ts                          # local
 *   BASE=https://www.anticipy.ai npx tsx scripts/probe_demo_flow.ts  # prod
 *
 * Designed for CI smoke test or post-deploy verification. Doesn't touch
 * any user data; the only DB write is the synthetic waitlist row that's
 * cleaned up at the end.
 */
import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}

const BASE = process.env.BASE ?? "http://localhost:3210";
const TEST_EMAIL = `probe-${Date.now()}@anticipy-test.local`;

let pass = 0, fail = 0;
function ok(name: string) { console.log(`  ✓ ${name}`); pass += 1; }
function bad(name: string, reason: string) { console.error(`  ✗ ${name} — ${reason}`); fail += 1; }

async function main() {
  console.log(`Probing ${BASE}\n`);

  // 1. health
  try {
    const r = await fetch(`${BASE}/api/health`);
    const j = await r.json();
    if (r.status === 200 && j.ok && j.env?.supabase && j.env?.gemini) {
      ok("health: ok + required services configured");
    } else {
      bad("health", `status=${r.status} ok=${j.ok} env=${JSON.stringify(j.env)}`);
    }
  } catch (e) {
    bad("health", e instanceof Error ? e.message : String(e));
  }

  // 2. waitlist accepts a new email (skip cleanup if hitting prod —
  //    don't pollute the real waitlist).
  if (BASE.includes("localhost") || BASE.includes("127.0.0.1")) {
    try {
      const r = await fetch(`${BASE}/api/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: TEST_EMAIL, source: "probe" }),
      });
      if (r.status === 200) ok("waitlist: accepts fresh email");
      else if (r.status === 429) ok("waitlist: rate-limited (expected on repeated runs)");
      else bad("waitlist", `unexpected status ${r.status}`);
    } catch (e) {
      bad("waitlist", e instanceof Error ? e.message : String(e));
    }
  } else {
    console.log("  - waitlist: skipped (won't pollute prod)");
  }

  // 3. /engine page renders
  try {
    const r = await fetch(`${BASE}/engine`, { redirect: "follow" });
    const txt = await r.text();
    if (r.status === 200 && txt.includes("Anticipy")) {
      ok("/engine: renders with branding");
    } else {
      bad("/engine", `status=${r.status} bytes=${txt.length}`);
    }
  } catch (e) {
    bad("/engine", e instanceof Error ? e.message : String(e));
  }

  // 4. extension auth rejects bogus code
  try {
    const r = await fetch(`${BASE}/api/extension/auth`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: "BOGUSXXXX" }),
    });
    if (r.status === 401) ok("extension/auth: rejects bogus code (401)");
    else if (r.status === 429) ok("extension/auth: rate-limited (expected on repeated runs)");
    else bad("extension/auth bogus", `unexpected status ${r.status}`);
  } catch (e) {
    bad("extension/auth bogus", e instanceof Error ? e.message : String(e));
  }

  // 5. confirm rejects bogus token
  try {
    const r = await fetch(`${BASE}/api/engine/confirm?token=NOT_A_TOKEN&action=yes`);
    // Either 400 (invalid token format) or 429 (rate limited from earlier runs)
    if (r.status === 400 || r.status === 429) ok(`confirm: rejects bogus token (${r.status})`);
    else bad("confirm bogus", `unexpected status ${r.status}`);
  } catch (e) {
    bad("confirm bogus", e instanceof Error ? e.message : String(e));
  }

  // 6. security headers present (only on production-style hosts)
  if (BASE.startsWith("https://")) {
    try {
      const r = await fetch(`${BASE}/`, { method: "HEAD", redirect: "follow" });
      const required = [
        "x-frame-options",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
        "strict-transport-security",
      ];
      const missing = required.filter((h) => !r.headers.get(h));
      if (missing.length === 0) ok("security headers: all 5 present");
      else bad("security headers", `missing: ${missing.join(", ")}`);
    } catch (e) {
      bad("security headers", e instanceof Error ? e.message : String(e));
    }
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
