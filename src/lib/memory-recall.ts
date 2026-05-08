/**
 * Memory recall layer — feeds top-N memory items into the intent prompt
 * on every /api/engine/analyze call.
 *
 * Strategy (v1, deliberately simple):
 *   - Pull the user's recent memory rows (last 200 inserts), then dedupe
 *     by (kind, key) keeping the freshest version of each fact.
 *   - Diversify across `kind` so a flood of one bucket (say, 30
 *     references to "the gucci shoes") doesn't crowd out preferences,
 *     relationships, contexts, etc.
 *   - Cap at `limit` (default 10) and format as
 *     "[kind:key] value" strings ready to drop into the prompt.
 *
 * v2 will switch to pgvector similarity against the current transcript
 * once we see what kinds of memory actually accumulate. Keeping v1
 * semantic-free and recency-biased keeps the wire-up landable today.
 */

import { supabaseAdmin } from "@/lib/supabase-admin";

interface MemoryRow {
  kind: string | null;
  key: string | null;
  value: string | null;
  created_at: string | null;
}

const RECENT_FETCH_LIMIT = 200;

export async function recallRelevantMemory(
  userId: string,
  _transcript: string,
  limit = 10
): Promise<string[]> {
  if (!userId) return [];

  let rows: MemoryRow[] = [];
  try {
    const { data, error } = await supabaseAdmin
      .from("anticipy_memory")
      .select("kind, key, value, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(RECENT_FETCH_LIMIT);
    if (error) {
      console.warn("[memory-recall] fetch failed:", error.message);
      return [];
    }
    rows = (data ?? []) as MemoryRow[];
  } catch (err) {
    console.warn(
      "[memory-recall] fetch threw; returning []:",
      err instanceof Error ? err.message : err
    );
    return [];
  }

  if (rows.length === 0) return [];

  // Dedupe by (kind, key) keeping the freshest row (rows are already sorted desc).
  const seen = new Set<string>();
  const deduped: MemoryRow[] = [];
  for (const r of rows) {
    const k = `${(r.kind || "").toLowerCase()}::${(r.key || "").toLowerCase()}`;
    if (!k.trim() || seen.has(k)) continue;
    seen.add(k);
    deduped.push(r);
  }

  // Diversify across kinds: round-robin across distinct kinds so one
  // category doesn't crowd out the others. Keeps the prompt useful even
  // when the user has 100 references to "the gucci shoes".
  const byKind: Record<string, MemoryRow[]> = {};
  const kindOrder: string[] = [];
  for (const r of deduped) {
    const kind = (r.kind || "other").toLowerCase();
    if (!byKind[kind]) {
      byKind[kind] = [];
      kindOrder.push(kind);
    }
    byKind[kind].push(r);
  }

  const result: MemoryRow[] = [];
  let added = true;
  while (added && result.length < limit) {
    added = false;
    for (const kind of kindOrder) {
      if (result.length >= limit) break;
      const list = byKind[kind];
      const next = list.shift();
      if (next) {
        result.push(next);
        added = true;
      }
    }
  }

  return result.map((r) => {
    const kind = (r.kind || "other").toLowerCase();
    const key = (r.key || "").toLowerCase();
    const value = (r.value || "").trim();
    return `[${kind}:${key}] ${value}`;
  });
}
