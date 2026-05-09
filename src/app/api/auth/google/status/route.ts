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
export async function GET(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user?.email) {
    return NextResponse.json({ connected: false });
  }
  try {
    const tokens = await getStoredTokens(user.email);
    return NextResponse.json({ connected: !!tokens });
  } catch {
    return NextResponse.json({ connected: false });
  }
}
