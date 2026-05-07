/**
 * Shared bearer-token auth helper for engine API routes.
 *
 * Validates a Supabase auth token from the `Authorization: Bearer <token>`
 * header and returns the resolved user. Returns `null` (or a 401 NextResponse
 * via `requireUser`) when the token is missing/invalid.
 */
import { NextResponse } from "next/server";
import { createClient, type User } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";

function authClient() {
  // Use the service role key for token validation. supabase.auth.getUser
  // accepts a JWT and round-trips to GoTrue regardless of the key used here.
  return createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
}

export interface AuthedUser {
  id: string;
  email: string | undefined;
  raw: User;
}

/**
 * Returns the authed user or null. Does not write a response.
 */
export async function getAuthedUser(req: Request): Promise<AuthedUser | null> {
  const header = req.headers.get("authorization") || req.headers.get("Authorization");
  if (!header || !header.toLowerCase().startsWith("bearer ")) return null;
  const token = header.slice(7).trim();
  if (!token) return null;

  const supabase = authClient();
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data?.user) return null;

  return { id: data.user.id, email: data.user.email, raw: data.user };
}

/**
 * Resolves the authed user or returns a 401 NextResponse.
 * Usage:
 *   const auth = await requireUser(req);
 *   if (auth instanceof NextResponse) return auth;
 *   // auth.id, auth.email available
 */
export async function requireUser(
  req: Request
): Promise<AuthedUser | NextResponse> {
  const user = await getAuthedUser(req);
  if (!user) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 401 }
    );
  }
  return user;
}
