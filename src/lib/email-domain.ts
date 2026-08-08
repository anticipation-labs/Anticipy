import "server-only";

/**
 * Split out of email-check.ts deliberately: this uses node:dns, and
 * email-check.ts is imported by a client component for its typo
 * suggestion. Bundling node:dns into the browser build is a hard error,
 * so the server-only half lives here.
 */
export interface DomainCheck {
  deliverable: boolean;
  reason: "ok" | "null_mx" | "no_mx" | "lookup_failed";
}

/**
 * Server-side DNS check. Distinguishes the two cases that matter:
 *
 *  - NULL MX (a single "." record) is RFC 7505 for "this domain accepts no
 *    mail, ever". That is a genuine hard signal and worth blocking on.
 *  - No MX at all is softer: some domains still receive on their A record,
 *    and DNS lookups fail transiently. Never block a candidate for that.
 */
export async function checkDomain(email: string): Promise<DomainCheck> {
  const domain = email.slice(email.lastIndexOf("@") + 1).toLowerCase();
  if (!domain) return { deliverable: false, reason: "no_mx" };
  try {
    const dns = await import("node:dns/promises");
    const mx = await dns.resolveMx(domain);
    if (!mx.length) return { deliverable: false, reason: "no_mx" };
    if (mx.length === 1 && (mx[0].exchange === "" || mx[0].exchange === ".")) {
      return { deliverable: false, reason: "null_mx" };
    }
    return { deliverable: true, reason: "ok" };
  } catch {
    // Includes NXDOMAIN and transient resolver failures. Soft — the
    // confirmation email and its bounce webhook are the real arbiter.
    return { deliverable: false, reason: "lookup_failed" };
  }
}
