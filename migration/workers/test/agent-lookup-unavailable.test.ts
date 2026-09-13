/**
 * test/agent-lookup-unavailable.test.ts — A LOOKUP THAT THREW IS NOT "NOT PAIRED".
 *
 *   node --experimental-strip-types migration/workers/test/agent-lookup-unavailable.test.ts
 *
 * Until 2026-09-12 routes/agent.ts paired() answered a THROWN D1 lookup as
 * `unpaired`, and /agent/key, /agent/llm and /agent/solve-captcha turned that
 * into the same 403 {"error":"not a paired agent"} a genuinely unpaired browser
 * gets. The shipped extension reads a 403 from /agent/llm as a credential
 * verdict: it wipes its key bundle and parks the errand needs_user "my model
 * key was rejected (403)" with no retry, while the heartbeat — a different path
 * whose own throw surfaces as a 5xx — keeps the phone reading "Chrome ready".
 * One transient D1 error mid-errand ended the errand and demanded a tap.
 *
 * Three legs per route: a throwing DB answers 503 and never 403; a healthy DB
 * with no matching row still answers 403 (the control — the floor still
 * refuses); and the 503 body carries no credential shape.
 */
import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { agentKey, agentLlm, agentCaptcha } from "../src/routes/agent.ts";

let passes = 0, failures = 0;
async function check(name: string, fn: () => Promise<void>) {
  try { await fn(); passes++; console.log("PASS " + name); }
  catch (err) { failures++; console.log("FAIL " + name + "\n     " + (err as Error).message); }
}

const ME = "agent-0123456789-abcdef-0123456789";
const TOKEN = "t".repeat(64);
const headers = { "X-Anticipy-Agent-ID": ME, "X-Anticipy-Agent-Token": TOKEN, "content-type": "application/json" };
const brokenDb = { prepare: () => ({ bind: () => ({
  first: async () => { throw new Error("D1_ERROR: Network connection lost."); },
  all: async () => { throw new Error("D1_ERROR: Network connection lost."); },
  run: async () => { throw new Error("D1_ERROR: Network connection lost."); },
}) }) } as unknown as D1Database;
const baseEnv = { GEMINI_API_KEY: "offline-fixture-only", ANTICIPY_SERVICE_TOKEN: "svc" };

const ROUTES: [string, (env: Record<string, unknown>) => Promise<Response>][] = [
  ["/agent/llm", (env) => agentLlm(new Request("https://api.anticipy.ai/agent/llm", { method: "POST", headers, body: "{}" }), env as never)],
  ["/agent/key", (env) => agentKey(new Request(`https://api.anticipy.ai/agent/key?agent_id=${ME}`, { headers }), env as never)],
  ["/agent/solve-captcha", (env) => agentCaptcha(new Request("https://api.anticipy.ai/agent/solve-captcha", { method: "POST", headers, body: "{}" }), env as never)],
];

for (const [path, call] of ROUTES) {
  await check(`${path}: a THROWN lookup is 503, never the 403 an unpaired browser gets`, async () => {
    const res = await call({ ...baseEnv, DB: brokenDb });
    const body = await res.json() as { error?: string };
    assert.equal(res.status, 503, `answered ${res.status} ${JSON.stringify(body)}`);
    assert.notEqual(body.error, "not a paired agent");
    const text = JSON.stringify(body).toLowerCase();
    for (const smell of ["api_key", "apikey", "service_token", "agent_token", "offline-fixture-only", "svc"]) {
      assert.equal(text.includes(smell), false, "the 503 body must carry no credential shape; found " + smell);
    }
  });
  await check(`${path}: CONTROL — a healthy database with no matching row is still 403`, async () => {
    const db = new FakeD1();
    const res = await call({ ...baseEnv, DB: asD1(db) });
    assert.equal(res.status, 403);
    assert.deepEqual(await res.json(), { error: "not a paired agent" });
    db.db.close();
  });
}

console.log(`\nagent-lookup-unavailable: ${passes} passed, ${failures} failed`);
if (failures > 0) process.exit(1);
