/**
 * src/pb/sender.ts — an inbound text becomes ONE events row, whoever carried it.
 *
 * Shared by routes/sms.ts (Twilio) and routes/sendblue.ts (Sendblue), and
 * deliberately carrier-blind: the brain (brain/worker.py handle_inbound, which
 * polls kind "sms_reply" with decision "") must not be able to tell which
 * carrier delivered a text, so both routes land the identical row through the
 * identical code. Ported from backend/pb_hooks/sms.pb.js:160-293, THE ORACLE
 * for this half; the signature halves stay in their routes because the two
 * carriers prove themselves differently.
 *
 * A PHONE NUMBER IS A ROUTING ADDRESS, NOT AN IDENTITY (sms.pb.js:160-163).
 * The number is resolved to one and only one signed-in account and that
 * canonical owner is stamped on the event. Shared, recycled and ambiguous
 * numbers fail closed: a text must never choose which person's browser to
 * drive. Two candidate sets, always unioned (sms.pb.js:165-239):
 *
 *   1. every owner_profile whose phone equals the sender, each candidate then
 *      resolved back through ITS OWN NEWEST profile row and kept only if that
 *      canonical row still carries the number — a match on an old duplicate
 *      profile is not current authority;
 *   2. every owners row whose phone equals the sender, admitted ONLY when that
 *      account has no owner_profile row at all — owners.phone is the sign-up
 *      seed, and once a profile exists it is canonical even with an empty
 *      phone, because admitting the seed would re-affiliate a number the
 *      person explicitly removed.
 *
 * Any read failure anywhere makes the answer UNKNOWN, and unknown is not
 * "nobody": a partial candidate set is never safe enough to pick an account,
 * even when the surviving set holds exactly one row. Unknown is a 500 so the
 * carrier retries (Twilio retries; Sendblue retries three times on a 5xx).
 *
 * IDEMPOTENCY IS THE DATABASE'S, NOT A PRE-READ. Carriers retry webhooks, and
 * the oracle read events.external_event_id before saving. Here the row is
 * written through records.create() — the same path every client's POST takes,
 * so fillEmpties() and the unique-collision mapping apply — and a collision on
 * the partial-unique index idx_events_external_event IS the duplicate signal.
 * A pre-read plus a write is a race two retries can both win; the index
 * cannot be won twice.
 */
import { COLLECTIONS } from "./schema.ts";
import { create, type Env, type RecordsRequest } from "./records.ts";

export type SenderResolution =
  | { kind: "owner"; owner_ref: string }
  | { kind: "none" }
  | { kind: "ambiguous"; count: number }
  | { kind: "unknown" };

/**
 * The three reads the resolution needs, and nothing else — so the decision
 * logic can be pinned with a fake in test/sender.test.ts while the D1 half
 * is proven on a real workerd by migration/spec/contract_tests.py.
 */
export interface SenderDb {
  /** owner_ref of every owner_profile row carrying this phone ('' refs excluded). */
  profileOwnerRefsByPhone(phone: string): Promise<string[]>;
  /** The phone on the account's NEWEST profile row, or null when it has no profile row. */
  currentProfilePhone(ownerRef: string): Promise<string | null>;
  /** id of every owners row carrying this phone — the sign-up seed. */
  ownerIdsByPhone(phone: string): Promise<string[]>;
}

export function d1SenderDb(db: D1Database): SenderDb {
  return {
    async profileOwnerRefsByPhone(phone) {
      const res = await db.prepare(
        `SELECT "owner_ref" FROM "owner_profile" WHERE "phone" = ?1 AND "owner_ref" != '' ` +
        `ORDER BY "updated" DESC`,
      ).bind(phone).all<{ owner_ref: string }>();
      return (res.results ?? []).map((r) => String(r.owner_ref ?? ""));
    },
    async currentProfilePhone(ownerRef) {
      const row = await db.prepare(
        `SELECT "phone" FROM "owner_profile" WHERE "owner_ref" = ?1 ORDER BY "updated" DESC LIMIT 1`,
      ).bind(ownerRef).first<{ phone: string | null }>();
      return row ? String(row.phone ?? "") : null;
    },
    async ownerIdsByPhone(phone) {
      const res = await db.prepare(
        `SELECT "id" FROM "owners" WHERE "phone" = ?1 ORDER BY "updated" DESC`,
      ).bind(phone).all<{ id: string }>();
      return (res.results ?? []).map((r) => String(r.id ?? ""));
    },
  };
}

/** sms.pb.js:165-239, exactly. See the file header for why each half exists. */
export async function resolveSenderWith(q: SenderDb, from: string): Promise<SenderResolution> {
  const phone = String(from ?? "").trim();
  if (!phone) return { kind: "none" };

  const matches = new Set<string>();
  let unknown = false;

  // 1. Profiles, each candidate re-read through its own canonical row.
  try {
    const candidates = new Set(await q.profileOwnerRefsByPhone(phone));
    for (const ref of candidates) {
      if (!ref) continue;
      try {
        const current = await q.currentProfilePhone(ref);
        if (current !== null && current.trim() === phone) matches.add(ref);
      } catch {
        // Unknown is not "not this owner". Discarding one failed candidate
        // can collapse a shared number from two accounts to one and route a
        // text across accounts.
        unknown = true;
      }
    }
  } catch {
    unknown = true;
  }

  // 2. The sign-up seed, admitted only for an account with no profile at all.
  // Always unioned with (1): if A's canonical profile carries the number and
  // B has only the seed, considering B only when profiles found nobody would
  // silently route B's text to A. The correct answer is ambiguity.
  try {
    for (const id of await q.ownerIdsByPhone(phone)) {
      if (!id) continue;
      try {
        const current = await q.currentProfilePhone(id);
        if (current === null) matches.add(id);
      } catch {
        unknown = true;
      }
    }
  } catch {
    unknown = true;
  }

  // Unknown outranks a match: sms.pb.js:265-269, "a partial candidate set is
  // never safe enough to pick an account, even when the surviving set
  // contains exactly one row."
  if (unknown) return { kind: "unknown" };
  if (matches.size === 0) return { kind: "none" };
  if (matches.size > 1) return { kind: "ambiguous", count: matches.size };
  return { kind: "owner", owner_ref: [...matches][0] };
}

export function resolveSender(env: { DB: D1Database }, from: string): Promise<SenderResolution> {
  return resolveSenderWith(d1SenderDb(env.DB), from);
}

// ---------------------------------------------------------------------------
// The write
// ---------------------------------------------------------------------------

export type WriteOutcome =
  | { kind: "written"; id: string }
  | { kind: "duplicate" }
  | { kind: "failed"; detail: string };

/**
 * The events row, exactly as sms.pb.js:280-288 writes it. Through
 * records.create(), so the row gets the same fillEmpties() every client's
 * POST gets (decision "" is what the brain's poll filters on — a NULL there
 * was ten minutes of deaf ears on 2026-09-05) and the same unique-collision
 * mapping: PocketBase's 400 { data: { external_event_id: validation_not_unique } }.
 */
export async function recordInboundReply(
  env: Env,
  r: { from: string; text: string; ownerRef: string; externalId: string },
): Promise<WriteOutcome> {
  const req: RecordsRequest = {
    collection: COLLECTIONS.events,
    recordId: null,
    method: "POST",
    // create() never reads the URL; the records API takes it for list/view.
    url: new URL("https://api.anticipy.ai/api/collections/events/records"),
    body: {
      device_id: "sms",
      kind: "sms_reply",
      text: r.text,
      decision: "",
      goal: r.from,               // the sender's number; the brain replies to it
      owner_ref: r.ownerRef,
      external_event_id: r.externalId,
    },
    principal: { kind: "service" },
    forcedScope: null,
    extraAst: null,
  };
  let res: Response;
  try {
    res = await create(env, req);
  } catch (e) {
    return { kind: "failed", detail: String((e as Error)?.message ?? e) };
  }
  let body: Record<string, unknown> | null = null;
  try { body = (await res.json()) as Record<string, unknown>; } catch { body = null; }
  if (res.status === 200) return { kind: "written", id: String(body?.id ?? "") };
  const data = (body?.data ?? null) as Record<string, { code?: string }> | null;
  if (res.status === 400 && data?.external_event_id?.code === "validation_not_unique") {
    return { kind: "duplicate" };
  }
  return { kind: "failed", detail: `${res.status} ${JSON.stringify(body ?? "")}` };
}

// ---------------------------------------------------------------------------
// The landing — resolution + write + the oracle's log lines, once
// ---------------------------------------------------------------------------

export type Landing =
  | { kind: "written"; id: string; owner_ref: string }
  | { kind: "already_handled" }
  | { kind: "dropped"; why: "empty" | "no_owner" | "ambiguous" }
  | { kind: "unknown" }                       // 500 — the carrier retries
  | { kind: "failed"; detail: string };       // 500 — the carrier retries

export interface InboundText {
  /** The sender's number, as the carrier gave it (E.164). */
  from: string;
  /** The message body. Trimmed here, as the oracle trims Body. */
  text: string;
  /** The carrier's unique message id — MessageSid, message_handle. The idempotency key. */
  externalId: string;
}

/** Logged numbers show their last six digits only, never the whole number. */
export const last6 = (n: string): string => (n ? "…" + String(n).slice(-6) : "(none)");

/**
 * Everything here ACCEPTS the request and decides whether it becomes an
 * event, so this is the last place a real text can disappear behind a 200.
 * It used to do exactly that on the PocketBase side: an unrecognised sender
 * produced empty TwiML and no log at all, which reads from the carrier's
 * console as a perfectly healthy webhook (sms.pb.js:252-257). Every non-event
 * outcome therefore logs, loudly, with the route and the carrier's id — and
 * never the text.
 */
export async function landInboundText(
  env: Env, route: string, idLabel: string, msg: InboundText,
): Promise<Landing> {
  const from = String(msg.from ?? "").trim();
  const text = String(msg.text ?? "").trim();
  const id = String(msg.externalId ?? "");
  const tag = `${idLabel}=${id} from=${last6(from)}`;

  if (!from || !text) {
    console.log(`${route} 200 but dropped: empty sender or text; ${tag}`);
    return { kind: "dropped", why: "empty" };
  }

  const who = await resolveSender(env, from);
  if (who.kind === "unknown") {
    // Make the carrier retry. A partial candidate set is never safe enough to
    // pick an account, even when the surviving set contains exactly one row.
    console.log(`${route} 500: phone ownership could not be fully verified — ` +
      `refusing to choose an account from partial data. ${tag}`);
    return { kind: "unknown" };
  }
  if (who.kind === "none") {
    console.log(`${route} 200 but DROPPED: no account owns the sender route — ` +
      `the sender's number is on no owner_profile or owners row, so every ` +
      `text from it vanishes. Set the phone on that account. ${tag}`);
    return { kind: "dropped", why: "no_owner" };
  }
  if (who.kind === "ambiguous") {
    console.log(`${route} 200 but DROPPED: ${who.count} accounts claim the sender ` +
      `route — ambiguous, refusing to pick whose browser to drive. ${tag}`);
    return { kind: "dropped", why: "ambiguous" };
  }

  const wrote = await recordInboundReply(env, {
    from, text, ownerRef: who.owner_ref, externalId: id,
  });
  if (wrote.kind === "duplicate") {
    // The carrier retried. The index made the retries one command, not two.
    console.log(`${route} 200, already handled: ${tag}`);
    return { kind: "already_handled" };
  }
  if (wrote.kind === "failed") {
    // A 500 here makes the carrier retry, which is the right outcome, but an
    // unexplained 500 is the same invisible outage in a different costume.
    console.log(`${route} 500: could not persist ${tag}: ${wrote.detail}`);
    return { kind: "failed", detail: wrote.detail };
  }
  return { kind: "written", id: wrote.id, owner_ref: who.owner_ref };
}
