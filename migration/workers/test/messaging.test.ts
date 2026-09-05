/**
 * Runs with no dependencies, no network and no D1:
 *
 *   node --experimental-strip-types migration/workers/test/messaging.test.ts
 *
 * Drives the REAL sendText in src/messaging.ts against a stubbed global fetch
 * and a captured console, and pins:
 *   - which provider is chosen for which environment, and that the owner's
 *     ANTICIPY_SMS_PROVIDER wins over what happens to be configured;
 *   - the exact Sendblue request (URL, both key headers, from_number/number/
 *     content) and the exact Twilio request the two call sites used to build
 *     (URL, Basic auth, form body To/From/Body);
 *   - what "sent" means: QUEUED/SENT are ok with the message_handle; a 2xx
 *     carrying ERROR or DECLINED or an error_code is NOT; a 401 is not; an
 *     unreadable 2xx is not; a thrown fetch is a result, never an exception;
 *   - that no key, token or message body ever reaches a log line, and that
 *     the line carries the provider and the last four digits only;
 *   - that SENDBLUE_API_BASE / TWILIO_API_BASE move the host for loopback only.
 *
 * Mutations this must catch (run by hand, see the commit that added it):
 *   (a) ERROR read as ok           → "2xx + ERROR" case red
 *   (b) provider default flipped   → "both configured → sendblue" case red
 *   (c) a secret in a log line     → "no secret in any log line" case red
 */
import assert from "node:assert/strict";
import {
  sendText, chooseProvider, apiBase, last4,
  SENDBLUE_BASE, TWILIO_BASE, SEND_TIMEOUT_MS,
  type MessagingEnv, type SendResult,
} from "../src/messaging.ts";

// Distinctive so a leak is unmistakable, and so `includes` cannot false-match.
const SB_KEY_ID = "sbkid-LEAK-9f3a1c";
const SB_SECRET = "sbsecret-LEAK-7b2e4d";
const SB_FROM = "+15550001111";
const TW_SID = "ACtwilio-LEAK-5c1d";
const TW_TOKEN = "twtoken-LEAK-2e8f0a";
const TW_KEY_SID = "SKtwkey-LEAK-4a9b";
const TW_KEY_SECRET = "twkeysecret-LEAK-1d6c";
const TW_FROM = "+15550002222";
const TO = "+15557654321";
const BODY = "Your Anticipy code is 483920. It expires in 10 minutes.";

const SENDBLUE: MessagingEnv = {
  SENDBLUE_API_KEY_ID: SB_KEY_ID, SENDBLUE_API_SECRET_KEY: SB_SECRET, SENDBLUE_FROM_NUMBER: SB_FROM,
};
const TWILIO: MessagingEnv = {
  TWILIO_ACCOUNT_SID: TW_SID, TWILIO_AUTH_TOKEN: TW_TOKEN, TWILIO_PHONE_NUMBER: TW_FROM,
};

// --- harness ----------------------------------------------------------------
interface Captured { url: string; method: string; headers: Record<string, string>; body: string; signal: unknown }
let calls: Captured[] = [];
let reply: () => Response = () => new Response("{}", { status: 200 });
const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const headers: Record<string, string> = {};
  new Headers(init?.headers).forEach((v, k) => { headers[k.toLowerCase()] = v; });
  const raw = init?.body;
  const body = raw instanceof URLSearchParams ? raw.toString() : String(raw ?? "");
  calls.push({ url: String(input), method: String(init?.method ?? "GET"), headers, body, signal: init?.signal });
  return reply();
}) as typeof fetch;

const logs: string[] = [];
const realLog = console.log;
console.log = (...args: unknown[]) => { logs.push(args.map(String).join(" ")); };

const json = (status: number, v: unknown) =>
  new Response(JSON.stringify(v), { status, headers: { "content-type": "application/json" } });

function reset(): void { calls = []; logs.length = 0; }

let failures = 0;
function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  reset();
  return Promise.resolve().then(fn).catch((err) => {
    failures++;
    console.error("FAIL " + what + "\n     " + (err as Error).message);
  });
}

// --- choice ------------------------------------------------------------------
await check("Sendblue is chosen when its three names are bound", () => {
  assert.equal(chooseProvider(SENDBLUE), "sendblue");
});

await check("both configured → Sendblue (the default points at the new provider)", () => {
  assert.equal(chooseProvider({ ...TWILIO, ...SENDBLUE }), "sendblue");
});

await check("Twilio is chosen when only TWILIO_* is bound", () => {
  assert.equal(chooseProvider(TWILIO), "twilio");
  assert.equal(chooseProvider({ TWILIO_ACCOUNT_SID: TW_SID, TWILIO_AUTH_TOKEN: TW_TOKEN, TWILIO_FROM: TW_FROM }),
    "twilio", "TWILIO_FROM is the second name for the sender");
  assert.equal(chooseProvider({ TWILIO_ACCOUNT_SID: TW_SID, TWILIO_PHONE_NUMBER: TW_FROM,
    TWILIO_API_KEY_SID: TW_KEY_SID, TWILIO_API_KEY_SECRET: TW_KEY_SECRET }),
    "twilio", "an API key pair is a credential on its own");
});

await check("two of three Sendblue names is not Sendblue", () => {
  assert.equal(chooseProvider({ SENDBLUE_API_KEY_ID: SB_KEY_ID, SENDBLUE_API_SECRET_KEY: SB_SECRET }), "none");
  assert.equal(chooseProvider({ ...TWILIO, SENDBLUE_API_KEY_ID: SB_KEY_ID, SENDBLUE_FROM_NUMBER: SB_FROM }), "twilio");
});

await check("neither configured → none, and sendText says so without calling anyone", async () => {
  assert.equal(chooseProvider({}), "none");
  const r = await sendText({}, TO, BODY);
  assert.deepEqual(r, { ok: false, provider: "none", status: 0, error: "no messaging provider configured" });
  assert.equal(calls.length, 0);
});

await check("ANTICIPY_SMS_PROVIDER is the owner's word and beats configuration both ways", async () => {
  assert.equal(chooseProvider({ ...TWILIO, ...SENDBLUE, ANTICIPY_SMS_PROVIDER: "twilio" }), "twilio");
  assert.equal(chooseProvider({ ...TWILIO, ...SENDBLUE, ANTICIPY_SMS_PROVIDER: "Sendblue " }), "sendblue");
  // Said sendblue, keys absent: a FAILED send, never a fall-through to Twilio.
  const r = await sendText({ ...TWILIO, ANTICIPY_SMS_PROVIDER: "sendblue" }, TO, BODY);
  assert.equal(r.ok, false);
  assert.equal(r.provider, "sendblue");
  assert.equal(calls.length, 0, "Twilio must not have been asked");
  // And the mirror: said twilio, Twilio absent — a failed send, not Sendblue.
  const t = await sendText({ ...SENDBLUE, ANTICIPY_SMS_PROVIDER: "twilio" }, TO, BODY);
  assert.deepEqual(t, { ok: false, provider: "twilio", status: 0, error: "twilio is not configured" });
  assert.equal(calls.length, 0, "Sendblue must not have been asked");
});

await check("an unrecognised ANTICIPY_SMS_PROVIDER falls back to configuration", () => {
  assert.equal(chooseProvider({ ...SENDBLUE, ANTICIPY_SMS_PROVIDER: "pigeon" }), "sendblue");
  assert.equal(chooseProvider({ ...TWILIO, ANTICIPY_SMS_PROVIDER: "pigeon" }), "twilio");
});

// --- the Sendblue wire ------------------------------------------------------
await check("the Sendblue request is exact: URL, both key headers, JSON from_number/number/content", async () => {
  reply = () => json(202, { message_handle: "mh_123", status: "QUEUED", error_code: null, error_message: null });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.equal(calls.length, 1);
  const c = calls[0];
  assert.equal(c.url, SENDBLUE_BASE + "/api/send-message");
  assert.equal(c.url, "https://api.sendblue.com/api/send-message");
  assert.equal(c.method, "POST");
  assert.equal(c.headers["sb-api-key-id"], SB_KEY_ID);
  assert.equal(c.headers["sb-api-secret-key"], SB_SECRET);
  assert.equal(c.headers["content-type"], "application/json");
  assert.equal(c.headers["authorization"], undefined, "no Basic auth on Sendblue");
  assert.deepEqual(JSON.parse(c.body), { from_number: SB_FROM, number: TO, content: BODY });
  assert.ok(c.signal instanceof AbortSignal, "AbortSignal.timeout must be supplied");
  assert.deepEqual(r, { ok: true, provider: "sendblue", id: "mh_123", status: "QUEUED" });
});

await check("status_callback rides along only when asked for", async () => {
  reply = () => json(200, { message_handle: "mh_2", status: "SENT" });
  await sendText(SENDBLUE, TO, BODY, { statusCallback: "https://api.anticipy.ai/sms/sendblue" });
  assert.deepEqual(JSON.parse(calls[0].body),
    { from_number: SB_FROM, number: TO, content: BODY, status_callback: "https://api.anticipy.ai/sms/sendblue" });
});

await check("QUEUED, SENT, ACCEPTED and PENDING are sends", async () => {
  for (const status of ["QUEUED", "SENT", "ACCEPTED", "PENDING", "queued"]) {
    reply = () => json(200, { message_handle: "mh_" + status, status });
    const r = await sendText(SENDBLUE, TO, BODY);
    assert.equal(r.ok, true, status);
    assert.equal((r as { id: string }).id, "mh_" + status);
  }
});

await check("2xx + ERROR is a failed send, on the status alone", async () => {
  // No error_code here on purpose: the status must be enough by itself, or
  // dropping ERROR from the failed set would pass on the code check instead.
  reply = () => json(200, { message_handle: "mh_e", status: "ERROR", error_code: null, error_message: null });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.equal(r.ok, false);
  assert.equal(r.provider, "sendblue");
  assert.equal((r as { status: number }).status, 200);
  assert.equal((r as { error: string }).error, "status ERROR");
  reply = () => json(200, { message_handle: "mh_e2", status: "ERROR", error_code: 4004, error_message: "number invalid" });
  const both = await sendText(SENDBLUE, TO, BODY);
  assert.equal(both.ok, false);
  assert.equal((both as { error: string }).error, "4004 number invalid", "the provider's words ride in the result");
});

await check("2xx + DECLINED is a failed send", async () => {
  reply = () => json(200, { message_handle: "mh_d", status: "DECLINED" });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.equal(r.ok, false);
});

await check("2xx + an error_code with a friendly status is still a failed send", async () => {
  reply = () => json(200, { message_handle: "mh_x", status: "QUEUED", error_code: "4001" });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.equal(r.ok, false);
  // 0 / null / "" are the no-error shapes, not codes.
  for (const code of [0, null, ""]) {
    reply = () => json(200, { message_handle: "mh_ok", status: "QUEUED", error_code: code });
    assert.equal((await sendText(SENDBLUE, TO, BODY)).ok, true, "error_code " + JSON.stringify(code));
  }
});

await check("401 is a failed send with the HTTP status", async () => {
  reply = () => json(401, { error_code: 4010, error_message: "invalid credentials" });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.deepEqual(r, { ok: false, provider: "sendblue", status: 401, error: "4010 invalid credentials" });
});

await check("a 2xx the Worker cannot read is not a success", async () => {
  reply = () => new Response("<html>", { status: 200 });
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.deepEqual(r, { ok: false, provider: "sendblue", status: 200, error: "unreadable response" });
});

await check("a thrown fetch (timeout, refused) is a result, never an exception", async () => {
  reply = () => { const e = new Error("The operation was aborted"); e.name = "TimeoutError"; throw e; };
  const r = await sendText(SENDBLUE, TO, BODY);
  assert.deepEqual(r, { ok: false, provider: "sendblue", status: 0, error: "TimeoutError" });
  reply = () => { throw new TypeError("fetch failed"); };
  const t = await sendText(TWILIO, TO, BODY);
  assert.deepEqual(t, { ok: false, provider: "twilio", status: 0, error: "TypeError" });
});

await check("an empty recipient sends nothing", async () => {
  const r = await sendText(SENDBLUE, "", BODY);
  assert.equal(r.ok, false);
  assert.equal(calls.length, 0);
});

// --- the Twilio wire, as the two call sites had it ---------------------------
await check("the Twilio request is exact: URL, Basic sid:token, form body To/From/Body", async () => {
  reply = () => json(201, { sid: "SM123", status: "queued" });
  const r = await sendText(TWILIO, TO, BODY);
  assert.equal(calls.length, 1);
  const c = calls[0];
  assert.equal(c.url, `${TWILIO_BASE}/2010-04-01/Accounts/${TW_SID}/Messages.json`);
  assert.equal(c.url, `https://api.twilio.com/2010-04-01/Accounts/${TW_SID}/Messages.json`);
  assert.equal(c.method, "POST");
  assert.equal(c.headers["authorization"], "Basic " + btoa(`${TW_SID}:${TW_TOKEN}`));
  assert.equal(c.headers["content-type"], "application/x-www-form-urlencoded");
  assert.equal(c.body, new URLSearchParams({ To: TO, From: TW_FROM, Body: BODY }).toString());
  assert.equal(c.headers["sb-api-key-id"], undefined);
  assert.ok(c.signal instanceof AbortSignal);
  assert.deepEqual(r, { ok: true, provider: "twilio", id: "SM123", status: "queued" });
});

await check("Twilio prefers the scoped API key pair, as password_reset.ts did; one name alone falls back", async () => {
  reply = () => json(201, { sid: "SM1", status: "queued" });
  await sendText({ ...TWILIO, TWILIO_API_KEY_SID: TW_KEY_SID, TWILIO_API_KEY_SECRET: TW_KEY_SECRET }, TO, BODY);
  assert.equal(calls[0].headers["authorization"], "Basic " + btoa(`${TW_KEY_SID}:${TW_KEY_SECRET}`));
  assert.ok(calls[0].url.includes("/Accounts/" + TW_SID + "/"), "the URL still carries the account SID");
  await sendText({ ...TWILIO, TWILIO_API_KEY_SID: TW_KEY_SID }, TO, BODY);
  assert.equal(calls[1].headers["authorization"], "Basic " + btoa(`${TW_SID}:${TW_TOKEN}`));
});

await check("TWILIO_FROM is honoured when TWILIO_PHONE_NUMBER is absent", async () => {
  reply = () => json(201, { sid: "SM1", status: "queued" });
  await sendText({ TWILIO_ACCOUNT_SID: TW_SID, TWILIO_AUTH_TOKEN: TW_TOKEN, TWILIO_FROM: "+15550003333" }, TO, BODY);
  assert.equal(new URLSearchParams(calls[0].body).get("From"), "+15550003333");
});

await check("Twilio: res.ok is the truth, exactly as before", async () => {
  reply = () => json(400, { code: 21211, message: "invalid To" });
  const r = await sendText(TWILIO, TO, BODY);
  assert.deepEqual(r, { ok: false, provider: "twilio", status: 400, error: "21211" });
  reply = () => new Response("", { status: 201 });
  assert.equal((await sendText(TWILIO, TO, BODY)).ok, true, "a 2xx with no body was ok before and still is");
});

// --- the loopback seatbelt ---------------------------------------------------
await check("SENDBLUE_API_BASE / TWILIO_API_BASE move the host for loopback only", async () => {
  assert.equal(apiBase(undefined, SENDBLUE_BASE, "X"), SENDBLUE_BASE);
  assert.equal(apiBase("", SENDBLUE_BASE, "X"), SENDBLUE_BASE);
  assert.equal(apiBase("http://127.0.0.1:9797/", SENDBLUE_BASE, "X"), "http://127.0.0.1:9797");
  assert.equal(apiBase("http://localhost:9797", SENDBLUE_BASE, "X"), "http://localhost:9797");
  assert.equal(apiBase("http://[::1]:9797", SENDBLUE_BASE, "X"), "http://[::1]:9797");
  assert.equal(apiBase("https://evil.example", SENDBLUE_BASE, "X"), SENDBLUE_BASE);
  assert.equal(apiBase("http://127.0.0.1.evil.example", TWILIO_BASE, "X"), TWILIO_BASE);
  assert.equal(apiBase("not a url", TWILIO_BASE, "X"), TWILIO_BASE);

  reply = () => json(200, { message_handle: "mh", status: "QUEUED" });
  await sendText({ ...SENDBLUE, SENDBLUE_API_BASE: "http://127.0.0.1:9797" }, TO, BODY);
  assert.equal(calls[0].url, "http://127.0.0.1:9797/api/send-message");
  await sendText({ ...SENDBLUE, SENDBLUE_API_BASE: "https://evil.example" }, TO, BODY);
  assert.equal(calls[1].url, "https://api.sendblue.com/api/send-message");
  reply = () => json(201, { sid: "SM", status: "queued" });
  await sendText({ ...TWILIO, TWILIO_API_BASE: "http://127.0.0.1:9798" }, TO, BODY);
  assert.equal(calls[2].url, `http://127.0.0.1:9798/2010-04-01/Accounts/${TW_SID}/Messages.json`);
  await sendText({ ...TWILIO, TWILIO_API_BASE: "https://evil.example" }, TO, BODY);
  assert.equal(calls[3].url, `https://api.twilio.com/2010-04-01/Accounts/${TW_SID}/Messages.json`);
});

await check("the timeout is the sweep's 15 s", () => {
  assert.equal(SEND_TIMEOUT_MS, 15_000);
});

// --- what reaches a log line --------------------------------------------------
await check("no secret and no body in any log line; provider and last four are there", async () => {
  const secrets = [SB_KEY_ID, SB_SECRET, TW_TOKEN, TW_KEY_SECRET, BODY, "483920"];
  const env = { ...TWILIO, ...SENDBLUE, TWILIO_API_KEY_SID: TW_KEY_SID, TWILIO_API_KEY_SECRET: TW_KEY_SECRET };
  const results: SendResult[] = [];
  // Every branch: Sendblue ok, Sendblue ERROR, Sendblue 401, unreadable, thrown,
  // Twilio ok, Twilio 400, forced-but-unconfigured, none, loopback ignored.
  reply = () => json(202, { message_handle: "mh", status: "QUEUED" });
  results.push(await sendText(env, TO, BODY, { tag: "password reset" }));
  reply = () => json(200, { status: "ERROR", error_code: 4004, error_message: "bad " + BODY });
  results.push(await sendText(env, TO, BODY));
  reply = () => json(401, { error_code: 4010, error_message: "key " + SB_KEY_ID + " rejected" });
  results.push(await sendText(env, TO, BODY));
  reply = () => new Response("<html>", { status: 200 });
  results.push(await sendText(env, TO, BODY));
  reply = () => { throw new Error("secret " + SB_SECRET + " " + TW_TOKEN); };
  results.push(await sendText(env, TO, BODY));
  reply = () => json(201, { sid: "SM", status: "queued" });
  results.push(await sendText({ ...env, ANTICIPY_SMS_PROVIDER: "twilio" }, TO, BODY, { tag: "internal_hq" }));
  reply = () => json(400, { code: 21211, message: "bad " + TW_TOKEN });
  results.push(await sendText({ ...env, ANTICIPY_SMS_PROVIDER: "twilio" }, TO, BODY));
  results.push(await sendText({ ...TWILIO, ANTICIPY_SMS_PROVIDER: "sendblue" }, TO, BODY));
  results.push(await sendText({}, TO, BODY));
  // A pasted URL with a token in it must not be echoed by the "ignored" line.
  results.push(await sendText({ ...env, SENDBLUE_API_BASE: "https://evil.example/" + SB_SECRET + "?k=" + TW_TOKEN }, TO, BODY));

  assert.ok(logs.length >= results.length, "every send logs at least one line");
  for (const line of logs) {
    for (const s of secrets) assert.ok(!line.includes(s), "leaked " + JSON.stringify(s) + " in: " + line);
    assert.ok(!line.includes(TO), "whole recipient number in: " + line);
  }
  const sent = logs.filter((l) => l.includes("→"));
  assert.ok(sent.length >= 6, "the provider lines are there");
  for (const line of sent) {
    assert.ok(line.includes("sendblue") || line.includes("twilio"), "provider named: " + line);
    assert.ok(line.includes(last4(TO)), "last four: " + line);
    assert.match(line, /http=\d+/, "http status: " + line);
  }
  assert.ok(logs.some((l) => l.startsWith("password reset: ")), "the caller's tag prefixes its line");
  assert.ok(logs.some((l) => l.startsWith("internal_hq: ")));
  // The result may carry the provider's words; the LOG may not. Callers do not log results.
  assert.match((results[2] as { error: string }).error, /rejected/);
});

await check("last4 is four digits and an ellipsis, never more", () => {
  assert.equal(last4("+15557654321"), "…4321");
  assert.equal(last4("555"), "…555");
  assert.equal(last4(""), "…");
});

globalThis.fetch = realFetch;
console.log = realLog;

if (failures) {
  console.error(`messaging: ${failures} failing`);
  process.exit(1);
}
console.log("messaging: all cases pass");
