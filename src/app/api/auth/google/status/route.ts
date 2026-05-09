import { NextResponse } from "next/server";
import { getStoredTokens } from "@/lib/google-calendar";
import { requireSupabaseUser } from "@/lib/require-auth";

export const dynamic = "force-dynamic";

/**
 * GET /api/auth/google/status
 *
 * Returns whether the *current authenticated user* has connected Google
 * Calendar. Tokens are keyed by email, so we look up by the auth user's
 * email — never a global TEST_USER_EMAIL — so signed-in users don't see
 * each other's connection state.
 *
 * Unauthenticated callers always get connected:false (no information leak).
 */
// Bound the entire status check at 4s so a Supabase regional outage doesn't
// burn the full Vercel function budget (10s) and 504. Mounting clients call
// this on /engine page load — a 504 here is what blocks the page from
// rendering. If anything hangs we just return connected:false fast and let
// the rest of the UI render.
const STATUS_TIMEOUT_MS = 4_000;

async function _withTimeout<T>(p: Promise<T>, ms: number, fallback: T): Promise<T> {
  let to: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      p,
      new Promise<T>((resolve) => {
        to = setTimeout(() => resolve(fallback), ms);
      }),
    ]);
  } finally {
    if (to) clearTimeout(to);
  }
}

export async function GET(req: Request) {
  const user = await _withTimeout(requireSupabaseUser(req), STATUS_TIMEOUT_MS, null);
  if (!user?.email) {
    return NextResponse.json({ connected: false });
  }
  try {
    const tokens = await _withTimeout(getStoredTokens(user.email), STATUS_TIMEOUT_MS, null);
    return NextResponse.json({ connected: !!tokens });
  } catch {
    return NextResponse.json({ connected: false });
  }
}
