import {
  formDataToParams,
  reconstructWebhookUrl,
  verifyTwilioRequest,
} from "@/lib/twilio-verify";

export const dynamic = "force-dynamic";

/**
 * Twilio voice-onboarding entry TwiML.
 *
 * Twilio POSTs here when the outbound voice call placed by
 * /api/twilio/voice-relay connects. The TwiML asks question 1 of 7
 * and sets the <Gather speech> action to /api/twilio/onboarding/answer
 * which loops through the remaining questions and finalises the
 * dossier write.
 *
 * The 7 questions mirror INTERVIEW_SCRIPT in
 * engine/app/anticipy/onboarding.py with phone-friendly wording (no
 * em-dashes, no nested parentheticals; speech-recognition friendly).
 *
 * Twilio signs the body with TWILIO_AUTH_TOKEN. Signature is checked
 * before any reply.
 *
 * Twilio behavior: When credentials are NOT a basic AccountSid/Token
 * (we use API Key SID:Secret in this build) Twilio still signs with
 * the auth token. If TWILIO_BROKER_TOKEN is the API Key secret rather
 * than the legacy AuthToken, the signature check uses the latter.
 */

import { ONBOARDING_QUESTIONS, QUESTION_TOTAL } from "@/lib/onboarding-questions";

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

function notRegisteredHangup(): Response {
  const body =
    '<Say voice="Polly.Joanna">This call was placed without an onboarding context. Goodbye.</Say><Hangup/>';
  return twiml(body);
}

export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    // Malformed body is treated the same as unsigned.
    return new Response("Forbidden", { status: 403 });
  }
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const url = new URL(req.url);
  const accountId = (url.searchParams.get("account_id") || "").trim();
  if (!accountId || accountId.length > 128) {
    return notRegisteredHangup();
  }

  const q0 = escapeXml(ONBOARDING_QUESTIONS[0]);
  const action =
    `/api/twilio/onboarding/answer`
    + `?account_id=${encodeURIComponent(accountId)}`
    + `&q=0`;

  // <Gather input="speech" speechTimeout="auto"> waits for the user to
  // stop speaking, then POSTs SpeechResult to the action URL. The
  // hints list nudges the Twilio recognizer toward the vocabulary
  // common in onboarding answers (names, tools, time zones).
  const body =
    `<Say voice="Polly.Joanna">Hi, this is Anticipy. I have seven quick questions to learn how to help you. Speak naturally after each one, then pause.</Say>`
    + `<Pause length="1"/>`
    + `<Say voice="Polly.Joanna">Question one of seven. ${q0}</Say>`
    + `<Gather input="speech" speechTimeout="auto" timeout="15"`
    + ` language="en-US"`
    + ` hints="boss, reports, partner, gmail, google calendar, notion, slack, linear, pacific, eastern, central, mountain, vancouver, san francisco, new york, toronto"`
    + ` action="${action}" method="POST">`
    + `<Say voice="Polly.Joanna">I am listening.</Say>`
    + `</Gather>`
    + `<Say voice="Polly.Joanna">I did not hear an answer. I will end the call now. Open Anticipy and try again when you have a moment.</Say>`
    + `<Hangup/>`;
  return twiml(body);
}

export async function GET() {
  return new Response("Method Not Allowed", { status: 405 });
}
