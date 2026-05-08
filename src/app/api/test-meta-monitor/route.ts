/**
 * Test-only invoker for src/lib/meta-monitor.ts. Mounted at
 * /api/test-meta-monitor (Next.js excludes any directory beginning
 * with `_` from routing, so a `__tests__` parent would 404).
 *
 * Exposes buildUserProfile() and recallUserProfile() to engine/
 * test_meta_monitor.py so we can stress concurrency and edge cases
 * without going through the full /confirm + /auto-proceed plumbing
 * (which already does the right thing in production but is too slow
 * to fan out 100 concurrent calls within a single test run).
 *
 * Hardening:
 *  - Refuses to run unless NODE_ENV !== "production".
 *  - Refuses unless x-test-secret header matches META_MONITOR_TEST_SECRET
 *    (defaults to "test-secret" so local dev runs work out of the box).
 *  - userId must look like a Supabase auth UUID. We don't allow this
 *    endpoint to manipulate arbitrary text user_ids.
 *
 * forceMalformed=true patches the buildUserProfile call so the JSON.parse
 * branch fires and exercises the "malformed Gemini response → preserve
 * existing profile" code path.
 */
import { NextResponse } from "next/server";
import { buildUserProfile, recallUserProfile } from "@/lib/meta-monitor";

export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(req: Request) {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ error: "Disabled" }, { status: 404 });
  }
  const secret = req.headers.get("x-test-secret") ?? "";
  const expected = process.env.META_MONITOR_TEST_SECRET ?? "test-secret";
  if (secret !== expected) {
    return NextResponse.json({ error: "Forbidden" }, { status: 403 });
  }

  let body: {
    op?: string;
    userId?: string;
    forceMalformed?: boolean;
  };
  try {
    body = (await req.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const op = String(body.op ?? "");
  const userId = String(body.userId ?? "");
  if (!UUID_RE.test(userId)) {
    return NextResponse.json(
      { error: "userId must be a UUID" },
      { status: 400 }
    );
  }

  if (op === "build") {
    if (body.forceMalformed) {
      // Set the test-only flag in process env BEFORE the call; the
      // buildUserProfile reads it and short-circuits as if Gemini
      // returned non-JSON garbage. We restore it after the call so
      // parallel tests don't affect each other.
      const prev = process.env.META_MONITOR_TEST_FORCE_MALFORMED;
      process.env.META_MONITOR_TEST_FORCE_MALFORMED = "1";
      try {
        await buildUserProfile(userId);
      } finally {
        if (prev === undefined) {
          delete process.env.META_MONITOR_TEST_FORCE_MALFORMED;
        } else {
          process.env.META_MONITOR_TEST_FORCE_MALFORMED = prev;
        }
      }
    } else {
      await buildUserProfile(userId);
    }
    return NextResponse.json({ ok: true });
  }

  if (op === "recall") {
    const profile = await recallUserProfile(userId);
    return NextResponse.json({ ok: true, profile });
  }

  return NextResponse.json({ error: `Unknown op: ${op}` }, { status: 400 });
}
