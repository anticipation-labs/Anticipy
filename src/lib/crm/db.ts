/**
 * Server-only Supabase client for CRM routes.
 *
 * Uses the service role key. Every CRM API route is gated by the
 * password cookie (verifyCrmGate) before invoking this client.
 * RLS is intentionally not applied to crm_* tables: there is one
 * trusted internal surface, and the gate is the only auth boundary.
 */
import { createClient, SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";

let cached: SupabaseClient | null = null;

export function crmDb(): SupabaseClient {
  if (cached) return cached;
  if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error(
      "Supabase env not configured: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required"
    );
  }
  cached = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return cached;
}

export const CRM_FILES_BUCKET = "crm-files";

export function publicFileUrl(path: string): string {
  const base = SUPABASE_URL.replace(/\/$/, "");
  return `${base}/storage/v1/object/public/${CRM_FILES_BUCKET}/${path}`;
}
