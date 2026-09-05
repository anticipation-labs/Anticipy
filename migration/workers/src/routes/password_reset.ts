/**
 * POST /auth/reset/request   { email }
 * POST /auth/reset/confirm   { email, code, password }
 *
 * Ported from backend/pb_hooks/password_reset.pb.js. "I forgot my password" by
 * TEXT, because this image has no way to send mail.
 *
 * Both routes sit OUTSIDE /api/collections/, so the data-API guard never sees
 * them -- they are the front door and must defend themselves.
 *
 * THE PROPERTY THAT MATTERS MOST IS INDISTINGUISHABILITY. /request answers the
 * same 200 for a real address, an unknown one, a missing field and an
 * unparseable body. Any difference -- a status, a word, a timing tell -- turns
 * this route into "does Omar have an account here?", one address at a time.
 * The contract suite compares whole bodies for exactly that reason.
 */
import bcrypt from "bcryptjs";
import { sendText, type MessagingEnv } from "../messaging.ts";

const SAME =
  "If that account exists and has a phone number, a code is on its way by text.";
const NOPE = "That code isn't right, or it has expired. Ask for a new one.";

/**
 * The text, verbatim from password_reset.pb.js:153-155 and CONTRACT.md §5.1.7.
 *
 * THE SECOND SENTENCE IS THE POINT, and the hook's own header (:20-21) says
 * why: "The message names the app and says plainly that it was not requested by
 * them if it wasn't — the standard phishing tell." A code arriving with no
 * explanation teaches the owner to act on unexplained codes, which is the
 * behaviour every account-takeover call relies on.
 *
 * WHAT WAS HERE UNTIL 2026-09-05: `Your Anticipy code is ${code}. It expires in
 * 10 minutes.` — shorter, correct about the code, and missing the warning the
 * original author put there on purpose (audit F39).
 */
const RESET_SMS = (code: string) =>
  `${code} is your Anticipy code to set a new password. It works for 10 minutes. `
  + `If you didn't ask for this, ignore it and your password stays as it is.`;

/**
 * The success line, verbatim from password_reset.pb.js:249 and CONTRACT.md
 * §5.2. app/ios/Tests/ResetMessageTests.swift:98 asserts on this exact body,
 * so it is a pin and not copy: "Password updated. You can sign in now." was a
 * different sentence than the one the phone's own test was written against.
 */
const DONE = "Done — sign in with your new password.";

const TTL_SECONDS = 600;        // 10 minutes
const MIN_GAP_SECONDS = 60;     // between texts to one person
const MAX_PER_HOUR = 5;
const MAX_ATTEMPTS = 5;         // guesses per code
const MIN_PASSWORD = 8;

/** The provider names (SENDBLUE_*, TWILIO_*, ANTICIPY_SMS_PROVIDER) come from MessagingEnv. */
export interface ResetEnv extends MessagingEnv {
  DB: D1Database;
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

const same = () => json(200, { ok: true, message: SAME });
const nope = () => json(400, { ok: false, message: NOPE });

async function sha256Hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Six digits from a CSPRNG, rejection-sampled so the digits stay uniform. */
function sixDigits(): string {
  const out: string[] = [];
  while (out.length < 6) {
    for (const b of crypto.getRandomValues(new Uint8Array(16))) {
      if (b < 250 && out.length < 6) out.push(String(b % 10));
    }
  }
  return out.join("");
}

function pbNow(d = new Date()): string {
  return d.toISOString().replace("T", " ").replace("Z", "Z");
}

/** PocketBase writes 15-char ids. */
function pbId(): string {
  const A = "abcdefghijklmnopqrstuvwxyz0123456789";
  return [...crypto.getRandomValues(new Uint8Array(15))]
    .map((b) => A[b % A.length]).join("");
}

async function readBody(req: Request): Promise<Record<string, unknown>> {
  try {
    const v = await req.json();
    return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
  } catch {
    return {};                 // an unreadable body is not a distinguishable one
  }
}

/**
 * The phone the code goes to.
 *
 * Once a profile row exists it is canonical INCLUDING an explicit empty phone.
 * Falling back from that empty to owners.phone would silently re-affiliate the
 * immutable sign-up number after the person removed it. Only an account with no
 * profile row at all may use the sign-up seed.
 */
async function phoneFor(db: D1Database, ownerId: string, ownerPhone: string) {
  const row = await db
    .prepare(`SELECT phone FROM owner_profile WHERE owner_ref = ? ORDER BY updated DESC LIMIT 1`)
    .bind(ownerId).first<{ phone: string | null }>();
  if (row) return String(row.phone ?? "").trim();
  return String(ownerPhone ?? "").trim();
}

/**
 * The code leaves through src/messaging.ts (Sendblue, else Twilio). `true`
 * only when the provider took it: a code the owner never receives must not
 * be left live in the table, and resetRequest below relies on exactly that.
 * sendText never throws, so a hung or refused provider is a `false` here and
 * the same 200 to the caller — an exception would have been a 500, and a 500
 * only for addresses that exist is the tell this route must never give.
 */
async function sendCode(env: ResetEnv, to: string, code: string): Promise<boolean> {
  const r = await sendText(env, to, RESET_SMS(code), { tag: "password reset" });
  return r.ok;
}

export async function resetRequest(req: Request, env: ResetEnv): Promise<Response> {
  const body = await readBody(req);
  const email = String(body.email ?? "").trim().toLowerCase();
  if (!email) return same();

  const owner = await env.DB
    .prepare(`SELECT id, phone FROM owners WHERE lower(email) = ? LIMIT 1`)
    .bind(email).first<{ id: string; phone: string | null }>();
  if (!owner) return same();

  let phone = "";
  try {
    phone = await phoneFor(env.DB, owner.id, String(owner.phone ?? ""));
  } catch {
    return same();             // unknown is not absent: fail closed, same reply
  }
  if (!phone) return same();

  const nowMs = Date.now();
  try {
    const recent = await env.DB
      .prepare(`SELECT created, used FROM password_resets WHERE owner = ? ORDER BY created DESC LIMIT 20`)
      .bind(owner.id).all<{ created: string; used: number }>();
    let inHour = 0;
    for (const r of recent.results ?? []) {
      const t = Date.parse(String(r.created).replace(" ", "T"));
      if (Number.isNaN(t)) continue;
      if (nowMs - t < 3600_000) inHour++;
      if (nowMs - t < MIN_GAP_SECONDS * 1000 && !r.used) return same();
    }
    if (inHour >= MAX_PER_HOUR) return same();
  } catch { /* throttling is best-effort; never a tell */ }

  const code = sixDigits();

  // SEND FIRST. If the text cannot leave the building, do not leave a live code
  // in the database pretending it did.
  if (!(await sendCode(env, phone, code))) return same();

  try {
    await env.DB.prepare(
      `INSERT INTO password_resets (id, owner, code_hash, expires, attempts, used, created, updated)
       VALUES (?,?,?,?,?,?,?,?)`)
      .bind(pbId(), owner.id, await sha256Hex(code),
            new Date(nowMs + TTL_SECONDS * 1000).toISOString(),
            0, 0, pbNow(), pbNow())
      .run();
  } catch { /* the code is already gone; saying so would be the tell */ }

  return same();
}

export async function resetConfirm(req: Request, env: ResetEnv): Promise<Response> {
  const body = await readBody(req);
  const email = String(body.email ?? "").trim().toLowerCase();
  const code = String(body.code ?? "").trim();
  const password = String(body.password ?? "");

  // The ONE thing said plainly. A length rule tells an attacker nothing about
  // accounts, and failing it silently makes the product look broken instead.
  if (password.length < MIN_PASSWORD) {
    return json(400, { ok: false, message: "Pick a password with at least 8 characters." });
  }

  const owner = await env.DB
    .prepare(`SELECT id FROM owners WHERE lower(email) = ? LIMIT 1`)
    .bind(email).first<{ id: string }>();
  if (!owner) return nope();

  const rec = await env.DB
    .prepare(`SELECT id, code_hash, expires, attempts FROM password_resets
              WHERE owner = ? AND used = 0 ORDER BY created DESC LIMIT 1`)
    .bind(owner.id).first<{ id: string; code_hash: string; expires: string; attempts: number }>();
  if (!rec) return nope();

  const spend = (id: string) =>
    env.DB.prepare(`UPDATE password_resets SET used = 1, updated = ? WHERE id = ?`)
      .bind(pbNow(), id).run().catch(() => undefined);

  const expMs = Date.parse(String(rec.expires).replace(" ", "T"));
  if (!Number.isNaN(expMs) && expMs <= Date.now()) { await spend(rec.id); return nope(); }

  const attempts = (rec.attempts || 0) + 1;
  if (attempts > MAX_ATTEMPTS) { await spend(rec.id); return nope(); }
  await env.DB.prepare(`UPDATE password_resets SET attempts = ?, updated = ? WHERE id = ?`)
    .bind(attempts, pbNow(), rec.id).run().catch(() => undefined);

  // Constant-time compare of the HASHES, not the codes. Only a SHA-256 is ever
  // stored, so a dump of this table is useless.
  const got = await sha256Hex(code);
  const want = String(rec.code_hash || "");
  if (got.length !== want.length) return nope();
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  if (diff !== 0) return nope();

  // $2a$ at cost 10 -- the same shape every existing owners.password already
  // carries, so nothing about the column changes.
  const hash = await bcrypt.hash(password, 10);
  await env.DB.prepare(`UPDATE owners SET password = ?, tokenKey = ?, updated = ? WHERE id = ?`)
    .bind(hash, pbId() + pbId(), pbNow(), owner.id).run();
  await spend(rec.id);

  return json(200, { ok: true, message: DONE });
}
