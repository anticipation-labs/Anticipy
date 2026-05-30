import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  formDataToParams,
  reconstructWebhookUrl,
  verifyTwilioRequest,
} from "@/lib/twilio-verify";
import {
  sanitizeAssistantName,
  validatePin,
  verifyPin,
  type ProfileRow,
} from "@/lib/profile";

export const dynamic = "force-dynamic";

/**
 * Twilio inbound voice PIN gather callback.
 *
 * Called by /api/twilio/voice as the <Gather action="..."> target.
 * Receives Digits from the caller, looks up all anticipy_profiles
 * rows matching the From E.164, and bcrypt-verifies the PIN against
 * each candidate's pin_hash. On success, returns TwiML that confirms
 * by assistant name and writes the matched user's ID to a per-call
 * routing notification (anticipy_voice_calls). The engine subscribes
 * to that table to pick up the call.
 *
 * On failure, we let the caller retry up to MAX_ATTEMPTS by passing
 * an `attempt` query parameter back to the parent /api/twilio/voice
 * <Gather>. Hard-fails after MAX_ATTEMPTS to prevent online PIN
 * brute-forcing.
 *
 * Note: anticipy_voice_calls is a forward-compat hook; the engine
 * does not yet poll it. Today this route returns ringing TwiML that
 * connects to a placeholder Say + Hangup; once the engine has a
 * voice dispatcher the TwiML here can <Dial> to a SIP endpoint or
 * conference. The auth + routing decision is what scales today.
 */

const MAX_ATTEMPTS = 3;

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function twiml(body: string): Response {
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>\n<Response>${body}</Response>`,
    { headers: { "Content-Type": "text/xml" } },
  );
}

function safeAssistantName(raw: string | null | undefined): string {
  if (!raw) return "Anticipy";
  const result = sanitizeAssistantName(raw);
  return result.ok && result.name ? result.name : "Anticipy";
}

function retryResponse(attempt: number, fromHint: string): Response {
  const nextAttempt = attempt + 1;
  if (nextAttempt > MAX_ATTEMPTS) {
    return twiml(
      `<Say voice="Polly.Joanna">Too many incorrect PIN attempts. Goodbye.</Say><Hangup/>`,
    );
  }
  const action = `/api/twilio/voice/pin?attempt=${nextAttempt}`;
  const remaining = MAX_ATTEMPTS - attempt;
  return twiml(
    `<Say voice="Polly.Joanna">PIN incorrect. You have ${remaining} ${remaining === 1 ? "try" : "tries"} left.</Say>` +
      `<Gather input="dtmf" numDigits="8" finishOnKey="#" timeout="8" action="${action}" method="POST">` +
      `<Say voice="Polly.Joanna">Enter your PIN now.</Say>` +
      `</Gather>` +
      `<Say voice="Polly.Joanna">No PIN received. Goodbye.</Say><Hangup/>`,
  );
}

function successResponse(assistantName: string): Response {
  const safeName = escapeXml(safeAssistantName(assistantName));
  return twiml(
    `<Say voice="Polly.Joanna">PIN accepted. ${safeName} is on the line.</Say>` +
      `<Pause length="1"/>` +
      `<Say voice="Polly.Joanna">Voice routing is in alpha. Please send a text instead, and ${safeName} will reply there.</Say><Hangup/>`,
  );
}

async function recordRouteDecision(
  userId: string,
  callSid: string,
  from: string,
): Promise<void> {
  // Best-effort. The table is only used for forward-compat / audit so
  // a failure here should not block the call.
  try {
    await supabaseAdmin
      .from("anticipy_voice_calls")
      .insert({
        user_id: userId,
        call_sid: callSid,
        from_number: from,
        routed_at: new Date().toISOString(),
      });
  } catch (exc) {
    // Insert may fail if the table does not yet exist; this is forward-
    // compat, do not surface.
    console.warn("[twilio-voice-pin] route audit insert skipped", exc);
  }
}

export async function POST(req: Request) {
  const url = new URL(req.url);
  const attemptParam = parseInt(url.searchParams.get("attempt") || "1", 10);
  const attempt =
    Number.isFinite(attemptParam) && attemptParam >= 1 ? attemptParam : 1;

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    // Malformed body. Treat the same as an unsigned request.
    return new Response("Forbidden", { status: 403 });
  }
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const from = (params.From || "").trim();
  const callSid = (params.CallSid || "").trim();
  const digits = (params.Digits || "").trim();

  if (!from) {
    return twiml(
      `<Say voice="Polly.Joanna">Caller ID missing. Goodbye.</Say><Hangup/>`,
    );
  }

  const pinValidation = validatePin(digits);
  if (!pinValidation.ok || !pinValidation.pin) {
    return retryResponse(attempt, from);
  }

  let matches: ProfileRow[] = [];
  try {
    const { data, error } = await supabaseAdmin
      .from("anticipy_profiles")
      .select("*")
      .eq("phone_e164", from);
    if (error || !data) {
      return twiml(
        `<Say voice="Polly.Joanna">Lookup failed. Please try again later.</Say><Hangup/>`,
      );
    }
    matches = data as ProfileRow[];
  } catch {
    return twiml(
      `<Say voice="Polly.Joanna">Lookup failed. Please try again later.</Say><Hangup/>`,
    );
  }

  // Verify against each candidate. Constant-time iteration over the
  // small candidate set; bcrypt.compare is itself constant-time per
  // hash so this does not leak which row matched.
  let matched: ProfileRow | null = null;
  for (const candidate of matches) {
    if (!candidate.pin_hash) continue;
    const isMatch = await verifyPin(pinValidation.pin, candidate.pin_hash);
    if (isMatch) {
      matched = candidate;
      break;
    }
  }

  if (!matched) {
    return retryResponse(attempt, from);
  }

  await recordRouteDecision(matched.id, callSid, from);
  return successResponse(matched.assistant_name);
}

export async function GET() {
  return new Response("Method Not Allowed", { status: 405 });
}
