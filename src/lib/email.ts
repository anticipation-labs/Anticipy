import { escapeHtml, sanitizeHeader } from "./escape";

const SENDGRID_API_KEY = process.env.SENDGRID_API_KEY;
const FROM_EMAIL = "hello@anticipy.ai";
const FROM_NAME = "Omar from Anticipy";
const OWNER_EMAIL = process.env.OWNER_EMAIL || "hello@anticipy.ai";
const CAL_LINK = "https://cal.com/omar-anticipy/anticipyfundraising30";

async function getSgMail() {
  const sgMail = (await import("@sendgrid/mail")).default;
  if (SENDGRID_API_KEY) {
    sgMail.setApiKey(SENDGRID_API_KEY);
  }
  return sgMail;
}

// ─── INVESTOR SIGNUP (from /funded) ────────────────────────────
export async function sendInvestorWelcome(email: string, name?: string | null) {
  if (!SENDGRID_API_KEY) return;

  // Strip control chars (CR/LF specifically) from the subject to prevent
  // header injection — a name with embedded "\r\nBcc: attacker@evil.com"
  // would otherwise add covert recipients via SendGrid's transport.
  const rawFirstName = sanitizeHeader(name?.split(" ")[0] || "", 60);
  const firstName = escapeHtml(rawFirstName);
  const greeting = firstName ? `Hey ${firstName}` : "Hey there";

  const sgMail = await getSgMail();
  await sgMail.send({
    to: email,
    from: { email: FROM_EMAIL, name: FROM_NAME },
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
  if (!SENDGRID_API_KEY) return;

  // Same header-injection protection as sendInvestorWelcome — see note there.
  const rawFirstName = sanitizeHeader(name?.split(" ")[0] || "", 60);
  const firstName = escapeHtml(rawFirstName);
  const greeting = firstName ? `Hey ${firstName}` : "Hey";

  const sgMail = await getSgMail();
  await sgMail.send({
    to: email,
    from: { email: FROM_EMAIL, name: FROM_NAME },
    subject: "Welcome to the Anticipy waitlist",
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.7;">
  <p style="font-size: 16px;">${greeting},</p>

  <p style="font-size: 16px;">Welcome to the waitlist. You're officially one of the first people following what we're building.</p>

  <p style="font-size: 16px;">Anticipy is an AI wearable that doesn't just listen — it acts. It handles real tasks for you: books appointments, sends follow-ups, fills out forms. You wear it, forget it's there, and things just get done.</p>

  <p style="font-size: 16px;">We'll keep you posted as things progress. When there's something to show, you'll be the first to know.</p>

  <p style="font-size: 16px;">Thanks for believing early.</p>

  <p style="font-size: 16px;">— Omar</p>

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0;" />

  <p style="font-size: 13px; color: #8a8a8a;">
    Anticipy. The AI wearable that acts.<br/>
    <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a>
  </p>
</div>
    `.trim(),
  });
}

// ─── PRE-ORDER CONFIRMATION (from /pre-orders/purchase Stripe Checkout) ────
export async function sendPreorderConfirmation(
  email: string,
  opts: {
    name?: string | null;
    amount: number;
    currency: string;
    sessionId: string;
  }
) {
  if (!SENDGRID_API_KEY) return;

  const rawFirstName = sanitizeHeader(opts.name?.split(" ")[0] || "", 60);
  const firstName = escapeHtml(rawFirstName);
  const greeting = firstName ? `Hi ${firstName},` : "Hi,";
  const amountDisplay = (opts.amount / 100).toFixed(2);
  const currencyDisplay = (opts.currency || "usd").toUpperCase();

  const sgMail = await getSgMail();
  await sgMail.send({
    to: email,
    from: { email: FROM_EMAIL, name: FROM_NAME },
    subject: "Your Anticipy pre-order is confirmed",
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.7;">
  <p style="font-size: 16px;">${greeting}</p>

  <p style="font-size: 16px;">Your Anticipy pendant pre-order is locked in at $${amountDisplay} ${currencyDisplay}. That is $50 off the $199 retail price, plus free shipping to the United States and Canada.</p>

  <p style="font-size: 16px;"><strong>What happens next.</strong> We're targeting shipping for August 2026. When manufacturing finishes, we will email you for any final shipping address confirmation and then ship the pendant, chain, and wireless charging pad to the address you entered at checkout.</p>

  <p style="font-size: 16px;"><strong>Your receipt.</strong> Stripe sent a separate emailed receipt to this address. Keep it for your records.</p>

  <p style="font-size: 16px;"><strong>Need to make changes.</strong> Reply to this email. We respond to every pre-order inquiry personally.</p>

  <p style="font-size: 13px; color: #8a8a8a; margin-top: 24px;">Reference: ${escapeHtml(opts.sessionId)}</p>

  <p style="font-size: 16px;">Thank you for being early.</p>

  <p style="font-size: 16px;">Omar Ebrahim<br/>Founder, Anticipy</p>

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0;" />

  <p style="font-size: 13px; color: #8a8a8a;">
    Anticipation Labs Inc. · <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a><br/>
    Pre-order terms: <a href="https://anticipy.ai/pre-orders/agreement" style="color: #C9A227;">anticipy.ai/pre-orders/agreement</a>
  </p>
</div>
    `.trim(),
  });
}

// ─── OWNER NOTIFICATION: waitlist signup ──────────────────────────
// Fires every time someone joins the waitlist. High-priority headers.
export async function sendOwnerWaitlistNotification(
  email: string,
  opts: { name?: string | null; source?: string; ip?: string | null; ua?: string | null; referrer?: string | null }
) {
  if (!SENDGRID_API_KEY) return;

  const safeEmail = escapeHtml(email);
  const safeName = escapeHtml(opts.name?.trim() || "(no name)");
  const safeSource = escapeHtml(opts.source || "website");
  const safeIp = escapeHtml(opts.ip || "unknown");
  const safeUa = escapeHtml(opts.ua || "unknown");
  const safeRef = escapeHtml(opts.referrer || "(direct)");

  const sgMail = await getSgMail();
  await sgMail.send({
    to: OWNER_EMAIL,
    from: { email: FROM_EMAIL, name: "Anticipy Waitlist" },
    replyTo: email,
    subject: `[Waitlist] ${opts.name?.trim() || email} joined`,
    headers: {
      "X-Priority": "1",
      "X-MSMail-Priority": "High",
      Importance: "High",
    },
    categories: ["waitlist-owner-notification"],
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
  if (!SENDGRID_API_KEY) return;

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

  const sgMail = await getSgMail();
  await sgMail.send({
    to: OWNER_EMAIL,
    from: { email: FROM_EMAIL, name: "Anticipy Pre-Order" },
    replyTo: email,
    subject: `[PRE-ORDER PAID] $${amountDisplay} from ${opts.name?.trim() || email}`,
    headers: {
      "X-Priority": "1",
      "X-MSMail-Priority": "High",
      Importance: "High",
    },
    categories: ["preorder-owner-notification"],
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
