/** SendBlue is the only live texting provider.
 * Old Twilio settings are ignored; invalid or incomplete configuration fails
 * without a network call. Provider acceptance is not a delivery receipt.
 * Logs contain provider/status and recipient suffix, never credentials or text.
 */

export interface MessagingEnv {
  // Sendblue — iMessage, else RCS, else SMS, from one number.
  SENDBLUE_API_KEY_ID?: string;
  SENDBLUE_API_SECRET_KEY?: string;
  SENDBLUE_FROM_NUMBER?: string;
  /** Test-only. Honoured for a loopback host and ignored for anything else. */
  SENDBLUE_API_BASE?: string;
  /** "sendblue". Empty also selects SendBlue when configured; anything else disables sending. */
  ANTICIPY_SMS_PROVIDER?: string;

  // Legacy deployment fields accepted for compatibility, never used to send.
  TWILIO_ACCOUNT_SID?: string;
  TWILIO_AUTH_TOKEN?: string;
  TWILIO_PHONE_NUMBER?: string;
  TWILIO_FROM?: string;
  TWILIO_API_KEY_SID?: string;
  TWILIO_API_KEY_SECRET?: string;
  /** Ignored legacy field, including in tests. */
  TWILIO_API_BASE?: string;
}

export type Provider = "sendblue";

export type SendResult =
  | { ok: true; provider: Provider; id: string; status: string }
  | { ok: false; provider: Provider | "none"; status: number; error: string };

export interface SendOptions {
  /** Names the caller in the log line, e.g. "password reset". Never the body. */
  tag?: string;
  /** Sendblue only: a URL Sendblue POSTs delivery status to. */
  statusCallback?: string;
}

export const SENDBLUE_BASE = "https://api.sendblue.com";
/** cron.ts carried `AbortSignal.timeout(15_000)`; a hung provider must not hold a tick open. */
export const SEND_TIMEOUT_MS = 15_000;

/** The Sendblue statuses that mean "this did not go out" even on a 2xx. */
const SENDBLUE_FAILED = new Set(["ERROR", "DECLINED"]);

function sendblueConfigured(env: MessagingEnv): boolean {
  return !!(str(env.SENDBLUE_API_KEY_ID) && str(env.SENDBLUE_API_SECRET_KEY)
    && str(env.SENDBLUE_FROM_NUMBER));
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/** Which provider `sendText` will use for this environment. Pure. */
export function chooseProvider(env: MessagingEnv): Provider | "none" {
  const said = str(env.ANTICIPY_SMS_PROVIDER).toLowerCase();
  if (said && said !== "sendblue") return "none";
  return sendblueConfigured(env) ? "sendblue" : "none";
}

/**
 * The test-only host override and its seatbelt: a base that is not loopback is
 * ignored, with a log line, and the real host is used. Same rule as
 * src/llm.ts providerBase and brain/voice_arm.py _cannot_reach_a_phone.
 */
export function apiBase(raw: string | undefined, real: string, name: string): string {
  const base = str(raw).replace(/\/+$/, "");
  if (!base) return real;
  let host = "";
  try { host = new URL(base).hostname; } catch { host = ""; }
  if (host !== "127.0.0.1" && host !== "localhost" && host !== "[::1]") {
    // The host, not the value: a pasted URL can carry a token in its path.
    console.log("messaging: " + name + " ignored, not a loopback host: " + (host || "(unparseable)"));
    return real;
  }
  return base;
}

/** The last four digits, for a log line. Never the number. */
export function last4(to: string): string {
  const digits = String(to ?? "").replace(/\D/g, "");
  return "…" + digits.slice(-4);
}

/**
 * Send one text. Never throws on a provider error; never logs a secret or
 * the body. See the header for what `ok` means.
 */
export async function sendText(
  env: MessagingEnv, to: string, body: string, opts: SendOptions = {},
): Promise<SendResult> {
  const who = (opts.tag ? opts.tag + ": " : "") + "messaging";
  const recipient = str(to);
  if (!recipient) {
    console.log(who + ": no recipient — nothing sent");
    return { ok: false, provider: "none", status: 0, error: "no recipient" };
  }
  const provider = chooseProvider(env);
  if (provider === "none") {
    console.log(who + ": no messaging provider configured — nothing sent to " + last4(recipient));
    return { ok: false, provider: "none", status: 0, error: "no messaging provider configured" };
  }
  try {
    return await viaSendblue(env, recipient, body, opts, who);
  } catch (err) {
    // Only the error name is logged; never expose request details.
    // The name is enough to tell a timeout
    // from a refused connection, and it is all that is logged.
    const name = err instanceof Error ? err.name : "Error";
    console.log(who + ": " + provider + " send to " + last4(recipient) + " threw " + name);
    return { ok: false, provider, status: 0, error: name };
  }
}

async function viaSendblue(
  env: MessagingEnv, to: string, body: string, opts: SendOptions, who: string,
): Promise<SendResult> {
  if (!sendblueConfigured(env)) {
    // The switch said Sendblue and the keys are not there. Say so; do not
    // text from the retiring number instead.
    console.log(who + ": sendblue selected but not configured — nothing sent to " + last4(to));
    return { ok: false, provider: "sendblue", status: 0, error: "sendblue is not configured" };
  }
  const payload: Record<string, string> = {
    from_number: str(env.SENDBLUE_FROM_NUMBER),
    number: to,
    content: body,
  };
  if (str(opts.statusCallback)) payload.status_callback = str(opts.statusCallback);

  const res = await fetch(apiBase(env.SENDBLUE_API_BASE, SENDBLUE_BASE, "SENDBLUE_API_BASE")
      + "/api/send-message", {
    method: "POST",
    headers: {
      "sb-api-key-id": str(env.SENDBLUE_API_KEY_ID),
      "sb-api-secret-key": str(env.SENDBLUE_API_SECRET_KEY),
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(SEND_TIMEOUT_MS),
  });

  let reply: Record<string, unknown> | null = null;
  try {
    const v: unknown = await res.json();
    if (v && typeof v === "object") reply = v as Record<string, unknown>;
  } catch { reply = null; }

  const status = reply ? String(reply.status ?? "").toUpperCase() : "";
  const code = reply ? reply.error_code : undefined;
  const hasError = code !== undefined && code !== null && code !== "" && code !== 0;
  const id = reply ? String(reply.message_handle ?? "") : "";
  const line = who + ": sendblue → " + last4(to) + " http=" + res.status
    + " status=" + (status || "?") + (hasError ? " error_code=" + String(code) : "");

  if (!res.ok) {
    console.log(line);
    return { ok: false, provider: "sendblue", status: res.status,
             error: describe(reply, "http " + res.status) };
  }
  if (!reply) {
    console.log(line + " (unreadable reply)");
    return { ok: false, provider: "sendblue", status: res.status, error: "unreadable response" };
  }
  if (SENDBLUE_FAILED.has(status) || hasError) {
    console.log(line);
    return { ok: false, provider: "sendblue", status: res.status,
             error: describe(reply, "status " + status) };
  }
  console.log(line + (id ? " id=" + id : ""));
  return { ok: true, provider: "sendblue", id, status };
}

/** The provider's own words for the RESULT only — callers do not log it. */
function describe(reply: Record<string, unknown> | null, fallback: string): string {
  const msg = reply ? String(reply.error_message ?? "") : "";
  const code = reply && reply.error_code != null ? String(reply.error_code) : "";
  return [code, msg].filter(Boolean).join(" ") || fallback;
}
