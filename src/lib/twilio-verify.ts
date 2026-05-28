import crypto from "crypto";

/**
 * Verify a Twilio webhook signature.
 *
 * Twilio signs each webhook with HMAC-SHA1 over the URL plus the POST body
 * params concatenated key+value in alphabetical order. Without this check,
 * anyone can POST to /api/engine/twilio/{sms-reply,voice-callback} and
 * confirm/reject pending intents on behalf of arbitrary phone numbers /
 * intent IDs.
 *
 * Returns true if the request is authentic, false otherwise. Fails closed:
 * if TWILIO_AUTH_TOKEN is unset, returns false (refuses all webhook traffic).
 *
 * The exported variant `verifyTwilioRequest` reads the signature header,
 * the request URL, and a parsed FormData body — call it after consuming
 * the body since FormData/Request bodies can only be read once.
 */
function expectedSignature(
  authToken: string,
  url: string,
  params: Record<string, string>
): string {
  const sortedKeys = Object.keys(params).sort();
  let payload = url;
  for (const key of sortedKeys) {
    payload += key + params[key];
  }
  return crypto
    .createHmac("sha1", authToken)
    .update(payload, "utf8")
    .digest("base64");
}

function safeEqual(a: string, b: string): boolean {
  const aBuf = Buffer.from(a);
  const bBuf = Buffer.from(b);
  if (aBuf.length !== bBuf.length) return false;
  return crypto.timingSafeEqual(aBuf, bBuf);
}

export function verifyTwilioRequest(
  signatureHeader: string | null,
  webhookUrl: string,
  formParams: Record<string, string>
): boolean {
  const authToken = process.env.TWILIO_AUTH_TOKEN;
  if (!authToken) return false;
  if (!signatureHeader) return false;
  const expected = expectedSignature(authToken, webhookUrl, formParams);
  return safeEqual(expected, signatureHeader);
}

/**
 * Build the URL Twilio used to sign this request. Twilio signs the original
 * request URL — including query string and the original host header. Behind
 * Vercel's proxy, `req.url` will be `http://0.0.0.0/...` internally, so we
 * reconstruct from x-forwarded-* headers when present.
 */
export function reconstructWebhookUrl(req: Request): string {
  const url = new URL(req.url);
  const forwardedHost = req.headers.get("x-forwarded-host");
  const forwardedProto = req.headers.get("x-forwarded-proto");
  if (forwardedHost) url.host = forwardedHost;
  if (forwardedProto) url.protocol = forwardedProto + ":";
  return url.toString();
}

export function formDataToParams(formData: FormData): Record<string, string> {
  const params: Record<string, string> = {};
  formData.forEach((value, key) => {
    params[key] = typeof value === "string" ? value : "";
  });
  return params;
}
