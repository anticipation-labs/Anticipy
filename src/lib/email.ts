import { escapeHtml, sanitizeHeader } from "./escape";
import {
  preorderConfirmationHtml,
  waitlistWelcomeHtml,
} from "./email-templates";

// Deliberately a DIFFERENT key from RESEND_API_KEY. The site's transactional
// mail sends from anticipyupdates.com, which is verified in the
// "anticipationlabs" Resend workspace. RESEND_API_KEY belongs to the separate
// "aevoy" workspace, where notifications@aevoy.com is verified — that key is
// still what the engine's intent emails use (src/lib/resend-notify.ts,
// notification-adapter.ts, execute-action.ts). Pointing both at one key would
// break whichever domain does not belong to that workspace. Falls back so a
// missing var degrades to the old behaviour rather than to silence.
const RESEND_API_KEY =
  process.env.MAIL_RESEND_API_KEY || process.env.RESEND_API_KEY;

// Sender identity, held in env so the From address can move to a different
// verified domain as a Vercel env change rather than a code change.
const FROM = process.env.MAIL_FROM || "Anticipy <hello@anticipyupdates.com>";

// Replies must land somewhere a human reads. The pre-order confirmation tells
// the customer to reply, and anticipyupdates.com is a fresh domain whose
// inbound forwarding is not guaranteed to be configured — so replies are
// pointed at an address known to be live instead of at the From domain.
const REPLY_TO = process.env.REPLY_TO || "omar@anticipationlabs.com";

// Every customer-facing email is blind-copied here, so there is a record of
// exactly what the customer received — not a separate summary that can drift
// from the real thing. Comma-separated to allow a backup inbox.
const OWNER_EMAILS = (process.env.OWNER_EMAIL || "omar@anticipationlabs.com")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const CAL_LINK = "https://cal.com/omar-anticipy/anticipyfundraising30";

interface SendArgs {
  to: string | string[];
  subject: string;
  html: string;
  replyTo?: string;
  /** Blind-copy the owner. On for anything a customer receives. */
  bccOwner?: boolean;
  headers?: Record<string, string>;
  tag?: string;
}

/**
 * Single transport for all transactional mail.
 *
 * Throws on every failure path. The previous implementation returned early
 * when the API key was missing and swallowed provider errors at the call
 * site, which is how a dead SendGrid account silently dropped every email
 * for two months while checkout kept returning 200. Callers decide what a
 * failure means; this layer never decides it means nothing.
 */
async function sendMail(args: SendArgs): Promise<string> {
  if (!RESEND_API_KEY) {
    throw new Error(
      "RESEND_API_KEY is not set — refusing to silently drop mail."
    );
  }

  const payload: Record<string, unknown> = {
    from: FROM,
    to: Array.isArray(args.to) ? args.to : [args.to],
    subject: sanitizeHeader(args.subject, 180),
    html: args.html,
  };

  if (args.bccOwner && OWNER_EMAILS.length) payload.bcc = OWNER_EMAILS;
  if (args.replyTo) payload.reply_to = [sanitizeHeader(args.replyTo, 254)];
  if (args.headers) payload.headers = args.headers;
  if (args.tag) payload.tags = [{ name: "category", value: args.tag }];

  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`Resend ${res.status}: ${detail.slice(0, 300)}`);
  }

  const data = (await res.json().catch(() => ({}))) as { id?: string };
  return data.id ?? "";
}

// ─── INVESTOR SIGNUP (from /funded) ────────────────────────────
export async function sendInvestorWelcome(email: string, name?: string | null) {
  // Strip control chars (CR/LF specifically) from any value that reaches a
  // header — a name with embedded "\r\nBcc: attacker@evil.com" would
  // otherwise add covert recipients.
  const rawFirstName = sanitizeHeader(name?.split(" ")[0] || "", 60);
  const firstName = escapeHtml(rawFirstName);
  const greeting = firstName ? `Hey ${firstName}` : "Hey there";

  return sendMail({
    to: email,
    bccOwner: true,
    replyTo: REPLY_TO,
    tag: "investor-welcome",
    subject: rawFirstName
      ? `${rawFirstName} — thanks for your interest in Anticipy`
      : "Thanks for your interest in Anticipy",
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.7;">
  <p style="font-size: 16px;">${greeting},</p>

  <p style="font-size: 16px;">Really appreciate you taking a look at what we're building. This isn't a mass email — I personally read every one of these and I'm genuinely excited to connect.</p>

  <p style="font-size: 16px;">Here's what you should know:</p>

  <ul style="font-size: 16px; padding-left: 20px;">
    <li>We're raising <strong>$1.5M at a $15M cap</strong> on a post-money SAFE</li>
    <li>The software runs today — the Action Engine is live and working</li>
    <li>Hardware prototype targeting September 2026, limited launch November</li>
    <li>This is pre-seed — the earliest possible stage to get in</li>
  </ul>

  <p style="font-size: 16px;">I'd love to walk you through the full picture on a call — including the deck. No slide presentation, just a real conversation about where this is going and why now is the moment.</p>

  <p style="text-align: center; margin: 32px 0;">
    <a href="${CAL_LINK}" style="display: inline-block; padding: 14px 32px; background-color: #C9A227; color: #0C0C0C; text-decoration: none; border-radius: 100px; font-weight: 600; font-size: 15px;">Book 30 Minutes with Me</a>
  </p>

  <p style="font-size: 16px;">If calls aren't your thing, just reply to this email. I read everything.</p>

  <p style="font-size: 16px;">Talk soon,<br/><strong>Omar Ebrahim</strong><br/>Founder, Anticipy<br/>
  <span style="color: #8a8a8a; font-size: 14px;">15 · West Vancouver · Building since age 8</span></p>

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0;" />

  <p style="font-size: 13px; color: #8a8a8a;">
    Anticipy — The AI wearable that acts.<br/>
    <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a> · <a href="https://anticipy.ai/funded" style="color: #C9A227;">Investor Page</a>
  </p>
</div>
    `.trim(),
  });
}

// ─── WAITLIST SIGNUP (from main site) ──────────────────────────
export async function sendWaitlistWelcome(email: string, name?: string | null) {
  // Same header-injection protection as sendInvestorWelcome — see note there.
  // The template escapes the name for HTML; this strips control chars.
  const rawFirstName = sanitizeHeader(name?.split(" ")[0] || "", 60);

  return sendMail({
    to: email,
    bccOwner: true,
    replyTo: REPLY_TO,
    tag: "waitlist-welcome",
    subject: "Welcome to the Anticipy waitlist",
    html: waitlistWelcomeHtml({ firstName: rawFirstName }),
  });
}

// ─── PRE-ORDER CONFIRMATION (from /pre-orders/purchase Stripe Checkout) ────
// Blind-copies the owner, so the record of what the customer received is the
// customer's actual email — not a reconstruction.
export async function sendPreorderConfirmation(
  email: string,
  opts: {
    name?: string | null;
    amount: number;
    currency: string;
    sessionId: string;
  }
) {
  // The template escapes the name for HTML; this strips control chars first.
  const rawFirstName = sanitizeHeader(opts.name?.split(" ")[0] || "", 60);
  const amountDisplay = (opts.amount / 100).toFixed(2);
  const currencyDisplay = (opts.currency || "usd").toUpperCase();

  return sendMail({
    to: email,
    bccOwner: true,
    replyTo: REPLY_TO,
    tag: "preorder-confirmation",
    subject: "Your Anticipy pre-order is confirmed",
    html: preorderConfirmationHtml({
      firstName: rawFirstName,
      amountDisplay,
      currencyDisplay,
      sessionId: opts.sessionId,
    }),
  });
}

// ─── OWNER NOTIFICATION: waitlist signup ──────────────────────────
// Fires every time someone joins the waitlist. High-priority headers.
export async function sendOwnerWaitlistNotification(
  email: string,
  opts: { name?: string | null; source?: string; ip?: string | null; ua?: string | null; referrer?: string | null }
) {
  const safeEmail = escapeHtml(email);
  const safeName = escapeHtml(opts.name?.trim() || "(no name)");
  const safeSource = escapeHtml(opts.source || "website");
  const safeIp = escapeHtml(opts.ip || "unknown");
  const safeUa = escapeHtml(opts.ua || "unknown");
  const safeRef = escapeHtml(opts.referrer || "(direct)");

  return sendMail({
    to: OWNER_EMAILS,
    replyTo: email,
    tag: "waitlist-owner-notification",
    subject: `[Waitlist] ${opts.name?.trim() || email} joined`,
    headers: {
      "X-Priority": "1",
      "X-MSMail-Priority": "High",
      Importance: "High",
    },
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">
  <h2 style="margin: 0 0 8px 0;">New waitlist signup</h2>
  <p style="color: #6b635b; margin: 0 0 24px 0;">${new Date().toUTCString()}</p>

  <table style="font-size: 14px; border-collapse: collapse; width: 100%;">
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Name</td><td style="padding: 6px 0;">${safeName}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Email</td><td style="padding: 6px 0;"><a href="mailto:${safeEmail}" style="color: #C9A227;">${safeEmail}</a></td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Source</td><td style="padding: 6px 0;">${safeSource}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Referrer</td><td style="padding: 6px 0;">${safeRef}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">IP</td><td style="padding: 6px 0;">${safeIp}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">User agent</td><td style="padding: 6px 0; font-size: 12px; color: #6b635b;">${safeUa}</td></tr>
  </table>

  <p style="margin: 32px 0 8px 0; font-size: 13px; color: #6b635b;">Reply to this email to respond directly. The reply-to header is already set to the signup address.</p>
</div>
    `.trim(),
  });
}

// ─── OWNER NOTIFICATION: pre-order paid ────────────────────────────
// Fires when Stripe webhook reports a successful pre-order. High-priority.
// This is the operational detail view; the owner also receives the customer's
// own confirmation via the bcc on sendPreorderConfirmation.
export async function sendOwnerPreorderNotification(
  email: string,
  opts: {
    name?: string | null;
    amount: number;
    currency: string;
    sessionId: string;
    paymentIntent?: string | null;
    shippingCity?: string | null;
    shippingState?: string | null;
    shippingCountry?: string | null;
  }
) {
  const safeEmail = escapeHtml(email);
  const safeName = escapeHtml(opts.name?.trim() || "(no name)");
  const amountDisplay = (opts.amount / 100).toFixed(2);
  const currencyDisplay = (opts.currency || "usd").toUpperCase();
  const safeSession = escapeHtml(opts.sessionId);
  const safePI = escapeHtml(opts.paymentIntent || "");
  const safeShip = escapeHtml(
    [opts.shippingCity, opts.shippingState, opts.shippingCountry]
      .filter(Boolean)
      .join(", ") || "(no address yet)"
  );

  return sendMail({
    to: OWNER_EMAILS,
    replyTo: email,
    tag: "preorder-owner-notification",
    subject: `[PRE-ORDER PAID] $${amountDisplay} from ${opts.name?.trim() || email}`,
    headers: {
      "X-Priority": "1",
      "X-MSMail-Priority": "High",
      Importance: "High",
    },
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">
  <h2 style="margin: 0 0 8px 0;">Pre-order paid: $${amountDisplay} ${currencyDisplay}</h2>
  <p style="color: #6b635b; margin: 0 0 24px 0;">${new Date().toUTCString()}</p>

  <table style="font-size: 14px; border-collapse: collapse; width: 100%;">
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Name</td><td style="padding: 6px 0;">${safeName}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Email</td><td style="padding: 6px 0;"><a href="mailto:${safeEmail}" style="color: #C9A227;">${safeEmail}</a></td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Amount</td><td style="padding: 6px 0;"><strong>$${amountDisplay} ${currencyDisplay}</strong></td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Shipping</td><td style="padding: 6px 0;">${safeShip}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Session</td><td style="padding: 6px 0; font-family: monospace; font-size: 11px;">${safeSession}</td></tr>
    <tr><td style="padding: 6px 12px 6px 0; color: #6b635b; vertical-align: top;">Payment Intent</td><td style="padding: 6px 0; font-family: monospace; font-size: 11px;">${safePI}</td></tr>
  </table>

  <p style="margin: 32px 0 8px 0; font-size: 13px; color: #6b635b;">
    Stripe dashboard: <a href="https://dashboard.stripe.com/payments" style="color: #C9A227;">payments</a><br/>
    Supabase row: query <code>anticipy_preorders</code> where <code>stripe_checkout_session_id = '${safeSession}'</code>
  </p>
</div>
    `.trim(),
  });
}
