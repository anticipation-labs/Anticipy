/**
 * Lightweight SendGrid wrapper for transactional CRM emails.
 * The SendGrid API key is the only one wired in env today.
 * If neither SENDGRID nor RESEND_API_KEY is configured, sendEmail returns
 * { sent: false, reason } so callers do not throw.
 */
const SG_KEY = process.env.SENDGRID_API_KEY;
const RESEND_KEY = process.env.RESEND_API_KEY;
const FROM = process.env.CRM_EMAIL_FROM || "omar@anticipy.ai";

export type SendResult = { sent: boolean; provider?: string; reason?: string };

export async function sendEmail(opts: {
  to: string;
  subject: string;
  text: string;
}): Promise<SendResult> {
  if (RESEND_KEY) {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${RESEND_KEY}`,
      },
      body: JSON.stringify({
        from: FROM,
        to: opts.to,
        subject: opts.subject,
        text: opts.text,
      }),
    });
    if (!res.ok) {
      return { sent: false, provider: "resend", reason: `Resend ${res.status}` };
    }
    return { sent: true, provider: "resend" };
  }
  if (SG_KEY) {
    const res = await fetch("https://api.sendgrid.com/v3/mail/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${SG_KEY}`,
      },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: opts.to }] }],
        from: { email: FROM, name: "Anticipy" },
        subject: opts.subject,
        content: [{ type: "text/plain", value: opts.text }],
      }),
    });
    if (!res.ok) {
      const t = await res.text().catch(() => "");
      return { sent: false, provider: "sendgrid", reason: `SendGrid ${res.status}: ${t.slice(0, 200)}` };
    }
    return { sent: true, provider: "sendgrid" };
  }
  return { sent: false, reason: "No email provider configured" };
}
