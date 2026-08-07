import crypto from "node:crypto";

/**
 * Server-side event capture.
 *
 * Exists because the events that matter most commercially are the ones the
 * browser is least able to send. A purchase confirmation happens on Stripe's
 * domain, and client-side conversion pixels are among the most reliably
 * blocked requests on the web — so a browser-reported revenue number is
 * always an undercount, and undercounts by an amount that correlates with
 * exactly the technical audience this product targets.
 *
 * Posting straight to PostHog's capture endpoint rather than pulling in
 * posthog-node: one fetch, no dependency, no client lifecycle to manage in a
 * serverless handler that may be frozen mid-flush.
 */

const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY;

// Deliberately NOT the /ingest proxy. That rewrite exists to dodge client-side
// content blockers; a server has no such problem, and routing server events
// back through our own edge would add a hop and a failure mode for nothing.
const POSTHOG_HOST = "https://us.i.posthog.com";

/**
 * SHA-256 of the normalised email — the same canonical person id the browser
 * computes in src/lib/analytics.ts. Both sides must produce identical output
 * for the webhook's events to land on the same person as the visitor's
 * browsing history, so the normalisation (trim, lowercase) is load-bearing
 * and must not drift between the two implementations.
 */
export function emailHashServer(email: string): string {
  return crypto
    .createHash("sha256")
    .update(email.trim().toLowerCase())
    .digest("hex");
}

interface ServerCaptureArgs {
  distinctId: string;
  event: string;
  properties?: Record<string, unknown>;
  /** Person properties to overwrite. */
  set?: Record<string, unknown>;
  /** Person properties to write only if not already present. */
  setOnce?: Record<string, unknown>;
}

/**
 * Never throws. A failed analytics call must not turn a successful payment
 * into a 500 that makes Stripe retry an already-fulfilled order.
 */
export async function captureServer(args: ServerCaptureArgs): Promise<boolean> {
  if (!POSTHOG_KEY || !args.distinctId) return false;

  const properties: Record<string, unknown> = { ...args.properties };
  if (args.set) properties.$set = args.set;
  if (args.setOnce) properties.$set_once = args.setOnce;

  try {
    const res = await fetch(`${POSTHOG_HOST}/i/v0/e/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: POSTHOG_KEY,
        event: args.event,
        distinct_id: args.distinctId,
        properties,
        timestamp: new Date().toISOString(),
      }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
