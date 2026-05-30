import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { supabaseAdmin } from "@/lib/supabase-admin";

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
 *   4. Sends via the shared Anticipy Twilio number using server-side
 *      creds in TWILIO_BROKER_SID / TWILIO_BROKER_TOKEN / TWILIO_BROKER_FROM.
 *   5. Logs each send to public.anticipy_twilio_sends for audit + abuse
 *      forensics.
 *
 * Mirrors the architecture of /api/engine/model: shared scarce server
 * secret, Supabase auth gate, per-user and per-IP rate limits, ALLOWED
 * set for the only field where the engine has freedom (the kind tag).
 *
 * Env required (Vercel):
 *   TWILIO_BROKER_SID
 *   TWILIO_BROKER_TOKEN
 *   TWILIO_BROKER_FROM    (E.164, the Anticipy public number)
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 *   SUPABASE_SERVICE_ROLE_KEY
 *
 * Supabase: see ./MIGRATION.sql for the anticipy_twilio_sends table the
 * owner must apply before this route logs successfully.
 */

const ALLOWED_KINDS = new Set(["preconfirm", "receipt", "followup"]);
const MAX_BODY_LEN = 320;
const E164_PATTERN = /^\+[1-9]\d{6,14}$/;
const STATUS_CALLBACK_URL = "https://www.anticipy.ai/api/twilio/status";

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

  const sid = (process.env.TWILIO_BROKER_SID || "").trim();
  const token = (process.env.TWILIO_BROKER_TOKEN || "").trim();
  const from = (process.env.TWILIO_BROKER_FROM || "").trim();
  if (!sid || !token || !from) {
    return NextResponse.json(
      { ok: false, error: "Anticipy Twilio broker is not configured." },
      { status: 503 },
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

  const form = new URLSearchParams();
  form.set("From", from);
  form.set("To", payload.to);
  form.set("Body", payload.body);
  form.set("StatusCallback", STATUS_CALLBACK_URL);

  const auth = Buffer.from(`${sid}:${token}`).toString("base64");
  const twilioUrl =
    `https://api.twilio.com/2010-04-01/Accounts/${encodeURIComponent(sid)}/Messages.json`;

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
