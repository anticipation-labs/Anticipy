/**
 * Supabase-backed HandoffStore for the US-008 deep-link flow.
 * Service-role only; the table has RLS on and no public policies.
 */
import type { SupabaseClient } from "@supabase/supabase-js";
import type { HandoffRow, HandoffStore } from "./handoff-token";

export function createSupabaseHandoffStore(
  supabase: SupabaseClient
): HandoffStore {
  return {
    async insert(row) {
      const { error } = await supabase
        .from("handoff_tokens")
        .insert({
          id: row.id,
          user_id: row.user_id,
          access_token: row.access_token,
          refresh_token: row.refresh_token,
          expires_at: row.expires_at,
        });
      if (error) {
        throw new Error(`handoff_tokens insert failed: ${error.message}`);
      }
    },

    async findById(id) {
      const { data, error } = await supabase
        .from("handoff_tokens")
        .select(
          "id, user_id, access_token, refresh_token, expires_at, consumed_at"
        )
        .eq("id", id)
        .maybeSingle();
      if (error) {
        throw new Error(`handoff_tokens lookup failed: ${error.message}`);
      }
      if (!data) return null;
      return data as HandoffRow;
    },

    async markConsumed(id, consumed_at) {
      const { error } = await supabase
        .from("handoff_tokens")
        .update({ consumed_at })
        .eq("id", id);
      if (error) {
        throw new Error(`handoff_tokens consume failed: ${error.message}`);
      }
    },
  };
}
