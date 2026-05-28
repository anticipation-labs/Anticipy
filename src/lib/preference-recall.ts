/**
 * Preference recall — feeds the wearer's prior accept/reject/edit/auto_proceed
 * signals into the intent extraction prompt so the LLM can pre-filter intents
 * that match patterns the wearer has already rejected (and avoid re-asking
 * about things they always confirm).
 *
 * Strategy is deliberately the same shape as memory-recall.ts:
 *   - Pull recent rows for this user (last RECENT_FETCH_LIMIT inserts).
 *   - Diversify across signal so a flood of "accept" rows doesn't crowd
 *     out the more important "reject" patterns (and vice versa).
 *   - Format as `[signal:action_type] reasoning` strings ready to drop into
 *     the prompt — same family as the memory recall format.
 *
 * Fail-open: any DB hiccup returns []. Caller never blocks the
 * /api/engine/analyze hot path on this output.
 */
import { supabaseAdmin } from "@/lib/supabase-admin";

interface PrefRow {
  signal: string | null;
  action_type: string | null;
  intent_summary: string | null;
  reasoning: string | null;
  created_at: string | null;
}

const RECENT_FETCH_LIMIT = 100;

export async function recallUserPreferences(
  userId: string,
  limit = 15
): Promise<string[]> {
  if (!userId) return [];

  let rows: PrefRow[] = [];
  try {
    const { data, error } = await supabaseAdmin
      .from("anticipy_preferences")
      .select("signal, action_type, intent_summary, reasoning, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(RECENT_FETCH_LIMIT);
    if (error) {
      console.warn("[preference-recall] fetch failed:", error.message);
      return [];
    }
    rows = (data ?? []) as PrefRow[];
  } catch (err) {
    console.warn(
      "[preference-recall] fetch threw; returning []:",
      err instanceof Error ? err.message : err
    );
    return [];
  }

  if (rows.length === 0) return [];

  // Round-robin across signal buckets so the prompt sees both rejects
  // (the most informative for filtering) and accepts (informative as
  // a hint, not for auto-confirm).
  const bySignal: Record<string, PrefRow[]> = {};
  // Order matters: rejects first so they make it into a small budget.
  const signalOrder = ["reject", "edit", "auto_proceed", "accept"];
  for (const r of rows) {
    const s = (r.signal || "").toLowerCase();
    if (!signalOrder.includes(s)) continue;
    if (!bySignal[s]) bySignal[s] = [];
    bySignal[s].push(r);
  }

  const result: PrefRow[] = [];
  let added = true;
  while (added && result.length < limit) {
    added = false;
    for (const s of signalOrder) {
      if (result.length >= limit) break;
      const list = bySignal[s];
      if (!list || list.length === 0) continue;
      const next = list.shift();
      if (next) {
        result.push(next);
        added = true;
      }
    }
  }

  return result.map((r) => {
    const signal = (r.signal || "signal").toLowerCase();
    const at = (r.action_type || "intent").toLowerCase();
    const reasoning = (r.reasoning || r.intent_summary || "").trim();
    return `[${signal}:${at}] ${reasoning}`;
  });
}
