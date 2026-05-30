import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const dynamic = "force-dynamic";

/**
 * Twilio outbound VOICE broker for the engine.
 *
 * Counterpart to /api/twilio/relay (SMS). Strangers downloading the
 * Mac DMG do not have their own Twilio accounts, so the local engine
 * cannot reach api.twilio.com directly to place a voice call. This
 * route is the website-side relay:
 *
 *   1. Authenticates the caller via Supabase session bearer token.
 *   2. Per-user and per-IP rate limits.
 *   3. Validates payload (E.164 recipient, US/CA only, allowed kind).
 *   4. Places the outbound call via Twilio Calls.json using the broker
 *      creds in TWILIO_BROKER_ACCOUNT_SID + TWILIO_BROKER_SID +
 *      TWILIO_BROKER_TOKEN + TWILIO_BROKER_FROM.
 *   5. The TwiML URL points at /api/twilio/onboarding/initial which
 *      walks the user through the 7-question Anticipy onboarding
 *      script. The same call_sid is the join key for every answer.
 *   6. Logs the placement to public.anticipy_voice_onboarding_calls
 *      so the engine can poll for transcript progress and surface it
 *      back to the popover.
 *
 * Voice does NOT need A2P 10DLC (that is SMS-only). It DOES need a
 * verified caller-ID for restricted Twilio accounts; if Twilio
 * returns error code 21215 the response surfaces the message verbatim
 * so the operator knows to verify +16196584447 in the Twilio console.
 *
 * Env required (Vercel):
 *   TWILIO_BROKER_ACCOUNT_SID
 *   TWILIO_BROKER_SID
 *   TWILIO_BROKER_TOKEN
 *   TWILIO_BROKER_FROM
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 *   SUPABASE_SERVICE_ROLE_KEY
 *
 * Optional:
 *   TWILIO_BROKER_VOICE_DAILY_USD_CAP  default 5
 *   TWILIO_BROKER_VOICE_PRICE_USD      default 0.20 (per call, conservative)
 *
 * Supabase: see ./MIGRATION.sql for anticipy_voice_onboarding_calls.
 */

const ALLOWED_KINDS = new Set(["onboarding"]);
const E164_PATTERN = /^\+[1-9]\d{6,14}$/;
const PREMIUM_PREFIXES = ["+1900", "+1976"];

interface RelayBody {
  to?: unknown;
  account_id?: unknown;
  kind?: unknown;
}

interface ValidatedPayload {
  to: string;
  accountId: string;
  kind: string;
}

function validatePayload(input: unknown): ValidatedPayload | null {
  if (!input || typeof input !== "object") return null;
  const src = input as RelayBody;
  const to = typeof src.to === "string" ? src.to.trim() : "";
  const accountId =
    typeof src.account_id === "string" ? src.account_id.trim() : "";
  const kind = typeof src.kind === "string" ? src.kind.trim() : "onboarding";
  if (!E164_PATTERN.test(to)) return null;
  if (!ALLOWED_KINDS.has(kind)) return null;
  if (!accountId || accountId.length > 128) return null;
  return { to, accountId, kind };
}

function isAllowedDestination(to: string): { ok: boolean; reason?: string } {
  if (!to.startsWith("+1")) {
    return {
      ok: false,
      reason:
        "Anticipy currently only calls US and Canada (+1) numbers. "
        + "International calls are disabled.",
    };
  }
  for (const prefix of PREMIUM_PREFIXES) {
    if (to.startsWith(prefix)) {
      return {
        ok: false,
        reason: "Premium-rate destination numbers are blocked.",
      };
    }
  }
  return { ok: true };
}

async function checkAccountWideVoiceCap(): Promise<{
  ok: boolean;
  reason?: string;
}> {
  const capUsd = Number(
    process.env.TWILIO_BROKER_VOICE_DAILY_USD_CAP || "5",
  );
  const pricePerCall = Number(
    process.env.TWILIO_BROKER_VOICE_PRICE_USD || "0.20",
  );
  if (!Number.isFinite(capUsd) || capUsd <= 0) return { ok: true };
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const { count, error } = await supabaseAdmin
    .from("anticipy_voice_onboarding_calls")
    .select("id", { count: "exact", head: true })
    .gte("placed_at", since);
  if (error) {
    // Fail-open on a transient Supabase blip; cap is best-effort.
    console.error("[voice-relay] cap query failed", error);
    return { ok: true };
  }
  const spend = (count ?? 0) * pricePerCall;
  if (spend >= capUsd) {
    return {
      ok: false,
      reason: `Account-wide daily voice cap reached ($${capUsd.toFixed(2)}).`,
    };
  }
  return { ok: true };
}

async function logPlacement(
  userId: string,
  accountId: string,
  to: string,
  twilioSid: string,
  status: string,
  errorDetail: string,
): Promise<void> {
  try {
    const { error } = await supabaseAdmin
      .from("anticipy_voice_onboarding_calls")
      .insert({
        user_id: userId,
        account_id: accountId,
        to_e164: to,
        twilio_sid: twilioSid,
        status: status,
        error: errorDetail || null,
        answers: [],
        question_index: 0,
        question_total: 7,
      });
    if (error) {
      console.error("[voice-relay] log insert failed", error);
    }
  } catch (exc) {
    console.error("[voice-relay] log insert unexpected", exc);
  }
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json(
      { ok: false, error: "Unauthorized" },
      { status: 401 },
    );
  }

  const ipLimit = rateLimit(`voice:ip:${clientIp(req)}`, 10, 60 * 60_000);
  const userLimit = rateLimit(`voice:user:${user.id}`, 4, 60 * 60_000);
  if (!ipLimit.allowed || !userLimit.allowed) {
    return NextResponse.json(
      { ok: false, error: "Too many requests" },
      { status: 429 },
    );
  }

  const raw = await req.json().catch(() => null);
  const payload = validatePayload(raw);
  if (!payload) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Invalid voice relay payload. Required: to (+1 E.164), "
          + "account_id, kind=onboarding.",
      },
      { status: 400 },
    );
  }

  const destinationGate = isAllowedDestination(payload.to);
  if (!destinationGate.ok) {
    return NextResponse.json(
      { ok: false, error: destinationGate.reason },
      { status: 400 },
    );
  }

  const accountSid = (
    process.env.TWILIO_BROKER_ACCOUNT_SID
    || process.env.TWILIO_BROKER_SID
    || ""
  ).trim();
  const sid = (process.env.TWILIO_BROKER_SID || "").trim();
  const token = (process.env.TWILIO_BROKER_TOKEN || "").trim();
  const from = (process.env.TWILIO_BROKER_FROM || "").trim();
  if (!accountSid || !sid || !token || !from) {
    return NextResponse.json(
      { ok: false, error: "Anticipy Twilio broker is not configured." },
      { status: 503 },
    );
  }
  if (!accountSid.startsWith("AC")) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Anticipy Twilio broker is misconfigured: TWILIO_BROKER_ACCOUNT_SID "
          + "must start with 'AC'.",
      },
      { status: 503 },
    );
  }

  const capGate = await checkAccountWideVoiceCap();
  if (!capGate.ok) {
    return NextResponse.json(
      { ok: false, error: capGate.reason },
      { status: 429 },
    );
  }

  // Compose the public TwiML URL that Twilio fetches when the user
  // answers. account_id is the join key so the answer route can land
  // each utterance under the right partition.
  const origin = (process.env.NEXT_PUBLIC_SITE_URL || "https://www.anticipy.ai")
    .replace(/\/+$/, "");
  const initialUrl =
    `${origin}/api/twilio/onboarding/initial`
    + `?account_id=${encodeURIComponent(payload.accountId)}`;
  const statusCallback = `${origin}/api/twilio/status`;

  const callsUrl =
    `https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Calls.json`;
  const auth = Buffer.from(`${sid}:${token}`).toString("base64");
  const form = new URLSearchParams({
    To: payload.to,
    From: from,
    Url: initialUrl,
    Method: "POST",
    StatusCallback: statusCallback,
    StatusCallbackMethod: "POST",
    Record: "false",
  });

  let twilioResp: Response;
  try {
    twilioResp = await fetch(callsUrl, {
      method: "POST",
      headers: {
        Authorization: `Basic ${auth}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: form.toString(),
    });
  } catch (exc) {
    return NextResponse.json(
      {
        ok: false,
        error: `Twilio transport failure: ${(exc as Error).message}`,
      },
      { status: 502 },
    );
  }

  const twilioStatus = twilioResp.status;
  let twilioBody: unknown;
  try {
    twilioBody = await twilioResp.json();
  } catch {
    twilioBody = { raw: (await twilioResp.text().catch(() => "")).slice(0, 600) };
  }

  if (twilioStatus < 200 || twilioStatus >= 300) {
    const obj = (twilioBody || {}) as Record<string, unknown>;
    const code = obj.code as number | undefined;
    const message = (obj.message as string) || "Twilio rejected the call";
    // Twilio code 21215 = "From number not verified for trial". The
    // operator action is to verify +16196584447 in the Twilio console.
    await logPlacement(
      user.id,
      payload.accountId,
      payload.to,
      "",
      "failed",
      `twilio_${twilioStatus}_${code || "?"}: ${message}`,
    );
    return NextResponse.json(
      {
        ok: false,
        error: message,
        code,
        twilio_status: twilioStatus,
        twilio_body: twilioBody,
        hint:
          code === 21215
            ? "Outbound voice caller-ID is not verified. Verify the From "
              + "number (+16196584447) in the Twilio console: Phone Numbers "
              + "-> Verified Caller IDs."
            : undefined,
      },
      { status: 502 },
    );
  }

  const obj = (twilioBody || {}) as Record<string, unknown>;
  const callSid = (obj.sid as string) || "";
  const callStatus = (obj.status as string) || "queued";

  await logPlacement(
    user.id,
    payload.accountId,
    payload.to,
    callSid,
    callStatus,
    "",
  );

  return NextResponse.json({
    ok: true,
    call_sid: callSid,
    status: callStatus,
    to: payload.to,
    from,
    initial_url: initialUrl,
  });
}

export async function GET() {
  return NextResponse.json(
    { ok: false, error: "Use POST" },
    { status: 405 },
  );
}
