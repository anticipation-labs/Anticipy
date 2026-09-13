/** Durable, exact-attempt OAuth recovery. No timers, messages, tool execution,
 * or account-wide reconciliation. Every vendor call is an owner-scoped read.
 * A later cron invocation resumes persisted attempts after the redirect dies.
 */
import type { CatalogProvider, Connection } from "../routes/connect.ts";
import { connectionsFromEnv } from "./provider.ts";

export const RECOVERY_CRON = "* * * * *";
export const RECOVERY_WINDOW_MS = 10 * 60_000;
export const RECOVERY_BATCH = 4;
export const RECOVERY_MAX_ATTEMPTS = 16;
export const RECOVERY_LEASE_MS = 90_000;
const OWNER = /^[a-z0-9]{15}$/;
const HANDLE = /^[a-f0-9]{64}$/;
const ACCOUNT = /^[A-Za-z0-9_-]{1,256}$/;
const TOOLKIT = /^[a-z0-9_-]{1,128}$/;
const RECOVERY_COLUMNS = ["recovery_account_id", "recovery_deadline", "recovery_next_check", "recovery_attempts", "recovery_lease"];
/** THE COLUMNS ARE HALF THE MIGRATION AND THE WEAKER HALF.
 *
 * 2026-09-11-oauth-recovery.sql is five ALTERs followed by an index and these
 * four triggers, and a plain ALTER ADD COLUMN is not rerunnable — so a first
 * apply interrupted after the columns leaves a database that a columns-only
 * readiness check calls READY while nothing cancels a disconnect. That is worse
 * than an unapplied migration, because an unapplied one fails closed and this
 * one runs OAuth recovery with no fence at all. Readiness asks for both halves.
 */
const RECOVERY_TRIGGERS = ["cancel_oauth_recovery_deleted_connection",
  "cancel_oauth_recovery_disconnected_connection",
  "cancel_oauth_recovery_decline_insert", "cancel_oauth_recovery_decline_update"];

export interface RecoveryEnv { DB: D1Database; COMPOSIO_API_KEY?: string; CONNECT_WAIT_MS?: unknown }
export interface AttemptIdentity { handle: string; owner: string; toolkit: string; accountId: string; now: number }
export interface RecoveryAttempt { handle: string; owner: string; toolkit: string; accountId: string; deadline: number; attempts: number }
export interface RecoveryStore {
  ready(): Promise<void>;
  arm(input: AttemptIdentity): Promise<boolean>;
  read(handle: string): Promise<RecoveryAttempt | null>;
  due(now: number, handle?: string): Promise<RecoveryAttempt[]>;
  claim(input: AttemptIdentity, lease: string): Promise<boolean>;
  defer(input: AttemptIdentity, lease: string, failed: boolean): Promise<void>;
  activate(input: AttemptIdentity, lease?: string): Promise<boolean>;
  confirmed(input: AttemptIdentity): Promise<boolean>;
  cancel(handle: string, owner: string): Promise<void>;
  /** Every in-flight attempt this owner has on one toolkit, cancelled. The
   *  API Skip door (POST /me/connections/skip) holds no link handle — the
   *  phone never saw one — so it cancels by owner and toolkit, the same
   *  predicate the decline triggers use. Only REDEEMED links are touched:
   *  an unopened one belongs to an owner who may still change their mind. */
  cancelToolkit(owner: string, toolkit: string): Promise<void>;
}
function valid(input: AttemptIdentity): boolean {
  return !!input && typeof input === "object"
    && [input.handle, input.owner, input.toolkit, input.accountId].every(v => typeof v === "string")
    && HANDLE.test(input.handle) && OWNER.test(input.owner) && TOOLKIT.test(input.toolkit)
    && ACCOUNT.test(input.accountId) && Number.isSafeInteger(input.now) && input.now > 0;
}
function attempt(row: Record<string, unknown> | null): RecoveryAttempt | null {
  if (!row) return null;
  const input = { handle: row.token_handle, owner: row.user_id, toolkit: row.toolkit,
    accountId: row.recovery_account_id, now: row.used_at };
  if (Object.values(input).some(v => v === null || v === undefined)) return null;
  if (!valid(input as AttemptIdentity) || typeof row.recovery_deadline !== "number"
      || !Number.isSafeInteger(row.recovery_deadline) || typeof row.recovery_attempts !== "number"
      || !Number.isInteger(row.recovery_attempts) || row.recovery_attempts < 0 || row.recovery_attempts > RECOVERY_MAX_ATTEMPTS) return null;
  return { handle: input.handle as string, owner: input.owner as string, toolkit: input.toolkit as string,
    accountId: input.accountId as string, deadline: row.recovery_deadline, attempts: row.recovery_attempts };
}

export function createRecoveryStore(env: Pick<RecoveryEnv, "DB">): RecoveryStore {
  // Per-object metadata cache only; no owner's credential/data is cached.
  let ready = false;
  const checkReady = async () => {
    if (ready) return;
    const result = await env.DB.prepare("PRAGMA table_info(connect_links)").all<{ name: string }>();
    const columns = new Set((result.results ?? []).map(r => r.name));
    if (!RECOVERY_COLUMNS.every(c => columns.has(c))) throw new Error("OAuth recovery migration is required");
    const made = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type='trigger' AND name IN (?1,?2,?3,?4)")
      .bind(...RECOVERY_TRIGGERS).all<{ name: string }>();
    const triggers = new Set((made.results ?? []).map(r => r.name));
    if (!RECOVERY_TRIGGERS.every(t => triggers.has(t))) throw new Error("OAuth recovery migration is required");
    ready = true;
  };
  const eligible = `r.token_handle=?1 AND r.user_id=?2 AND r.toolkit=?3 AND r.recovery_account_id=?4
    AND r.used_at IS NOT NULL AND r.used_at<=?5 AND r.completed_at IS NULL
    AND r.recovery_deadline>?5 AND r.recovery_deadline<=r.used_at+${RECOVERY_WINDOW_MS}
    AND EXISTS(SELECT 1 FROM owners WHERE id=r.user_id)
    AND NOT EXISTS(SELECT 1 FROM purges WHERE owner_ref=r.user_id)`;
  const args = (i: AttemptIdentity) => [i.handle, i.owner, i.toolkit, i.accountId, i.now];
  return {
    ready: checkReady,
    async arm(input) {
      if (!valid(input)) return false;
      await checkReady();
      const result = await env.DB.prepare(`UPDATE connect_links
        SET recovery_account_id=?4, recovery_deadline=MIN(used_at+?6,?5+?6),
            recovery_next_check=?5, recovery_attempts=0, recovery_lease=NULL
        WHERE token_handle=?1 AND user_id=?2 AND toolkit=?3 AND used_at IS NOT NULL
          AND used_at<=?5 AND used_at+?6>?5 AND completed_at IS NULL AND recovery_account_id IS NULL AND recovery_deadline IS NULL
          AND EXISTS(SELECT 1 FROM owners WHERE id=?2)
          AND NOT EXISTS(SELECT 1 FROM purges WHERE owner_ref=?2)`)
        .bind(...args(input), RECOVERY_WINDOW_MS).run();
      return Number(result.meta?.changes) === 1;
    },
    async read(handle) {
      if (!HANDLE.test(handle)) return null;
      await checkReady();
      const row = await env.DB.prepare("SELECT * FROM connect_links WHERE token_handle=?1").bind(handle).first<Record<string, unknown>>();
      const found = attempt(row);
      if (row?.recovery_account_id !== null && row?.recovery_account_id !== undefined && !found) {
        throw new Error("OAuth recovery metadata is invalid");
      }
      return found;
    },
    async due(now, handle) {
      if (!Number.isSafeInteger(now) || now <= 0 || (handle !== undefined && !HANDLE.test(handle))) return [];
      await checkReady();
      const rows = await env.DB.prepare(`SELECT r.* FROM connect_links r
        WHERE r.recovery_account_id IS NOT NULL AND r.completed_at IS NULL
          AND r.recovery_next_check<=?1 AND r.recovery_deadline>?1
          AND r.used_at<=?1 AND r.recovery_deadline<=r.used_at+${RECOVERY_WINDOW_MS}
          AND r.recovery_attempts<${RECOVERY_MAX_ATTEMPTS}
          AND EXISTS(SELECT 1 FROM owners WHERE id=r.user_id)
          AND NOT EXISTS(SELECT 1 FROM purges WHERE owner_ref=r.user_id)
          ${handle ? "AND r.token_handle=?2" : ""}
        ORDER BY r.recovery_next_check,r.token_handle LIMIT ${RECOVERY_BATCH}`)
        .bind(...(handle ? [now, handle] : [now])).all<Record<string, unknown>>();
      return (rows.results ?? []).map(attempt).filter((row): row is RecoveryAttempt => row !== null);
    },
    async claim(input, lease) {
      if (!valid(input) || !HANDLE.test(lease)) return false;
      await checkReady();
      const result = await env.DB.prepare(`UPDATE connect_links AS r
        SET recovery_lease=?6,recovery_next_check=?5+${RECOVERY_LEASE_MS},recovery_attempts=recovery_attempts+1
        WHERE ${eligible} AND r.recovery_next_check<=?5 AND r.recovery_attempts<${RECOVERY_MAX_ATTEMPTS}`)
        .bind(...args(input), lease).run();
      return Number(result.meta?.changes) === 1;
    },
    async defer(input, lease, failed) {
      if (!valid(input) || !HANDLE.test(lease)) return;
      // Only the current lease can schedule another read. Never reset attempts,
      // the exact target, or completed/cancelled state after an uncertain write.
      await env.DB.prepare(`UPDATE connect_links AS r SET recovery_lease=NULL,
        recovery_next_check=?5+CASE WHEN ?7=0 THEN 60000
          WHEN recovery_attempts<=1 THEN 60000 WHEN recovery_attempts=2 THEN 120000
          WHEN recovery_attempts=3 THEN 240000 ELSE 300000 END
        WHERE ${eligible} AND r.recovery_lease=?6`)
        .bind(...args(input), lease, failed ? 1 : 0).run();
    },
    async activate(input, lease) {
      if (!valid(input) || (lease !== undefined && !HANDLE.test(lease))) return false;
      await checkReady();
      const guard = eligible + (lease ? " AND r.recovery_lease=?6" : "");
      const bound = lease ? [...args(input), lease] : args(input);
      const connection = env.DB.prepare(`INSERT INTO "connections"
        (connected_account_id,user_id,toolkit,alias,status,writes_enabled,last_used_at)
        SELECT r.recovery_account_id,r.user_id,r.toolkit,r.alias,'connected',0,NULL FROM connect_links r WHERE ${guard}
        ON CONFLICT(connected_account_id) DO UPDATE SET status='connected'
          WHERE connections.user_id=excluded.user_id AND connections.toolkit=excluded.toolkit`).bind(...bound);
      const connected = `EXISTS(SELECT 1 FROM connections c WHERE c.connected_account_id=?4
        AND c.user_id=?2 AND c.toolkit=?3 AND c.status='connected')`;
      const nudge = env.DB.prepare(`INSERT INTO "connect_nudges" (user_id,toolkit,state,level,acted_at)
        SELECT r.user_id,r.toolkit,'connected',0,?5 FROM connect_links r WHERE ${guard} AND ${connected}
        ON CONFLICT(user_id,toolkit) DO UPDATE SET state='connected',acted_at=excluded.acted_at`).bind(...bound);
      const finish = env.DB.prepare(`UPDATE connect_links AS r SET completed_at=?5,recovery_lease=NULL
        WHERE ${guard} AND ${connected}`).bind(...bound);
      const result = await env.DB.batch([connection, nudge, finish]);
      return Number(result[2]?.meta?.changes) === 1;
    },
    async confirmed(input) {
      if (!valid(input)) return false;
      const row = await env.DB.prepare(`SELECT 1 AS confirmed FROM connect_links r JOIN connections c
        ON c.connected_account_id=r.recovery_account_id AND c.user_id=r.user_id AND c.toolkit=r.toolkit
        WHERE r.token_handle=?1 AND r.user_id=?2 AND r.toolkit=?3 AND r.recovery_account_id=?4
          AND r.completed_at IS NOT NULL AND c.status='connected'
          AND NOT EXISTS(SELECT 1 FROM purges WHERE owner_ref=r.user_id)`)
        .bind(input.handle, input.owner, input.toolkit, input.accountId).first();
      return row !== null;
    },
    async cancel(handle, owner) {
      if (typeof handle !== "string" || !HANDLE.test(handle) || typeof owner !== "string" || !OWNER.test(owner)) return;
      await checkReady();
      await env.DB.prepare(`UPDATE connect_links SET recovery_deadline=0,recovery_lease=NULL
        WHERE token_handle=?1 AND user_id=?2 AND completed_at IS NULL`).bind(handle, owner).run();
    },
    async cancelToolkit(owner, toolkit) {
      if (!OWNER.test(owner) || !TOOLKIT.test(toolkit)) return;
      await checkReady();
      await env.DB.prepare(`UPDATE connect_links SET recovery_deadline=0, recovery_lease=NULL
        WHERE user_id=?1 AND toolkit=?2 AND completed_at IS NULL AND used_at IS NOT NULL
          AND NOT EXISTS(SELECT 1 FROM purges WHERE owner_ref=?1)`).bind(owner, toolkit).run();
    },
  };
}

/** ACTIVE exact account only. An arbitrary new account or mixed-owner list is
 * not evidence for this OAuth attempt, even if it happens to use the same app. */
export function activeAttempt(list: unknown, wanted: RecoveryAttempt): boolean {
  if (!Array.isArray(list)) return false;
  let targets = 0;
  for (const item of list as Partial<Connection>[]) {
    if (!item || typeof item !== "object" || item.user_id !== wanted.owner
        || typeof item.connected_account_id !== "string" || typeof item.toolkit !== "string") return false;
    if (item.connected_account_id === wanted.accountId) {
      if (item.toolkit !== wanted.toolkit || item.status !== "connected") return false;
      targets++;
    }
  }
  return targets === 1;
}
function leaseToken(): string {
  return [...crypto.getRandomValues(new Uint8Array(32))].map(v => v.toString(16).padStart(2, "0")).join("");
}
export async function recoverOAuthAttempts(env: RecoveryEnv, injected?: {
  store?: RecoveryStore; provider?: Pick<CatalogProvider, "connections">; now?: () => number; handle?: string;
}): Promise<{ checked: number; activated: number; unavailable: number }> {
  const report = { checked: 0, activated: 0, unavailable: 0 };
  if (env.CONNECT_WAIT_MS === 0 || env.CONNECT_WAIT_MS === "0") return report;
  const store = injected?.store ?? createRecoveryStore(env);
  const now = injected?.now ?? Date.now;
  const due = await store.due(now(), injected?.handle);
  // Do not instantiate the vendor or inspect credentials when no work is due.
  if (!due.length) return report;
  const provider = injected?.provider ?? connectionsFromEnv(env);
  for (const row of due) {
    const lease = leaseToken();
    const input = { ...row, now: now() };
    if (!await store.claim(input, lease)) continue;
    report.checked++;
    let failed = false;
    try {
      const listed = await provider.connections(row.owner as never);
      if (activeAttempt(listed, row)) {
        if (await store.activate({ ...input, now: now() }, lease)) report.activated++;
      }
    } catch {
      failed = true; report.unavailable++;
    } finally {
      // A failed defer only delays the next read until the persisted lease
      // expires; no effect is replayed and activation remains one transaction.
      try { await store.defer({ ...input, now: now() }, lease, failed); } catch { /* lease expires */ }
    }
  }
  return report;
}
