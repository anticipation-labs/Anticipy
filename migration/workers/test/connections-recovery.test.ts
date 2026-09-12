/** Actual recovery SQL over SQLite; fake vendor only. No account/provider traffic. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { createRecoveryStore, recoverOAuthAttempts, RECOVERY_CRON } from "../src/connections/recovery.ts";
import { connectPageDone, connectPageGo, connectPageSkip, tokenHandle } from "../src/routes/connect.ts";
import { createD1Store, forgetLiveColumns } from "../src/connections/store.ts";
import { issueToken } from "../src/api/auth.ts";
import {
  connectionsApiRoute, CONNECTIONS_API_ROUTES, type ConnectionsApiDeps, type ConnectionsApiEnv,
} from "../src/routes/connections_api.ts";

const NOW = 1_789_000_000_000;
const OWNER = "owneroauth00001";
const OTHER = "owneroauth00002";
const TOOLKIT = "synthetic_mail";
const ACCOUNT = "ca_synthetic_recovery";
let passes = 0;
async function check(name: string, fn: () => Promise<void>) {
  await fn(); passes++; console.log("PASS " + name);
}
const MIGRATION = readFileSync(new URL("../../d1/2026-09-11-oauth-recovery.sql", import.meta.url), "utf8");
const RECOVERY_COLUMNS = ["recovery_account_id", "recovery_deadline", "recovery_next_check",
  "recovery_attempts", "recovery_lease"];
const RECOVERY_TRIGGERS = ["cancel_oauth_recovery_deleted_connection",
  "cancel_oauth_recovery_disconnected_connection",
  "cancel_oauth_recovery_decline_insert", "cancel_oauth_recovery_decline_update"];

/** THE DATABASE BEFORE THIS MIGRATION, BUILT ON PURPOSE.
 *
 * FakeD1 loads the real schema.sql, which now declares the recovery columns and
 * triggers — so a rig that applied the migration only "if the column is missing"
 * stopped applying it the day schema.sql gained them, silently, and every check
 * in this file ran against the fresh-install half. It would have passed with an
 * EMPTY migration file. Winding the fresh database back is the only way to hold
 * the upgrade path to the same standard, and it keeps the two databases
 * identical in every other respect, which is what makes comparing them mean
 * anything. The index goes before the columns: SQLite will not drop a column
 * anything still names.
 */
function windBack(db: FakeD1) {
  for (const name of RECOVERY_TRIGGERS) db.db.exec(`DROP TRIGGER IF EXISTS ${name}`);
  db.db.exec("DROP INDEX IF EXISTS idx_connect_links_recovery");
  for (const column of RECOVERY_COLUMNS) db.db.exec(`ALTER TABLE connect_links DROP COLUMN "${column}"`);
}

function rig(opts: { upgraded?: boolean } = {}) {
  const db = new FakeD1();
  if (opts.upgraded) {
    windBack(db);
    // No guard. A migration file that stopped creating something has to be a
    // hard failure here, not a quiet no-op.
    db.db.exec(MIGRATION);
  }
  for (const id of [OWNER, OTHER]) db.db.prepare("INSERT INTO owners(id,email,tokenKey) VALUES (?,?,?)").run(id, `${id}@example.invalid`, `synthetic-${id}`);
  const store = createRecoveryStore({ DB: asD1(db) });
  return { db, store };
}

/** Both builds, so a check written once holds for the fresh install and the
 *  upgraded database. `schema-migration-parity.test.ts` proves the two are
 *  declared the same; this proves they BEHAVE the same. */
const BUILDS: { label: string; make: () => ReturnType<typeof rig> }[] = [
  { label: "fresh schema.sql", make: () => rig() },
  { label: "upgraded by the migration file", make: () => rig({ upgraded: true }) },
];
async function arm(r: ReturnType<typeof rig>, token = "a".repeat(43), overrides = {}) {
  const handle = await tokenHandle(token);
  r.db.db.prepare("INSERT INTO connect_links(token_handle,user_id,toolkit,alias,expires_at,used_at) VALUES (?,?,?,?,?,?)")
    .run(handle, OWNER, TOOLKIT, "work", NOW + 600_000, NOW);
  assert.equal(await r.store.arm({ handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW, ...overrides }), true);
  return { handle, token };
}
function account(overrides = {}) { return { user_id: OWNER, toolkit: TOOLKIT, connected_account_id: ACCOUNT, status: "connected", alias: null, writes_enabled: false, last_used_at: null, ...overrides }; }
function rows(r: ReturnType<typeof rig>) { return r.db.rows("SELECT * FROM connections"); }

await check("dedicated minute cron is not the retired reminder schedule", async () => {
  assert.equal(RECOVERY_CRON, "* * * * *");
});
await check("45-second OAuth completion survives the original request ending", async () => {
  const r = rig(); await arm(r); let calls = 0;
  const first = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; return []; } } });
  assert.equal(first.activated, 0);
  // A different store models a later scheduled invocation, not retained memory.
  const second = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: createRecoveryStore({ DB: asD1(r.db) }), now: () => NOW + 60_000, provider: { connections: async () => { calls++; return [account()]; } } });
  assert.equal(second.activated, 1); assert.equal(calls, 2); assert.equal(rows(r).length, 1);
});
await check("empty pending queue spends no vendor call", async () => {
  const r = rig(); let calls = 0;
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; return []; } } });
  assert.equal(calls, 0);
});
await check("concurrent sweeps and callback activate once with one nudge", async () => {
  const r = rig(); const { handle } = await arm(r); let calls = 0;
  const opts = { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; return [account()]; } } };
  await Promise.all([recoverOAuthAttempts({ DB: asD1(r.db) }, opts), recoverOAuthAttempts({ DB: asD1(r.db) }, opts)]);
  assert.equal(calls, 1); assert.equal(rows(r).length, 1);
  assert.equal(await r.store.activate({ handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }), false);
  assert.equal(r.db.rows("SELECT * FROM connect_nudges").length, 1);
});
for (const [name, listed] of [
  ["different account", [account({ connected_account_id: "ca_other" })]],
  ["foreign owner", [account({ user_id: OTHER })]],
  ["different toolkit", [account({ toolkit: "synthetic_calendar" })]],
  ["expired credential", [account({ status: "needs_reconnect" })]],
  ["disconnected credential", [account({ status: "disconnected" })]],
  ["duplicate target", [account(), account()]],
  ["malformed list", null],
] as const) await check(name + " never activates", async () => {
  const r = rig(); await arm(r);
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => listed as never } });
  assert.equal(rows(r).length, 0); assert.equal(r.db.rows("SELECT * FROM connect_nudges").length, 0);
});
await check("provider unavailable releases lease with bounded backoff; no automatic send", async () => {
  const r = rig(); await arm(r); let calls = 0;
  const opts = { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; throw Error("synthetic unavailable"); } } };
  await recoverOAuthAttempts({ DB: asD1(r.db) }, opts); await recoverOAuthAttempts({ DB: asD1(r.db) }, opts);
  const [row] = r.db.rows("SELECT recovery_lease,recovery_attempts,recovery_next_check FROM connect_links");
  assert.equal(calls, 1); assert.equal(row.recovery_lease, null); assert.equal(row.recovery_attempts, 1);
  assert.ok(Number(row.recovery_next_check) > NOW); assert.equal(rows(r).length, 0);
});
await check("expired attempt costs no provider request", async () => {
  const r = rig(); await arm(r); let calls = 0;
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW + 600_001, provider: { connections: async () => { calls++; return [account()]; } } });
  assert.equal(calls, 0); assert.equal(rows(r).length, 0);
});
await check("failed activation batch rolls back completion and both tables", async () => {
  const r = rig(); const a = await arm(r);
  r.db.failOn = sql => sql.includes('INSERT INTO "connect_nudges"');
  await assert.rejects(r.store.activate({ handle: a.handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }));
  assert.equal(rows(r).length, 0); assert.equal(r.db.rows("SELECT completed_at FROM connect_links")[0].completed_at, null);
  r.db.failOn = null;
  assert.equal(await r.store.activate({ handle: a.handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW + 1 }), true);
});
await check("activation preserves existing permission, alias, last use and nudge history", async () => {
  const r = rig(); await arm(r);
  r.db.db.prepare("INSERT INTO connections VALUES (?,?,?,?,?,?,?)").run(ACCOUNT, OWNER, TOOLKIT, "personal", "needs_reconnect", 1, NOW - 1);
  r.db.db.prepare("INSERT INTO connect_nudges(user_id,toolkit,state,level,snooze_until,trigger,sent_at,acted_at,channel) VALUES (?,?,?,?,?,?,?,?,?)")
    .run(OWNER, TOOLKIT, "needs_reconnect", 2, NOW + 1000, "user_named_it", NOW - 5, NOW - 4, "ios");
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => [account()] } });
  const row = rows(r)[0]; assert.equal(row.writes_enabled, 1); assert.equal(row.alias, "personal"); assert.equal(row.last_used_at, NOW - 1);
  const nudge = r.db.rows("SELECT * FROM connect_nudges")[0]; assert.equal(nudge.level, 2); assert.equal(nudge.sent_at, NOW - 5); assert.equal(nudge.channel, "ios");
});
await check("disconnect during provider I/O cancels recovery before activation", async () => {
  const r = rig(); await arm(r);
  r.db.db.prepare("INSERT INTO connections VALUES (?,?,?,?,?,?,?)").run(ACCOUNT, OWNER, TOOLKIT, "work", "connected", 0, null);
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => { r.db.db.prepare("DELETE FROM connections WHERE connected_account_id=?").run(ACCOUNT); return [account()]; } } });
  assert.equal(rows(r).length, 0); assert.equal(r.db.rows("SELECT * FROM connect_nudges").length, 0);
});
await check("callback cannot report an expired account as connected", async () => {
  const r = rig(); const a = await arm(r); let writes = 0;
  const result = await connectPageDone(a.token, { status: "success", connectedAccountId: ACCOUNT }, {
    signedInAs: OWNER, now: NOW, recovery: r.store,
    store: { read: async () => r.db.rows("SELECT * FROM connect_links WHERE token_handle=?", a.handle)[0] as never,
      complete: async () => ({ won: true, row: null }) } as never,
    provider: { connections: async () => [account({ status: "needs_reconnect" })] as never }, onConnected: async () => { writes++; },
  });
  assert.notEqual(result.state, "connected"); assert.equal(writes, 0); assert.equal(rows(r).length, 0);
});

await check("new OAuth link journals exact provider ID before redirect; repeat creates no second link", async () => {
  const r = rig(); const token = "c".repeat(43), handle = await tokenHandle(token); let calls = 0;
  const store = createD1Store({ DB: asD1(r.db) });
  await store.put({ token_handle: handle, user_id: OWNER as never, toolkit: TOOLKIT, alias: "work", expires_at: NOW + 600000, used_at: null, completed_at: null });
  const opts = { signedInAs: OWNER, store, recovery: r.store, now: NOW, state: null, baseUrl: "https://fixture.invalid", provider: { authorize: async () => {
    calls++; return { redirectUrl: "https://provider.invalid/synthetic", connectedAccountId: ACCOUNT };
  } } };
  assert.equal((await connectPageGo(token, opts)).state, "ok");
  assert.equal((await r.store.read(handle))?.accountId, ACCOUNT);
  assert.equal((await connectPageGo(token, opts)).state, "already-used"); assert.equal(calls, 1);
});
await check("callback and scheduled recovery share actual atomic persistence", async () => {
  const r = rig(); const a = await arm(r); const store = createD1Store({ DB: asD1(r.db) });
  let legacyWrites = 0;
  const opts = { signedInAs: OWNER, store, recovery: r.store, now: NOW,
    provider: { connections: async () => [account()] as never }, onConnected: async () => { legacyWrites++; } };
  const [callback, sweep] = await Promise.all([
    connectPageDone(a.token, { status: "success", connectedAccountId: ACCOUNT }, opts),
    recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, provider: opts.provider, now: () => NOW }),
  ]);
  assert.equal(callback.state, "connected"); assert.equal(legacyWrites, 0);
  assert.equal(rows(r).length, 1); assert.equal(r.db.rows("SELECT * FROM connect_nudges").length, 1);
  assert.equal(Number(callback.state === "connected" && callback.recorded) + sweep.activated, 1);
});
await check("wrong callback account cannot finish the journaled attempt", async () => {
  const r = rig(); const a = await arm(r);
  const result = await connectPageDone(a.token, { status: "success", connectedAccountId: "ca_other" }, {
    signedInAs: OWNER, store: createD1Store({ DB: asD1(r.db) }), recovery: r.store, now: NOW,
    provider: { connections: async () => [account({ connected_account_id: "ca_other" })] as never }, onConnected: async () => { throw Error("legacy path"); },
  });
  assert.equal(result.state, "not-connected"); assert.equal(rows(r).length, 0);
});
await check("callback rechecks deadline after vendor I/O", async () => {
  const r = rig(); const a = await arm(r);
  const result = await connectPageDone(a.token, { status: "success", connectedAccountId: ACCOUNT }, {
    signedInAs: OWNER, store: createD1Store({ DB: asD1(r.db) }), recovery: r.store, now: NOW,
    commitClock: () => NOW + 600001,
    provider: { connections: async () => [account()] as never }, onConnected: async () => { throw Error("legacy path"); },
  });
  assert.equal(result.state, "not-recorded"); assert.equal(rows(r).length, 0);
});
await check("missing migration refuses before the provider is called", async () => {
  const r = rig(); const a = await arm(r); let calls = 0;
  const missing = { ...r.store, ready: async () => { throw Error("migration missing"); } };
  const result = await connectPageGo(a.token, { signedInAs: OWNER, store: createD1Store({ DB: asD1(r.db) }), recovery: missing,
    now: NOW, state: null, baseUrl: "https://fixture.invalid", provider: { authorize: async () => { calls++; throw Error("must not call"); } } });
  assert.equal(result.state, "provider-unavailable"); assert.equal(calls, 0);
});
await check("process death after claim is recovered after lease expiry", async () => {
  const r = rig(); const a = await arm(r);
  assert.equal(await r.store.claim({ ...a, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }, "1".repeat(64)), true);
  let calls = 0; const provider = { connections: async () => { calls++; return [account()] as never; } };
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, provider, now: () => NOW + 60000 });
  assert.equal(calls, 0);
  const report = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, provider, now: () => NOW + 90000 });
  assert.equal(report.activated, 1); assert.equal(calls, 1);
});
await check("stale lease cannot activate or release a newer claim", async () => {
  const r = rig(); const a = await arm(r); const input = { ...a, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW };
  assert.equal(await r.store.claim(input, "1".repeat(64)), true);
  assert.equal(await r.store.claim({ ...input, now: NOW + 90000 }, "2".repeat(64)), true);
  assert.equal(await r.store.activate({ ...input, now: NOW + 90000 }, "1".repeat(64)), false);
  await r.store.defer({ ...input, now: NOW + 90000 }, "1".repeat(64), false);
  assert.equal(r.db.rows("SELECT recovery_lease FROM connect_links")[0].recovery_lease, "2".repeat(64));
});
await check("explicit skip cancels even an already-declined attempt before provider return", async () => {
  const r = rig(); const a = await arm(r); const store = createD1Store({ DB: asD1(r.db) });
  // Prior decline predates a new connect. It need not update again on Skip.
  r.db.db.prepare("INSERT INTO connect_nudges(user_id,toolkit,state,level) VALUES (?,?,'declined',1)").run(OWNER, TOOLKIT);
  r.db.db.prepare("UPDATE connect_links SET recovery_deadline=?").run(NOW + 600000);
  await connectPageSkip(a.token, { signedInAs: OWNER, store, recovery: r.store, now: NOW });
  assert.equal(await r.store.activate({ ...a, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }), false);
  assert.equal(rows(r).length, 0);
});
// Renamed 2026-09-11. It was called "purged owner and malformed persisted
// metadata fail closed" and contained no purge at all — a name that made a
// missing case look covered, which is worse than an absent test. The purge is
// now its own check below.
await check("malformed persisted recovery metadata fails closed", async () => {
  const r = rig(); const a = await arm(r); let calls = 0;
  r.db.db.prepare("UPDATE connect_links SET recovery_account_id='bad account'").run();
  await assert.rejects(r.store.read(a.handle), /metadata/);
  await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; return [account()] as never; } } });
  assert.equal(calls, 0);
});
await check("an owner who asked to be erased is never read, armed or activated", async () => {
  const r = rig(); const a = await arm(r); let calls = 0;
  // A second, un-armed link, written BEFORE the purge lands: schema.sql's own
  // erasure fence refuses an INSERT for an owner who already has a purges row,
  // so building this afterwards would be testing that fence instead of this one.
  const second = "z".repeat(43), handle = await tokenHandle(second);
  r.db.db.prepare("INSERT INTO connect_links(token_handle,user_id,toolkit,alias,expires_at,used_at) VALUES (?,?,?,?,?,?)")
    .run(handle, OWNER, "synthetic_notes", "work", NOW + 600_000, NOW);
  r.db.db.prepare("INSERT INTO purges(id,owner_ref,legacy_uuid,requested_at,memory_purged) VALUES (?,?,?,?,?)")
    .run("purge-1", OWNER, "", NOW, 0);
  const report = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW,
    provider: { connections: async () => { calls++; return [account()] as never; } } });
  assert.equal(report.checked, 0, "a purged owner must not even be listed as due");
  assert.equal(calls, 0, "no vendor call may be made on behalf of a purged owner");
  assert.equal(rows(r).length, 0);
  assert.equal(await r.store.arm({ handle, owner: OWNER, toolkit: "synthetic_notes", accountId: ACCOUNT, now: NOW }), false,
    "a purged owner must not be able to start a new attempt");
  assert.equal(await r.store.claim({ handle: a.handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }, "1".repeat(64)), false,
    "a purged owner's existing attempt must not be claimable");
});
// ---------------------------------------------------------------------------
// THE PHONE'S SKIP DOOR — POST /me/connections/skip (2026-09-12, OMNI-1).
//
// The page door above cancels through `recovery.cancel(handle)`. The phone
// holds no handle: its Skip is a toolkit slug and a bearer token, and until
// this date the door relied on the decline TRIGGERS alone — which fire only
// when `recordSkip` writes a `connect_nudges` row. Two of its branches write
// nothing (`already-declined`, `nothing-to-decline`), answered 200, and left
// the attempt armed: the minute cron then connected the account the person
// had just turned down. The iOS caller is gated off today
// (`ConnectOnboardingPolicy.serverRecordsTheSoftSnooze = false`), which is
// why nobody was bitten; the door is fixed before the gate opens.
// ---------------------------------------------------------------------------
const FOURTEEN_DAYS = 14 * 24 * 60 * 60 * 1000;
const SKIP_PATH = CONNECTIONS_API_ROUTES.skip;
async function skipRig(seedNudge: { state: string; level: number; snooze: number | null } | null,
  depsOverride?: (deps: ConnectionsApiDeps) => ConnectionsApiDeps) {
  const r = rig();
  const env = { DB: asD1(r.db), ANTICIPY_AUTH_SECRET: "skip-api-recovery-secret" } as unknown as ConnectionsApiEnv;
  forgetLiveColumns(env as never);
  // ORDER IS THE REAL ORDER: a standing nudge row predates the new connect,
  // exactly as "explicit skip cancels even an already-declined attempt" seeds
  // it. Seeding it after the link would fire the decline trigger on the seed
  // itself and test nothing.
  if (seedNudge) {
    r.db.db.prepare("INSERT INTO connect_nudges(user_id,toolkit,state,level,acted_at,snooze_until) VALUES (?,?,?,?,?,?)")
      .run(OWNER, TOOLKIT, seedNudge.state, seedNudge.level, NOW - 60_000, seedNudge.snooze);
  }
  const a = await arm(r, "s".repeat(43));
  const full: ConnectionsApiDeps = {
    store: createD1Store(env as never),
    provider: {
      toolkit: async () => { throw new Error("catalog not needed for /skip"); },
      connections: async () => [],
      disconnect: async () => ({ revoked: false, deleted: false, revokeUnavailable: true }),
    },
    words: { sentences: async () => [] },
    recovery: r.store,
    now: () => NOW,
  } as unknown as ConnectionsApiDeps;
  const deps = depsOverride ? depsOverride(full) : full;
  const token = await issueToken(env as never, OWNER, `synthetic-${OWNER}`);
  const skip = () => connectionsApiRoute(new Request("https://api.anticipy.ai" + SKIP_PATH, {
    method: "POST", headers: { "content-type": "application/json", Authorization: token },
    body: JSON.stringify({ toolkit: TOOLKIT }),
  }), env, deps);
  // What the minute cron does next: the vendor reports the account ACTIVE (the
  // person finished at the vendor before tapping Skip in the app).
  const cron = () => recoverOAuthAttempts({ DB: asD1(r.db) }, { store: createRecoveryStore({ DB: asD1(r.db) }),
    now: () => NOW + 30_000, provider: { connections: async () => [account()] } });
  return { r, a, env, deps, skip, cron };
}
for (const [name, seed, state] of [
  ["a first tap (recorded — the trigger path, the control)", null, "recorded"],
  ["a second tap inside a standing snooze (already-declined — writes no row)",
    { state: "declined", level: 1, snooze: NOW + FOURTEEN_DAYS }, "already-declined"],
  ["an app whose first account is connected (nothing-to-decline — writes no row)",
    { state: "connected", level: 0, snooze: null }, "nothing-to-decline"],
] as const) await check(`the phone's Skip cancels the armed attempt on ${name}`, async () => {
  const s = await skipRig(seed);
  const res = await s.skip();
  assert.equal(res.status, 200);
  assert.equal(((await res.json()) as { state: string }).state, state);
  assert.deepEqual(await s.r.store.due(NOW + 1), [], "the attempt is still due after the owner's Skip was answered 200");
  assert.equal((await s.cron()).activated, 0, "the next minute cron connected the account the owner just declined");
  assert.equal(rows(s.r).length, 0);
  assert.equal(await s.r.store.activate({ handle: s.a.handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }), false,
    "a late vendor callback must not revive what the owner declined");
});
await check("the phone's Skip cancels only this app's attempt, and never an unopened link", async () => {
  const s = await skipRig(null);
  // A second armed attempt on ANOTHER app, and an unopened link on THIS app.
  const otherHandle = await tokenHandle("t".repeat(43));
  s.r.db.db.prepare("INSERT INTO connect_links(token_handle,user_id,toolkit,alias,expires_at,used_at) VALUES (?,?,?,?,?,?)")
    .run(otherHandle, OWNER, "synthetic_calendar", "work", NOW + 600_000, NOW);
  assert.equal(await s.r.store.arm({ handle: otherHandle, owner: OWNER, toolkit: "synthetic_calendar", accountId: "ca_other_app", now: NOW }), true);
  const unopened = await tokenHandle("u".repeat(43));
  s.r.db.db.prepare("INSERT INTO connect_links(token_handle,user_id,toolkit,alias,expires_at) VALUES (?,?,?,?,?)")
    .run(unopened, OWNER, TOOLKIT, "work", NOW + 600_000);
  assert.equal((await s.skip()).status, 200);
  const due = await s.r.store.due(NOW + 1);
  assert.deepEqual(due.map(d => d.handle), [otherHandle], "the other app's attempt must stay armed");
  const link = s.r.db.rows("SELECT recovery_deadline FROM connect_links WHERE token_handle=?", unopened)[0];
  assert.equal(link.recovery_deadline, null, "an unopened link belongs to an owner who may still change their mind");
});
await check("a Skip door with no recovery fence wired answers 503 and writes no ladder rung", async () => {
  // Absence is not "nothing to cancel". A skip that could not fence the cron
  // has not landed, and the phone must not be told it has.
  const s = await skipRig(null, deps => { const { recovery: _r, ...rest } = deps; return rest as ConnectionsApiDeps; });
  const res = await s.skip();
  assert.equal(res.status, 503);
  assert.equal(s.r.db.rows("SELECT * FROM connect_nudges").length, 0, "the ladder must not move when the fence could not go up");
  assert.equal((await s.r.store.due(NOW + 1)).length, 1, "the honest state: the attempt IS still armed, and the phone was told so");
});
await check("a fence that throws answers 503 before the ladder is read", async () => {
  let reads = 0;
  const s = await skipRig(null, deps => ({
    ...deps,
    store: new Proxy(deps.store, { get(t, k, rcv) { if (k === "readNudge" || k === "putNudge") reads++; return Reflect.get(t, k, rcv); } }),
    recovery: { cancelToolkit: async () => { throw new Error("synthetic D1 outage"); } },
  }));
  assert.equal((await s.skip()).status, 503);
  assert.equal(reads, 0, "the ladder was consulted before the fence was known to be up");
  assert.equal(s.r.db.rows("SELECT * FROM connect_nudges").length, 0);
});
await check("cancelToolkit refuses a malformed owner or toolkit without touching the database", async () => {
  const s = await skipRig(null);
  s.r.db.failOn = () => true;
  await s.r.store.cancelToolkit("not an owner", TOOLKIT);
  await s.r.store.cancelToolkit(OWNER, "not a toolkit!");
  s.r.db.failOn = null;
  assert.equal((await s.r.store.due(NOW + 1)).length, 1);
});
await check("cancelToolkit does nothing for an owner who asked to be erased", async () => {
  const s = await skipRig(null);
  s.r.db.db.prepare("INSERT INTO purges(id,owner_ref,legacy_uuid,requested_at,memory_purged) VALUES (?,?,?,?,?)")
    .run("purge-skip", OWNER, "", NOW, 0);
  await s.r.store.cancelToolkit(OWNER, TOOLKIT);
  const [row] = s.r.db.rows("SELECT recovery_deadline FROM connect_links WHERE token_handle=?", s.a.handle);
  assert.notEqual(row.recovery_deadline, 0, "a purged owner's rows are the erasure's to touch, not this door's");
});

await check("erasing an account is not blocked by the cancellation triggers", async () => {
  // The trigger bodies UPDATE connect_links, and the erasure fence RAISEs ABORT
  // on that table for any owner holding a purges row. Without the NOT EXISTS
  // clause in the triggers this DELETE aborts and the owner can never be
  // erased — measured on 2026-09-11, not theorised.
  const r = rig(); await arm(r);
  r.db.db.prepare("INSERT INTO connections VALUES (?,?,?,?,?,?,?)").run(ACCOUNT, OWNER, TOOLKIT, "work", "connected", 0, null);
  r.db.db.exec(readFileSync(new URL("../../d1/2026-09-07-account-erasure-fence.sql", import.meta.url), "utf8"));
  r.db.db.prepare("INSERT INTO purges(id,owner_ref,legacy_uuid,requested_at,memory_purged) VALUES (?,?,?,?,?)")
    .run("purge-1", OWNER, "", NOW, 0);
  r.db.db.exec(`DELETE FROM connections WHERE connected_account_id='${ACCOUNT}'`);
  assert.equal(rows(r).length, 0);
});
await check("a decline does not poison a link the owner has not opened yet", async () => {
  // The decline triggers are scoped to REDEEMED links. An unopened one belongs
  // to an owner who may still change their mind, and arm() refuses forever once
  // recovery_deadline is set, so poisoning it costs a tap and a vendor call.
  const r = rig(); const token = "y".repeat(43), handle = await tokenHandle(token);
  r.db.db.prepare("INSERT INTO connect_links(token_handle,user_id,toolkit,alias,expires_at,used_at) VALUES (?,?,?,?,?,?)")
    .run(handle, OWNER, TOOLKIT, "work", NOW + 600_000, null);
  r.db.db.prepare("INSERT INTO connect_nudges(user_id,toolkit,state) VALUES (?,?,?)").run(OWNER, TOOLKIT, "declined_soft");
  assert.equal(r.db.rows("SELECT recovery_deadline FROM connect_links")[0].recovery_deadline, null);
  r.db.db.prepare("UPDATE connect_links SET used_at=?").run(NOW);
  assert.equal(await r.store.arm({ handle, owner: OWNER, toolkit: TOOLKIT, accountId: ACCOUNT, now: NOW }), true);
});
for (const build of BUILDS) {
  await check(`[${build.label}] a disconnect during provider.authorize refuses the arm`, async () => {
    // The PRE-ARM window: the link is redeemed and recovery_account_id is still
    // NULL, because arm() runs only after the vendor returns. An account-only
    // cancellation predicate cannot see this row, and the minute cron would
    // reconnect the app the owner just removed.
    const r = build.make(); const token = "w".repeat(43), handle = await tokenHandle(token);
    const store = createD1Store({ DB: asD1(r.db) });
    await store.put({ token_handle: handle, user_id: OWNER as never, toolkit: TOOLKIT, alias: "work",
      expires_at: NOW + 600_000, used_at: null, completed_at: null });
    r.db.db.prepare("INSERT INTO connections VALUES (?,?,?,?,?,?,?)").run(ACCOUNT, OWNER, TOOLKIT, "work", "connected", 0, null);
    const result = await connectPageGo(token, { signedInAs: OWNER, store, recovery: r.store, now: NOW,
      state: null, baseUrl: "https://fixture.invalid", provider: { authorize: async () => {
        r.db.db.prepare("DELETE FROM connections WHERE connected_account_id=?").run(ACCOUNT);
        return { redirectUrl: "https://provider.invalid/synthetic", connectedAccountId: ACCOUNT };
      } } });
    assert.equal(result.state, "provider-unavailable", "an arm the disconnect fenced must not redirect");
    assert.equal(r.db.rows("SELECT recovery_account_id FROM connect_links")[0].recovery_account_id, null);
    let calls = 0;
    const report = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW + 60_000,
      provider: { connections: async () => { calls++; return [account()] as never; } } });
    assert.equal(report.activated, 0); assert.equal(calls, 0);
    assert.equal(rows(r).length, 0, "the minute cron re-created a connection the owner removed");
  });
  await check(`[${build.label}] a genuinely missing migration refuses before the vendor is called`, async () => {
    // Not a stubbed `ready`: the real checkReady against a real pre-migration
    // database, which is the only thing that proves the deploy ordering.
    const db = new FakeD1(); windBack(db);
    db.db.prepare("INSERT INTO owners(id,email,tokenKey) VALUES (?,?,?)").run(OWNER, "x@example.invalid", "k");
    const store = createRecoveryStore({ DB: asD1(db) });
    await assert.rejects(store.ready(), /migration is required/);
    const token = "v".repeat(43);
    const links = createD1Store({ DB: asD1(db) });
    await links.put({ token_handle: await tokenHandle(token), user_id: OWNER as never, toolkit: TOOLKIT,
      alias: "work", expires_at: NOW + 600_000, used_at: null, completed_at: null });
    let calls = 0;
    const result = await connectPageGo(token, { signedInAs: OWNER, store: links, recovery: store, now: NOW,
      state: null, baseUrl: "https://fixture.invalid",
      provider: { authorize: async () => { calls++; throw Error("must not call"); } } });
    assert.equal(result.state, "provider-unavailable"); assert.equal(calls, 0);
  });
}
await check("columns without triggers is not ready — a half-applied migration must not look fine", async () => {
  const db = new FakeD1();
  for (const name of RECOVERY_TRIGGERS) db.db.exec(`DROP TRIGGER ${name}`);
  const store = createRecoveryStore({ DB: asD1(db) });
  await assert.rejects(store.ready(), /migration is required/,
    "the columns alone advertised a database with no cancellation fence as ready");
});
await check("bounded sweep claims at most four due rows", async () => {
  const r = rig();
  for (const letter of ["d", "e", "f", "g", "h", "i"]) await arm(r, letter.repeat(43));
  let calls = 0;
  const report = await recoverOAuthAttempts({ DB: asD1(r.db) }, { store: r.store, now: () => NOW, provider: { connections: async () => { calls++; return []; } } });
  assert.equal(report.checked, 4); assert.equal(calls, 4);
});

console.log(`${passes} recovery checks passed`);
