/**
 * src/cron.ts — the two cronAdd jobs, as Cron Triggers.
 *
 *   cronAdd("internal_hq_sweep",  "*\/5 * * * *")   internal_hq.pb.js:2139
 *   cronAdd("internal_hq_prune",  "17 4 * * *")     internal_hq.pb.js:2642
 *
 * Cloudflare's `scheduled` handler receives `event.cron` — the literal
 * schedule string from wrangler.jsonc — so one Worker carries both and
 * dispatches on it. There is no per-trigger entrypoint.
 *
 * THREE DIFFERENCES FROM PocketBase's SCHEDULER THAT CHANGE THE CODE:
 *
 * 1. CRON TRIGGERS ARE UTC, ALWAYS. PocketBase's cron runs in the container's
 *    timezone. `17 4 * * *` is 04:17 in whatever TZ the Railway container had.
 *    Confirm that container's TZ before assuming the prune keeps its hour;
 *    it prunes on a 60-day cutoff so an hour's drift is harmless, but the
 *    SWEEP sends SMS reminders and an hour matters there.
 *    → marked UNVERIFIED in ARCHITECTURE.md.
 *
 * 2. NO SHARED PROCESS MEMORY, so anything the sweep kept between ticks has to
 *    live in D1 or a DO. (The sweep as written keeps nothing; verified by
 *    reading internal_hq.pb.js:2139-2636 — every piece of state is a row.)
 *
 * 3. WALL-CLOCK AND SUBREQUEST BUDGET. The sweep sends Twilio messages in a
 *    loop (`sendSMS`, internal_hq.pb.js:2165-2181). Each send is one
 *    subrequest. A tick that has 200 reminders due makes 200 of them.
 *    See ARCHITECTURE.md §7 for the limit and the batching this needs.
 */
import { pbNow } from "./pb/wire.ts";

export interface CronEnv {
  DB: D1Database;
  TWILIO_ACCOUNT_SID: string;
  TWILIO_AUTH_TOKEN: string;
  TWILIO_PHONE_NUMBER: string;
}

export async function scheduled(
  event: ScheduledController, env: CronEnv, ctx: ExecutionContext,
): Promise<void> {
  switch (event.cron) {
    case "*/5 * * * *": ctx.waitUntil(sweep(env)); return;
    case "17 4 * * *":  ctx.waitUntil(prune(env)); return;
    default:
      console.log(`cron: no handler for schedule ${JSON.stringify(event.cron)}`);
  }
}

// ---------------------------------------------------------------------------
// internal_hq_prune — internal_hq.pb.js:2642-2682
//
// Ported nearly verbatim because every clause has a reason written beside it,
// and the reasons are about a volume that has been filled once already
// (1700000037_backup_footprint.js:13-14). D1 has its own size ceiling.
// ---------------------------------------------------------------------------

async function prune(env: CronEnv): Promise<void> {
  const now = Date.now();
  const cut60 = new Date(now - 60 * 24 * 3600 * 1000).toISOString();
  const cut30 = new Date(now - 30 * 24 * 3600 * 1000).toISOString();
  const nowISO = new Date(now).toISOString();

  // The 200-row cap per table is the original's, and it is not arbitrary: it
  // bounds the work one tick does so a backlog drains over several days
  // instead of timing out forever on the first.
  const statements = [
    // :2644-2648  the activity ledger
    env.DB.prepare(
      `DELETE FROM "internal_activity" WHERE "id" IN (
         SELECT "id" FROM "internal_activity" WHERE "created" <= ?1
         ORDER BY "created" ASC LIMIT 200)`).bind(cut60),

    // :2657-2662  expired sessions. Housekeeping, NOT a security control —
    // they are already refused on every request by the dual-auth block.
    env.DB.prepare(
      `DELETE FROM "internal_sessions" WHERE "id" IN (
         SELECT "id" FROM "internal_sessions"
         WHERE "expires" != '' AND "expires" <= ?1
         ORDER BY "expires" ASC LIMIT 200)`).bind(nowISO),

    // :2667-2672  READ notifications older than 30 days. UNREAD ROWS ARE NEVER
    // PRUNED AT ANY AGE: a thing somebody was told and has not seen yet is the
    // one row in this collection that still has a job to do.
    env.DB.prepare(
      `DELETE FROM "internal_notifs" WHERE "id" IN (
         SELECT "id" FROM "internal_notifs"
         WHERE "read" = 1 AND "created" <= ?1
         ORDER BY "created" ASC LIMIT 200)`).bind(cut30),

    // :2676-2681  SPENT reminders older than 30 days. A live one (sent_at = '')
    // is left alone however far in the future it points.
    env.DB.prepare(
      `DELETE FROM "internal_reminders" WHERE "id" IN (
         SELECT "id" FROM "internal_reminders"
         WHERE "sent_at" != '' AND "sent_at" <= ?1
         ORDER BY "sent_at" ASC LIMIT 200)`).bind(cut30),
  ];

  // One batch, one round trip. The original wraps each block in its own
  // try/catch so one failing table does not stop the others; D1's batch is
  // atomic, so an equivalent needs four separate awaits if that independence
  // matters. It does not here — every statement is a bounded DELETE on a
  // different table — so the atomic form is kept and the failure is loud.
  try {
    await env.DB.batch(statements);
  } catch (err) {
    console.log(`internal_hq: prune failed: ${String(err)}`);
  }
}

// ---------------------------------------------------------------------------
// internal_hq_sweep — internal_hq.pb.js:2139-2636
//
// SKELETON ONLY. The deployed sweep is ~500 lines: due reminders, the
// three-try ceiling (REMIND_MAX_TRIES), notification fan-out, and the Twilio
// send. It is ported in Phase 5 (ARCHITECTURE.md §12, Phase 5), not here, and the two
// things that must change on the way are marked.
// ---------------------------------------------------------------------------

async function sweep(env: CronEnv): Promise<void> {
  const nowISO = new Date().toISOString();

  const due = await env.DB.prepare(
    `SELECT * FROM "internal_reminders"
      WHERE "sent_at" = '' AND "fire_at" != '' AND "fire_at" <= ?1
      ORDER BY "fire_at" ASC LIMIT 50`,
  ).bind(nowISO).all<Record<string, unknown>>();

  for (const row of due.results ?? []) {
    // CHANGE 1 — every send is a SUBREQUEST against this invocation's budget.
    // Batching to 50 above is what keeps one tick inside it; the original had
    // no such ceiling because a Go process has none.
    const ok = await sendSMS(env, String(row.to ?? ""), String(row.text ?? ""));
    if (!ok) continue;
    await env.DB.prepare(
      `UPDATE "internal_reminders" SET "sent_at" = ?1 WHERE "id" = ?2`,
    ).bind(pbNow(), String(row.id)).run();
  }
}

/**
 * internal_hq.pb.js:2164-2190, ported. The hand-rolled base64 there
 * (`b64`, :2150-2162) exists because the JSVM has no btoa; Workers do, so it
 * is dropped — that is a deletion of 14 lines, not a behaviour change.
 */
async function sendSMS(env: CronEnv, to: string, text: string): Promise<boolean> {
  const { TWILIO_ACCOUNT_SID: sid, TWILIO_AUTH_TOKEN: auth,
          TWILIO_PHONE_NUMBER: from } = env;
  if (!sid || !auth || !from || !to) return false;
  try {
    const res = await fetch(
      `https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`,
      {
        method: "POST",
        headers: {
          Authorization: "Basic " + btoa(`${sid}:${auth}`),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({ From: from, To: to, Body: text }),
        // CHANGE 2 — the original passes `timeout: 15`. fetch() has no timeout
        // option; AbortSignal.timeout is the equivalent and MUST be supplied,
        // or a hung Twilio connection holds the whole tick open.
        signal: AbortSignal.timeout(15_000),
      });
    return res.ok;
  } catch {
    return false;
  }
}
