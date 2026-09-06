/**
 * POST /sms/inbound   -- Twilio's inbound webhook.
 * POST /transcription/token
 *
 * Ported from backend/pb_hooks/sms.pb.js + twilio_signature.js. The signature
 * half is here; the owner-resolution + event-write half is src/pb/sender.ts,
 * shared with routes/sendblue.ts so that a text lands in the identical events
 * row whichever carrier brought it and the brain cannot tell them apart.
 *
 * TWILIO_AUTH_TOKEN IS LOAD-BEARING AND CANNOT BE REPLACED BY AN API KEY.
 * Twilio signs X-Twilio-Signature with the ACCOUNT AUTH TOKEN and offers no
 * API-key equivalent. Outbound can prefer a scoped key; this cannot. With the
 * token unset every text 403s and the product just looks deaf -- which is what
 * happened from 2026-08-12 to 08-15, zero inbound events, nobody noticed. So an
 * unset token answers 503 "not configured", not 403: a permanent-sounding
 * refusal for a configuration problem hides it.
 *
 * The PocketBase original hand-rolls SHA-1 and base64 across ~200 lines because
 * its JS runtime has no crypto at all. WebCrypto has HMAC-SHA1, so this is the
 * same algorithm in a tenth of the code -- and constant-time comparison comes
 * free rather than being hand-written.
 *
 * THE ALGORITHM, exactly: HMAC-SHA1 over the full request URL followed by every
 * POST parameter, sorted by key, appended as key+value with no separators.
 * Base64 of the digest is the signature.
 */
import { landInboundText, last6 } from "../pb/sender.ts";
import { handleInboundText, type TextCommandEnv } from "../connections/wiring.ts";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });
const text = (status: number, body: string) =>
  new Response(body, { status, headers: { "content-type": "text/plain" } });

/** CONTRACT.md §6.12 rule 8: the one 200 body, whatever became of the text. */
const twiml = () =>
  new Response("<?xml version='1.0' encoding='UTF-8'?><Response></Response>",
    { status: 200, headers: { "content-type": "application/xml" } });

/**
 * `SmsEnv` is deliberately a SUPERSET of what the signature half needs: the
 * text twin (src/connections/text_commands.ts) runs on the same request and
 * wants the store, the vendor, the model and a way to reply. Every one of
 * those is optional here and checked at the seam — a Worker missing one logs
 * that the twin is not wired and lands the message exactly as before.
 */
export interface SmsEnv extends Partial<TextCommandEnv> {
  DB: D1Database;
  TWILIO_AUTH_TOKEN?: string;
  TWILIO_ACCOUNT_SID?: string;
  TWILIO_PHONE_NUMBER?: string;
  TWILIO_FROM?: string;
  ANTICIPY_TWILIO_WEBHOOK_URL?: string;
}

async function twilioSignature(authToken: string, url: string, params: URLSearchParams) {
  let data = url;
  for (const k of [...params.keys()].sort()) data += k + (params.get(k) ?? "");
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(authToken),
    { name: "HMAC", hash: "SHA-1" }, false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return btoa(String.fromCharCode(...new Uint8Array(mac)));
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

/**
 * Logged URLs never carry a query. The historical binding kept the shared
 * secret in "?token=...", and a log line is the one place it must not come
 * back (sms.pb.js:67-72).
 */
function safeUrl(url: string): string {
  const cut = url.indexOf("?");
  return cut < 0 ? url : url.slice(0, cut) + "?<query redacted>";
}

export async function smsInbound(
  req: Request, env: SmsEnv, ctx?: ExecutionContext,
): Promise<Response> {
  // "Silent failures: zero, ever" (MVP spec §09). Every refusal says which
  // check refused, because the only symptom of the last inbound outage lived
  // on Twilio's side of the wire as error 11200 (sms.pb.js:74-80).
  const refuse = (status: number, check: string, detail: string): Response => {
    console.log(`sms/inbound ${status}: ${check} — ${detail}`);
    return text(status, status === 503 ? "sms webhook is not configured" : "forbidden");
  };

  const authToken = env.TWILIO_AUTH_TOKEN || "";
  // Unset is a CONFIGURATION problem and says so. 403 here would look like a
  // forged request forever and hide a deaf product.
  if (!authToken) {
    return refuse(503, "not configured",
      "TWILIO_AUTH_TOKEN is unset on this Worker, so EVERY inbound text is being " +
      "refused. An API key cannot stand in for it — Twilio signs webhooks with the " +
      "account auth token only. `wrangler secret put TWILIO_AUTH_TOKEN`.");
  }

  const ctype = (req.headers.get("content-type") || "").toLowerCase();
  if (!ctype.includes("application/x-www-form-urlencoded")) {
    return text(415, "unsupported content type");
  }

  const raw = await req.text();
  const params = new URLSearchParams(raw);
  const messageSid = params.get("MessageSid") || params.get("SmsSid") || "";
  const from = (params.get("From") || "").trim();
  const who = `MessageSid=${messageSid || "(none)"} From=${last6(from)}`;

  // Twilio signs the URL IT called. Behind a proxy that is not necessarily the
  // URL this Worker sees, so an explicit override wins when set.
  const url = env.ANTICIPY_TWILIO_WEBHOOK_URL || req.url;
  const sent = req.headers.get("X-Twilio-Signature") || "";
  const want = await twilioSignature(authToken, url, params);
  if (!sent || !constantTimeEqual(sent, want)) {
    return refuse(403, sent ? "signature mismatch" : "signature missing",
      `Twilio's configured URL must be ${safeUrl(url)} (set ` +
      `ANTICIPY_TWILIO_WEBHOOK_URL to pin it behind a proxy); ${who}`);
  }

  const accountSid = params.get("AccountSid") || "";
  if (env.TWILIO_ACCOUNT_SID && accountSid !== env.TWILIO_ACCOUNT_SID) {
    return refuse(403, "wrong account",
      `AccountSid on the message is not TWILIO_ACCOUNT_SID for this deployment; ${who}`);
  }
  // The oracle (sms.pb.js:150) refuses when To is not the number, and an
  // absent To is not the number. The first cut here let an empty To through.
  const to = params.get("To") || "";
  const mine = env.TWILIO_PHONE_NUMBER || env.TWILIO_FROM || "";
  if (mine && to !== mine) {
    return refuse(403, "wrong number",
      `To=${last6(to)} is not this deployment's TWILIO_PHONE_NUMBER; ${who}`);
  }

  const body = (params.get("Body") || "").trim();
  // A signed Twilio SMS always carries SM + 32 hex (sms.pb.js:152-155,
  // CONTRACT.md §6.12 rule 6). A carrier id's shape is transport, not meaning.
  if (!/^SM[a-fA-F0-9]{32}$/.test(messageSid)) {
    return refuse(403, "malformed MessageSid",
      "a signed Twilio SMS always carries SM + 32 hex; got " +
      String(messageSid || "(none)").slice(0, 8) + "…");
  }

  // Everything above refuses. Everything below accepts the request and decides
  // whether it becomes an event -- src/pb/sender.ts, shared with Sendblue.
  const landed = await landInboundText(
    { DB: env.DB }, "sms/inbound", "MessageSid",
    { from, text: body, externalId: messageSid });
  if (landed.kind === "unknown") return text(500, "temporary routing failure");
  if (landed.kind === "failed") return text(500, "could not persist the message");

  // THE TEXT TWIN. The spec's rule for the whole connections area is one line:
  // "everything here has a text twin", and until this call existed nothing
  // anywhere read an inbound message for one — "disconnect slack" reached
  // nobody who understood it.
  //
  // AFTER THE ROW, NEVER INSTEAD OF IT. The event is already written above, so
  // the brain sees this message exactly as it always has whatever the twin
  // decides; the twin only ever ADDS a reply, and on most messages it adds
  // nothing (`not_for_us`).
  //
  // THE OWNER COMES FROM THE STORED ROW `landInboundText` resolved by phone
  // number, never from a body field. `body` is handed over verbatim: any
  // "does this look like a connections message" test in front of this call
  // would be the law-1 violation the module exists to avoid.
  //
  // waitUntil, NOT await. Twilio wants the TwiML promptly and the twin spends
  // a model call; without it a Worker cancels background work the moment the
  // response is returned, which is the failure connections-wait.ts already
  // prints for /c/{token}/go. With no ctx it is awaited instead, so a caller
  // that cannot pass one still gets the behaviour rather than silence.
  if (landed.kind === "written") {
    const run = handleInboundText(
      env as unknown as TextCommandEnv, landed.owner_ref, body, landed.id);
    if (ctx) ctx.waitUntil(run); else await run;
  }

  // Dropped, already handled, written: all 200 with the empty TwiML, as the
  // oracle answers. The log line is the only place the difference shows, on
  // purpose -- Twilio must not retry a text that was refused for a reason.
  return twiml();
}

export async function transcriptionToken(_req: Request, _env: SmsEnv): Promise<Response> {
  // Anonymous is asked to sign in. NOT 502/503: the phone's catch block
  // schedules a retry on those, so a temporary-sounding refusal spins a
  // reconnect loop forever against a permanent decision.
  return json(401, { ok: false, message: "Sign in first." });
}
