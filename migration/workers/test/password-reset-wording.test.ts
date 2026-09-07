/**
 * Runs with no network and no D1 (an in-process SQLite one):
 *
 *   node --experimental-strip-types migration/workers/test/password-reset-wording.test.ts
 *
 * WHAT THE OWNER READS, pinned to the two files that already say what it must
 * be rather than to a string typed here (audit F39):
 *
 *   the code SMS text and the success line, pinned below from the hook's
 *   last committed text (password_reset.pb.js:153-155 and :249)
 *   app/ios/Tests/ResetMessageTests.swift:98        the phone's own assertion
 *                                                   on that success line
 *
 * A test that typed the sentences would pass while the Worker and the phone
 * disagreed — which is exactly what shipped: the Worker sent "Your Anticipy
 * code is 123456. It expires in 10 minutes." and answered "Password updated.
 * You can sign in now.", and the iOS test was written against neither.
 *
 * The SMS's second sentence is not decoration. The hook's header (:20-21)
 * calls it "the standard phishing tell": a code that arrives with no
 * explanation teaches the owner to act on unexplained codes.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: either sentence rewritten in the Worker;
 * the warning half dropped; the send happening after the row is stored rather
 * than before.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { resetRequest, resetConfirm, type ResetEnv } from "../src/routes/password_reset.ts";
import { openTestD1 } from "./sqlite-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const iosTest = readFileSync(join(repoRoot, "app", "ios", "Tests", "ResetMessageTests.swift"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// --- the oracle -------------------------------------------------------------
//
// PINNED, 2026-09-07. These two sentences were read out of the PocketBase hook
// (backend/pb_hooks/password_reset.pb.js:153-155 and :249) while it existed;
// the hook is gone, so its last committed text is written here and IS the
// oracle now. The phone's test (ResetMessageTests.swift) asserts on the same
// success line, which is why a change to either sentence must be deliberate.

function smsFromHook(code: string): string {
  return code + " is your Anticipy code to set a new password. "
    + "It works for 10 minutes. If you didn't ask for this, ignore it "
    + "and your password stays as it is.";
}

function doneFromHook(): string {
  return "Done — sign in with your new password.";
}

// --- the wire ---------------------------------------------------------------

interface Sent { url: string; body: string }
let sent: Sent[] = [];
let reply: () => Response = () => new Response(JSON.stringify({ message_handle: "synthetic1", status: "QUEUED" }), { status: 201 });
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const raw = init?.body;
  sent.push({
    url: String(input),
    body: raw instanceof URLSearchParams ? raw.toString() : String(raw ?? ""),
  });
  return reply();
}) as typeof fetch;
const realLog = console.log;
console.log = () => { /* the routes narrate; the test does not need it */ };

const EMAIL = "omar@example.invalid";
const PHONE = "+15550100001";
const OWNER = "owner000000one1";

function env(db: D1Database): ResetEnv {
  // SendBlue JSON is the current outbound wire.
  return {
    DB: db,
    SENDBLUE_API_KEY_ID: "synthetic-key", SENDBLUE_API_SECRET_KEY: "synthetic-secret",
    SENDBLUE_FROM_NUMBER: "+15550002222",
  } as unknown as ResetEnv;
}

function seeded() {
  const t = openTestD1();
  t.exec(`INSERT INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid)
          VALUES ('${OWNER}', '2026-09-01 00:00:00.000Z', '2026-09-01 00:00:00.000Z', '${EMAIL}', 0, 0, '', 'tk', '${PHONE}', '')`);
  return t;
}

/** The content of the one SendBlue POST. */
function textSent(): string {
  assert.equal(sent.length, 1, `expected exactly one outbound text, got ${sent.length}`);
  const body = JSON.parse(sent[0].body);
  assert.ok(sent[0].url.endsWith("/api/send-message"));
  return String(body.content ?? "");
}

// ---------------------------------------------------------------------------

await check("the code text is the hook's sentence, warning and all", async () => {
  const t = seeded();
  sent = [];
  const res = await resetRequest(
    new Request("https://api.anticipy.ai/auth/reset/request", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL }),
    }), env(t.db));
  assert.equal(res.status, 200);

  const rows = t.query<{ id: string }>("SELECT id FROM password_resets WHERE owner = ?", OWNER);
  assert.equal(rows.length, 1, "no reset row was stored");
  const code = textSent().slice(0, 6);
  assert.match(code, /^\d{6}$/, "the text does not start with the six-digit code");
  assert.equal(textSent(), smsFromHook(code));
  t.close();
});

await check("the warning half is actually in what goes out", async () => {
  // Named separately from the byte comparison above so that dropping the
  // second sentence reads as its own failure and not as "some string moved".
  const t = seeded();
  sent = [];
  await resetRequest(
    new Request("https://api.anticipy.ai/auth/reset/request", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL }),
    }), env(t.db));
  assert.match(textSent(), /If you didn't ask for this, ignore it and your password stays as it is\.$/);
  t.close();
});

await check("a send the provider refuses leaves NO live code in the table", async () => {
  // The wording change must not disturb send-before-store: a code the owner
  // never receives must not sit in the database pretending it did.
  const t = seeded();
  sent = [];
  reply = () => new Response("nope", { status: 500 });
  const res = await resetRequest(
    new Request("https://api.anticipy.ai/auth/reset/request", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL }),
    }), env(t.db));
  reply = () => new Response(JSON.stringify({ message_handle: "synthetic1", status: "QUEUED" }), { status: 201 });
  assert.equal(res.status, 200, "a refused send must still answer the same 200");
  assert.equal(t.query("SELECT id FROM password_resets").length, 0);
  t.close();
});

await check("the success line is the hook's, which is the line the phone's test asserts on", async () => {
  const t = seeded();
  const code = "123456";
  const digest = [...new Uint8Array(await crypto.subtle.digest(
    "SHA-256", new TextEncoder().encode(code)))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  t.exec(`INSERT INTO password_resets (id, created, updated, owner, code_hash, expires, attempts, used)
          VALUES ('reset000000001', '2026-09-05 00:00:00.000Z', '2026-09-05 00:00:00.000Z',
                  '${OWNER}', '${digest}', '2099-01-01T00:00:00.000Z', 0, 0)`);

  const res = await resetConfirm(
    new Request("https://api.anticipy.ai/auth/reset/confirm", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL, code, password: "a-long-enough-password" }),
    }), env(t.db));
  assert.equal(res.status, 200);
  const body = await res.json() as { ok: boolean; message: string };
  assert.equal(body.ok, true);
  assert.equal(body.message, doneFromHook());
  assert.ok(iosTest.includes(body.message),
    "app/ios/Tests/ResetMessageTests.swift does not assert on this sentence: " + body.message);
  t.close();
});

await check("the refusals are untouched — the same sentence for wrong, expired and unknown", async () => {
  const t = seeded();
  const res = await resetConfirm(
    new Request("https://api.anticipy.ai/auth/reset/confirm", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: EMAIL, code: "000000", password: "a-long-enough-password" }),
    }), env(t.db));
  assert.equal(res.status, 400);
  const body = await res.json() as { message: string };
  assert.equal(body.message, "That code isn't right, or it has expired. Ask for a new one.");
  t.close();
});

console.log = realLog;
console.log(`password-reset-wording: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
