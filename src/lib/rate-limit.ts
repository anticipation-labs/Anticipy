/**
 * In-memory IP rate limiter — alpha-grade.
 *
 * Buckets are per-(key, namespace). State is process-local so a deploy or
 * cold-start resets all counters; that's acceptable for an alpha. For
 * production, swap with Upstash Redis or Supabase RPC.
 */
type Bucket = { count: number; resetAt: number };

const buckets = new Map<string, Bucket>();

export interface RateLimitResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;
}

/**
 * Check whether `key` is under `limit` requests per `windowMs`.
 * On allow, increments the bucket. On deny, leaves the bucket untouched.
 */
export function rateLimit(
  key: string,
  limit: number,
  windowMs: number
): RateLimitResult {
  const now = Date.now();
  const existing = buckets.get(key);
  if (!existing || existing.resetAt <= now) {
    buckets.set(key, { count: 1, resetAt: now + windowMs });
    return { allowed: true, remaining: limit - 1, resetAt: now + windowMs };
  }
  if (existing.count >= limit) {
    return { allowed: false, remaining: 0, resetAt: existing.resetAt };
  }
  existing.count += 1;
  return {
    allowed: true,
    remaining: limit - existing.count,
    resetAt: existing.resetAt,
  };
}

/**
 * Best-effort IP extraction from a Next.js Request. Trusts the
 * x-forwarded-for header chain (Vercel sets this); falls back to "unknown"
 * which collapses all anonymous traffic into a single bucket — safer than
 * letting it through unrestricted.
 */
export function clientIp(req: Request): string {
  const xff = req.headers.get("x-forwarded-for") || "";
  const first = xff.split(",")[0]?.trim();
  if (first) return first;
  const real = req.headers.get("x-real-ip");
  if (real) return real.trim();
  return "unknown";
}
