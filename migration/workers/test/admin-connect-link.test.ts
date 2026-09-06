// The Week A gate's manual trigger, driven end to end over the real schema:
// a key-holder names an owner and apps, a link row lands in connect_links,
// and ONE text carrying OUR url (never the vendor's) goes to that owner's own
// phone. One suite, the chain step only — the owner's rule for this run.
import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { adminConnectLink, ADMIN_CONNECT_LINK_PATH, type AdminConnectLinkEnv } from "../src/routes/admin_connect_link.ts";
import { resetConnectionsProvider } from "../src/connections/provider.ts";


const OWNER = "4i2vafx1g01nlia";      // 15 lowercase alphanumerics, the owner-id shape
const KEY = "test-internal-key";
const PHONE = "+16045550100";

let passes = 0, failures = 0;
async function check(name: string, fn: () => Promise<void> | void) {
  try { await fn(); passes++; console.log("  ok   " + name); }
  catch (e) { failures++; console.log("  FAIL " + name + "\n       " + String((e as Error).message).split("\n")[0]); }
}

/** Real schema, one owner with a phone, fetch stubbed: the vendor's toolkit
 *  read answers a fixed row, the SMS provider records what it was asked to
 *  send and sends nothing. */
function rig() {
  const d1 = new FakeD1();
  // The seed shape connect-auth.test.ts uses, verbatim: FakeD1 wraps a sync
  // sqlite handle at .db, and this is the owners column set the schema wants.
  d1.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
  ).run(OWNER, "2026-09-06 00:00:00.000Z", "2026-09-06 00:00:00.000Z", "o@anticipy-test.invalid", "key-o", PHONE);
  const rows = (sql: string) => d1.db.prepare(sql).all() as Record<string, unknown>[];
  const texts: { to: string; body: string }[] = [];
  const real = globalThis.fetch;
  globalThis.fetch = (async (input: unknown, init?: { body?: unknown }) => {
    const url = String((input as { url?: string })?.url ?? input);
    const json = (s: number, v: unknown) => new Response(JSON.stringify(v), { status: s, headers: { "content-type": "application/json" } });
    if (url.includes("composio.dev")) {
      if (url.includes("/toolkits/")) return json(200, { slug: "zellibrix", name: "Zellibrix", meta: { logo: "https://z.example.invalid/l.png", description: "Notes." } });
      return json(200, {});
    }
    // Any messaging provider: record, do not send.
    let b: Record<string, unknown> = {};
    try { b = JSON.parse(String(init?.body ?? "{}")); } catch { /* form body */ }
    texts.push({ to: String(b.number ?? b.To ?? b.to ?? ""), body: String(b.content ?? b.Body ?? b.body ?? "") });
    return json(200, { status: "SENT", message_handle: "h1", sid: "s1" });
  }) as typeof globalThis.fetch;
  resetConnectionsProvider();
  const env = {
    DB: asD1(d1), ANTICIPY_INTERNAL_KEY: KEY, COMPOSIO_API_KEY: "k",
    SENDBLUE_API_KEY_ID: "a", SENDBLUE_API_SECRET_KEY: "b", SENDBLUE_FROM_NUMBER: "+15550000000",
  } as unknown as AdminConnectLinkEnv;
  return { d1, rows, env, texts, restore: () => { globalThis.fetch = real; } };
}

const post = (body: unknown, key: string | null = KEY) => new Request("https://api.anticipy.ai" + ADMIN_CONNECT_LINK_PATH, {
  method: "POST", body: JSON.stringify(body),
  headers: { "content-type": "application/json", ...(key ? { "X-Internal-Key": key } : {}) },
});

await check("no key -> 401 before any read; wrong key -> 401; nothing minted", async () => {
  const r = rig();
  assert.equal((await adminConnectLink(post({ owner: OWNER, toolkits: ["zellibrix"] }, null), r.env)).status, 401);
  assert.equal((await adminConnectLink(post({ owner: OWNER, toolkits: ["zellibrix"] }, "nope"), r.env)).status, 401);
  assert.equal(r.rows(`SELECT count(*) n FROM "connect_links"`)[0].n, 0);
  assert.equal(r.texts.length, 0);
  r.restore();
});

await check("an owner nobody has is 404, not a mint for nobody", async () => {
  const r = rig();
  const res = await adminConnectLink(post({ owner: "zzzzzzzzzzzzzzz", toolkits: ["zellibrix"] }), r.env);
  assert.equal(res.status, 404);
  assert.equal(r.rows(`SELECT count(*) n FROM "connect_links"`)[0].n, 0);
  r.restore();
});

await check("THE CHAIN: key + owner + app -> one link row, one text, OUR url, to the owner's own phone", async () => {
  const r = rig();
  const res = await adminConnectLink(post({ owner: OWNER, toolkits: ["zellibrix"] }), r.env);
  const body = await res.json() as { ok: boolean; url: string; sent: boolean };
  assert.equal(res.status, 200, JSON.stringify(body));
  assert.ok(body.url.startsWith("https://api.anticipy.ai/c/"), body.url);
  assert.equal(body.sent, true);
  const rows = r.rows(`SELECT "user_id" FROM "connect_links"`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user_id, OWNER, "the link is bound to the owner named, not somebody else");
  assert.equal(r.texts.length, 1, "exactly one text");
  assert.equal(r.texts[0].to, PHONE, "to the owner's own phone");
  assert.ok(r.texts[0].body.includes(body.url), "the text carries our link");
  assert.ok(!/composio|google\.com|accounts\./i.test(r.texts[0].body), "never a vendor url or name");
  r.restore();
});

await check("send:false mints and returns the url without texting (for the app-side test)", async () => {
  const r = rig();
  const res = await adminConnectLink(post({ owner: OWNER, toolkits: ["zellibrix"], send: false }), r.env);
  const body = await res.json() as { url: string; sent: boolean };
  assert.equal(res.status, 200);
  assert.ok(body.url.startsWith("https://api.anticipy.ai/c/"));
  assert.equal(body.sent, false);
  assert.equal(r.texts.length, 0);
  r.restore();
});

await check("it writes NO nudge row and spends none of the weekly budget -- a link asked for is not an ask", async () => {
  const r = rig();
  await adminConnectLink(post({ owner: OWNER, toolkits: ["zellibrix"] }), r.env);
  assert.equal(r.rows(`SELECT count(*) n FROM "connect_nudges"`)[0].n, 0);
  r.restore();
});

console.log(`admin-connect-link: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
