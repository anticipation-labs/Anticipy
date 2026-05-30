import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  formDataToParams,
  reconstructWebhookUrl,
  verifyTwilioRequest,
} from "@/lib/twilio-verify";
import {
  sanitizeAssistantName,
  shouldResetWindow,
  type ProfileRow,
} from "@/lib/profile";

export const dynamic = "force-dynamic";

/**
 * Twilio inbound voice webhook for the shared Anticipy broker number.
 *
 * Twilio POSTs here when the shared inbound number receives a call.
 * The route returns TwiML that:
 *   1. If the From E.164 maps to exactly one anticipy_profiles row AND
 *      that user has voice budget left today, greets the user by their
 *      chosen assistant name and gathers a 6 digit PIN by DTMF.
 *   2. If multiple rows share that phone (account shared across users),
 *      same gather flow, PIN disambiguates which user's engine to wake.
 *   3. If no rows match, says the number is not registered and hangs up.
 *
 * The PIN entered by the caller is verified by the sibling
 * /api/twilio/voice/pin route, which is the `action` of the <Gather>
 * and runs bcrypt against the candidate hashes.
 *
 * Signature is verified with TWILIO_AUTH_TOKEN before any DB read.
 */

interface VoiceGreetContext {
  to: string;
  from: string;
  assistantName: string;
  candidateCount: number;
  callSid: string;
}

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

function notRegisteredResponse(): Response {
  const body =
    '<Say voice="Polly.Joanna">This number is not registered with Anticipy. Visit anticipy.ai/app to set up.</Say><Hangup/>';
  return twiml(body);
}

function capReachedResponse(assistantName: string): Response {
  const safeName = escapeXml(safeAssistantName(assistantName));
  const body =
    `<Say voice="Polly.Joanna">${safeName} has reached today's voice limit. Please try again tomorrow, or send a text.</Say><Hangup/>`;
  return twiml(body);
}

function greetAndGather(ctx: VoiceGreetContext): Response {
  // We always require the PIN, even when there is a single candidate
  // for the From number, so the same number cannot impersonate the
  // owner from a stolen handset. The greeting names the assistant so
  // the caller knows they reached the right person's setup.
  const safeName = escapeXml(safeAssistantName(ctx.assistantName));
  const action = `/api/twilio/voice/pin`;
  const body =
    `<Say voice="Polly.Joanna">Hi, ${safeName} here. Please enter your 4 to 8 digit PIN, then press pound.</Say>` +
    `<Gather input="dtmf" numDigits="8" finishOnKey="#" timeout="8" action="${action}" method="POST">` +
    `<Say voice="Polly.Joanna">Enter your PIN now.</Say>` +
    `</Gather>` +
    `<Say voice="Polly.Joanna">No PIN received. Goodbye.</Say><Hangup/>`;
  return twiml(body);
}

export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    // Malformed body (e.g. JSON sent to a Twilio webhook) is treated
    // the same as an unsigned request. Return 403 so probers and
    // accidental hits do not get a 500.
    return new Response("Forbidden", { status: 403 });
  }
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const from = (params.From || "").trim();
  const to = (params.To || "").trim();
  const callSid = (params.CallSid || "").trim();

  if (!from) {
    return notRegisteredResponse();
  }

  let matches: ProfileRow[] = [];
  try {
    const { data, error } = await supabaseAdmin
      .from("anticipy_profiles")
      .select("*")
      .eq("phone_e164", from);
    if (error) {
      console.error("[twilio-voice] profile lookup failed", error);
      return notRegisteredResponse();
    }
    matches = (data ?? []) as ProfileRow[];
  } catch (exc) {
    console.error("[twilio-voice] profile lookup raised", exc);
    return notRegisteredResponse();
  }

  if (matches.length === 0) {
    return notRegisteredResponse();
  }

  // For multi-account shared-phone setups, pick the assistant name of
  // the most recently active user as the greeting. The PIN gather
  // disambiguates which engine actually wakes up.
  let chosen = matches[0];
  if (matches.length > 1) {
    const sorted = matches
      .slice()
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
    chosen = sorted[0];
  }

  // Cap: if every candidate has hit today's voice cap there is no
  // point gathering a PIN. The cap window can have rolled, so we
  // honor shouldResetWindow before comparing.
  const eligible = matches.filter((row) => {
    const reset = shouldResetWindow(row.daily_window_started_at);
    const usedToday = reset ? 0 : Number(row.daily_voice_minutes_used) || 0;
    return usedToday < Number(row.daily_voice_minutes_cap || 0);
  });
  if (eligible.length === 0) {
    return capReachedResponse(chosen.assistant_name);
  }

  return greetAndGather({
    to,
    from,
    assistantName: chosen.assistant_name,
    candidateCount: matches.length,
    callSid,
  });
}

export async function GET() {
  // Twilio uses POST. Anything else gets a 405 so curious GETs do not
  // accidentally see an empty TwiML envelope and assume the route is up.
  return new Response("Method Not Allowed", { status: 405 });
}
