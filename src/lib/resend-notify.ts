import { escapeHtml, sanitizeHeader } from "./escape";
import { signConfirmToken } from "./confirm-token";
import { sendNotification } from "./notification-adapter";

const FROM_EMAIL = "Anticipy <notifications@aevoy.com>";

interface IntentNotification {
  intentId: string;
  summary: string;
  evidenceQuote: string;
  importance: string;
  actionType: string;
  // Owning user id. When present, baked into the HMAC signature so the
  // resulting token can only confirm the matching intent. Optional for
  // backwards compatibility with callers that don't yet pass it.
  userId?: string;
}

type Importance = "critical" | "important" | "standard" | "low";

function importanceLabel(importance: string): { label: string; color: string } {
  switch (importance as Importance) {
    case "critical":
      return { label: "Critical", color: "#FF6B6B" };
    case "important":
      return { label: "Important", color: "#F0A04B" };
    case "standard":
      return { label: "Standard", color: "#C8A97E" };
    default:
      return { label: "Low", color: "#8A8A8A" };
  }
}

export async function sendIntentEmail(
  toEmail: string,
  intent: IntentNotification,
  baseUrl: string,
  subjectPrefix?: string
): Promise<{ id: string } | null> {
  // Issue a signed token bound to (intentId, userId, expiresAt). The
  // confirm route validates the signature + expiry, and accepts old plain
  // intentId links for a 24h grace window via the legacy fallback path.
  const token = signConfirmToken({
    intentId: intent.intentId,
    userId: intent.userId ?? "",
  });
  const safeToken = encodeURIComponent(token);
  const confirmUrl = `${baseUrl}/api/engine/confirm?token=${safeToken}&action=yes`;
  const rejectUrl = `${baseUrl}/api/engine/confirm?token=${safeToken}&action=no`;

  const { label: importanceText, color: importanceColor } = importanceLabel(
    intent.importance
  );

  const rawSubject = subjectPrefix
    ? `${subjectPrefix} Anticipy: ${intent.summary}`
    : `Anticipy: ${intent.summary}`;
  const subject = sanitizeHeader(rawSubject, 180);

  const safeSummary = escapeHtml(intent.summary);
  const safeQuote = escapeHtml(intent.evidenceQuote);
  const safePreheader = escapeHtml(
    `${importanceText} · ${intent.summary}`.slice(0, 140)
  );

  const html = buildHtml({
    safeSummary,
    safeQuote,
    safePreheader,
    importanceText,
    importanceColor,
    confirmUrl,
    rejectUrl,
  });

  const text = buildText({
    summary: intent.summary,
    evidenceQuote: intent.evidenceQuote,
    importanceText,
    confirmUrl,
    rejectUrl,
  });

  const result = await sendNotification({
    channel: "email",
    from: FROM_EMAIL,
    to: toEmail,
    subject,
    html,
    text,
    intentId: intent.intentId,
    userId: intent.userId,
    importance: intent.importance as Importance,
    idempotencyKey: `intent-email:${intent.intentId}:${toEmail}`,
    recordAttempt: false,
    headers: {
      "X-Entity-Ref-ID": intent.intentId,
    },
  });

  if (!result.ok) {
    console.error("Notification email error:", result.error);
    return null;
  }

  return { id: result.providerMessageId || "" };
}

interface HtmlArgs {
  safeSummary: string;
  safeQuote: string;
  safePreheader: string;
  importanceText: string;
  importanceColor: string;
  confirmUrl: string;
  rejectUrl: string;
}

function buildHtml(a: HtmlArgs): string {
  return `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="dark light">
<meta name="supported-color-schemes" content="dark light">
<title>Anticipy</title>
</head>
<body style="margin:0;padding:0;background-color:#0C0C0C;color:#FAFAFA;-webkit-font-smoothing:antialiased;">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;color:#0C0C0C;">${a.safePreheader}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#0C0C0C;">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="520" cellspacing="0" cellpadding="0" border="0" style="max-width:520px;width:100%;background-color:#111111;border:1px solid #1F1F1F;border-radius:16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
        <tr>
          <td style="padding:28px 32px 0 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td align="left" style="font-family:Georgia,'Times New Roman',serif;font-size:20px;letter-spacing:0.02em;color:#C8A97E;">Anticipy</td>
                <td align="right" style="font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:${a.importanceColor};font-weight:600;">${a.importanceText}</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 0 32px;font-size:13px;color:#8A8A8A;line-height:1.4;">I heard you mention</td>
        </tr>
        <tr>
          <td style="padding:8px 32px 0 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td style="border-left:3px solid #C8A97E;padding:4px 0 4px 14px;font-style:italic;font-size:15px;line-height:1.5;color:#E8E8E8;">&ldquo;${a.safeQuote}&rdquo;</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 32px 0 32px;font-size:17px;line-height:1.45;color:#FAFAFA;font-weight:600;">${a.safeSummary}</td>
        </tr>
        <tr>
          <td style="padding:24px 32px 0 32px;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td bgcolor="#C8A97E" style="border-radius:100px;mso-padding-alt:0;">
                  <a href="${a.confirmUrl}" style="display:inline-block;padding:12px 28px;color:#0C0C0C;text-decoration:none;font-weight:600;font-size:14px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;border-radius:100px;line-height:1;">Yes, do it</a>
                </td>
                <td style="width:10px;font-size:0;line-height:0;">&nbsp;</td>
                <td bgcolor="#1F1F1F" style="border-radius:100px;mso-padding-alt:0;">
                  <a href="${a.rejectUrl}" style="display:inline-block;padding:12px 28px;color:#A8A8A8;text-decoration:none;font-weight:500;font-size:14px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;border-radius:100px;line-height:1;">Skip</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:20px 32px 0 32px;font-size:12px;line-height:1.5;color:#5A5A5A;">Tap a button above and Anticipy will handle the rest. Links expire after the first tap.</td>
        </tr>
        <tr>
          <td style="padding:28px 32px 28px 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td style="border-top:1px solid #1F1F1F;padding-top:18px;font-size:11px;line-height:1.5;color:#5A5A5A;">
                  Sent because you wear Anticipy. <a href="${a.confirmUrl.split("/api/")[0]}/engine" style="color:#8A8A8A;text-decoration:underline;">Open the dashboard</a>.
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>`;
}

interface TextArgs {
  summary: string;
  evidenceQuote: string;
  importanceText: string;
  confirmUrl: string;
  rejectUrl: string;
}

function buildText(a: TextArgs): string {
  return [
    `Anticipy - ${a.importanceText}`,
    "",
    "I heard you mention:",
    `  "${a.evidenceQuote}"`,
    "",
    a.summary,
    "",
    `Yes, do it:  ${a.confirmUrl}`,
    `Skip:        ${a.rejectUrl}`,
    "",
    "Links expire after the first tap.",
  ].join("\n");
}
