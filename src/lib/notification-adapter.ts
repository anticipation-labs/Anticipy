import { Resend } from "resend";
import { sanitizeHeader } from "./escape";
import { supabaseAdmin } from "./supabase-admin";

export type NotificationChannel = "email" | "sms" | "voice";
export type NotificationProvider = "twilio" | "resend" | "cloudflare";
export type NotificationImportance = "low" | "standard" | "important" | "critical";

export interface NotificationRequest {
  intentId?: string;
  userId?: string;
  channel: NotificationChannel;
  to: string;
  subject?: string;
  text: string;
  html?: string;
  importance?: NotificationImportance;
  idempotencyKey?: string;
  metadata?: Record<string, unknown>;
  headers?: Record<string, string>;
  from?: string;
  replyTo?: string;
  recordAttempt?: boolean;
}

export interface NotificationResult {
  ok: boolean;
  channel: NotificationChannel;
  provider: NotificationProvider;
  providerMessageId?: string;
  mock?: boolean;
  error?: string;
}

const resend = new Resend(process.env.RESEND_API_KEY ?? "re_placeholder");

export async function sendNotification(
  request: NotificationRequest
): Promise<NotificationResult> {
  const provider = chooseProvider(request.channel);
  if (mockMode(request.channel)) {
    const result: NotificationResult = {
      ok: true,
      channel: request.channel,
      provider,
      providerMessageId: `mock_${provider}_${Date.now()}`,
      mock: true,
    };
    await recordNotificationAttempt(request, result, "mock_sent");
    return result;
  }

  let result: NotificationResult;
  try {
    if (request.channel === "sms") {
      result = await sendTwilioSms(request);
    } else if (request.channel === "voice") {
      result = await sendTwilioVoice(request);
    } else if (provider === "cloudflare") {
      result = await sendCloudflareEmail(request);
    } else {
      result = await sendResendEmail(request);
    }
  } catch (err) {
    result = {
      ok: false,
      channel: request.channel,
      provider,
      error: err instanceof Error ? err.message : "Notification send failed",
    };
  }

  await recordNotificationAttempt(
    request,
    result,
    result.ok ? "sent" : "failed"
  );
  return result;
}

function chooseProvider(channel: NotificationChannel): NotificationProvider {
  if (channel === "sms" || channel === "voice") return "twilio";
  const configured = (process.env.ANTICIPY_NOTIFY_EMAIL_PROVIDER || "auto").toLowerCase();
  if (configured === "cloudflare") return "cloudflare";
  if (configured === "resend") return "resend";
  if (process.env.CLOUDFLARE_ACCOUNT_ID && process.env.CLOUDFLARE_EMAIL_API_TOKEN) {
    return "cloudflare";
  }
  return "resend";
}

function mockMode(channel: NotificationChannel): boolean {
  if (process.env.ANTICIPY_NOTIFY_MOCK === "true") return true;
  return (channel === "sms" || channel === "voice") && process.env.TWILIO_MOCK === "true";
}

function fromEmail(request: NotificationRequest): { email: string; formatted: string } {
  const configuredEmail =
    request.from ||
    process.env.ANTICIPY_NOTIFY_FROM_EMAIL ||
    "notifications@aevoy.com";
  const match = configuredEmail.match(/<([^>]+)>/);
  const email = sanitizeHeader((match?.[1] || configuredEmail).trim(), 180);
  assertAllowedFromEmail(email);
  const name = sanitizeHeader(
    process.env.ANTICIPY_NOTIFY_FROM_NAME || "Anticipy",
    80
  );
  const formatted = configuredEmail.includes("<") ? configuredEmail : `${name} <${email}>`;
  return { email, formatted };
}

function assertAllowedFromEmail(email: string): void {
  const allowlist = (process.env.ANTICIPY_NOTIFY_FROM_ALLOWLIST ||
    "notifications@aevoy.com,aevoy@aevoy.com")
    .split(",")
    .map((v) => v.trim().toLowerCase())
    .filter(Boolean);
  if (!allowlist.includes(email.toLowerCase())) {
    throw new Error(`from address is not in allowlist: ${email}`);
  }
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required env var: ${name}`);
  return value;
}

async function sendTwilioSms(
  request: NotificationRequest
): Promise<NotificationResult> {
  const sid = requireEnv("TWILIO_ACCOUNT_SID");
  const token = requireEnv("TWILIO_AUTH_TOKEN");
  const phone = process.env.TWILIO_PHONE_NUMBER;
  const messagingService = process.env.TWILIO_MESSAGING_SERVICE_SID;
  if (!phone && !messagingService) {
    throw new Error("Missing TWILIO_PHONE_NUMBER or TWILIO_MESSAGING_SERVICE_SID");
  }

  const params = new URLSearchParams({
    To: request.to,
    Body: request.text,
  });
  if (messagingService) {
    params.set("MessagingServiceSid", messagingService);
  } else if (phone) {
    params.set("From", phone);
  }
  if (process.env.TWILIO_STATUS_CALLBACK_URL) {
    params.set("StatusCallback", process.env.TWILIO_STATUS_CALLBACK_URL);
  }

  const data = await twilioPost(sid, token, "Messages.json", params);
  return {
    ok: true,
    channel: "sms",
    provider: "twilio",
    providerMessageId: data.sid,
  };
}

async function sendTwilioVoice(
  request: NotificationRequest
): Promise<NotificationResult> {
  const sid = requireEnv("TWILIO_ACCOUNT_SID");
  const token = requireEnv("TWILIO_AUTH_TOKEN");
  const phone = requireEnv("TWILIO_PHONE_NUMBER");
  const baseUrl =
    process.env.NEXT_PUBLIC_SITE_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000");

  const params = new URLSearchParams({
    To: request.to,
    From: phone,
  });
  if (request.intentId) {
    params.set("Url", `${baseUrl}/api/engine/twilio/voice-script/${request.intentId}`);
    params.set("Method", "POST");
  } else {
    params.set("Twiml", `<Response><Say>${escapeXml(request.text)}</Say></Response>`);
  }
  if (process.env.TWILIO_STATUS_CALLBACK_URL) {
    params.set("StatusCallback", process.env.TWILIO_STATUS_CALLBACK_URL);
  }

  const data = await twilioPost(sid, token, "Calls.json", params);
  return {
    ok: true,
    channel: "voice",
    provider: "twilio",
    providerMessageId: data.sid,
  };
}

async function twilioPost(
  sid: string,
  token: string,
  resource: string,
  params: URLSearchParams
): Promise<{ sid?: string }> {
  const res = await fetch(
    `https://api.twilio.com/2010-04-01/Accounts/${sid}/${resource}`,
    {
      method: "POST",
      headers: {
        Authorization: `Basic ${Buffer.from(`${sid}:${token}`).toString("base64")}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: params.toString(),
    }
  );
  if (!res.ok) {
    throw new Error(`Twilio ${resource} error ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

async function sendResendEmail(
  request: NotificationRequest
): Promise<NotificationResult> {
  requireEnv("RESEND_API_KEY");
  const subject = sanitizeHeader(request.subject || "Anticipy", 180);
  const from = fromEmail(request).formatted;
  const { data, error } = await resend.emails.send({
    from,
    to: request.to,
    subject,
    html: request.html,
    text: request.text,
    replyTo: request.replyTo || process.env.ANTICIPY_NOTIFY_REPLY_TO,
    headers: request.headers,
  });
  if (error) {
    throw new Error(`Resend error: ${JSON.stringify(error)}`);
  }
  return {
    ok: true,
    channel: "email",
    provider: "resend",
    providerMessageId: data?.id,
  };
}

async function sendCloudflareEmail(
  request: NotificationRequest
): Promise<NotificationResult> {
  const accountId = requireEnv("CLOUDFLARE_ACCOUNT_ID");
  const token = requireEnv("CLOUDFLARE_EMAIL_API_TOKEN");
  const subject = sanitizeHeader(request.subject || "Anticipy", 180);
  const { formatted } = fromEmail(request);
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/email/sending/send`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: formatted,
        to: [request.to],
        subject,
        html: request.html,
        text: request.text,
        headers: request.headers,
      }),
    }
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data?.success === false) {
    throw new Error(`Cloudflare email error ${res.status}: ${JSON.stringify(data)}`);
  }
  return {
    ok: true,
    channel: "email",
    provider: "cloudflare",
    providerMessageId: String(data?.result?.id || data?.result?.message_id || ""),
  };
}

async function recordNotificationAttempt(
  request: NotificationRequest,
  result: NotificationResult,
  status: string
): Promise<void> {
  if (request.recordAttempt === false || !request.intentId) return;
  try {
    await supabaseAdmin.from("anticipy_notifications").insert({
      intent_id: request.intentId,
      user_id: request.userId,
      channel: request.channel,
      provider: result.provider,
      provider_message_id: result.providerMessageId,
      recipient: request.to,
      status,
      idempotency_key: request.idempotencyKey,
      error: result.error,
      metadata: request.metadata || {},
    });
  } catch {
    try {
      await supabaseAdmin.from("anticipy_notifications").insert({
        intent_id: request.intentId,
        channel: request.channel,
        recipient: request.to,
        status,
      });
    } catch {
      // Notification delivery must not fail because receipt logging failed.
    }
  }
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
