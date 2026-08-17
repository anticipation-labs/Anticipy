import { escapeHtml } from "./escape";
import { TM_HTML } from "./tm";

/**
 * Branded HTML for customer-facing transactional email.
 *
 * Constraints these templates are written against, which explain choices that
 * look dated next to normal web markup:
 *  - Table layout with role="presentation". Outlook on Windows renders through
 *    Word, which ignores flex/grid and most modern CSS.
 *  - Inline styles plus bgcolor attributes. Gmail strips <style> blocks.
 *  - Absolute image URLs on our own origin. Email cannot load relative paths,
 *    and data: URIs are stripped by Gmail.
 *  - Every image has alt text and a fixed width. Most clients block images by
 *    default on first open, so the email has to read correctly with none of
 *    them loaded.
 *  - Total HTML stays well under 102KB, the size at which Gmail clips a
 *    message and hides the footer behind a "View entire message" link.
 */

const SITE = "https://www.anticipy.ai";
const IMG = `${SITE}/email`;

const BG = "#0C0C0C";
const CARD = "#111111";
const HAIRLINE = "#1F1F1F";
const GOLD = "#C8A97E";
const TEXT = "#FAFAFA";
const MUTED = "#8A8A8A";
const DIM = "#5A5A5A";
const FONT =
  "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif";
const SERIF = "Georgia,'Times New Roman',serif";

interface ShellArgs {
  preheader: string;
  eyebrow: string;
  heroSrc: string;
  heroAlt: string;
  body: string;
  footerNote: string;
}

/**
 * Shared chrome: dark canvas, centred card, serif wordmark, hero image,
 * footer. Both emails differ only in their eyebrow, hero and body.
 */
function shell(a: ShellArgs): string {
  return `<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="IE=edge" />
<meta name="color-scheme" content="dark light" />
<meta name="supported-color-schemes" content="dark light" />
<title>Anticipy</title>
</head>
<body style="margin:0;padding:0;background-color:${BG};color:${TEXT};-webkit-font-smoothing:antialiased;">
<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden;mso-hide:all;color:${BG};">${a.preheader}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" bgcolor="${BG}" style="background-color:${BG};">
  <tr>
    <td align="center" style="padding:32px 16px;">
      <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;background-color:${CARD};border:1px solid ${HAIRLINE};border-radius:16px;overflow:hidden;font-family:${FONT};">

        <tr>
          <td style="padding:26px 32px 22px 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td align="left" style="font-family:${SERIF};font-size:21px;letter-spacing:0.02em;color:${GOLD};">Anticipy${TM_HTML}</td>
                <td align="right" style="font-size:10px;text-transform:uppercase;letter-spacing:0.14em;color:${MUTED};font-weight:600;">${a.eyebrow}</td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:0;font-size:0;line-height:0;">
            <img src="${a.heroSrc}" width="600" alt="${a.heroAlt}" style="display:block;width:100%;max-width:600px;height:auto;border:0;outline:none;text-decoration:none;" />
          </td>
        </tr>

        ${a.body}

        <tr>
          <td style="padding:8px 32px 30px 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td style="border-top:1px solid ${HAIRLINE};padding-top:20px;font-size:11px;line-height:1.6;color:${DIM};">
                  ${a.footerNote}<br /><br />
                  Anticipation Labs${TM_HTML} Inc. &middot; <a href="${SITE}" style="color:${MUTED};text-decoration:underline;">anticipy.ai</a>
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

/** A paragraph row at the card's standard horizontal padding. */
function p(html: string, topPad = 18): string {
  return `<tr><td style="padding:${topPad}px 32px 0 32px;font-size:15px;line-height:1.65;color:#D8D8D8;">${html}</td></tr>`;
}

export function preorderConfirmationHtml(opts: {
  firstName: string;
  amountDisplay: string;
  currencyDisplay: string;
  sessionId: string;
}): string {
  // Escaped here rather than at the call site: the name reaches us from Stripe
  // checkout, so it is attacker-controlled text landing in markup.
  const safeFirst = escapeHtml(opts.firstName);
  const greeting = safeFirst ? `You're in, ${safeFirst}.` : "You're in.";

  const body = `
        <tr>
          <td style="padding:30px 32px 0 32px;font-size:25px;line-height:1.3;color:${TEXT};font-weight:600;letter-spacing:-0.01em;">${greeting}</td>
        </tr>
        ${p(
          "Your Anticipy pendant is reserved. You're among the first people who will ever wear one.",
          14
        )}

        <tr>
          <td style="padding:24px 32px 0 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#0E0E0E;border:1px solid ${HAIRLINE};border-radius:12px;">
              <tr>
                <td style="padding:18px 20px;">
                  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="font-size:13px;color:${MUTED};">
                    <tr>
                      <td style="padding:5px 0;">Anticipy Pendant &mdash; pre-order</td>
                      <td align="right" style="padding:5px 0;color:${TEXT};font-weight:600;font-size:15px;">$${opts.amountDisplay} ${opts.currencyDisplay}</td>
                    </tr>
                    <tr>
                      <td style="padding:5px 0;">Retail at launch</td>
                      <td align="right" style="padding:5px 0;color:${MUTED};text-decoration:line-through;">$199.00</td>
                    </tr>
                    <tr>
                      <td style="padding:5px 0;">Shipping to US &amp; Canada</td>
                      <td align="right" style="padding:5px 0;color:${GOLD};">Free</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:28px 32px 0 32px;font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:${GOLD};font-weight:600;">What happens next</td>
        </tr>
        ${p(
          `<strong style="color:${TEXT};">We build.</strong> Manufacturing is targeting Q4 2026.`,
          14
        )}
        ${p(
          `<strong style="color:${TEXT};">We check in.</strong> Before anything ships we'll email you to confirm your address.`,
          8
        )}
        ${p(
          `<strong style="color:${TEXT};">It arrives.</strong> Pendant, chain and wireless charging pad, boxed and ready to wear.`,
          8
        )}

        <tr>
          <td style="padding:26px 32px 0 32px;">
            <img src="${IMG}/preorder-included.jpg" width="536" alt="Anticipy pendant with its chain coiled on slate" style="display:block;width:100%;max-width:536px;height:auto;border:0;border-radius:12px;outline:none;text-decoration:none;" />
          </td>
        </tr>

        ${p(
          `Stripe emailed your receipt separately &mdash; keep it for your records. Need to change anything, or just want to ask a question? Reply to this email. I read every one personally.`,
          24
        )}

        <tr>
          <td style="padding:22px 32px 0 32px;font-size:15px;line-height:1.6;color:#D8D8D8;">
            Omar Ebrahim<br /><span style="color:${MUTED};font-size:13px;">Founder, Anticipy</span>
          </td>
        </tr>

        <tr>
          <td style="padding:22px 32px 0 32px;font-size:11px;color:${DIM};font-family:monospace;">Order reference: ${escapeHtml(
            opts.sessionId
          )}</td>
        </tr>
  `;

  return shell({
    preheader: `Your Anticipy pendant is reserved — $${opts.amountDisplay} ${opts.currencyDisplay}, free shipping.`,
    eyebrow: "Pre-order confirmed",
    heroSrc: `${IMG}/preorder-hero-v2.jpg`,
    heroAlt:
      "An Anticipy pendant hanging on its chain, the indicator lit warm amber",
    body,
    footerNote: `You're receiving this because you pre-ordered an Anticipy pendant. Pre-order terms: <a href="${SITE}/pre-orders/agreement" style="color:${MUTED};text-decoration:underline;">anticipy.ai/pre-orders/agreement</a>`,
  });
}

export function waitlistWelcomeHtml(opts: { firstName: string }): string {
  // Escaped here for the same reason as the pre-order greeting: this name comes
  // from a public signup form.
  const safeFirst = escapeHtml(opts.firstName);
  const greeting = safeFirst
    ? `You're on the list, ${safeFirst}.`
    : "You're on the list.";

  const body = `
        <tr>
          <td style="padding:30px 32px 0 32px;font-size:25px;line-height:1.3;color:${TEXT};font-weight:600;letter-spacing:-0.01em;">${greeting}</td>
        </tr>
        ${p(
          "You're now one of the first people following what we're building &mdash; before it's public, before it's on a shelf.",
          14
        )}
        ${p(
          `Anticipy is a pendant that doesn't just listen. It <strong style="color:${TEXT};">acts</strong>. It books the appointment, sends the follow-up, fills in the form. You wear it, you forget it's there, and the things you said you'd do quietly get done.`
        )}

        <tr>
          <td style="padding:26px 32px 0 32px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#0E0E0E;border-left:2px solid ${GOLD};border-radius:4px;">
              <tr>
                <td style="padding:16px 20px;font-size:14px;line-height:1.6;color:#C4C4C4;font-style:italic;">
                  Nothing to charge every night. Nothing to open. Nothing to remember.
                </td>
              </tr>
            </table>
          </td>
        </tr>

        ${p(
          "We'll write when there's something real to show you &mdash; not before. When pre-orders open to the public, you'll hear it here first.",
          24
        )}

        <tr>
          <td style="padding:26px 32px 0 32px;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0">
              <tr>
                <td bgcolor="${GOLD}" style="border-radius:100px;mso-padding-alt:0;">
                  <a href="${SITE}/pre-orders" style="display:inline-block;padding:13px 30px;color:#0C0C0C;text-decoration:none;font-weight:600;font-size:14px;font-family:${FONT};border-radius:100px;line-height:1;">See the pendant</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        ${p("Thanks for believing early.", 24)}

        <tr>
          <td style="padding:18px 32px 0 32px;font-size:15px;line-height:1.6;color:#D8D8D8;">
            Omar Ebrahim<br /><span style="color:${MUTED};font-size:13px;">Founder, Anticipy</span>
          </td>
        </tr>
  `;

  return shell({
    preheader:
      "The AI pendant that acts on what you say. We'll write when there's something real to show.",
    eyebrow: "Waitlist",
    heroSrc: `${IMG}/waitlist-hero.jpg`,
    heroAlt:
      "An Anticipy pendant with its chain coiled beside it on dark slate",
    body,
    footerNote:
      "You're receiving this because you joined the Anticipy waitlist.",
  });
}
