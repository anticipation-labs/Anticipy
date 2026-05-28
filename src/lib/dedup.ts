/**
 * Server-side intent deduplication helpers.
 *
 * The 30-second auto-analyze tick re-processes the cumulative transcript
 * each time, so the LLM frequently re-emits the same intent with slightly
 * different wording. We use a small Jaccard-similarity check against intents
 * already stored in the same session (and against intents queued earlier in
 * the same request batch) to drop duplicates before they ever reach the DB
 * or trigger notifications.
 */

export interface ExistingIntent {
  action_type: string | null;
  summary_for_user: string | null;
  evidence_quote: string | null;
}

export interface IntentCandidate {
  action_type: string;
  summary_for_user: string;
  evidence_quote: string;
}

export const SUMMARY_OVERLAP_THRESHOLD = 0.8;
export const SAME_TYPE_EVIDENCE_THRESHOLD = 0.6;
export const SAME_TYPE_SUMMARY_THRESHOLD = 0.5;

/** Lowercase, drop short stop-tokens, dedupe — keeps the Jaccard signal. */
export function tokenize(text: string | null | undefined): string[] {
  const words = (text || "")
    .toLowerCase()
    .split(/\W+/)
    .filter((w) => w.length > 2);
  const seen: Record<string, boolean> = {};
  const out: string[] = [];
  for (const w of words) {
    if (seen[w]) continue;
    seen[w] = true;
    out.push(w);
  }
  return out;
}

/** Jaccard similarity over deduplicated, length-filtered tokens. */
export function jaccardSimilarity(a: string, b: string): number {
  const wordsA = tokenize(a);
  const wordsB = tokenize(b);
  if (wordsA.length === 0 || wordsB.length === 0) return 0;
  const setB: Record<string, boolean> = {};
  for (const w of wordsB) setB[w] = true;
  let intersection = 0;
  for (const w of wordsA) if (setB[w]) intersection += 1;
  const union = wordsA.length + wordsB.length - intersection;
  return union === 0 ? 0 : intersection / union;
}

/**
 * Returns true if the candidate looks like an intent we've already captured.
 *
 * Rules (in order):
 *   1. Any existing intent with summary Jaccard ≥ 0.8 → duplicate (regardless of action_type)
 *   2. Same action_type AND evidence Jaccard ≥ 0.6 → duplicate
 *   3. Same action_type AND summary Jaccard ≥ 0.5 → duplicate
 */
export function isDuplicateOfExisting(
  candidate: IntentCandidate,
  existing: ExistingIntent[]
): boolean {
  for (const e of existing) {
    const summarySim = jaccardSimilarity(
      candidate.summary_for_user,
      e.summary_for_user || ""
    );
    if (summarySim >= SUMMARY_OVERLAP_THRESHOLD) return true;

    const sameType = e.action_type === candidate.action_type;
    if (sameType) {
      const evidenceSim = jaccardSimilarity(
        candidate.evidence_quote,
        e.evidence_quote || ""
      );
      if (evidenceSim >= SAME_TYPE_EVIDENCE_THRESHOLD) return true;
      if (summarySim >= SAME_TYPE_SUMMARY_THRESHOLD) return true;
    }
  }
  return false;
}

/**
 * Action types that represent conversational back-and-forth, not real future
 * tasks. Dropped before insertion regardless of LLM confidence.
 */
export const IGNORED_ACTION_TYPES: ReadonlySet<string> = new Set([
  "confirm_item_possession",
  "clarify_status",
  "email_subject_instruction",
  "email_instruction",
  "check_email_flagging",
  "send_email_instruction",
  "confirm_status",
  "answer_question",
  "acknowledge",
  "small_talk",
  "respond_to_message",
  "reply_to_question",
]);

export const CONFIDENCE_THRESHOLD = 0.65;

export interface RawIntent {
  action_type?: unknown;
  confidence?: unknown;
  importance?: unknown;
  summary_for_user?: unknown;
  evidence_quote?: unknown;
  parameters?: unknown;
}

/**
 * Apply confidence threshold + ignored-type filter.
 * Returns intents that passed all gates, with `action_type` lowercased
 * for downstream comparison stability.
 *
 * Defensive against non-array input, non-object entries, and non-finite
 * confidence values (NaN, Infinity) — the upstream LLM has produced all
 * three at various points.
 */
export function filterValidIntents(intents: unknown): IntentCandidate[] {
  if (!Array.isArray(intents)) return [];
  const out: IntentCandidate[] = [];
  for (const entry of intents) {
    if (entry === null || typeof entry !== "object") continue;
    const i = entry as RawIntent;
    if (typeof i.confidence !== "number" || !Number.isFinite(i.confidence)) continue;
    if (i.confidence < CONFIDENCE_THRESHOLD) continue;
    const actionType = String(i.action_type ?? "").toLowerCase().trim();
    if (!actionType) continue;
    if (IGNORED_ACTION_TYPES.has(actionType)) continue;
    const summary = String(i.summary_for_user ?? "").trim();
    if (!summary) continue;
    out.push({
      action_type: actionType,
      summary_for_user: summary,
      evidence_quote: String(i.evidence_quote ?? "").trim(),
    });
  }
  return out;
}
