"use client";

import { createClient } from "@supabase/supabase-js";
import { getSupabasePublicConfig } from "./config";

let browserClient = null;

export function createBrowserSupabaseClient() {
  const config = getSupabasePublicConfig();
  if (!config.configured) return null;
  if (!browserClient) {
    browserClient = createClient(config.url, config.key, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storageKey: "anticipy.auth.next",
      },
    });
  }
  return browserClient;
}
