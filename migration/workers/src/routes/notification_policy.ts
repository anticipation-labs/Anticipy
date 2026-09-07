import { verifyToken, type AuthEnv } from "../api/auth.ts";
import { QUIET_HOURS_START, QUIET_HOURS_END } from "../connections/nudge.ts";

/** The current outreach policy, not a receipt for any individual message. */
export function notificationPolicyAt(now: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(now);
  const value = (name: string) => Number(parts.find(p => p.type === name)?.value);
  const hour = value("hour"), minute = value("minute"), second = value("second");
  if (![hour, minute, second].every(Number.isFinite)) throw new Error("Unknown local clock");
  const observedAt = now.getTime() / 1000;
  return {
    quietHoursActive: hour >= QUIET_HOURS_START || hour < QUIET_HOURS_END,
    startHour: QUIET_HOURS_START, endHour: QUIET_HOURS_END, timeZone,
    observedAt,
    // Never let a cached night badge cross the next hour boundary, including
    // the exact 08:00 end of the window. Failed refreshes become unknown.
    expiresAt: Math.min(observedAt + 60,
      Math.floor(observedAt) + (60 - minute) * 60 - second),
  };
}

type Env = AuthEnv & { DB: D1Database };
const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});

export async function notificationPolicy(request: Request, env: Env): Promise<Response> {
  if (request.method !== "GET") return reply(405, { message: "Method not allowed." });
  const auth = await verifyToken(env, request.headers.get("Authorization") || "");
  if (!auth) return reply(401, { message: "Sign in first." });
  if (auth.claims.collectionName !== "owners") return reply(403, { message: "Account required." });
  try {
    const profile = await env.DB.prepare(
      'SELECT timezone FROM owner_profile WHERE owner_ref = ?1 ORDER BY updated DESC, created DESC, id DESC LIMIT 1',
    ).bind(auth.claims.id).first<{ timezone: string }>();
    const zone = profile?.timezone?.trim() || "America/Vancouver";
    return reply(200, notificationPolicyAt(new Date(), zone));
  } catch {
    // Unknown configuration must not masquerade as either day or night.
    return reply(503, { message: "Texting schedule is unavailable." });
  }
}
