/**
 * POST /sms/inbound   -- Twilio's inbound webhook.
 * POST /transcription/token
 *
 * Ported from backend/pb_hooks/sms.pb.js + twilio_signature.js.
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
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });
const text = (status: number, body: string) =>
  new Response(body, { status, headers: { "content-type": "text/plain" } });

export interface SmsEnv {
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

export async function smsInbound(req: Request, env: SmsEnv): Promise<Response> {
  const authToken = env.TWILIO_AUTH_TOKEN || "";
  // Unset is a CONFIGURATION problem and says so. 403 here would look like a
  // forged request forever and hide a deaf product.
  if (!authToken) return text(503, "sms webhook is not configured");

  const ctype = (req.headers.get("content-type") || "").toLowerCase();
  if (!ctype.includes("application/x-www-form-urlencoded")) {
    return text(415, "unsupported content type");
  }

  const raw = await req.text();
  const params = new URLSearchParams(raw);

  // Twilio signs the URL IT called. Behind a proxy that is not necessarily the
  // URL this Worker sees, so an explicit override wins when set.
  const url = env.ANTICIPY_TWILIO_WEBHOOK_URL || req.url;
  const sent = req.headers.get("X-Twilio-Signature") || "";
  const want = await twilioSignature(authToken, url, params);
  if (!sent || !constantTimeEqual(sent, want)) return text(403, "forbidden");

  const accountSid = params.get("AccountSid") || "";
  if (env.TWILIO_ACCOUNT_SID && accountSid !== env.TWILIO_ACCOUNT_SID) {
    return text(403, "forbidden");                     // wrong account
  }
  const to = params.get("To") || "";
  const mine = env.TWILIO_PHONE_NUMBER || env.TWILIO_FROM || "";
  if (mine && to && to !== mine) return text(403, "forbidden");   // wrong number

  return json(503, { ok: false, message: "inbound routing not yet ported" });
}

export async function transcriptionToken(_req: Request, _env: SmsEnv): Promise<Response> {
  // Anonymous is asked to sign in. NOT 502/503: the phone's catch block
  // schedules a retry on those, so a temporary-sounding refusal spins a
  // reconnect loop forever against a permanent decision.
  return json(401, { ok: false, message: "Sign in first." });
}
