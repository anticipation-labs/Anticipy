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

// ─── BUILDER APPLICATION (from /build) ─────────────────────────────
// Goes to the owner with reply-to set to the applicant, so replying lands in
// their inbox directly. This email is also the fallback record: if the
// database write failed, everything they wrote is still here, which is why
// the whole submission is reproduced rather than summarised.
export async function sendApplicationNotification(a: {
  name: string;
  email: string;
  location: string;
  thing1: string;
  thing1Extra: string;
  thing2: string;
  thing2Extra: string;
  // Role-application fields. Empty on the /build funnel, which has no role.
  roleLabels?: string[];
  questionSet?: string | null;
  answers?: { id: string; question: string; answer: string }[];
  links?: string[];
  availability?: string;
  startDate?: string;
  vancouver?: string;
  workAuthorized?: boolean | null;
  spokenFields: string[];
  files: { url: string; filename: string }[];
  resumeLink: string | null;
  domainOk: boolean;
  domainReason: string;
  utmSource: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
  referrer: string | null;
  storedInDb: boolean;
}) {
  const e = escapeHtml;
  // Applicants write prose with line breaks — preserve them, let no markup through.
  const para = (s: string) => e(s).replace(/\n/g, "<br/>");
  const spoken = (f: string) =>
    a.spokenFields.includes(f)
      ? ' <span style="font-size:11px;color:#8a8a8a;font-weight:400;">(spoken)</span>'
      : "";

  const block = (label: string, body: string, extra: string, key: string) => `
  <div style="margin: 0 0 26px 0;">
    <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #C9A227; font-weight: 600; margin: 0 0 6px 0;">${label}${spoken(key)}</p>
    <p style="font-size: 15px; line-height: 1.65; color: #1a1a1a; margin: 0;">${para(body)}</p>
    ${
      extra
        ? `<p style="font-size: 14px; line-height: 1.65; color: #4a4a4a; margin: 10px 0 0 0; padding-left: 12px; border-left: 2px solid #e8e2db;">${para(extra)}</p>`
        : ""
    }
  </div>`;

  const attribution = [
    a.utmSource && `source: ${e(a.utmSource)}`,
    a.utmMedium && `medium: ${e(a.utmMedium)}`,
    a.utmCampaign && `campaign: ${e(a.utmCampaign)}`,
    a.referrer && `referrer: ${e(a.referrer)}`,
  ]
    .filter(Boolean)
    .join(" &middot; ");

  const fileList = a.files.length
    ? a.files
        .map(
          (f) =>
            `<p style="margin:0 0 6px 0;font-size:14px;"><a href="${e(f.url)}" style="color:#C9A227;font-weight:600;">${e(f.filename)}</a></p>`
        )
        .join("")
    : "";

  const roles = a.roleLabels ?? [];
  const answers = a.answers ?? [];
  const isRole = roles.length > 0;

  // Role applications carry their own questions, so the two fixed /build
  // blocks are replaced by the answer list the candidate actually saw.
  const answerBlocks = answers
    .map((ans) => block(ans.question, ans.answer, "", ans.id))
    .join("");

  const linkBlock = (a.links ?? []).length
    ? `<div style="margin: 0 0 26px 0;">
         <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #C9A227; font-weight: 600; margin: 0 0 6px 0;">Links</p>
         ${(a.links ?? [])
           .map(
             (l) =>
               `<p style="margin:0 0 5px 0;font-size:14px;"><a href="${e(l)}" style="color:#C9A227;" rel="noopener noreferrer">${e(l)}</a></p>`
           )
           .join("")}
       </div>`
    : "";

  const logistics = [
    a.availability && `<strong>Availability:</strong> ${e(a.availability)}`,
    a.startDate && `<strong>Can start:</strong> ${e(a.startDate)}`,
    a.vancouver && `<strong>Vancouver:</strong> ${e(a.vancouver)}`,
    a.workAuthorized === false
      ? `<strong style="color:#8A1F1F;">Not legally able to work / under minimum age</strong>`
      : a.workAuthorized === true
        ? `<strong>Legally able to work:</strong> yes`
        : "",
  ]
    .filter(Boolean)
    .join("<br/>");

  const logisticsBlock = logistics
    ? `<div style="margin: 0 0 26px 0; padding: 14px 16px; background: #FAF8F5; border-radius: 8px;">
         <p style="font-size: 14px; line-height: 1.7; color: #1a1a1a; margin: 0;">${logistics}</p>
       </div>`
    : "";

  return sendMail({
    to: OWNER_EMAILS,
    replyTo: a.email,
    tag: isRole ? "role-application" : "builder-application",
    // The tag in the subject is what makes these filterable in a mailbox.
    subject: isRole
      ? `[${roles.length > 1 ? "MULTI" : (a.questionSet ?? "ROLE").toUpperCase()}] ${a.name} — ${a.location}`
      : `[BUILD] ${a.name} — ${a.location}`,
    headers: {
      "X-Priority": "1",
      "X-MSMail-Priority": "High",
      Importance: "High",
    },
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 640px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">
  ${
    a.storedInDb
      ? ""
      : `<p style="background:#FDECEC;border:1px solid #F5C2C2;border-radius:8px;padding:12px 14px;font-size:13px;color:#8A1F1F;margin:0 0 20px 0;"><strong>Not saved to the database.</strong> The row write failed, so this email is the only copy. Check the anticipy_applications table exists.</p>`
  }

  ${
    isRole
      ? `<p style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #C9A227; font-weight: 600; margin: 0 0 8px 0;">Applying for</p>
         <p style="font-size: 16px; font-weight: 600; margin: 0 0 16px 0;">${roles.map((r) => e(r)).join("<br/>")}</p>`
      : ""
  }

  <h2 style="margin: 0 0 4px 0; font-size: 21px;">${e(a.name)}</h2>
  <p style="color: #6b635b; margin: 0 0 22px 0; font-size: 14px;">
    <a href="mailto:${e(a.email)}" style="color: #C9A227;">${e(a.email)}</a>
    &middot; ${e(a.location)}
    ${a.domainOk ? "" : ` &middot; <span style="color:#8A1F1F;">email domain check: ${e(a.domainReason)}</span>`}
  </p>

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 0 0 24px 0;" />

  ${logisticsBlock}

  ${
    isRole
      ? `${answerBlocks}${linkBlock}`
      : `${block("The first thing", a.thing1, a.thing1Extra, "thing1")}
         ${block("The second thing", a.thing2, a.thing2Extra, "thing2")}`
  }

  ${
    fileList || a.resumeLink
      ? `<hr style="border: none; border-top: 1px solid #e8e2db; margin: 26px 0 18px 0;" />
         ${fileList}
         ${a.resumeLink ? `<p style="margin:0 0 6px 0;font-size:14px;"><a href="${e(a.resumeLink)}" style="color:#C9A227;font-weight:600;" rel="noopener noreferrer">${e(a.resumeLink)}</a></p>` : ""}
         <p style="font-size:12px;color:#8a8a8a;margin:8px 0 0 0;">Private links, expire in 14 days.</p>`
      : ""
  }

  ${attribution ? `<p style="font-size: 12px; color: #8a8a8a; margin: 20px 0 0 0;">${attribution}</p>` : ""}
  <p style="font-size: 12px; color: #8a8a8a; margin: 16px 0 0 0;">Reply to this email to reach ${e(a.name)} directly.</p>
</div>
    `.trim(),
  });
}

// ─── APPLICANT RECEIPT ─────────────────────────────────────────────
// Sent to the applicant. Two jobs: it closes the loop for a person who has
// just spent real effort, and it is the only genuine proof the address
// exists — a hard bounce on this message is ground truth, obtained at zero
// friction. That is why there is no magic-link confirmation step on the form.
export async function sendApplicantReceipt(
  email: string,
  name: string,
  copy?: {
    roleLabels?: string[];
    answers?: { id: string; question: string; answer: string }[];
    links?: string[];
    availability?: string;
    startDate?: string;
    vancouver?: string;
    attachmentNames?: string[];
  }
) {
  const first = escapeHtml(sanitizeHeader(name.split(" ")[0] || "", 60));
  const e = escapeHtml;
  const para = (s: string) => e(s).replace(/\n/g, "<br/>");

  const roles = copy?.roleLabels ?? [];
  const answers = copy?.answers ?? [];

  // A copy of what they wrote. Worth including for its own sake — people
  // rarely keep a record of what they said — and it also means a candidate
  // arriving at the interview can reread their own answers.
  const transcript = answers.length
    ? `
  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0 24px;" />
  <p style="font-size: 13px; color: #8a8a8a; margin: 0 0 20px;">Your answers, for your records:</p>
  ${
    roles.length
      ? `<p style="font-size: 14px; margin: 0 0 20px;"><strong>Role:</strong> ${roles.map((r) => e(r)).join(", ")}</p>`
      : ""
  }
  ${answers
    .map(
      (ans) => `
  <div style="margin: 0 0 20px;">
    <p style="font-size: 13px; color: #6b635b; margin: 0 0 5px;">${e(ans.question)}</p>
    <p style="font-size: 15px; line-height: 1.65; margin: 0;">${para(ans.answer)}</p>
  </div>`
    )
    .join("")}
  ${
    (copy?.links ?? []).length
      ? `<div style="margin: 0 0 20px;"><p style="font-size: 13px; color: #6b635b; margin: 0 0 5px;">Links</p>${(copy?.links ?? [])
          .map(
            (l) =>
              `<p style="margin:0 0 4px;font-size:14px;"><a href="${e(l)}" style="color:#C9A227;" rel="noopener noreferrer">${e(l)}</a></p>`
          )
          .join("")}</div>`
      : ""
  }
  ${
    (copy?.attachmentNames ?? []).length
      ? `<p style="font-size: 14px; margin: 0 0 20px;"><strong>Attached:</strong> ${(copy?.attachmentNames ?? []).map((f) => e(f)).join(", ")}</p>`
      : ""
  }
  ${
    copy?.availability || copy?.startDate || copy?.vancouver
      ? `<p style="font-size: 14px; line-height: 1.7; margin: 0 0 20px; color: #4a4a4a;">${[
          copy?.availability && `Availability: ${e(copy.availability)}`,
          copy?.startDate && `Can start: ${e(copy.startDate)}`,
          copy?.vancouver && `Location: ${e(copy.vancouver)}`,
        ]
          .filter(Boolean)
          .join("<br/>")}</p>`
      : ""
  }`
    : "";

  return sendMail({
    to: email,
    bccOwner: false,
    replyTo: REPLY_TO,
    tag: "application-receipt",
    // Every role they picked, not just the first — somebody who applied for
    // both engineering roles was being told their application was for one.
    subject: roles.length
      ? `Your Anticipy application — ${sanitizeHeader(roles.join(" + "), 120)}`
      : "Your Anticipy application",
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.7;">
  <p style="font-size: 16px;">${first ? `${first},` : "Hi,"}</p>

  <p style="font-size: 16px;">Your application is in. A person reads these — there is no filter and no scoring.</p>

  <p style="font-size: 16px;">If you booked a time with Omar, it is in your calendar and he will be there. If you did not, and you would like to, the link is still on the confirmation page.</p>

  <p style="font-size: 16px;">Replying to this email reaches us directly.</p>

  <p style="font-size: 16px;">Omar Ebrahim<br/><span style="color:#8a8a8a;font-size:14px;">Founder, Anticipy</span></p>
  ${transcript}
  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0;" />
  <p style="font-size: 13px; color: #8a8a8a;">
    Anticipation Labs Inc. &middot; <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a>
  </p>
</div>
    `.trim(),
  });
}

// ─── UGC CREATOR PROGRAM ───────────────────────────────────────────
// Two messages per signup: the owner's copy of everything, and the creator's
// own record of the link they claimed and the rate they claimed it at.

export async function sendUgcNotification(a: {
  name: string;
  email: string;
  location: string;
  handle: string;
  socials: Record<string, string>;
  answers: { id: string; question: string; answer: string }[];
  payoutMethod: string;
  payoutDetail: string;
  domainOk: boolean;
  domainReason: string;
  utmSource: string | null;
  utmMedium: string | null;
  utmCampaign: string | null;
  referrer: string | null;
  storedInDb: boolean;
}) {
  const e = escapeHtml;
  const para = (s: string) => e(s).replace(/\n/g, "<br/>");

  const socialRows = Object.entries(a.socials)
    .map(
      ([k, v]) =>
        `<p style="margin:0 0 5px 0;font-size:14px;"><span style="color:#8a8a8a;text-transform:capitalize;">${e(k)}:</span> ${e(v)}</p>`
    )
    .join("");

  const answerBlocks = a.answers
    .filter((x) => x.answer)
    .map(
      (x) => `
  <div style="margin: 0 0 26px 0;">
    <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #C9A227; font-weight: 600; margin: 0 0 6px 0;">${e(x.question)}</p>
    <p style="font-size: 15px; line-height: 1.65; color: #1a1a1a; margin: 0;">${para(x.answer)}</p>
  </div>`
    )
    .join("");

  const attribution = [
    a.utmSource && `source: ${e(a.utmSource)}`,
    a.utmMedium && `medium: ${e(a.utmMedium)}`,
    a.utmCampaign && `campaign: ${e(a.utmCampaign)}`,
    a.referrer && `referrer: ${e(a.referrer)}`,
  ]
    .filter(Boolean)
    .join(" &middot; ");

  return sendMail({
    to: OWNER_EMAILS,
    replyTo: a.email,
    tag: "ugc-signup",
    subject: `[UGC] ${a.name} — /c/${a.handle}`,
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 640px; margin: 0 auto; color: #1a1a1a; line-height: 1.6;">
  ${
    a.storedInDb
      ? ""
      : `<p style="background:#FDECEC;border:1px solid #F5C2C2;border-radius:8px;padding:12px 14px;font-size:13px;color:#8A1F1F;margin:0 0 20px 0;"><strong>Not saved to the database.</strong> The row write failed, so this email is the only copy — and the link below is NOT reserved. Check the anticipy_ugc_creators table exists.</p>`
  }

  <p style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.12em; color: #C9A227; font-weight: 600; margin: 0 0 8px 0;">New UGC creator</p>
  <h2 style="margin: 0 0 4px 0; font-size: 21px;">${e(a.name)}</h2>
  <p style="color: #6b635b; margin: 0 0 18px 0; font-size: 14px;">
    <a href="mailto:${e(a.email)}" style="color: #C9A227;">${e(a.email)}</a>
    &middot; ${e(a.location)}
    ${a.domainOk ? "" : ` &middot; <span style="color:#8A1F1F;">email domain check: ${e(a.domainReason)}</span>`}
  </p>

  <div style="margin: 0 0 22px 0; padding: 14px 16px; background: #FAF8F5; border-radius: 8px;">
    <p style="font-size: 15px; margin: 0 0 8px 0;"><strong>Their link:</strong> anticipy.ai/c/${e(a.handle)}</p>
    <p style="font-size: 14px; margin: 0;"><strong>Pay to:</strong> ${e(a.payoutMethod)} &mdash; ${e(a.payoutDetail)}</p>
  </div>

  ${socialRows ? `<div style="margin: 0 0 22px 0;">${socialRows}</div>` : ""}

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 0 0 24px 0;" />

  ${answerBlocks}

  <p style="font-size: 12px; color: #8a8a8a; margin: 20px 0 0 0;">Agreed to ad disclosure and the 90-day paid-usage licence.</p>
  ${attribution ? `<p style="font-size: 12px; color: #8a8a8a; margin: 8px 0 0 0;">${attribution}</p>` : ""}
  <p style="font-size: 12px; color: #8a8a8a; margin: 8px 0 0 0;">Reply to this email to reach ${e(a.name)} directly.</p>
</div>
    `.trim(),
  });
}

export async function sendUgcWelcome(email: string, name: string, handle: string) {
  const first = escapeHtml(sanitizeHeader(name.split(" ")[0] || "", 60));
  const h = escapeHtml(handle);
  const link = `https://anticipy.ai/c/${h}`;

  return sendMail({
    to: email,
    bccOwner: false,
    replyTo: REPLY_TO,
    tag: "ugc-welcome",
    subject: `Your Anticipy link: anticipy.ai/c/${sanitizeHeader(handle, 40)}`,
    html: `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; line-height: 1.7;">
  <p style="font-size: 16px;">${first ? `${first},` : "Hi,"}</p>

  <p style="font-size: 16px;">You're in. This is your link — it's live right now, and everything you earn is tracked through it.</p>

  <p style="text-align: center; margin: 28px 0;">
    <a href="${link}" style="display:inline-block;padding:14px 28px;background:#171512;color:#FAF8F4;text-decoration:none;border-radius:100px;font-weight:600;font-size:15px;">${link.replace("https://", "")}</a>
  </p>

  <p style="font-size: 16px;">Put it in your bio before you post anything. A video without the link earns the flat fee and nothing else.</p>

  <p style="font-size: 15px; line-height: 1.8;">
    <strong>$25</strong> per video, once it passes 1,000 views.<br/>
    <strong>15%</strong> of every order through your link.
  </p>

  <p style="font-size: 16px;"><strong>To get paid for a video:</strong> post it, tag <strong>@anticipy</strong>, label it as an ad, then send me the link. Once it clears 1,000 views I'll pay it out.</p>

  <p style="font-size: 15px; color: #6b635b;">Two things you agreed to, so they're not a surprise later: every paid video has to be labelled as an ad — the platform's paid-partnership toggle or #ad in the caption is enough — and we can run your video as an ad for 90 days from the day you send it. You keep the video and can post it wherever you like.</p>

  <p style="font-size: 16px;">Reply to this email if anything's unclear. It reaches me directly.</p>

  <p style="font-size: 16px;">Omar Ebrahim<br/><span style="color:#8a8a8a;font-size:14px;">Founder, Anticipy</span></p>

  <hr style="border: none; border-top: 1px solid #e8e2db; margin: 32px 0;" />
  <p style="font-size: 13px; color: #8a8a8a;">
    Anticipation Labs Inc. &middot; <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a>
  </p>
</div>
    `.trim(),
  });
}
