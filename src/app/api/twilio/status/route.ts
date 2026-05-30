import * as crypto from "crypto";
import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  reconstructWebhookUrl,
  formDataToParams,
} from "@/lib/twilio-verify";

export const dynamic = "force-dynamic";

/**
 * Twilio StatusCallback handler for outbound SMS sent via the broker.
 *
 * The broker route at /api/twilio/relay wires StatusCallback to this URL
 * on every Messages.json POST. Twilio then POSTs back delivery status
 * updates (queued, sending, sent, delivered, failed, undelivered) so we
 * can reconcile the row written by the broker. Without this route those
 * Twilio retries pile up as 404s in our access logs and Twilio keeps
 * retrying for hours.
 *
 * Verification uses the same HMAC-SHA1 pattern as
 * /api/twilio/sms-inbound: alphabetical concat of POST params appended
 * to the original webhook URL, HMAC'd with TWILIO_BROKER_TOKEN (the
 * Anticipy broker account's auth token, which is what signed the
 * outbound send and therefore the same secret Twilio uses for the
 * StatusCallback signature).
 *
 * Persists into public.anticipy_twilio_sends, keyed by twilio_sid. If
 * the row already exists (broker wrote it on the outbound POST), we
 * UPDATE status/error_code/error_message. If it does not exist (status
 * arrived before our broker row landed, or status arrived for a send we
 * did not originate through the broker), we INSERT a placeholder row
 * marked source='inbound_status_only' so the audit table still captures
 * the status.
 *
 * Returns 200 with empty body on success so Twilio stops retrying.
 *
 * Env required:
 *   TWILIO_BROKER_TOKEN
 *   SUPABASE_SERVICE_ROLE_KEY
 *   NEXT_PUBLIC_SUPABASE_URL
 */

const TERMINAL_STATUSES = new Set(["delivered", "failed", "undelivered"]);

export async function POST(req: Request) {
  const brokerToken = (process.env.TWILIO_BROKER_TOKEN || "").trim();
  if (!brokerToken) {
    return new Response("Twilio broker is not configured.", { status: 503 });
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return new Response("Bad Request", { status: 400 });
  }
  const params = formDataToParams(formData);
  if (Object.keys(params).length === 0) {
    return new Response("Bad Request", { status: 400 });
  }

  const signature = req.headers.get("x-twilio-signature");
  if (
    !verifyWithBrokerToken(
      brokerToken,
      signature,
      reconstructWebhookUrl(req),
      params,
    )
  ) {
    return new Response("Forbidden", { status: 403 });
  }

  const messageSid = (params.MessageSid || "").trim();
  if (!messageSid) {
    return new Response("Bad Request", { status: 400 });
  }
  const messageStatus = (params.MessageStatus || "").trim();
  const errorCode = (params.ErrorCode || "").trim() || null;
  const errorMessage = (params.ErrorMessage || "").trim() || null;
  const toNumber = (params.To || "").trim();
  const fromNumber = (params.From || "").trim();

  if (TERMINAL_STATUSES.has(messageStatus)) {
    console.log(
      "[twilio-status] terminal",
      JSON.stringify({
        sid: messageSid,
        status: messageStatus,
        error_code: errorCode,
        error_message: errorMessage,
        to: toNumber,
        from: fromNumber,
      }),
    );
  }

  try {
    const { data: updated, error: updateErr } = await supabaseAdmin
      .from("anticipy_twilio_sends")
      .update({
        status: messageStatus,
        error_code: errorCode,
        error_message: errorMessage,
      })
      .eq("twilio_sid", messageSid)
      .select("id");
    if (updateErr) {
      console.error("[twilio-status] update failed", updateErr);
      return new Response("Server error", { status: 500 });
    }

    if (!updated || updated.length === 0) {
      // No broker row exists for this MessageSid. Insert a placeholder so
      // the status is still captured (and so any later broker-side write
      // for the same sid can be reconciled by the ops dashboard).
      const { error: insertErr } = await supabaseAdmin
        .from("anticipy_twilio_sends")
        .insert({
          to_e164: toNumber,
          body_len: 0,
          kind: "status",
          twilio_sid: messageSid,
          status: messageStatus,
          error_code: errorCode,
          error_message: errorMessage,
          source: "inbound_status_only",
        });
      if (insertErr) {
        // Duplicate sid is fine. Two status pings can race; the second
        // loses the insert race but the row is there.
        const code = (insertErr as { code?: string }).code;
        if (code !== "23505") {
          console.error("[twilio-status] placeholder insert failed", insertErr);
          return new Response("Server error", { status: 500 });
        }
      }
    }
  } catch (exc) {
    console.error("[twilio-status] unexpected error", exc);
    return new Response("Server error", { status: 500 });
  }

  return new Response(null, { status: 200 });
}

export async function OPTIONS() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Twilio-Signature",
    },
  });
}

/**
 * Twilio signs StatusCallback POSTs with the auth token of the account
 * that sent the original message. The broker uses TWILIO_BROKER_TOKEN
 * for its sends, so that is the secret to verify with here. The shared
 * verifyTwilioRequest helper reads TWILIO_AUTH_TOKEN; we replicate its
 * HMAC-SHA1 logic locally with the broker token instead.
 */
function verifyWithBrokerToken(
  token: string,
  signatureHeader: string | null,
  webhookUrl: string,
  params: Record<string, string>,
): boolean {
  if (!signatureHeader) return false;
  const sortedKeys = Object.keys(params).sort();
  let payload = webhookUrl;
  for (const key of sortedKeys) {
    payload += key + params[key];
  }
  const expected = crypto
    .createHmac("sha1", token)
    .update(payload, "utf8")
    .digest("base64");
  const aBuf = Buffer.from(expected);
  const bBuf = Buffer.from(signatureHeader);
  if (aBuf.length !== bBuf.length) return false;
  return crypto.timingSafeEqual(aBuf, bBuf);
}
