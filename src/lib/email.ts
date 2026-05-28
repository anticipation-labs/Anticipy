import { escapeHtml, sanitizeHeader } from "./escape";

const SENDGRID_API_KEY = process.env.SENDGRID_API_KEY;
const FROM_EMAIL = "hello@anticipy.ai";
const FROM_NAME = "Omar from Anticipy";
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
    Anticipy — The AI wearable that acts.<br/>
    <a href="https://anticipy.ai" style="color: #C9A227;">anticipy.ai</a>
  </p>
</div>
    `.trim(),
  });
}
