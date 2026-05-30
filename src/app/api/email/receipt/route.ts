import * as React from "react";
import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { clientIp, rateLimit } from "@/lib/rate-limit";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { sendEmail, RESEND_FROM_ADDRESS } from "@/lib/resend";
import { Receipt, type ReceiptProps } from "@/emails/Receipt";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Resend email broker for the engine.
 *
 * Mirrors /api/twilio/relay so the local engine can call one website
 * endpoint without holding any provider key on the user's Mac. Per
 * ARCHITECTURE.md section 8, every "receipt" or "what I did" email
 * goes through here, the website renders the React Email template
 * (src/emails/Receipt.tsx), and the Resend SDK does the actual send.
 *
 * Why broker (not direct):
 *   1. Strangers downloading the DMG will never have a Resend key.
 *   2. React Email only renders server-side in Node and the engine is
 *      Python. The template lives next to the brand colors here.
 *   3. One key on Vercel, zero credential surface per Mac.
 *   4. Allowlist + rate limit + audit log enforced in one place.
 *
 * Request shape (POST JSON):
 *   {
 *     "to":       "omarkebrahim+anticipy-test@gmail.com",
 *     "subject":  "Drafted follow-up to Sarah Lin",
 *     "kind":     "receipt",            // free-form classifier
 *     "goal_id":  "g-abc123",           // threads inbound replies
 *     "props": {
 *       "recipientName": "Omar",
 *       "goalSummary":   "Replied to Sarah about Friday demo.",
 *       "actionTaken":   "Sent your draft reply at 2:14 pm.",
 *       "nextSteps":     "I will surface her response when it lands."
 *     }
 *   }
 *
 * Response (200):
 *   { "ok": true, "message_id": "re_abc...", "sent_at": "2026-..." }
 *
 * Response (400 / 401 / 403 / 429 / 500):
 *   { "ok": false, "error": "<plain English>" }
 *
 * Auth: Supabase session JWT via Authorization: Bearer <token>.
 * Allowlist (per memory feedback_no_real_send_testing):
 *   - omarkebrahim@gmail.com
 *   - omarkebrahim+anticipy-*@gmail.com  (any +anticipy-... subaddress)
 *   - *@anticipy.ai
 *   - *@aevoy.com
 * Anything else returns 403 with a clear message. Loosen the allowlist
 * only after the no-real-send policy is explicitly lifted.
 *
 * Rate limits:
 *   per user_id: 10 sends per 60 seconds
 *   per ip:      30 sends per 60 minutes (defense in depth on token leak)
 *
 * Audit:
 *   Insert row in public.anticipy_email_sends per ./MIGRATION.sql for
 *   abuse trace and cost reconciliation. Subject + recipient + length
 *   only. The actual rendered HTML body is never stored.
 */

const ALLOWED_KINDS = new Set([
  "receipt",
  "preconfirm",
  "followup",
  "summary",
  "test",
]);

// Practical upper bounds. Resend itself enforces stricter limits at send
// time but these reject obviously-bad input before we touch the SDK.
const MAX_SUBJECT_LEN = 180;
const MAX_TO_LEN = 254;
const MAX_GOAL_ID_LEN = 80;
const MAX_KIND_LEN = 32;
const MAX_PROP_FIELD_LEN = 2000;

const EMAIL_PATTERN =
  /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/;

interface ReceiptRequestBody {
  to?: unknown;
  subject?: unknown;
  kind?: unknown;
  goal_id?: unknown;
  props?: unknown;
}

interface ValidatedPayload {
  to: string;
  subject: string;
  kind: string;
  goal_id: string;
  props: ReceiptProps;
}

function asString(value: unknown, maxLen: number): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > maxLen) return null;
  // Strip CR/LF defensively so a subject or recipient cannot smuggle a
  // header break. (Resend does its own escaping but defense in depth.)
  return trimmed.replace(/[\r\n\t]+/g, " ");
}

function asOptionalString(value: unknown, maxLen: number): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (trimmed.length > maxLen) return trimmed.slice(0, maxLen);
  return trimmed;
}

function validatePayload(input: unknown): ValidatedPayload | null {
  if (!input || typeof input !== "object") return null;
  const src = input as ReceiptRequestBody;

  const to = asString(src.to, MAX_TO_LEN);
  if (!to || !EMAIL_PATTERN.test(to)) return null;

  const subject = asString(src.subject, MAX_SUBJECT_LEN);
  if (!subject) return null;

  const kind = asString(src.kind, MAX_KIND_LEN);
  if (!kind || !ALLOWED_KINDS.has(kind)) return null;

  const goalId = asString(src.goal_id, MAX_GOAL_ID_LEN);
  if (!goalId) return null;

  if (!src.props || typeof src.props !== "object") return null;
  const rawProps = src.props as Record<string, unknown>;
  const goalSummary = asString(rawProps.goalSummary, MAX_PROP_FIELD_LEN);
  const actionTaken = asString(rawProps.actionTaken, MAX_PROP_FIELD_LEN);
  if (!goalSummary || !actionTaken) return null;
  const recipientName = asOptionalString(rawProps.recipientName, 120);
  const nextSteps = asOptionalString(rawProps.nextSteps, MAX_PROP_FIELD_LEN);

  return {
    to: to.toLowerCase(),
    subject,
    kind,
    goal_id: goalId,
    props: {
      recipientName,
      goalSummary,
      actionTaken,
      nextSteps,
    },
  };
}

interface AllowResult {
  ok: boolean;
  reason?: string;
}

/**
 * Enforce the no-real-send allowlist from
 * MEMORY.md/feedback_no_real_send_testing.md.
 *
 * Loosen only when the policy is explicitly lifted. Errors are plain
 * English so a misconfigured engine gives the operator a clear hint.
 */
function isAllowedRecipient(toLower: string): AllowResult {
  const omarBase = "omarkebrahim@gmail.com";
  const omarSubAddrPattern = /^omarkebrahim\+anticipy-[a-z0-9_-]+@gmail\.com$/;
  if (toLower === omarBase) return { ok: true };
  if (omarSubAddrPattern.test(toLower)) return { ok: true };
  if (toLower.endsWith("@anticipy.ai")) return { ok: true };
  if (toLower.endsWith("@aevoy.com")) return { ok: true };
  return {
    ok: false,
    reason:
      "Recipient is not on the Anticipy allowlist. Allowed: owner email, "
      + "owner +anticipy-... subaddresses, @anticipy.ai, @aevoy.com.",
  };
}

async function logSend(args: {
  userId: string;
  to: string;
  subject: string;
  kind: string;
  goalId: string;
  resendMessageId: string;
  status: string;
  error: string;
}): Promise<void> {
  try {
    const { error } = await supabaseAdmin
      .from("anticipy_email_sends")
      .insert({
        user_id: args.userId,
        to_email: args.to,
        subject: args.subject,
        kind: args.kind,
        goal_id: args.goalId,
        resend_message_id: args.resendMessageId,
        status: args.status,
        error: args.error,
      });
    if (error) {
      // Audit logging is best effort: the send already happened (or
      // already failed). Never bubble the audit error to the caller.
      console.error("[email-receipt] log insert failed", error);
    }
  } catch (exc) {
    console.error("[email-receipt] log insert unexpected", exc);
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

  const ipLimit = rateLimit(`email:ip:${clientIp(req)}`, 30, 60 * 60_000);
  // 10 sends per minute per user. The runbook value the prompt requires.
  // The IP bucket is per hour because IPs are shared and a stricter
  // per-IP minute cap would block legitimate multi-user offices.
  const userLimit = rateLimit(`email:user:${user.id}`, 10, 60_000);
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
      { ok: false, error: "Invalid email payload" },
      { status: 400 },
    );
  }

  const allow = isAllowedRecipient(payload.to);
  if (!allow.ok) {
    // Log the blocked attempt so we can spot a stuck engine quickly.
    await logSend({
      userId: user.id,
      to: payload.to,
      subject: payload.subject,
      kind: payload.kind,
      goalId: payload.goal_id,
      resendMessageId: "",
      status: "blocked_allowlist",
      error: allow.reason || "",
    });
    return NextResponse.json(
      { ok: false, error: allow.reason },
      { status: 403 },
    );
  }

  // Build the React tree here so the lib stays free of template imports.
  const tree = React.createElement(Receipt, payload.props);

  const result = await sendEmail({
    to: payload.to,
    subject: payload.subject,
    react: tree,
    react_props: payload.props as unknown as Record<string, unknown>,
    goal_id: payload.goal_id,
    kind: payload.kind,
  });

  if (!result.ok) {
    await logSend({
      userId: user.id,
      to: payload.to,
      subject: payload.subject,
      kind: payload.kind,
      goalId: payload.goal_id,
      resendMessageId: "",
      status: "error",
      error: result.error || "unknown",
    });
    const status = (result.error || "").includes("RESEND_API_KEY") ? 503 : 502;
    return NextResponse.json(
      { ok: false, error: result.error || "Email send failed" },
      { status },
    );
  }

  await logSend({
    userId: user.id,
    to: payload.to,
    subject: payload.subject,
    kind: payload.kind,
    goalId: payload.goal_id,
    resendMessageId: result.message_id || "",
    status: "sent",
    error: "",
  });

  return NextResponse.json({
    ok: true,
    message_id: result.message_id || "",
    sent_at: result.sent_at || new Date().toISOString(),
    from: RESEND_FROM_ADDRESS,
  });
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
