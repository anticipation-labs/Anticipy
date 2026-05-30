import type { ReactNode } from "react";
import { Resend } from "resend";

/**
 * Thin Resend SDK wrapper. The route /api/email/receipt is the only caller.
 *
 * Why this lives separately from src/lib/notification-adapter.ts and
 * src/lib/email.ts:
 *   notification-adapter handles legacy intent-confirm emails and routes
 *   between Resend and Cloudflare. email.ts wraps SendGrid for waitlist
 *   + investor + pre-order flows. Both predate the broker pattern in
 *   ARCHITECTURE.md section 8. This module is the new, narrow surface
 *   the local engine talks to via the broker route. Keeping it separate
 *   avoids modifying either of those modules and keeps the surface area
 *   small enough for a single agent to own.
 *
 * Env required at runtime:
 *   RESEND_API_KEY  (Resend dashboard. Missing key is handled gracefully.)
 *
 * From + reply-to follow planning/00-handoff/RESEARCH/resend-email.md:
 *   From:     Anticipy <hello@send.anticipy.ai>  (subdomain send.anticipy.ai
 *             does not collide with the Porkbun forwarder on the apex.)
 *   ReplyTo:  goal-<goal_id>@reply.anticipy.ai  (any local part on reply.
 *             is captured by the inbound webhook so each goal threads back
 *             into the right timeline row.)
 *
 * TODO(owner): npm install resend @react-email/components
 *   resend@^6.9.4 is already in package.json (notification-adapter.ts uses
 *   it). @react-email/components is OPTIONAL here. This module renders the
 *   Receipt template using plain React + inline styles so the build does
 *   not gate on it. The Resend SDK still pulls @react-email/render at
 *   runtime, so the production env needs that package installed. The
 *   adapter that already runs in prod requires it too, so no new install
 *   is needed unless that adapter was missing it.
 */

const FROM_ADDRESS = "Anticipy <hello@send.anticipy.ai>";
const REPLY_DOMAIN = "reply.anticipy.ai";

let cachedClient: Resend | null = null;
let cachedKey: string | null = null;

function getClient(): Resend | null {
  const key = (process.env.RESEND_API_KEY ?? "").trim();
  if (!key) return null;
  if (cachedClient && cachedKey === key) return cachedClient;
  cachedClient = new Resend(key);
  cachedKey = key;
  return cachedClient;
}

export interface SendEmailOptions {
  to: string;
  subject: string;
  // React tree to render. Caller constructs e.g. <Receipt {...props} />
  // so this module never imports the templates directly.
  react: ReactNode;
  // Mirror of the props for telemetry. Not sent to Resend.
  react_props?: Record<string, unknown>;
  // Goal id is mandatory because it is the only stable thread key
  // between an outbound receipt and an inbound reply (the reply-to
  // local-part encodes it).
  goal_id: string;
  // Free-form classifier, e.g. "receipt", "preconfirm", "followup".
  // Used for audit table + cost reconciliation.
  kind: string;
  // Optional idempotency override. Defaults to "goal/<goal_id>/<kind>"
  // which dedupes "re-send the same receipt twice on retry" inside
  // Resend's 24h window.
  idempotencyKey?: string;
}

export interface SendEmailResult {
  ok: boolean;
  message_id?: string;
  error?: string;
  // Sent timestamp in ISO format. Caller logs to audit table.
  sent_at?: string;
}

function buildReplyTo(goalId: string): string {
  // Local-part allows letters, digits, hyphens, underscores. Strip the
  // rest so a goal id with weird chars cannot smuggle a header break.
  const safe = goalId.replace(/[^A-Za-z0-9_-]/g, "");
  const local = safe || "no-goal";
  return `goal-${local}@${REPLY_DOMAIN}`;
}

export async function sendEmail(
  opts: SendEmailOptions,
): Promise<SendEmailResult> {
  const client = getClient();
  if (!client) {
    // Missing key is not a crash. Caller can decide to 503 or fail soft.
    console.error("[resend] RESEND_API_KEY is not set");
    return { ok: false, error: "RESEND_API_KEY is not set" };
  }
  if (!opts.goal_id || typeof opts.goal_id !== "string") {
    return { ok: false, error: "goal_id is required" };
  }
  if (!opts.kind || typeof opts.kind !== "string") {
    return { ok: false, error: "kind is required" };
  }

  const replyTo = buildReplyTo(opts.goal_id);
  const idempotencyKey =
    opts.idempotencyKey || `goal/${opts.goal_id}/${opts.kind}`;

  try {
    const { data, error } = await client.emails.send(
      {
        from: FROM_ADDRESS,
        to: opts.to,
        subject: opts.subject,
        react: opts.react,
        replyTo,
        headers: {
          "X-Anticipy-Goal-Id": opts.goal_id,
          "X-Anticipy-Kind": opts.kind,
        },
      },
      // Resend supports request-level idempotency. 24h dedupe window per
      // RESEARCH/resend-email.md section 2.
      { idempotencyKey },
    );

    if (error) {
      const message =
        typeof error === "object" && error && "message" in error
          ? String((error as { message: unknown }).message)
          : JSON.stringify(error);
      return { ok: false, error: `Resend error: ${message}` };
    }

    return {
      ok: true,
      message_id: data?.id || "",
      sent_at: new Date().toISOString(),
    };
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    return { ok: false, error: `Resend transport failed: ${message}` };
  }
}

// Exported for tests and for the route's surface introspection.
export const RESEND_FROM_ADDRESS = FROM_ADDRESS;
export const RESEND_REPLY_DOMAIN = REPLY_DOMAIN;
