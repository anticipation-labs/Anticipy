/**
 * src/messaging.ts — the one place this Worker sends a text.
 *
 * Two routes text on their own, and until 2026-09-05 each carried its own
 * hardcoded Twilio request: the HQ reminder sweep (cron.ts `sendSMS`) and the
 * six-digit password-reset code (routes/password_reset.ts `sendCode`). The
 * texting channel is moving to Sendblue (research/2026-09-05-cloudflare-era-plan.md,
 * "The texting channel moves from Twilio to Sendblue"), so both now come here,
 * and here is where the provider is chosen.
 *
 * WHO IS CHOSEN, in order:
 *   1. ANTICIPY_SMS_PROVIDER=sendblue or =twilio is the owner's word and wins
 *      outright. "sendblue" with no Sendblue keys is a FAILED send, never a
 *      quiet fall-through to the retiring number.
 *   2. Otherwise Sendblue when SENDBLUE_API_KEY_ID, SENDBLUE_API_SECRET_KEY and
 *      SENDBLUE_FROM_NUMBER are all bound.
 *   3. Otherwise Twilio when its account, a sender and a credential are bound —
 *      the exact request the two call sites used to build.
 *   4. Otherwise nothing is sent and the result says so.
 *
 * WHAT "SENT" MEANS. A reset code that silently fails is a locked-out owner; a
 * reminder that fails must not be stamped as delivered (cron.ts logAct
 * "reminder.sent" vs "reminder.gave_up"). So `ok: true` is strict:
 *   Sendblue — a 2xx whose body carries neither status ERROR/DECLINED nor an
 *              error_code. A 2xx the Worker cannot read is NOT a success.
 *   Twilio   — `res.ok`, exactly as before.
 * Nothing here throws on a provider error: a timeout, a refused connection or
 * a bad body all come back as `{ ok: false }`.
 *
 * WHAT IS LOGGED. Provider, the last four digits of the recipient, the HTTP
 * status and the provider's status/error code. Never a key, never a token,
 * never the message body (a reset code IS the body), never a whole number.
 *
 * SENDBLUE_API_BASE / TWILIO_API_BASE replace the real host for a LOOPBACK
 * value only — the rule brain/voice_arm.py `_cannot_reach_a_phone` and
 * src/llm.ts `providerBase` both apply — so a test can point the real code at
 * a recorder and nothing else can point it anywhere.
 *
 * Sendblue's wire (docs.sendblue.com, checked 2026-09-05):
 *   POST {base}/api/send-message
 *   headers  sb-api-key-id, sb-api-secret-key
 *   body     { from_number, number, content, status_callback? }   all E.164
 *   reply    { message_handle, status, error_code, error_message, … }
 *   status ∈ QUEUED PENDING SENT DELIVERED ACCEPTED … ERROR DECLINED
 */

export interface MessagingEnv {
  // Sendblue — iMessage, else RCS, else SMS, from one number.
  SENDBLUE_API_KEY_ID?: string;
  SENDBLUE_API_SECRET_KEY?: string;
  SENDBLUE_FROM_NUMBER?: string;
  /** Test-only. Honoured for a loopback host and ignored for anything else. */
  SENDBLUE_API_BASE?: string;
  /** "sendblue" | "twilio". Unset: chosen by what is configured. */
  ANTICIPY_SMS_PROVIDER?: string;

  // Twilio — retiring. Kept until the plan's step 9 removes the secrets.
  TWILIO_ACCOUNT_SID?: string;
  TWILIO_AUTH_TOKEN?: string;
  TWILIO_PHONE_NUMBER?: string;
  TWILIO_FROM?: string;
  TWILIO_API_KEY_SID?: string;
  TWILIO_API_KEY_SECRET?: string;
  /** Test-only, same loopback rule. */
  TWILIO_API_BASE?: string;
}

export type Provider = "sendblue" | "twilio";

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
export const TWILIO_BASE = "https://api.twilio.com";
/** cron.ts carried `AbortSignal.timeout(15_000)`; a hung provider must not hold a tick open. */
export const SEND_TIMEOUT_MS = 15_000;

/** The Sendblue statuses that mean "this did not go out" even on a 2xx. */
const SENDBLUE_FAILED = new Set(["ERROR", "DECLINED"]);

function sendblueConfigured(env: MessagingEnv): boolean {
  return !!(str(env.SENDBLUE_API_KEY_ID) && str(env.SENDBLUE_API_SECRET_KEY)
    && str(env.SENDBLUE_FROM_NUMBER));
}

function twilioConfigured(env: MessagingEnv): boolean {
  const cred = twilioCredential(env);
  return !!(str(env.TWILIO_ACCOUNT_SID) && twilioFrom(env) && cred.user && cred.secret);
}

function twilioFrom(env: MessagingEnv): string {
  // TWILIO_PHONE_NUMBER *or* TWILIO_FROM, as internal_hq.pb.js:2167 has it.
  // Reading only the first means a deployment that sets the second sends
  // nothing at all and reports no error.
  return str(env.TWILIO_PHONE_NUMBER) || str(env.TWILIO_FROM);
}

/**
 * Same preference as brain/voice_arm.py and the old password_reset.ts: a
 * scoped, revocable API key over the full-access auth token. Both key names
 * or neither — one alone falls back to the token.
 */
function twilioCredential(env: MessagingEnv): { user: string; secret: string } {
  const keySid = str(env.TWILIO_API_KEY_SID);
  const keySecret = str(env.TWILIO_API_KEY_SECRET);
  if (keySid && keySecret) return { user: keySid, secret: keySecret };
  return { user: str(env.TWILIO_ACCOUNT_SID), secret: str(env.TWILIO_AUTH_TOKEN) };
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

/** Which provider `sendText` will use for this environment. Pure. */
export function chooseProvider(env: MessagingEnv): Provider | "none" {
  const said = str(env.ANTICIPY_SMS_PROVIDER).toLowerCase();
  if (said === "sendblue" || said === "twilio") return said;
  if (said) {
    console.log("messaging: ANTICIPY_SMS_PROVIDER=" + said.slice(0, 32)
      + " is not a provider; choosing by what is configured");
  }
  if (sendblueConfigured(env)) return "sendblue";
  if (twilioConfigured(env)) return "twilio";
  return "none";
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
    return provider === "sendblue"
      ? await viaSendblue(env, recipient, body, opts, who)
      : await viaTwilio(env, recipient, body, who);
  } catch (err) {
    // A thrown fetch carries a URL at most: Twilio's has the account SID (not
    // a secret), Sendblue's nothing. The name is enough to tell a timeout
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

/**
 * The request the two call sites built until 2026-09-05, moved here unchanged:
 * Basic auth, form body To/From/Body, `res.ok` as the truth.
 * internal_hq.pb.js:2164-2190 and password_reset.pb.js:104.
 */
async function viaTwilio(
  env: MessagingEnv, to: string, body: string, who: string,
): Promise<SendResult> {
  const sid = str(env.TWILIO_ACCOUNT_SID);
  const from = twilioFrom(env);
  const cred = twilioCredential(env);
  if (!sid || !from || !cred.user || !cred.secret) {
    console.log(who + ": twilio selected but not configured — nothing sent to " + last4(to));
    return { ok: false, provider: "twilio", status: 0, error: "twilio is not configured" };
  }
  const base = apiBase(env.TWILIO_API_BASE, TWILIO_BASE, "TWILIO_API_BASE");
  const res = await fetch(`${base}/2010-04-01/Accounts/${sid}/Messages.json`, {
    method: "POST",
    headers: {
      Authorization: "Basic " + btoa(`${cred.user}:${cred.secret}`),
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ To: to, From: from, Body: body }),
    signal: AbortSignal.timeout(SEND_TIMEOUT_MS),
  });

  let reply: Record<string, unknown> | null = null;
  try {
    const v: unknown = await res.json();
    if (v && typeof v === "object") reply = v as Record<string, unknown>;
  } catch { reply = null; }
  const status = reply ? String(reply.status ?? "") : "";
  const line = who + ": twilio → " + last4(to) + " http=" + res.status + " status=" + (status || "?");
  console.log(line);
  if (!res.ok) {
    const code = reply && reply.code != null ? String(reply.code) : "";
    return { ok: false, provider: "twilio", status: res.status, error: code || "http " + res.status };
  }
  return { ok: true, provider: "twilio", id: reply ? String(reply.sid ?? "") : "", status };
}
