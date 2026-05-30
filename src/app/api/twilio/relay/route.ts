import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { shouldResetWindow, type ProfileRow } from "@/lib/profile";

export const dynamic = "force-dynamic";

/**
 * Twilio SMS broker for the engine.
 *
 * Strangers downloading the Mac DMG do not have their own Twilio
 * accounts, so the local engine pre-confirm gate cannot reach
 * api.twilio.com directly. This route is the website-side relay:
 *   1. Authenticates the caller using their Supabase session token.
 *   2. Per-user and per-IP rate limits to bound abuse if a token leaks.
 *   3. Validates payload (E.164 recipient, body length, allowed kind).
 *   4. Loads anticipy_profiles row for the caller; enforces per-user
 *      daily SMS cap and resets the 24h window if needed.
 *   5. Blocks non +1 numbers and known premium prefixes so an unbounded
 *      international or premium-line send cannot drain the broker
 *      account.
 *   6. Enforces account-wide $5/day SMS spend cap by counting recent
 *      anticipy_twilio_sends inserts in the trailing 24h window.
 *   7. Sends via the shared Anticipy Twilio number using server-side
 *      creds in TWILIO_BROKER_ACCOUNT_SID (URL path) +
 *      TWILIO_BROKER_SID (Basic Auth username, either the Account SID
 *      or an API Key SID) + TWILIO_BROKER_TOKEN (Basic Auth password,
 *      either the Account Auth Token or an API Key Secret) +
 *      TWILIO_BROKER_FROM.
 *   8. Logs each send to public.anticipy_twilio_sends for audit and
 *      cost reconciliation, then increments the per-user counter.
 *
 * Mirrors the architecture of /api/engine/model: shared scarce server
 * secret, Supabase auth gate, per-user and per-IP rate limits, ALLOWED
 * set for the only field where the engine has freedom (the kind tag).
 *
 * Env required (Vercel):
 *   TWILIO_BROKER_ACCOUNT_SID  (Account SID, starts with "AC"; used
 *                              in the Twilio Messages.json URL path.
 *                              Falls back to TWILIO_BROKER_SID for
 *                              backward compat with deploys that set
 *                              the single combined var to an AC...
 *                              Account SID.)
 *   TWILIO_BROKER_SID          (Basic Auth username. Either an API
 *                              Key SID starting with "SK" (preferred)
 *                              or the Account SID starting with "AC".)
 *   TWILIO_BROKER_TOKEN        (Basic Auth password. Either an API
 *                              Key Secret (preferred) or the Account
 *                              Auth Token.)
 *   TWILIO_BROKER_FROM         (E.164, the Anticipy public number)
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 *   SUPABASE_SERVICE_ROLE_KEY
 *
 * Optional:
 *   TWILIO_BROKER_SMS_DAILY_USD_CAP  account-wide $/day SMS cap, default 5
 *   TWILIO_BROKER_SMS_PRICE_USD      assumed cost per outbound, default 0.0083
 *
 * Supabase: see ./MIGRATION.sql for anticipy_twilio_sends and
 * ../../onboarding/profile/MIGRATION.sql for anticipy_profiles.
 */

const ALLOWED_KINDS = new Set(["preconfirm", "receipt", "followup"]);
const MAX_BODY_LEN = 320;
const E164_PATTERN = /^\+[1-9]\d{6,14}$/;
const STATUS_CALLBACK_URL = "https://www.anticipy.ai/api/twilio/status";

// US/CA premium and special-rate prefixes that bill at multiples of
// the standard A2P rate. Block these outright. The "+1900" family is
// pay-per-call/SMS; +1976 historically the same. Anyone with a real
// reason to text these will not be coming through the broker.
const PREMIUM_PREFIXES = ["+1900", "+1976"];

interface RelayBody {
  to?: unknown;
  body?: unknown;
  kind?: unknown;
}

interface ValidatedPayload {
  to: string;
  body: string;
  kind: string;
}

function validatePayload(input: unknown): ValidatedPayload | null {
  if (!input || typeof input !== "object") return null;
  const src = input as RelayBody;
  const to = typeof src.to === "string" ? src.to.trim() : "";
  const body = typeof src.body === "string" ? src.body : "";
  const kind = typeof src.kind === "string" ? src.kind.trim() : "";
  if (!E164_PATTERN.test(to)) return null;
  if (!body || body.length === 0 || body.length > MAX_BODY_LEN) return null;
  if (!ALLOWED_KINDS.has(kind)) return null;
  return { to, body, kind };
}

function isAllowedDestination(to: string): { ok: boolean; reason?: string } {
  if (!to.startsWith("+1")) {
    return {
      ok: false,
      reason:
        "Anticipy currently only sends to US and Canada (+1) numbers. International sends are disabled.",
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

async function loadOrCreateProfile(userId: string): Promise<ProfileRow | null> {
  const existing = await supabaseAdmin
    .from("anticipy_profiles")
    .select("*")
    .eq("id", userId)
    .maybeSingle();
  if (existing.error) {
    console.error("[twilio-relay] profile select failed", existing.error);
    return null;
  }
  if (existing.data) return existing.data as ProfileRow;
  const inserted = await supabaseAdmin
    .from("anticipy_profiles")
    .insert({ id: userId })
    .select("*")
    .single();
  if (inserted.error) {
    console.error("[twilio-relay] profile insert failed", inserted.error);
    return null;
  }
  return inserted.data as ProfileRow;
}

async function checkAccountWideSmsCap(): Promise<{
  ok: boolean;
  reason?: string;
}> {
  const capUsd = Number(
    process.env.TWILIO_BROKER_SMS_DAILY_USD_CAP || "5",
  );
  const pricePerSms = Number(
    process.env.TWILIO_BROKER_SMS_PRICE_USD || "0.0083",
  );
  if (!Number.isFinite(capUsd) || capUsd <= 0) return { ok: true };
  const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
  const { count, error } = await supabaseAdmin
    .from("anticipy_twilio_sends")
    .select("id", { count: "exact", head: true })
    .gte("sent_at", since);
  if (error) {
    // If the cap check fails closed we would block all sends on a
    // transient Supabase blip. Log + allow so the cap is best-effort.
    console.error("[twilio-relay] account cap select failed", error);
    return { ok: true };
  }
  const spend = (count ?? 0) * pricePerSms;
  if (spend >= capUsd) {
    return {
      ok: false,
      reason: `Account-wide daily SMS cap reached ($${capUsd.toFixed(2)}).`,
    };
  }
  return { ok: true };
}

async function logSend(
  userId: string,
  to: string,
  bodyLen: number,
  kind: string,
  twilioSid: string,
  status: string,
): Promise<void> {
  try {
    const { error } = await supabaseAdmin
      .from("anticipy_twilio_sends")
      .insert({
        user_id: userId,
        to_e164: to,
        body_len: bodyLen,
        kind,
        twilio_sid: twilioSid,
        status,
      });
    if (error) {
      // Audit logging is best effort. The send already happened; do not
      // fail the caller if Supabase is wedged or the table is missing.
      console.error("[twilio-relay] log insert failed", error);
    }
  } catch (exc) {
    console.error("[twilio-relay] log insert unexpected", exc);
  }
}

async function incrementUserDailyCounter(
  userId: string,
  current: ProfileRow,
): Promise<void> {
  const resetTo = shouldResetWindow(current.daily_window_started_at);
  const nextCount = resetTo
    ? 1
    : (current.daily_sms_count_used || 0) + 1;
  const update: Record<string, unknown> = {
    daily_sms_count_used: nextCount,
    updated_at: new Date().toISOString(),
  };
  if (resetTo) {
    update.daily_window_started_at = resetTo;
    // Voice counter rolls on the same window so the daily reset is
    // coherent across both surfaces.
    update.daily_voice_minutes_used = 0;
  }
  const { error } = await supabaseAdmin
    .from("anticipy_profiles")
    .update(update)
    .eq("id", userId);
  if (error) {
    console.error("[twilio-relay] counter increment failed", error);
  }
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  const ipLimit = rateLimit(`twilio:ip:${clientIp(req)}`, 30, 60 * 60_000);
  const userLimit = rateLimit(`twilio:user:${user.id}`, 10, 60 * 60_000);
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
      { ok: false, error: "Invalid relay payload" },
      { status: 400 },
    );
  }

  // Destination gates run BEFORE the env check so a misconfigured
  // server never silently accepts a non +1 or premium send during
  // the time between config-loss and the next deploy.
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
  // The URL path MUST be the Account SID. API Key SIDs start with "SK"
  // and would resolve to a 404 on api.twilio.com. The Basic Auth pair
  // (sid:token) can be either an API Key (SK + secret, preferred for
  // least privilege) or the Account SID + Auth Token (legacy path).
  if (!accountSid.startsWith("AC")) {
    return NextResponse.json(
      {
        ok: false,
        error:
          "Anticipy Twilio broker is misconfigured: account SID must "
          + "start with 'AC'. Set TWILIO_BROKER_ACCOUNT_SID to the "
          + "Twilio Account SID (the URL path requires it).",
      },
      { status: 503 },
    );
  }

  const profile = await loadOrCreateProfile(user.id);
  if (!profile) {
    return NextResponse.json(
      { ok: false, error: "Profile lookup failed" },
      { status: 500 },
    );
  }

  // Reset window without persisting yet (the counter-increment step
  // below writes both the reset and the increment in one update).
  const resetTo = shouldResetWindow(profile.daily_window_started_at);
  const usedAtCheck = resetTo ? 0 : profile.daily_sms_count_used || 0;
  if (usedAtCheck >= profile.daily_sms_count_cap) {
    return NextResponse.json(
      {
        ok: false,
        error: `You have hit today's send cap of ${profile.daily_sms_count_cap} messages.`,
      },
      { status: 429 },
    );
  }

  const accountCap = await checkAccountWideSmsCap();
  if (!accountCap.ok) {
    return NextResponse.json(
      { ok: false, error: accountCap.reason },
      { status: 429 },
    );
  }

  const form = new URLSearchParams();
  form.set("From", from);
  form.set("To", payload.to);
  form.set("Body", payload.body);
  form.set("StatusCallback", STATUS_CALLBACK_URL);

  const auth = Buffer.from(`${sid}:${token}`).toString("base64");
  const twilioUrl =
    `https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(accountSid)}/Messages.json`;

  let upstream: Response;
  try {
    upstream = await fetch(twilioUrl, {
      method: "POST",
      headers: {
        Authorization: `Basic ${auth}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: form.toString(),
    });
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    return NextResponse.json(
      { ok: false, error: `Twilio transport failed: ${message}` },
      { status: 502 },
    );
  }

  let twilioBody: Record<string, unknown> = {};
  const text = await upstream.text();
  try {
    twilioBody = text ? JSON.parse(text) : {};
  } catch {
    twilioBody = { raw: text };
  }

  if (upstream.status === 201) {
    const twilioSid = typeof twilioBody.sid === "string" ? twilioBody.sid : "";
    const twilioStatus =
      typeof twilioBody.status === "string" ? twilioBody.status : "queued";
    await logSend(
      user.id,
      payload.to,
      payload.body.length,
      payload.kind,
      twilioSid,
      twilioStatus,
    );
    await incrementUserDailyCounter(user.id, profile);
    return NextResponse.json({ ok: true, sid: twilioSid });
  }

  const errorMessage =
    typeof twilioBody.message === "string"
      ? twilioBody.message
      : `Twilio rejected the send (status ${upstream.status}).`;
  await logSend(
    user.id,
    payload.to,
    payload.body.length,
    payload.kind,
    "",
    `error:${upstream.status}`,
  );
  return NextResponse.json(
    { ok: false, error: errorMessage },
    { status: upstream.status === 401 ? 502 : upstream.status },
  );
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    },
  });
}
