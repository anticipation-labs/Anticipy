import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  verifyTwilioRequest,
  reconstructWebhookUrl,
  formDataToParams,
} from "@/lib/twilio-verify";

export const dynamic = "force-dynamic";

/**
 * TwiML endpoint for Twilio voice calls.
 * Speaks the intent summary and gathers user response (speech or DTMF).
 *
 * Verified against the X-Twilio-Signature header — without this an
 * attacker who guessed an intent UUID could pull the summary text by
 * hitting this URL directly.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ intentId: string }> }
) {
  const formData = await req.formData();
  const twilioParams = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), twilioParams)) {
    return new Response("Forbidden", { status: 403 });
  }

  const { intentId } = await params;

  const { data: intent } = await supabaseAdmin
    .from("anticipy_intents")
    .select("summary_for_user, evidence_quote, importance")
    .eq("id", intentId)
    .single();

  if (!intent) {
    const twiml = `<?xml version="1.0" encoding="UTF-8"?>
<Response><Say voice="Polly.Joanna">Sorry, I could not find that action. Goodbye.</Say></Response>`;
    return new Response(twiml, {
      headers: { "Content-Type": "text/xml" },
    });
  }

  const baseUrl =
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.VERCEL_URL
      ? `https://${process.env.VERCEL_URL}`
      : "http://localhost:3000");

  const callbackUrl = `${baseUrl}/api/engine/twilio/voice-callback?intentId=${intentId}`;

  const twiml = `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">Hi, this is Anticipy.</Say>
  <Pause length="1"/>
  <Say voice="Polly.Joanna">${escapeXml(intent.summary_for_user)}</Say>
  <Pause length="1"/>
  <Gather input="speech dtmf" timeout="10" numDigits="1" action="${escapeXml(callbackUrl)}" method="POST">
    <Say voice="Polly.Joanna">Press 1 or say yes to confirm. Press 2 or say no to skip.</Say>
  </Gather>
  <Say voice="Polly.Joanna">I didn't hear a response. I'll skip this one for now. Goodbye.</Say>
</Response>`;

  return new Response(twiml, {
    headers: { "Content-Type": "text/xml" },
  });
}

// Twilio is configured (in twilio-notify.ts) to fetch this URL via POST,
// so GET should never reach here in practice. We refuse it explicitly so an
// unsigned probe can't bypass the signature check by switching method.
export async function GET() {
  return new Response("Method Not Allowed", { status: 405 });
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
