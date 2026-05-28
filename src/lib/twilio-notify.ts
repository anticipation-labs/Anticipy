import { sendNotification } from "./notification-adapter";

interface TwilioResult {
  success: boolean;
  sid?: string;
  mock?: boolean;
  error?: string;
}

/**
 * Send SMS notification. Falls back to mock/log mode when Twilio credentials are unavailable.
 */
export async function sendSMS(
  to: string,
  body: string,
  intentId?: string
): Promise<TwilioResult> {
  const result = await sendNotification({
    channel: "sms",
    to,
    text: body,
    intentId,
    idempotencyKey: intentId ? `sms:${intentId}:${to}` : undefined,
  });
  return {
    success: result.ok,
    sid: result.providerMessageId,
    mock: result.mock,
    error: result.error,
  };
}

/**
 * Initiate a voice call with interactive TwiML (Gather for speech/DTMF).
 * Uses a TwiML URL endpoint for dynamic voice script with user response handling.
 */
export async function sendVoiceCall(
  to: string,
  message: string,
  intentId?: string
): Promise<TwilioResult> {
  const result = await sendNotification({
    channel: "voice",
    to,
    text: message,
    intentId,
    importance: "critical",
    idempotencyKey: intentId ? `voice:${intentId}:${to}` : undefined,
  });
  return {
    success: result.ok,
    sid: result.providerMessageId,
    mock: result.mock,
    error: result.error,
  };
}

/**
 * Send notification via the user's preferred channel.
 * Tries SMS first, then voice for critical importance.
 */
export async function sendTwilioNotification(
  to: string,
  summary: string,
  importance: string,
  intentId?: string
): Promise<TwilioResult> {
  // Always send SMS
  const smsBody = `Anticipy: ${summary}\n\nReply YES to confirm or NO to skip.`;
  const smsResult = await sendSMS(to, smsBody, intentId);

  // For critical items, also call
  if (importance === "critical") {
    await sendVoiceCall(to, summary, intentId);
  }

  return smsResult;
}
