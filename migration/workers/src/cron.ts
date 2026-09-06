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
 * 3. WALL-CLOCK AND SUBREQUEST BUDGET. The sweep sends texts in a loop
 *    (`sendSMS`, internal_hq.pb.js:2165-2181). Each send is one subrequest.
 *    A tick that has 200 reminders due makes 200 of them.
 *    See ARCHITECTURE.md §7 for the limit and the batching this needs.
 */
import { newRecordId, pbNow } from "./pb/wire.ts";
import { sendText, type MessagingEnv } from "./messaging.ts";
import { connectNudgeSweep } from "./connections/nudge.ts";

/**
 * The Twilio names stay required here because index.ts Env extends this and
 * routes/sms.ts's HMAC reads TWILIO_AUTH_TOKEN; the Sendblue names and the
 * provider switch arrive through MessagingEnv.
 */
export interface CronEnv extends MessagingEnv {
  DB: D1Database;
  TWILIO_ACCOUNT_SID: string;
  TWILIO_AUTH_TOKEN: string;
  TWILIO_PHONE_NUMBER: string;
  TWILIO_FROM?: string;
  RESEND_API_KEY?: string;
  /**
   * The evidence bucket. OPTIONAL here and required in index.ts's Env: the
   * prune must run on a rig that has no bucket bound rather than throw and
   * leave the audit ledger unswept beside it.
   */
  EVIDENCE?: R2Bucket;
}

export async function scheduled(
  event: ScheduledController, env: CronEnv, ctx: ExecutionContext,
): Promise<void> {
  switch (event.cron) {
    // TWO waitUntil CALLS, NOT ONE CHAINED PROMISE. The reminder sweep carries
    // things somebody is waiting for; the connect ask is an interruption
    // nobody asked for. They must not be able to take each other down, and
    // `connectAsks` (below) is what makes that true in both directions.
    // The reminder leg is registered FIRST so that it is already running
    // whatever the second line does.
    case "*/5 * * * *":
      ctx.waitUntil(sweep(env));
      ctx.waitUntil(connectAsks(env));
      return;
    case "17 4 * * *":  ctx.waitUntil(prune(env)); return;
    default:
      console.log(`cron: no handler for schedule ${JSON.stringify(event.cron)}`);
  }
}

// ---------------------------------------------------------------------------
// THE CONNECT ASK — src/connections/nudge.ts connectNudgeSweep.
//
// Five minutes is the cadence even though one owner is asked at most once a
// week: the ask is supposed to land at a MOMENT — just after a result, with
// the laptop shut — and a nightly sweep would only ever arrive long after
// every such moment had passed. Who is due comes from
// src/connections/due.ts, which is wired in through `installNudgeWiring`; with
// no wiring installed the sweep logs that it asked nobody and returns.
//
// NOT LIVE YET, AND NOT BECAUSE OF THIS LINE. `wrangler.jsonc` registers only
// `17 4 * * *`; `*/5 * * * *` is commented out there with its reason (two
// sweeps against one database would send the team every reminder twice), and
// only wrangler.dev.jsonc carries it. So THIS WHOLE CASE — the HQ reminder
// sweep included — is dead in production until the cutover that file
// describes. Do not answer that by hanging the connect ask off the nightly
// `17 4 * * *` leg: an ask that lands at 04:17 UTC is the 3am text the policy
// in src/connections/nudge.ts exists to prevent.
//
// WHY THIS WRAPPER EXISTS, rather than passing the sweep to waitUntil
// directly. Two failures, and `.catch()` on the call would only cover one:
//
//   1. A SYNCHRONOUS THROW happens before any promise exists — a wiring fault,
//      a module that did not initialise — so `.catch` is never reached and
//      `scheduled` itself throws. An `async function` turns that into a
//      rejection this try/catch owns.
//   2. A REJECTED PROMISE handed to waitUntil marks this scheduled invocation
//      as failed. `ScheduledController.noRetry()` exists in this runtime's own
//      types because a failed invocation is a candidate for being run again —
//      and running this tick again re-runs `sweep(env)`, THE LEG THAT SENDS
//      REMINDER TEXTS. One broken connect ask must never be able to text
//      somebody their reminder twice.
//
// So this swallows, loudly, and the tick that carries the rest survives it.
// ---------------------------------------------------------------------------

async function connectAsks(env: CronEnv): Promise<void> {
  try {
    await connectNudgeSweep(env);
  } catch (err) {
    console.log(`connect nudge sweep: failed, the rest of the tick continues: ${String(err)}`);
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

  // The two RECORD-LEVEL sweeps PocketBase ran on every write and Cloudflare
  // ran nowhere. They are here rather than on the write path because a Worker
  // has no onRecordAfterCreateSuccess: this cron is the only thing that runs on
  // its own. See auditLedgerCap and evidenceCap.
  await auditLedgerCap(env);
  await evidenceCap(env);
}

// ---------------------------------------------------------------------------
// audit_retention.pb.js:71-83 — THE STANDING CAP ON THE AUDIT LEDGER.
//
// That table filled the 5 GB production volume on 2026-08-15 and SQLite could
// not write ANY row: crash loop, hard outage, and the visible symptom was cruel
// — a password-reset text went out (the send happens first) whose code could
// then never be stored, so the correct code was rejected every time. The hook
// answered it with a sweep on every audit write, so the ledger could never
// again exceed KEEP.
//
// On Cloudflare llm.ts:311 says "KEEP audit_retention's sweep" and nothing did:
// auditBegin is a bare INSERT, the only DELETE is behind a manual POST
// /admin/purge-audit that nothing calls, and cron.ts dispatched two jobs
// neither of which touched the table. Measured 2026-09-05 (audit F27): 102 rows
// holding 12.4 MB of request/response JSON, ~72% of the whole D1 database, and
// rows still arriving after the cutover.
//
// PER-WRITE vs DAILY: the hook trimmed continuously; this trims once a day. The
// difference is a day's worth of tagged certification calls, which is bounded
// and operator-visible, against one extra DELETE on every model call, which is
// not free on the hottest proxy path. D1's ceiling is 10 GB and the daily cap
// keeps the table three orders of magnitude below it.
//
// KEEP is 300, the same number audit_retention.pb.js:28 and routes/service.ts's
// purgeAudit use. It is deliberately not lifted into a shared constant: that
// file belongs to another change in flight, and two literals that agree are
// better than a merge conflict in the middle of a retention sweep. If they ever
// disagree, this comment is where to start.
// ---------------------------------------------------------------------------

const AUDIT_KEEP = 300;

async function auditLedgerCap(env: CronEnv): Promise<void> {
  try {
    const res = await env.DB.prepare(
      `DELETE FROM "agent_llm_audit" WHERE "id" NOT IN (
         SELECT "id" FROM "agent_llm_audit" ORDER BY "created" DESC LIMIT ?1)`,
    ).bind(AUDIT_KEEP).run();
    const gone = Number(res.meta?.changes ?? 0);
    if (gone) console.log(`audit_retention: trimmed ${gone} audit row(s), keeping ${AUDIT_KEEP}`);
  } catch (err) {
    // Never let housekeeping be the thing that breaks the tick.
    console.log(`audit_retention: sweep failed: ${String(err)}`);
  }
}

// ---------------------------------------------------------------------------
// evidence.pb.js:244-269 — TWO CEILINGS, BECAUSE ONE WAS NOT ENOUGH LAST TIME.
//
// KEEP_TOTAL is the disk half; KEEP_PER_OWNER is the privacy half — "nobody's
// screenshots accumulate indefinitely just because they were the quiet
// account". Both are the hook's own numbers.
//
// WHAT IS NEW HERE AND WAS NOT IN THE HOOK: the bytes. On PocketBase the image
// lived beside the row and was deleted with it. On Cloudflare the row is in D1
// and the bytes are in R2, so deleting the row alone leaves a paid-for object
// no row can ever name again. The keys are read BEFORE the delete and the
// objects go after it — that order on purpose: a row without its bytes answers
// `that evidence is not available` (assets.ts), which is the designed absence;
// bytes without their row are unreachable and merely cost money. Losing the
// second half is a bill, losing the first is a broken door.
// ---------------------------------------------------------------------------

const EVIDENCE_KEEP_PER_OWNER = 20;
const EVIDENCE_KEEP_TOTAL = 60;
/** Bounds one tick, the way the original's SWEEP_BATCH did. */
const EVIDENCE_SWEEP_BATCH = 200;

async function evidenceCap(env: CronEnv): Promise<void> {
  let surplus: { id: string; image: string }[] = [];
  try {
    // ONE read for both ceilings. `rn` counts each owner's rows newest-first,
    // so `rn > 20` is the per-owner cap; the NOT IN is the global one.
    const res = await env.DB.prepare(
      `SELECT "id", "image" FROM (
         SELECT "id", "image",
                ROW_NUMBER() OVER (PARTITION BY "owner_ref" ORDER BY "created" DESC) AS rn
           FROM "evidence")
        WHERE rn > ?1
           OR "id" NOT IN (SELECT "id" FROM "evidence" ORDER BY "created" DESC LIMIT ?2)
        LIMIT ?3`,
    ).bind(EVIDENCE_KEEP_PER_OWNER, EVIDENCE_KEEP_TOTAL, EVIDENCE_SWEEP_BATCH)
      .all<{ id: string; image: string }>();
    surplus = res.results ?? [];
  } catch (err) {
    console.log(`evidence: retention read failed: ${String(err)}`);
    return;
  }
  if (!surplus.length) return;

  try {
    await env.DB.batch(surplus.map((row) =>
      env.DB.prepare(`DELETE FROM "evidence" WHERE "id" = ?1`).bind(row.id)));
  } catch (err) {
    // The rows are still there, so the bytes must stay too — deleting objects
    // for rows that survived is how a live evidence row starts 404ing.
    console.log(`evidence: retention delete failed, bytes left alone: ${String(err)}`);
    return;
  }

  if (!env.EVIDENCE) {
    console.log(`evidence: ${surplus.length} row(s) pruned but no bucket is bound; `
      + `their objects are orphaned in R2`);
    return;
  }
  const keys = surplus.filter((r) => r.image).map((r) => `evidence/${r.id}/${r.image}`);
  if (!keys.length) return;
  try {
    await env.EVIDENCE.delete(keys);
    console.log(`evidence: pruned ${surplus.length} row(s) and ${keys.length} object(s)`);
  } catch (err) {
    console.log(`evidence: rows pruned but ${keys.length} object(s) remain in R2: ${String(err)}`);
  }
}

// ---------------------------------------------------------------------------
// internal_hq_sweep — internal_hq.pb.js:2139-2636, ported in full.
//
// WHAT WAS HERE BEFORE, and why it had to go: a skeleton that selected due
// rows out of internal_reminders and then called sendSMS(row.to, row.text).
// internal_reminders has no `to` column and no `text` column. Both read
// undefined, sendSMS refused on the empty recipient, `continue` skipped the
// sent_at write — so the sweep ran every five minutes, sent nothing, marked
// nothing, and never raised an error. A silent no-op that reports success is
// the exact failure are_the_ears_live.py exists to catch, and it would have
// shipped looking like a working cron.
//
// Six passes, in the source's order:
//   A  todo.remind_at        the one-shot bell
//   B  follow-ups            one nudge, ever, 2 days past due
//   C  internal_reminders    the ones one column cannot express
//   D  the notification digest
//   E  research slot backstop
//   F  the repeat motor
//
// CLAIM FIRST, THEN SEND, everywhere. This cron refires every five minutes
// forever, so send-first with a failed persist is unbounded duplicate texts.
// The stamp rolls back ONLY when every channel failed, and after three goes it
// stays stamped and logs the give-up — a permanently wrong phone number must
// not generate a real Twilio call every five minutes until somebody looks.
//
// SUBREQUEST BUDGET is the one thing this runtime adds. Every send is a
// subrequest against this invocation. The source's own batch ceilings (20, 10,
// 20, 200) are kept exactly, which is what holds a tick inside the budget; they
// were chosen for other reasons but they serve here too.
// ---------------------------------------------------------------------------

const REMIND_MAX_TRIES = 3;

/** Accepts a PocketBase datetime with or without its trailing Z. */
function pbTime(v: unknown): number {
  if (!v) return NaN;
  let t = String(v).trim().replace(" ", "T");
  if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
  return new Date(t).getTime();
}

type Row = Record<string, unknown>;

async function allRows(env: CronEnv, sql: string, ...binds: unknown[]): Promise<Row[]> {
  try {
    const r = await env.DB.prepare(sql).bind(...binds).all<Row>();
    return r.results ?? [];
  } catch (err) {
    console.log("internal_hq: query failed: " + err);
    return [];
  }
}

async function logAct(env: CronEnv, action: string, subject: string, ref: string): Promise<void> {
  try {
    await env.DB.prepare(
      "INSERT INTO internal_activity (id, created, actor, actor_name, action, subject, verb, ref) "
      + "VALUES (?1,?2,'','HQ',?3,?4,'',?5)",
    ).bind(newRecordId(), pbNow(), action, subject, ref || "").run();
  } catch { /* the ledger is not the delivery */ }
}

/** Assignees, or the creator when there are none. Active people only. */
async function recipientsOf(env: CronEnv, todo: Row): Promise<Row[]> {
  let ids: string[] = [];
  try {
    const parsed = JSON.parse(String(todo.assignees ?? "") || "[]");
    if (Array.isArray(parsed)) ids = parsed.map(String);
  } catch { ids = []; }
  if (!ids.length && String(todo.created_by ?? "")) ids = [String(todo.created_by)];
  const out: Row[] = [];
  for (const id of ids) {
    try {
      const p = await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(id).first<Row>();
      if (p && !(p.active === 0 || p.active === null)) out.push(p);
    } catch { /* skip */ }
  }
  return out;
}

/** D1 stores booleans as INTEGER. `!== false` on a 0 is TRUE in JS; see
 *  hq_data.ts boolDefaultTrue for the bug that idiom causes. */
function optedIn(v: unknown): boolean {
  return !(v === 0 || v === false || v === "0" || v === "false");
}

async function sweep(env: CronEnv): Promise<void> {
  const nowISO = new Date().toISOString();

  // ---- PASS A: reminders ---------------------------------------------------
  const due = await allRows(env,
    "SELECT * FROM internal_todos WHERE status = 'open' AND remind_at != '' "
    + "AND remind_at <= ?1 AND remind_sent_at = '' ORDER BY remind_at ASC LIMIT 20", nowISO);
  for (const todo of due) {
    try {
      // The claim — before any send.
      await env.DB.prepare("UPDATE internal_todos SET remind_sent_at = ?1 WHERE id = ?2")
        .bind(nowISO, String(todo.id)).run();
      const channel = String(todo.remind_channel ?? "") || "email";
      const title = String(todo.title ?? "");
      const dueDate = String(todo.due ?? "");
      const text = "Reminder from Anticipy HQ: " + title + (dueDate ? " (due " + dueDate + ")" : "");
      let anySent = false;
      for (const p of await recipientsOf(env, todo)) {
        if ((channel === "email" || channel === "both") && String(p.email ?? "")) {
          if (await sendEmail(env, String(p.email), "Reminder: " + title.slice(0, 120), text)) anySent = true;
        }
        if ((channel === "sms" || channel === "both") && String(p.phone ?? "")) {
          if (await sendSMS(env, String(p.phone), text.slice(0, 300))) anySent = true;
        }
      }
      if (anySent) {
        if (Number(todo.remind_attempts) || 0) {
          await env.DB.prepare("UPDATE internal_todos SET remind_attempts = 0 WHERE id = ?1")
            .bind(String(todo.id)).run();
        }
        await logAct(env, "reminder.sent",
          "Reminder went out for “" + title.slice(0, 80) + "”", String(todo.id));
      } else {
        // Every channel failed. A blip deserves another go; a permanently
        // unreachable recipient must NOT retry forever.
        const tries = (Number(todo.remind_attempts) || 0) + 1;
        if (tries >= REMIND_MAX_TRIES) {
          // Keep the claim stamped: this is the give-up, not a delivery.
          await env.DB.prepare("UPDATE internal_todos SET remind_attempts = ?1 WHERE id = ?2")
            .bind(tries, String(todo.id)).run();
          await logAct(env, "reminder.gave_up", "Gave up reminding about “" + title.slice(0, 80)
            + "” after " + tries + " tries — check the contact details", String(todo.id));
        } else {
          await env.DB.prepare(
            "UPDATE internal_todos SET remind_attempts = ?1, remind_sent_at = '' WHERE id = ?2")
            .bind(tries, String(todo.id)).run();
          await logAct(env, "reminder.failed", "Reminder for “" + title.slice(0, 80)
            + "” could not be delivered (try " + tries + " of " + REMIND_MAX_TRIES + ")",
            String(todo.id));
        }
      }
    } catch (err) { console.log("internal_hq: reminder send failed: " + err); }
  }

  // ---- PASS B: follow-ups — one nudge, ever, 2 days past due ---------------
  const cutoff = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  const late = await allRows(env,
    "SELECT * FROM internal_todos WHERE status = 'open' AND due != '' AND due <= ?1 "
    + "AND followup_sent_at = '' ORDER BY due ASC LIMIT 10", cutoff);
  for (const todo of late) {
    try {
      await env.DB.prepare("UPDATE internal_todos SET followup_sent_at = ?1 WHERE id = ?2")
        .bind(nowISO, String(todo.id)).run();
      const title = String(todo.title ?? "");
      const text = "Still open, past due: " + title
        + " (was due " + String(todo.due ?? "") + ") — Anticipy HQ";
      let anySent = false;
      for (const p of await recipientsOf(env, todo)) {
        // else-if, not two ifs: a nudge is one message on the best channel.
        if (String(p.email ?? "")) {
          if (await sendEmail(env, String(p.email), "Past due: " + title.slice(0, 120), text)) anySent = true;
        } else if (String(p.phone ?? "")) {
          if (await sendSMS(env, String(p.phone), text.slice(0, 300))) anySent = true;
        }
      }
      if (anySent) {
        await logAct(env, "followup.sent",
          "Nudged about “" + title.slice(0, 80) + "” (past due)", String(todo.id));
      }
    } catch (err) { console.log("internal_hq: followup failed: " + err); }
  }

  // ---- PASS C: internal_reminders -----------------------------------------
  // todo.remind_at above is the one-shot bell and keeps working untouched.
  // This exists because "one hour before" and "daily until done" are two
  // reminders on one task, and one column cannot hold two times.
  const rems = await allRows(env,
    "SELECT * FROM internal_reminders WHERE sent_at = '' AND fire_at != '' "
    + "AND fire_at <= ?1 ORDER BY fire_at ASC LIMIT 20", nowISO);
  for (const rem of rems) {
    try {
      const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
        .bind(String(rem.todo ?? "")).first<Row>();
      // The task is gone or finished: retire the reminder quietly. Firing a
      // bell about a task nobody can open is worse than silence.
      if (!todo || String(todo.status ?? "") !== "open") {
        await env.DB.prepare("UPDATE internal_reminders SET sent_at = ?1 WHERE id = ?2")
          .bind(nowISO, String(rem.id)).run();
        continue;
      }
      // The claim — before any send.
      await env.DB.prepare("UPDATE internal_reminders SET sent_at = ?1 WHERE id = ?2")
        .bind(nowISO, String(rem.id)).run();

      const channel = String(rem.channel ?? "") || "inapp";
      const title = String(todo.title ?? "");
      const label = String(rem.label ?? "") || "Reminder";
      const dueStr = String(todo.due ?? "");
      const dueTime = String(todo.due_time ?? "");
      const text = label + ": " + title
        + (dueStr ? " (due " + dueStr + (dueTime ? " " + dueTime : "") + ")" : "")
        + " — Anticipy HQ";

      // person = "" means every recipient of the todo, which is the rule Pass A
      // already uses. One definition of "who does this reach".
      let people: Row[] = [];
      if (String(rem.person ?? "")) {
        const p = await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
          .bind(String(rem.person)).first<Row>();
        if (p && optedIn(p.active)) people = [p];
      } else {
        people = await recipientsOf(env, todo);
      }

      let anySent = false;
      for (const p of people) {
        // An in-app reminder is a row in the tray, not a send. It always
        // succeeds, which is why it never touches the retry budget below.
        if (channel === "inapp") {
          try {
            await env.DB.prepare(
              "INSERT INTO internal_notifs (id, created, person, kind, text, sub, todo, actor, read, emailed_at, smsed_at) "
              + "VALUES (?1,?2,?3,'deadline',?4,?5,?6,'',0,?7,?8)",
            ).bind(newRecordId(), pbNow(), String(p.id), label, title.slice(0, 300),
                   String(todo.id), nowISO, nowISO).run();
            anySent = true;
          } catch { /* skip */ }
          continue;
        }
        if ((channel === "email" || channel === "both") && String(p.email ?? "") && optedIn(p.email_on)) {
          if (await sendEmail(env, String(p.email), label + ": " + title.slice(0, 120), text)) anySent = true;
        }
        if ((channel === "sms" || channel === "both") && String(p.phone ?? "") && optedIn(p.sms_on)) {
          if (await sendSMS(env, String(p.phone), text.slice(0, 300))) anySent = true;
        }
      }

      if (anySent) {
        await logAct(env, "reminder.sent",
          "Reminder went out for “" + title.slice(0, 80) + "”", String(todo.id));
        // The one rule that comes back. Re-armed AFTER a successful send, never
        // before — otherwise a rule that can never be delivered walks its
        // fire_at forward forever and the give-up counter never runs.
        if (String(rem.rule ?? "") === "daily_until_done") {
          try {
            await env.DB.prepare(
              "UPDATE internal_reminders SET fire_at = ?1, sent_at = '', attempts = 0 WHERE id = ?2")
              .bind(new Date(Date.now() + 86400000).toISOString(), String(rem.id)).run();
          } catch { /* skip */ }
        }
      } else {
        const tries = (Number(rem.attempts) || 0) + 1;
        if (tries >= REMIND_MAX_TRIES) {
          await env.DB.prepare("UPDATE internal_reminders SET attempts = ?1 WHERE id = ?2")
            .bind(tries, String(rem.id)).run();     // keep the claim: the give-up
          await logAct(env, "reminder.gave_up", "Gave up reminding about “" + title.slice(0, 80)
            + "” after " + tries + " tries — check the contact details", String(todo.id));
        } else {
          await env.DB.prepare(
            "UPDATE internal_reminders SET attempts = ?1, sent_at = '' WHERE id = ?2")
            .bind(tries, String(rem.id)).run();
          await logAct(env, "reminder.failed", "Reminder for “" + title.slice(0, 80)
            + "” could not be delivered (try " + tries + " of " + REMIND_MAX_TRIES + ")",
            String(todo.id));
        }
      }
    } catch (err) { console.log("internal_hq: scheduled reminder failed: " + err); }
  }

  // ---- PASS D: the notification digest ------------------------------------
  //
  // ONE MESSAGE PER PERSON PER SWEEP, never one per event. Three comments on a
  // task inside a minute is one email that says three things.
  //
  // The ten-minute settle is what makes that true. The age is checked in JS and
  // not in the WHERE clause deliberately: `created` is an autodate written as
  // "2026-08-22 04:11:34.880Z" with a SPACE, and comparing it against a JS
  // toISOString() with its T separator is the exact shape of bug that has
  // already produced NaN and a permanently jammed queue in this file.
  const SETTLE_MS = 10 * 60 * 1000;
  const pending = await allRows(env,
    "SELECT * FROM internal_notifs WHERE read = 0 AND emailed_at = '' "
    + "ORDER BY created ASC LIMIT 200");

  const byPerson: Record<string, Row[]> = {};
  for (const n of pending) {
    const born = pbTime(n.created);
    if (isNaN(born) || Date.now() - born < SETTLE_MS) continue;
    const pid = String(n.person ?? "");
    if (!pid) continue;
    if (!byPerson[pid]) byPerson[pid] = [];
    if (byPerson[pid].length < 20) byPerson[pid].push(n);
  }

  for (const pid of Object.keys(byPerson)) {
    try {
      const rows = byPerson[pid];
      const person = await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(pid).first<Row>();
      // No person, or a deactivated one: stamp the batch so it stops being
      // reconsidered every five minutes forever, and send nothing.
      if (!person || !optedIn(person.active)) {
        for (const n of rows) {
          try {
            await env.DB.prepare(
              "UPDATE internal_notifs SET emailed_at = ?1, smsed_at = ?1 WHERE id = ?2")
              .bind(nowISO, String(n.id)).run();
          } catch { /* skip */ }
        }
        continue;
      }
      const pref = String(person.remind_pref ?? "") || "inapp";
      const wantEmail = (pref === "email" || pref === "both")
        && optedIn(person.email_on) && !!String(person.email ?? "");
      const wantSMS = (pref === "sms" || pref === "both")
        && optedIn(person.sms_on) && !!String(person.phone ?? "");

      // THE CLAIM, ON EVERY ROW IN THE BATCH, BEFORE ANY SEND. If this dies
      // between here and the Resend call the person misses one digest — and
      // every one of those events is still in their tray, unread, where they
      // will see it. The other way round they get the same text every five
      // minutes until somebody restarts the backend.
      for (const n of rows) {
        try {
          if (wantSMS) {
            await env.DB.prepare(
              "UPDATE internal_notifs SET emailed_at = ?1, smsed_at = ?1 WHERE id = ?2")
              .bind(nowISO, String(n.id)).run();
          } else {
            await env.DB.prepare("UPDATE internal_notifs SET emailed_at = ?1 WHERE id = ?2")
              .bind(nowISO, String(n.id)).run();
          }
        } catch { /* skip */ }
      }
      // "in-app only" is a real answer, not a failure. The rows are stamped
      // above so this person's tray fills and their phone stays quiet.
      if (!wantEmail && !wantSMS) continue;

      const lines = rows.map((n) =>
        "• " + String(n.text ?? "") + (String(n.sub ?? "") ? " — " + String(n.sub) : ""));
      const count = rows.length;
      const subject = count + (count === 1 ? " update" : " updates") + " in Anticipy HQ";
      // text/, not html/. A comment body is whatever somebody typed, and the
      // only safe thing to do with it at this boundary is send it as text so no
      // mail client is ever asked to parse it as markup.
      const bodyText = lines.join("\n") + "\n\nOpen HQ: https://www.anticipy.ai/hq";
      if (wantEmail) await sendEmail(env, String(person.email), subject, bodyText);
      if (wantSMS) {
        const head = lines.slice(0, 2).join("\n");
        const rest = count - Math.min(2, count);
        await sendSMS(env, String(person.phone),
          (head + (rest > 0 ? "\n…and " + rest + " more." : "") + "\nanticipy.ai/hq").slice(0, 300));
      }
      await logAct(env, "digest.sent", "Sent " + String(person.name ?? "") + " a digest of "
        + count + (count === 1 ? " update" : " updates"), "");
    } catch (err) { console.log("internal_hq: digest failed: " + err); }
  }

  // ---- PASS E: research slot backstop -------------------------------------
  // The original bug this guards: a datetime already ending in Z had a SECOND
  // Z appended, giving Invalid Date -> NaN, so the stale-clear branch could
  // never fire. One worker dying mid-research pinned the single slot forever
  // and every later run answered 409 until somebody restarted the backend.
  try {
    const meter = await env.DB.prepare(
      "SELECT * FROM internal_meter WHERE name = 'research' LIMIT 1").first<Row>();
    const liveId = String(meter?.live_job_id ?? "");
    if (meter && liveId) {
      let clear = false;
      const j = await env.DB.prepare("SELECT * FROM jobs WHERE id = ?1 LIMIT 1")
        .bind(liveId).first<Row>();
      if (!j) {
        clear = true;
      } else {
        const st = String(j.status ?? "");
        if (st === "done" || st === "failed" || st === "cancelled") clear = true;
        else {
          const upd = pbTime(j.updated);
          if (!isNaN(upd) && Date.now() - upd > 30 * 60 * 1000) clear = true;
        }
      }
      if (clear) {
        await env.DB.prepare("UPDATE internal_meter SET live_job_id = '' WHERE id = ?1")
          .bind(String(meter.id)).run();
      }
    }
  } catch { /* the backstop is a backstop */ }

  // ---- PASS F: the repeat motor -------------------------------------------
  await repeatMotor(env);
}

/**
 * For every series (title+track+rule), once the latest instance's due date is
 * behind the local calendar, lay down the next occurrence. Completion does NOT
 * stop a series — "on his calendar every day" means every day, done or not. To
 * end a series, set its repeat to none.
 *
 * "Local" is a fixed UTC-8, matching the source. It could be Intl here, and
 * deliberately is not: changing which day a recurring task lands on is a
 * decision to make once, on both systems, not a side effect of a migration.
 * For a day-granular generator the only cost is that new items appear at 1am
 * Vancouver in summer instead of midnight.
 *
 * Missed cycles are NOT backfilled — after downtime a series resumes at the
 * most recent scheduled date, one item, not a pile of stale ones.
 */
async function repeatMotor(env: CronEnv): Promise<void> {
  try {
    const dayMs = 86400000;
    const localToday = new Date(Date.now() - 480 * 60000).toISOString().slice(0, 10);
    const parseDay = (v: unknown) => Date.parse(String(v).slice(0, 10) + "T00:00:00Z");
    const fmtDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);
    const DOW: Record<string, number> = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };

    const nextAfter = (rule: string, dueMs: number): number => {
      if (rule === "daily") return dueMs + dayMs;
      if (rule.indexOf("every:") === 0) {
        const n = parseInt(rule.slice(6), 10);
        return (n >= 2 && n <= 29) ? dueMs + n * dayMs : NaN;
      }
      if (rule === "weekdays") {
        let t = dueMs + dayMs;
        while ([0, 6].includes(new Date(t).getUTCDay())) t += dayMs;
        return t;
      }
      if (rule === "weekly") return dueMs + 7 * dayMs;
      if (rule.indexOf("weekly:") === 0) {
        const want = DOW[rule.slice(7)];
        if (want === undefined) return NaN;
        let t = dueMs + dayMs;
        while (new Date(t).getUTCDay() !== want) t += dayMs;
        return t;
      }
      if (rule === "monthly") {
        const d = new Date(dueMs);
        const day = d.getUTCDate();
        const n = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
        const last = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth() + 1, 0)).getUTCDate();
        n.setUTCDate(Math.min(day, last));
        return n.getTime();
      }
      return NaN;
    };

    const todayMs = parseDay(localToday);
    const reps = await allRows(env,
      "SELECT * FROM internal_todos WHERE repeat_rule != '' AND repeat_rule != 'none' "
      + "AND due != '' ORDER BY due DESC LIMIT 500");

    // One row per series: the instance with the greatest due carries the torch.
    const latest: Record<string, Row> = {};
    for (const t of reps) {
      const k = String(t.title ?? "") + "|" + String(t.track ?? "") + "|" + String(t.repeat_rule ?? "");
      if (!latest[k] || String(t.due ?? "") > String(latest[k].due ?? "")) latest[k] = t;
    }

    let made = 0;
    for (const k of Object.keys(latest)) {
      const t = latest[k];
      const rule = String(t.repeat_rule ?? "");
      const dueMs = parseDay(t.due);
      if (isNaN(dueMs)) continue;
      let next = nextAfter(rule, dueMs);
      if (isNaN(next) || next > todayMs) continue;
      // Resume at the most recent scheduled date <= today (no backfill pile).
      let guard = 0;
      while (guard++ < 400) {
        const peek = nextAfter(rule, next);
        if (isNaN(peek) || peek > todayMs) break;
        next = peek;
      }
      const nextStr = fmtDay(next);
      const already = await env.DB.prepare(
        "SELECT id FROM internal_todos WHERE title = ?1 AND track = ?2 AND due = ?3 LIMIT 1",
      ).bind(String(t.title ?? ""), String(t.track ?? ""), nextStr).first<Row>();
      if (already) continue;   // already laid down

      try {
        // Subtasks come along with their checkmarks wiped — a fresh day.
        let subs: Array<{ t: string; done: boolean }> = [];
        try {
          const parsed = JSON.parse(String(t.subtasks ?? "") || "[]");
          if (Array.isArray(parsed)) subs = parsed.map((x: Row) => ({ t: String(x.t ?? ""), done: false }));
        } catch { subs = []; }

        // A reminder rides forward by the same distance the due date moved.
        let remindAt = "";
        let remindChannel = "";
        const ra = String(t.remind_at ?? "");
        if (ra) {
          const raMs = Date.parse(ra.replace(" ", "T").replace(/([^Zz])$/, "$1Z"));
          if (!isNaN(raMs)) {
            remindAt = new Date(raMs + (next - dueMs)).toISOString().slice(0, 16);
            remindChannel = String(t.remind_channel ?? "") || "email";
          }
        }

        await env.DB.prepare(
          "INSERT INTO internal_todos (id, created, updated, title, notes, track, assignees,"
          + " watchers, priority, stage, status, due, due_time, repeat_rule, created_by,"
          + " subtasks, remind_at, remind_channel, remind_sent_at, followup_sent_at,"
          + " remind_attempts, cmt_count, attachments, hold_reason, done_at, done_by,"
          + " research_job_id, position)"
          + " VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,'todo','open',?10,?11,?12,?13,?14,?15,?16,"
          + "'','',0,0,'[]','','','','',0)",
        ).bind(newRecordId(), pbNow(), pbNow(), String(t.title ?? ""), String(t.notes ?? ""),
               String(t.track ?? ""), String(t.assignees ?? "[]"), String(t.watchers ?? "[]"),
               String(t.priority ?? "") || "normal", nextStr, String(t.due_time ?? ""),
               rule, String(t.created_by ?? ""), JSON.stringify(subs),
               remindAt, remindChannel).run();
        made++;
      } catch (err) {
        console.log("internal_hq: repeat motor could not lay down '" + String(t.title ?? "") + "': " + err);
      }
    }

    if (made > 0) {
      await logAct(env, "repeat.laydown",
        "Laid down " + made + " repeating task" + (made === 1 ? "" : "s") + " for " + localToday, "");
    }
  } catch (err) {
    console.log("internal_hq: repeat motor failed (never blocking): " + err);
  }
}

/**
 * Resend. internal_hq.pb.js:2185-2201.
 */
async function sendEmail(
  env: CronEnv, to: string, subject: string, text: string,
): Promise<boolean> {
  const rk = env.RESEND_API_KEY || "";
  if (!rk || !to) return false;
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { "Authorization": "Bearer " + rk, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: "Anticipy HQ <notifications@aevoy.com>",
        to: [to], subject, text,
      }),
    });
    return res.status >= 200 && res.status < 300;
  } catch { return false; }
}

/**
 * internal_hq.pb.js:2164-2190, ported. The request itself now lives in
 * src/messaging.ts, which chooses Sendblue or Twilio; what this keeps is the
 * contract every pass above relies on: `true` only when the provider took the
 * message, `false` for every other outcome, and never a throw — a throw here
 * would skip the give-up accounting and leave the claim stamped with nothing
 * sent. (The hand-rolled base64 in the source, `b64` :2150-2162, existed
 * because the JSVM has no btoa; Workers do.)
 */
async function sendSMS(env: CronEnv, to: string, text: string): Promise<boolean> {
  if (!to) return false;
  return (await sendText(env, to, text, { tag: "internal_hq" })).ok;
}
