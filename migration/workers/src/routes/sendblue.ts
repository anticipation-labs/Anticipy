/**
 * POST /sms/sendblue   -- Sendblue's webhook.
 *
 * Sendblue (docs.sendblue.com, read 2026-09-05) posts application/json to ONE
 * dashboard-configured URL (Developer → Webhooks) for two different things:
 * inbound messages (is_outbound:false, status "RECEIVED") and status updates
 * on texts we sent (is_outbound:true; SENT / DELIVERED / ERROR …). It proves
 * itself with the dashboard's secret sent verbatim in the `sb-signing-secret`
 * header — a shared secret compared directly, not an HMAC over the body. It
 * retries up to three times on a 5xx, 45 s apart, and wants a 2xx.
 *
 * The shape of every decision here is the Twilio route's (routes/sms.ts) and
 * the oracle's (backend/pb_hooks/sms.pb.js):
 *
 *   configuration problem   503, and it says so -- a 403 here would look like
 *                           a forged request forever and hide a deaf product
 *                           (that is what 2026-08-12..15 looked like)
 *   forged / unsigned       403 "forbidden"
 *   wrong number            403 "forbidden"
 *   not a reply             200 and ignored, logged: status updates, group
 *                           chats (the brain holds one conversation per owner)
 *   nobody / two people     200 and dropped, logged -- a text never chooses
 *                           whose browser to drive
 *   routing uncertain       500 "temporary routing failure" -- Sendblue retries
 *   the row                 the identical events row Twilio lands, through the
 *                           identical code (src/pb/sender.ts): device_id "sms",
 *                           kind "sms_reply", text, decision "", goal = the
 *                           sender, owner_ref, external_event_id = message_handle
 *
 * Fields read: is_outbound, status, message_handle, from_number (falling back
 * to `number`, which Sendblue documents as the other party), to_number,
 * sendblue_number, content, media_url, group_id, participants. Nothing else
 * is looked at; nothing is logged but the ids and the last six digits.
 */
import { landInboundText, last6, type Landing } from "../pb/sender.ts";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });
const text = (status: number, body: string) =>
  new Response(body, { status, headers: { "content-type": "text/plain" } });

export interface SendblueEnv {
  DB: D1Database;
  /** The dashboard's webhook secret. Unset = 503, never 403. */
  SENDBLUE_WEBHOOK_SECRET?: string;
  /** This deployment's Sendblue number, E.164. Set = a message to any other number is refused. */
  SENDBLUE_FROM_NUMBER?: string;
}

/**
 * Byte-wise over the longer of the two, so the answer does not depend on where
 * the first difference is (the same loop as index.ts timingSafeEqual). The
 * length is not secret; the bytes are.
 */
function secretEqual(a: string, b: string): boolean {
  if (!a || !b) return false;
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.byteLength ^ bb.byteLength;
  const n = Math.max(ab.byteLength, bb.byteLength);
  for (let i = 0; i < n; i++) diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  return diff === 0;
}

export async function sendblueInbound(req: Request, env: SendblueEnv): Promise<Response> {
  const secret = env.SENDBLUE_WEBHOOK_SECRET || "";
  // Unset is a CONFIGURATION problem and says so. "Silent failures: zero,
  // ever" -- the only other symptom would be Sendblue's dashboard showing
  // 403s, which reads as an attack, not as a missing secret.
  if (!secret) {
    console.log("sms/sendblue 503: not configured — SENDBLUE_WEBHOOK_SECRET is unset " +
      "on this Worker, so EVERY Sendblue message is being refused. Generate one, " +
      "enter it in Sendblue's dashboard (Developer → Webhooks, the secret beside " +
      "the URL) and `wrangler secret put SENDBLUE_WEBHOOK_SECRET` the same value.");
    return text(503, "sendblue webhook is not configured");
  }

  const sent = req.headers.get("sb-signing-secret") || "";
  if (!sent || !secretEqual(sent, secret)) {
    console.log(`sms/sendblue 403: ${sent ? "secret mismatch" : "secret missing"} — ` +
      "the sb-signing-secret header must equal SENDBLUE_WEBHOOK_SECRET; if the " +
      "dashboard's secret was rotated, rotate the Worker's in the same window.");
    return text(403, "forbidden");
  }

  let payload: Record<string, unknown>;
  try {
    const parsed: unknown = await req.json();
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("not an object");
    payload = parsed as Record<string, unknown>;
  } catch {
    // A body that is not JSON will not become JSON on a retry: 4xx, not 5xx.
    console.log("sms/sendblue 400: body is not a JSON object");
    return json(400, { ok: false, error: "body must be a JSON object" });
  }
  const str = (k: string): string => {
    const v = payload[k];
    return v === null || v === undefined ? "" : String(v).trim();
  };

  const handle = str("message_handle");
  const status = str("status");

  // Status callbacks are not replies. They arrive on this same URL for every
  // text WE send, and treating one as an inbound reply would have the brain
  // hearing its own "DELIVERED".
  const isOutbound = payload.is_outbound === true || payload.is_outbound === "true";
  if (isOutbound) {
    console.log(`sms/sendblue 200, ignored: outbound status update ${status || "(no status)"} ` +
      `message_handle=${handle} to=${last6(str("to_number") || str("number"))}`);
    return json(200, { ok: true, ignored: "status update" });
  }

  // Wrong number, as the Twilio route refuses a text addressed to a number
  // that is not TWILIO_PHONE_NUMBER. Every number the payload names must be
  // ours, and it must name one.
  const mine = (env.SENDBLUE_FROM_NUMBER || "").trim();
  if (mine) {
    const named = [str("to_number"), str("sendblue_number")].filter(Boolean);
    if (named.length === 0 || named.some((n) => n !== mine)) {
      console.log(`sms/sendblue 403: wrong number — to_number=${last6(str("to_number"))} ` +
        `sendblue_number=${last6(str("sendblue_number"))} is not this deployment's ` +
        `SENDBLUE_FROM_NUMBER; message_handle=${handle}`);
      return text(403, "forbidden");
    }
  }

  // Group chats: the brain holds one conversation per owner, and a reply in a
  // group is addressed to the group, not to Anticipy. Ignored, not refused.
  const groupId = str("group_id");
  const participants = Array.isArray(payload.participants) ? payload.participants : [];
  if (groupId || participants.length > 2) {
    console.log(`sms/sendblue 200, ignored: group message (group_id ${groupId ? "set" : "empty"}, ` +
      `${participants.length} participants); message_handle=${handle}`);
    return json(200, { ok: true, ignored: "group message" });
  }

  // Without the carrier's id a retry cannot be told from a second text, and
  // the idempotency this route promises would be a promise about nothing.
  // Sendblue always sends one; a payload without it is malformed, and a
  // malformed payload does not improve on retry.
  const from = str("from_number") || str("number");
  if (!handle) {
    console.log(`sms/sendblue 400: message_handle missing; from=${last6(from)}`);
    return json(400, { ok: false, error: "message_handle is required" });
  }

  // Empty content is dropped on both carriers, so the brain sees the same
  // thing whichever one delivered it. A media-only message is dropped too,
  // and the log says so: no events column carries media_url, and an
  // empty-text row would only be marked "ignore" by the brain
  // (brain/worker.py handle_inbound) -- a row that exists to be ignored.
  const content = str("content");
  const media = str("media_url");
  if (!from || !content) {
    console.log(`sms/sendblue 200 but dropped: ${!from ? "empty from_number" :
      media ? "media-only message (no events column carries media_url)" : "empty content"}; ` +
      `message_handle=${handle} from=${last6(from)}`);
    return json(200, { ok: true, dropped: "empty content" });
  }

  const landed: Landing = await landInboundText(
    { DB: env.DB }, "sms/sendblue", "message_handle",
    { from, text: content, externalId: handle });

  switch (landed.kind) {
    case "written":         return json(200, { ok: true });
    case "already_handled": return json(200, { ok: true, ignored: "already handled" });
    case "dropped":
      return json(200, { ok: true, dropped:
        landed.why === "no_owner" ? "no owner" :
        landed.why === "ambiguous" ? "ambiguous sender" : "empty content" });
    case "unknown":         return text(500, "temporary routing failure");
    case "failed":          return json(500, { ok: false, error: "could not persist the message" });
  }
}
