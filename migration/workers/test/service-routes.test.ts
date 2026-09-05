/**
 * Runs with no network and no wrangler:
 *
 *   node --experimental-strip-types migration/workers/test/service-routes.test.ts
 *
 * The three account routes ported on 2026-09-05 (audit F01/F02/F03/F14/F40),
 * driven as the phone and the extension drive them: a real Request, the real
 * handler, the real SQL, the real migration/d1/schema.sql (partial-unique
 * indexes included) behind test/fake-d1.ts, and a real HMAC-signed account
 * token from src/pb/auth.ts. Nothing here asserts that a constant exists; every
 * check is a status code, a body the iPhone decodes, or a row in the database.
 *
 * The wire half -- a real workerd, a real D1, a real sign-in -- is
 * migration/spec/contract_tests.py (TestServiceRoutes, TestAccountDelete,
 * TestAgentRoutes) run by scripts/service_contract_local.sh.
 *
 * MUTATIONS THIS FILE MUST GO RED ON, i.e. what it is actually holding down:
 *   * profile upsert stops seeding the first row from the account;
 *   * omission stops preserving a field (presence-not-truthiness inverted);
 *   * an unreadable account read is converted into empty seeds instead of 500;
 *   * phone removal stops covering the ownerless residue, or covers another
 *     account's rows;
 *   * claim adopts a uuid this account never recorded;
 *   * claim adopts transcripts while a second account exists;
 *   * /agent/key drops `owner` or `vision_model`, or hands out a vision model
 *     /agent/llm would refuse;
 *   * /me/delete answers without account_deleted / memory_purge, or writes a
 *     purge row with no legacy_uuid.
 */
import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { authClaim, phoneRemove, profileUpsert, type ServiceEnv } from "../src/routes/service.ts";
import { agentKey, agentRegister, type AgentEnv } from "../src/routes/agent.ts";
import { accountDelete } from "../src/routes/account_delete.ts";
import { enabledModels } from "../src/llm.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const SECRET = "service-routes-test-secret";
const NOW = "2026-09-05 12:00:00.000Z";

interface Rig {
  db: FakeD1;
  env: ServiceEnv & AgentEnv;
  token: string;
  ref: string;
}

/** One account, signed in, with whatever rows a test asks for. */
async function rig(opts: {
  email?: string; phone?: string; legacy?: string;
} = {}): Promise<Rig> {
  const db = new FakeD1();
  const ref = "ownerrefaaaaaa1";
  db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'','key-1',?,?)`,
  ).run(ref, NOW, NOW, opts.email ?? "her@anticipy-test.invalid",
        opts.phone ?? "", opts.legacy ?? "");
  const env = {
    DB: asD1(db), ANTICIPY_AUTH_SECRET: SECRET,
    ANTICIPY_BROWSER_MODEL: "google/gemini-3.1-pro-preview",
    ANTICIPY_VISION_MODEL: "google/gemini-2.5-flash",
    GEMINI_API_KEY: "fake-gemini-key",
  } as unknown as ServiceEnv & AgentEnv;
  const token = await issueToken(env, ref, "key-1");
  return { db, env, token, ref };
}

const post = (path: string, token: string | null, body: unknown) =>
  new Request("https://api.anticipy.ai" + path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(token ? { Authorization: token } : {}),
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });

const bodyOf = async (r: Response) => (await r.json()) as Record<string, unknown>;

const profileRows = (db: FakeD1, ref: string) =>
  db.rows<Record<string, string>>(
    `SELECT * FROM owner_profile WHERE owner_ref = ? ORDER BY updated DESC, created DESC, id DESC`, ref);

// ===========================================================================
// POST /me/profile/upsert -- the route a TestFlight signup cannot save without
// ===========================================================================

await check("a signed-in first write CREATES the profile and echoes the canonical row", async () => {
  const r = await rig({ email: "her@anticipy-test.invalid", phone: "+15550100001", legacy: "legacy-uuid-1234" });
  const resp = await profileUpsert(post("/me/profile/upsert", r.token,
    { first_name: "Ada", timezone: "America/Vancouver" }), r.env);
  assert.equal(resp.status, 200);
  const b = await bodyOf(resp);
  assert.equal(b.ok, true, "the iPhone requires ok:true before it will paint Saved");
  const p = b.profile as Record<string, string>;
  assert.equal(p.owner_ref, r.ref, "AnticipyBackend.swift:410-420 compares this to its own accountID");
  assert.equal(p.first_name, "Ada");
  assert.equal(p.timezone, "America/Vancouver", "the zone the brain judges quiet hours in");
  // Seeded from the account on the FIRST row only.
  assert.equal(p.email, "her@anticipy-test.invalid", "the account's email seeds the first profile");
  assert.equal(p.phone, "+15550100001", "the account's phone seeds the first profile");
  assert.equal(p.owner_id, "legacy-uuid-1234", "owner_id prefers the recorded legacy uuid");
  assert.ok(p.id, "the row has an id");
  // And it is really in the database, which is the only thing the brain reads.
  const rows = profileRows(r.db, r.ref);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.timezone, "America/Vancouver");
});

await check("the echoed row carries every field the client verifies, none missing", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { name: "Ada L" }), r.env);
  const p = (await bodyOf(resp)).profile as Record<string, string>;
  for (const key of ["id", "owner_ref", "owner_id", "phone", "name", "first_name",
                     "last_name", "email", "birthday", "facts", "timezone"]) {
    assert.ok(key in p, "the canonical row must carry " + key);
  }
});

await check("owner_id falls back to the account id when nothing was recorded", async () => {
  const r = await rig({ legacy: "" });
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { name: "Ada" }), r.env);
  const p = (await bodyOf(resp)).profile as Record<string, string>;
  assert.equal(p.owner_id, r.ref, "owner_id is required by the schema and may never be blank");
});

await check("PRESENCE, not truthiness: omission keeps, '' clears", async () => {
  const r = await rig({ phone: "+15550100001" });
  await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada", phone: "+15550100002" }), r.env);
  // Omitting the phone must not blank it -- Settings saves identity and phone
  // as two independent requests.
  const kept = await bodyOf(await profileUpsert(
    post("/me/profile/upsert", r.token, { last_name: "Lovelace" }), r.env));
  assert.equal((kept.profile as Record<string, string>).phone, "+15550100002",
    "an omitted field must survive an unrelated save");
  assert.equal((kept.profile as Record<string, string>).first_name, "Ada");
  // An explicit empty string is a real value and clears.
  const cleared = await bodyOf(await profileUpsert(
    post("/me/profile/upsert", r.token, { phone: "" }), r.env));
  assert.equal((cleared.profile as Record<string, string>).phone, "",
    "an explicit '' is a value, not an omission");
});

await check("once a profile exists its empty phone is authoritative and the sign-up seed never returns", async () => {
  const r = await rig({ phone: "+15550100001" });
  await profileUpsert(post("/me/profile/upsert", r.token, { phone: "" }), r.env);
  const again = await bodyOf(await profileUpsert(
    post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env));
  assert.equal((again.profile as Record<string, string>).phone, "",
    "re-seeding from owners.phone would re-affiliate a number the person removed");
});

await check("a second save updates the canonical row and never makes a second one", async () => {
  const r = await rig();
  await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env);
  await profileUpsert(post("/me/profile/upsert", r.token, { last_name: "Lovelace" }), r.env);
  assert.equal(profileRows(r.db, r.ref).length, 1, "one profile row per account");
});

await check("a legacy database WITHOUT the partial-unique index collapses its duplicates", async () => {
  const r = await rig();
  // The index is what makes a duplicate unreachable today; these rows are the
  // ones imported from before it existed (schema.sql:371-377).
  r.db.db.exec(`DROP INDEX idx_owner_profile_owner_ref`);
  const mk = (id: string, updated: string, phone: string) => r.db.db.prepare(
    `INSERT INTO owner_profile (id, created, updated, owner_id, phone, owner_ref)
     VALUES (?,?,?,?,?,?)`).run(id, updated, updated, "legacy-1", phone, r.ref);
  mk("profileolder11", "2026-09-01 00:00:00.000Z", "+15550100009");
  mk("profilenewest1", "2026-09-04 00:00:00.000Z", "");
  const b = await bodyOf(await profileUpsert(
    post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env));
  assert.equal(b.ok, true);
  assert.equal(b.removedDuplicates, 1, "the older duplicate is deleted, not merged");
  const rows = profileRows(r.db, r.ref);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.id, "profilenewest1", "the NEWEST row is canonical");
  assert.equal(rows[0]!.phone, "", "an older non-empty phone must not merge back in");
});

await check("a field outside the editable eight is refused -- ownership is never sent", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", r.token,
    { owner_ref: "somebody-else" }), r.env);
  assert.equal(resp.status, 400);
  assert.equal((await bodyOf(resp)).message, "That field is not part of the owner profile.");
  assert.equal(profileRows(r.db, r.ref).length, 0, "a refused write writes nothing");
});

await check("a non-string value is refused", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { name: 42 }), r.env);
  assert.equal(resp.status, 400);
  assert.equal((await bodyOf(resp)).message, "Profile fields must be text.");
});

await check("a body that is not an object is refused, and says so", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, ["not", "an", "object"]), r.env);
  assert.equal(resp.status, 400);
  assert.equal((await bodyOf(resp)).message, "The profile update must be an object.");
});

await check("an unreadable body is a different sentence from a wrong-shaped one", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, "{not json"), r.env);
  assert.equal(resp.status, 400);
  assert.equal((await bodyOf(resp)).message, "The profile update was unreadable.");
});

await check("an anonymous upsert is refused", async () => {
  const r = await rig();
  const resp = await profileUpsert(post("/me/profile/upsert", null, { name: "Ada" }), r.env);
  assert.equal(resp.status, 401);
  assert.equal((await bodyOf(resp)).message, "Sign in first.");
});

await check("AN UNREADABLE ACCOUNT IS 500, NEVER EMPTY SEEDS", async () => {
  const r = await rig({ email: "her@anticipy-test.invalid", phone: "+15550100001" });
  // The SECOND read of `owners` on this request: the first is the token
  // verification in src/pb/auth.ts, which runs before the handler's own read.
  r.db.failNth(/SELECT \* FROM "owners"/, 2);
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env);
  assert.equal(resp.status, 500, "unknown state refuses; it is never a blank profile");
  assert.equal((await bodyOf(resp)).message,
    "I couldn't verify the complete profile, so nothing was reported as saved.");
  assert.equal(profileRows(r.db, r.ref).length, 0);
});

await check("a refused WRITE reports the rollback sentence and leaves no row", async () => {
  const r = await rig();
  r.db.failOn = (sql) => /INSERT INTO "owner_profile"/.test(sql);
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env);
  assert.equal(resp.status, 500);
  assert.equal((await bodyOf(resp)).message,
    "I couldn't verify the complete profile, so nothing was reported as saved.");
  assert.equal(profileRows(r.db, r.ref).length, 0);
});

await check("a write that lands but cannot be PROVEN says so, and does not claim ok", async () => {
  const r = await rig();
  r.db.failNth(/SELECT \* FROM "owner_profile"/, 2);   // the read-back
  const resp = await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env);
  assert.equal(resp.status, 500);
  assert.equal((await bodyOf(resp)).message,
    "The server could not verify the saved profile. Refresh before relying on it.");
});

// ===========================================================================
// POST /me/phone/remove
// ===========================================================================

async function withProfile(r: Rig, over: Partial<Record<string, string>> = {}): Promise<void> {
  r.db.db.prepare(
    `INSERT INTO owner_profile (id, created, updated, owner_id, phone, owner_ref)
     VALUES (?,?,?,?,?,?)`,
  ).run(over.id ?? "profileaaaaaa1", NOW, NOW, over.owner_id ?? "legacy-uuid-1234",
        over.phone ?? "+15550100001", over.owner_ref ?? r.ref);
}

await check("removal clears the account seed AND the profile, and counts what it cleared", async () => {
  const r = await rig({ phone: "+15550100001", legacy: "legacy-uuid-1234" });
  await withProfile(r);
  const resp = await phoneRemove(post("/me/phone/remove", r.token, {}), r.env);
  assert.equal(resp.status, 200);
  const b = await bodyOf(resp);
  // AnticipyBackend.swift:374-386 requires all three.
  assert.equal(b.ok, true);
  assert.equal(b.phone, "");
  assert.equal(b.clearedProfiles, 1);
  assert.equal(r.db.rows<{ phone: string }>(`SELECT phone FROM owners WHERE id = ?`, r.ref)[0]!.phone, "");
  assert.equal(profileRows(r.db, r.ref)[0]!.phone, "", "an unrevoked profile phone still routes texts");
});

await check("the OWNERLESS RESIDUE is revoked too -- claim_legacy could have left it", async () => {
  const r = await rig({ phone: "+15550100001", legacy: "legacy-uuid-1234" });
  await withProfile(r, { id: "orphanprofile1", owner_ref: "", owner_id: "legacy-uuid-1234" });
  const b = await bodyOf(await phoneRemove(post("/me/phone/remove", r.token, {}), r.env));
  assert.equal(b.clearedProfiles, 1);
  const orphan = r.db.rows<{ phone: string }>(
    `SELECT phone FROM owner_profile WHERE id = 'orphanprofile1'`)[0]!;
  assert.equal(orphan.phone, "", "an ownerless row attributable by owner_id still routes the number");
});

await check("a residue row attributable by the ACCOUNT REF is revoked too", async () => {
  const r = await rig({ phone: "+15550100001", legacy: "" });
  await withProfile(r, { id: "orphanprofile2", owner_ref: "", owner_id: r.ref });
  const b = await bodyOf(await phoneRemove(post("/me/phone/remove", r.token, {}), r.env));
  assert.equal(b.clearedProfiles, 1);
  assert.equal(r.db.rows<{ phone: string }>(
    `SELECT phone FROM owner_profile WHERE id = 'orphanprofile2'`)[0]!.phone, "");
});

await check("SOMEBODY ELSE'S profile is never touched", async () => {
  const r = await rig({ phone: "+15550100001", legacy: "legacy-uuid-1234" });
  r.db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid)
     VALUES ('strangerowner1',?,?,'him@anticipy-test.invalid',0,0,'','key-2','+15550100002','legacy-uuid-9999')`,
  ).run(NOW, NOW);
  await withProfile(r, { id: "strangerprof1", owner_ref: "strangerowner1", owner_id: "legacy-uuid-9999",
                         phone: "+15550100002" });
  const b = await bodyOf(await phoneRemove(post("/me/phone/remove", r.token, {}), r.env));
  assert.equal(b.clearedProfiles, 0, "this account has no profile of its own here");
  assert.equal(r.db.rows<{ phone: string }>(
    `SELECT phone FROM owner_profile WHERE id = 'strangerprof1'`)[0]!.phone, "+15550100002");
  assert.equal(r.db.rows<{ phone: string }>(
    `SELECT phone FROM owners WHERE id = 'strangerowner1'`)[0]!.phone, "+15550100002");
});

await check("a refused write reports the rollback sentence and the number is STILL THERE", async () => {
  const r = await rig({ phone: "+15550100001" });
  await withProfile(r);
  r.db.failOn = (sql) => /UPDATE "owner_profile" SET "phone"/.test(sql);
  const resp = await phoneRemove(post("/me/phone/remove", r.token, {}), r.env);
  assert.equal(resp.status, 500);
  assert.equal((await bodyOf(resp)).message,
    "I couldn't verify that every copy was removed, so the change was not completed.");
  assert.equal(r.db.rows<{ phone: string }>(`SELECT phone FROM owners WHERE id = ?`, r.ref)[0]!.phone,
    "+15550100001", "the batch is one transaction: the owners half must roll back with it");
});

await check("UNKNOWN IS FAILURE: an unverifiable removal never answers ok", async () => {
  const r = await rig({ phone: "+15550100001" });
  await withProfile(r);
  // Reads of `owners` on this request: 1 the token verification, 2 the
  // handler's own read, 3 THE POST-COMMIT PROOF -- which is the one to break.
  r.db.failNth(/SELECT \* FROM "owners"/, 3);
  const resp = await phoneRemove(post("/me/phone/remove", r.token, {}), r.env);
  assert.equal(resp.status, 500);
  assert.equal((await bodyOf(resp)).message,
    "The server could not verify the removal. Refresh your account before relying on it.");
});

await check("an anonymous removal is refused", async () => {
  const r = await rig();
  const resp = await phoneRemove(post("/me/phone/remove", null, {}), r.env);
  assert.equal(resp.status, 401);
});

// ===========================================================================
// POST /auth/claim
// ===========================================================================

function seedLegacyRows(r: Rig, uuid: string): void {
  r.db.db.prepare(`INSERT INTO jobs (id, created, updated, goal, status, owner, owner_ref)
                   VALUES ('jobaaaaaaaaaaa1',?,?,'book a table','queued',?, '')`).run(NOW, NOW, uuid);
  r.db.db.prepare(`INSERT INTO segments (id, created, updated, status, owner, owner_ref)
                   VALUES ('segaaaaaaaaaa1',?,?,'open',?,'')`).run(NOW, NOW, uuid);
  r.db.db.prepare(`INSERT INTO agents (id, created, updated, agent_id, pair_code, owner, owner_ref)
                   VALUES ('agentaaaaaaaa1',?,?,'ext-1','123456',?,'')`).run(NOW, NOW, uuid);
  r.db.db.prepare(`INSERT INTO owner_profile (id, created, updated, owner_id, owner_ref)
                   VALUES ('legacyprofile1',?,?,?,'')`).run(NOW, NOW, uuid);
  r.db.db.prepare(`INSERT INTO events (id, created, updated, device_id, kind, text, owner_ref)
                   VALUES ('eventaaaaaaaa1',?,?,'iphone','transcript','what he said','')`).run(NOW, NOW);
}

await check("the four provable tables are adopted onto the account", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  seedLegacyRows(r, "legacy-uuid-1234");
  const resp = await authClaim(post("/auth/claim", r.token, { legacy_uuid: "legacy-uuid-1234" }), r.env);
  assert.equal(resp.status, 200);
  const claimed = (await bodyOf(resp)).claimed as Record<string, number>;
  assert.deepEqual(claimed, { jobs: 1, owner_profile: 1, segments: 1, agents: 1, events: 1 });
  for (const [table, id] of [["jobs", "jobaaaaaaaaaaa1"], ["segments", "segaaaaaaaaaa1"],
                             ["agents", "agentaaaaaaaa1"], ["owner_profile", "legacyprofile1"]] as const) {
    assert.equal(r.db.rows<{ owner_ref: string }>(
      `SELECT owner_ref FROM ${table} WHERE id = ?`, id)[0]!.owner_ref, r.ref,
      `${table} was not adopted -- signing up would look like losing everything`);
  }
});

await check("A UUID THIS ACCOUNT NEVER RECORDED IS REFUSED, and moves nothing", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  seedLegacyRows(r, "somebody-elses-uuid");
  const resp = await authClaim(post("/auth/claim", r.token,
    { legacy_uuid: "somebody-elses-uuid" }), r.env);
  assert.equal(resp.status, 403, "a pair code hands this value out; it is a claim, never proof");
  assert.equal((await bodyOf(resp)).message, "That device isn't on this account.");
  assert.equal(r.db.rows<{ owner_ref: string }>(
    `SELECT owner_ref FROM owner_profile WHERE id = 'legacyprofile1'`)[0]!.owner_ref, "",
    "the stranger's name, email, phone and birthday must not move");
});

await check("an account with nothing recorded claims nothing", async () => {
  const r = await rig({ legacy: "" });
  seedLegacyRows(r, "legacy-uuid-1234");
  const b = await bodyOf(await authClaim(post("/auth/claim", r.token, {}), r.env));
  assert.deepEqual(b.claimed, { jobs: 0, owner_profile: 0, segments: 0, agents: 0, events: 1 },
    "no uuid means no provable rows; the transcripts are still unambiguous here");
});

await check("a uuid shorter than 8 characters proves nothing", async () => {
  const r = await rig({ legacy: "short" });
  seedLegacyRows(r, "short");
  const b = await bodyOf(await authClaim(post("/auth/claim", r.token, { legacy_uuid: "short" }), r.env));
  assert.equal((b.claimed as Record<string, number>).jobs, 0);
});

await check("a row somebody already owns is not re-adopted", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  r.db.db.prepare(`INSERT INTO jobs (id, created, updated, goal, status, owner, owner_ref)
                   VALUES ('jobaaaaaaaaaaa2',?,?,'x','queued','legacy-uuid-1234','strangerowner1')`)
    .run(NOW, NOW);
  const b = await bodyOf(await authClaim(post("/auth/claim", r.token,
    { legacy_uuid: "legacy-uuid-1234" }), r.env));
  assert.equal((b.claimed as Record<string, number>).jobs, 0);
  assert.equal(r.db.rows<{ owner_ref: string }>(
    `SELECT owner_ref FROM jobs WHERE id = 'jobaaaaaaaaaaa2'`)[0]!.owner_ref, "strangerowner1");
});

await check("TRANSCRIPTS ARE NOT ADOPTED WHILE A SECOND ACCOUNT EXISTS", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  seedLegacyRows(r, "legacy-uuid-1234");
  r.db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified, password, tokenKey, phone, legacy_uuid)
     VALUES ('strangerowner1',?,?,'him@anticipy-test.invalid',0,0,'','key-2','','')`).run(NOW, NOW);
  const b = await bodyOf(await authClaim(post("/auth/claim", r.token,
    { legacy_uuid: "legacy-uuid-1234" }), r.env));
  assert.equal((b.claimed as Record<string, number>).events, 0,
    "events carry no owner column at all -- a brand-new account once opened onto "
    + "someone else's spoken sentences, and that is the bug this rule exists for");
  assert.equal(r.db.rows<{ owner_ref: string }>(
    `SELECT owner_ref FROM events WHERE id = 'eventaaaaaaaa1'`)[0]!.owner_ref, "");
  assert.equal((b.claimed as Record<string, number>).jobs, 1, "the provable rows still move");
});

await check("one table that cannot be read does not lose the tables that can", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  seedLegacyRows(r, "legacy-uuid-1234");
  r.db.failOn = (sql) => /FROM "jobs"/.test(sql);
  const b = await bodyOf(await authClaim(post("/auth/claim", r.token,
    { legacy_uuid: "legacy-uuid-1234" }), r.env));
  const claimed = b.claimed as Record<string, number>;
  assert.equal(claimed.jobs, 0);
  assert.equal(claimed.segments, 1);
  assert.equal(claimed.agents, 1);
  assert.equal(claimed.owner_profile, 1);
});

await check("an anonymous claim is refused", async () => {
  const r = await rig();
  const resp = await authClaim(post("/auth/claim", null, { legacy_uuid: "legacy-uuid-1234" }), r.env);
  assert.equal(resp.status, 401);
});

// ===========================================================================
// GET /agent/key -- the owner card and the vision model (F01)
// ===========================================================================

async function pairedAgent(r: Rig): Promise<Request> {
  const token = "a".repeat(64);
  r.db.db.prepare(
    `INSERT INTO agents (id, created, updated, agent_id, agent_token, pair_code, paired, owner_ref)
     VALUES ('agentpaired001',?,?,'ext-paired-0123456789',?,'654321',1,?)`,
  ).run(NOW, NOW, token, r.ref);
  return new Request("https://api.anticipy.ai/agent/key?agent_id=ext-paired-0123456789",
    { headers: { "X-Anticipy-Agent-Token": token } });
}

await check("/agent/key hands the hands the OWNER CARD and the vision model", async () => {
  const r = await rig();
  await profileUpsert(post("/me/profile/upsert", r.token,
    { first_name: "Ada", last_name: "Lovelace", email: "ada@anticipy-test.invalid",
      phone: "+15550100001", birthday: "1815-12-10", facts: "{\"seat\":\"aisle\"}" }), r.env);
  const resp = await agentKey(await pairedAgent(r), r.env);
  assert.equal(resp.status, 200);
  const b = await bodyOf(resp);
  assert.equal(b.llm_proxy, true);
  assert.equal(b.owner_ref, r.ref);
  const owner = b.owner as Record<string, string>;
  assert.deepEqual(owner, {
    first_name: "Ada", last_name: "Lovelace", email: "ada@anticipy-test.invalid",
    phone: "+15550100001", birthday: "1815-12-10", facts: "{\"seat\":\"aisle\"}",
  }, "agent_loop.js:383 tells the model the details are NOT on file without this");
  assert.equal(b.vision_model, "google/gemini-2.5-flash");
  assert.equal(b.model, "google/gemini-3.1-pro-preview");
});

await check("the vision model handed out is BY CONSTRUCTION one /agent/llm accepts", async () => {
  const r = await rig();
  const resp = await agentKey(await pairedAgent(r), r.env);
  const b = await bodyOf(resp);
  const allowed = enabledModels(r.env);
  // Not a restatement of the constant: this is the pair that was broken live
  // -- the extension fell back to anthropic/claude-sonnet-4.6 and the proxy
  // answered 403, which the extension reads as a rejected key.
  assert.equal(b.vision_model, allowed.vision);
  assert.equal(b.model, allowed.browser);
  assert.notEqual(b.vision_model, "", "an empty vision_model is what triggered the fallback");
});

await check("no profile is `owner: null`, not a refusal", async () => {
  const r = await rig();
  const b = await bodyOf(await agentKey(await pairedAgent(r), r.env));
  assert.equal(b.owner, null);
  assert.equal(b.vision_model, "google/gemini-2.5-flash", "the eyes still work without a profile");
});

await check("AN UNREADABLE PROFILE COSTS A FORM, NOT THE WHOLE RUN", async () => {
  const r = await rig();
  const req = await pairedAgent(r);
  r.db.failOn = (sql) => /FROM "owner_profile"/.test(sql);
  const resp = await agentKey(req, r.env);
  assert.equal(resp.status, 200, "the profile is an enabler; its absence must not fence the browser");
  const b = await bodyOf(resp);
  assert.equal(b.owner, null);
  assert.equal(b.vision_model, "google/gemini-2.5-flash");
});

await check("no provider key at all is still the 503", async () => {
  const r = await rig();
  const req = await pairedAgent(r);
  const env = { ...r.env, GEMINI_API_KEY: "", GOOGLE_API_KEY: "", OPENROUTER_API_KEY: "" };
  const resp = await agentKey(req, env as AgentEnv);
  assert.equal(resp.status, 503);
  assert.equal((await bodyOf(resp)).error, "backend has no model configured");
});

await check("/agent/key never carries a vendor or service credential", async () => {
  const r = await rig();
  await profileUpsert(post("/me/profile/upsert", r.token, { first_name: "Ada" }), r.env);
  const text = await (await agentKey(await pairedAgent(r), r.env)).text();
  for (const smell of ["fake-gemini-key", "api_key", "apikey", "service_token", "agent_token"]) {
    assert.equal(text.toLowerCase().includes(smell), false,
      "the extension is a published zip; found " + smell);
  }
});

// ===========================================================================
// POST /agent/register -- the row is born complete (F40)
// ===========================================================================

await check("a registered agent row carries its browser and last_seen from birth", async () => {
  const r = await rig();
  const resp = await agentRegister(post("/agent/register", null,
    { agent_id: "ext-fresh-install-01234", browser: "Chrome/141" }), r.env);
  assert.equal(resp.status, 200);
  const b = await bodyOf(resp);
  assert.match(String(b.id), /^[a-z0-9]{15}$/, "the row id is the extension's recordId");
  const row = r.db.rows<{ browser: string; last_seen: string }>(
    `SELECT browser, last_seen FROM agents WHERE agent_id = 'ext-fresh-install-01234'`)[0]!;
  assert.equal(row.browser, "Chrome/141");
  assert.ok(row.last_seen, "last_seen is the hook's, written at registration");
});

await check("a browser string longer than 500 chars is sliced, not refused", async () => {
  const r = await rig();
  await agentRegister(post("/agent/register", null,
    { agent_id: "ext-fresh-install-56789", browser: "x".repeat(900) }), r.env);
  const row = r.db.rows<{ browser: string }>(
    `SELECT browser FROM agents WHERE agent_id = 'ext-fresh-install-56789'`)[0]!;
  assert.equal(row.browser.length, 500);
});

// ===========================================================================
// POST /me/delete -- the body the phone actually decodes (F14)
// ===========================================================================

await check("a completed delete answers the three things the phone decodes", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  await withProfile(r);
  const resp = await accountDelete(post("/me/delete", r.token, { confirm: "delete" }), r.env);
  assert.equal(resp.status, 200);
  const b = await bodyOf(resp);
  // AnticipyApp.swift:330-336: success = 200 && ok && account_deleted &&
  // purge in {scheduled, purged}. Two of the three were missing.
  assert.equal(b.ok, true);
  assert.equal(b.account_deleted, true);
  assert.equal(b.memory_purge, "scheduled");
  assert.equal(r.db.rows(`SELECT id FROM owners WHERE id = ?`, r.ref).length, 0);
});

await check("THE PURGE ROW CARRIES legacy_uuid, or the founder's memory is never found", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  await accountDelete(post("/me/delete", r.token, { confirm: "delete" }), r.env);
  const purge = r.db.rows<{ owner_ref: string; legacy_uuid: string; memory_purged: number }>(
    `SELECT owner_ref, legacy_uuid, memory_purged FROM purges`)[0]!;
  assert.equal(purge.owner_ref, r.ref);
  assert.equal(purge.legacy_uuid, "legacy-uuid-1234",
    "brain/supervisor.py:215 reads this to find memory outside <state root>/<ref>");
  assert.equal(purge.memory_purged, 0, "the drain has not run yet, and the row must say so");
});

await check("rows gone but the account surviving is a 409, and says the purge is waiting", async () => {
  const r = await rig({ legacy: "legacy-uuid-1234" });
  r.db.failOn = (sql) => /DELETE FROM owners/.test(sql);
  const resp = await accountDelete(post("/me/delete", r.token, { confirm: "delete" }), r.env);
  assert.equal(resp.status, 409, "the iPhone singles this status out from a 500");
  const b = await bodyOf(resp);
  assert.equal(b.ok, false);
  assert.equal(b.account_deleted, false);
  assert.equal(b.memory_purge, "waiting on the account closing");
});

await check("the confirmation is still proof of intent", async () => {
  const r = await rig();
  const resp = await accountDelete(post("/me/delete", r.token, { confirm: "yes" }), r.env);
  assert.equal(resp.status, 400);
  assert.equal(r.db.rows(`SELECT id FROM owners WHERE id = ?`, r.ref).length, 1);
});

console.log(`service-routes: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
