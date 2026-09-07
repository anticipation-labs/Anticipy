/**
 * GET /admin/sms/lines — what Sendblue says this account can send FROM, and
 * which recipients it may send TO. Internal-key only. A diagnostic, because
 * the Sendblue keys live only on the Worker and nothing else can ask.
 *
 * WHY (2026-09-06): /admin/connect-link minted a link and Sendblue refused the
 * text with "This from number is not authorized on this account". The docs
 * say from_number "must be a number on your account" and that on free
 * shared-line plans "a recipient must be verified as a contact on your account
 * before you can message them" — two walls, and wrangler.jsonc:287 records
 * that SENDBLUE_FROM_NUMBER was never deliberately set. This route reads both
 * facts from the vendor rather than guessing. It returns numbers only; the
 * keys never leave the Worker.
 */
import { SENDBLUE_BASE, type MessagingEnv } from "../messaging.ts";

export const ADMIN_SMS_LINES_PATH = "/admin/sms/lines";
export type AdminSmsLinesEnv = MessagingEnv & { ANTICIPY_INTERNAL_KEY?: string };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });
}

export async function adminSmsLines(req: Request, env: AdminSmsLinesEnv): Promise<Response> {
  if (req.method !== "GET") return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET" } });
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal key is not configured" });
  const got = req.headers.get("X-Internal-Key") || "";
  let d = got.length === key.length ? 0 : 1;
  for (let i = 0; i < got.length && i < key.length; i++) d |= got.charCodeAt(i) ^ key.charCodeAt(i);
  if (d !== 0) return json(401, { error: "wrong key" });

  const headers = {
    "sb-api-key-id": String(env.SENDBLUE_API_KEY_ID || ""),
    "sb-api-secret-key": String(env.SENDBLUE_API_SECRET_KEY || ""),
  };
  const ask = async (path: string) => {
    const r = await fetch(SENDBLUE_BASE + path, { headers });
    let body: unknown = null;
    try { body = await r.json(); } catch { body = null; }
    return { status: r.status, body };
  };
  const [lines, contacts] = await Promise.all([ask("/api/lines"), ask("/api/contacts")]);
  return json(200, {
    ok: true,
    configured_from: String(env.SENDBLUE_FROM_NUMBER || "") || null,
    lines, contacts,
  });
}
