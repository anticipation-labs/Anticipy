/**
 * Typed contracts for the v-final-prototype 9-layer architecture.
 *
 * One source of truth shared by:
 *   - the proactive engine (publishes Intent on intent.detected.{user_id})
 *   - the middle layer (subscribes to Intent, publishes Task on task.dispatched.{user_id})
 *   - the executor (subscribes to Task, publishes Result on task.completed.{user_id})
 *   - the website's /engine page (subscribes to Result for status display)
 *
 * The Supabase tables live in `supabase/migrations/20260513_anticipy_v2_typed_contracts.sql`.
 * Table columns and the fields here MUST stay in lockstep — if you change
 * one, change both. Schema-of-record is the SQL migration.
 *
 * These types intentionally mirror the master prompt's contract block
 * VERBATIM (down to field names and enum values) so the architecture's
 * three sides can be developed and tested independently against typed
 * fake objects.
 */

// ─────────────────────────────────────────────────────────────────────────
// Intent — proactive engine publishes
// ─────────────────────────────────────────────────────────────────────────

export type HedgeFilterDecision = "COMMIT" | "STORE_AS_LATENT" | "REFUSE";

export type IntentSource = "pendant" | "mac_mic" | "typed";

export interface TranscriptSegment {
  speaker: "wearer" | "other";
  text: string;
  start_ts: number;
  end_ts: number;
}

export interface UtteranceWindow {
  transcript_segments: TranscriptSegment[];
  start_ts: string; // ISO-8601
  end_ts: string;   // ISO-8601
}

export interface IntentSlots {
  filled: Record<string, unknown>;
  needs_memory: string[];
  needs_inference: string[];
  ambiguous: string[];
}

export interface Intent {
  intent_id: string; // uuid
  user_id: string;
  utterance_window: UtteranceWindow;
  action_category: string | null;
  proposed_skill_hint: string | null;
  slots: IntentSlots;
  detection_confidence: number | null;
  hedge_filter_decision: HedgeFilterDecision;
  hedge_filter_reason: string | null;
  proactivity_score: number | null;
  source: IntentSource;
  /** ISO-8601 timestamp from Supabase `created_at`. */
  timestamp: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Task — middle layer publishes
// ─────────────────────────────────────────────────────────────────────────

export interface RecipeStep {
  action: string; // e.g. "click", "type", "navigate", "wait"
  target_ref: string | null;
  value: string | null;
  timeout_ms: number;
  postcondition: unknown | null; // free-form per skill
}

export interface PostconditionSpec {
  /** Path of the skill's symbolic verifier (e.g. "skills/book_resy/verify.py"). */
  verifier: string;
  /** Free-form parameters passed to the verifier. */
  spec: unknown;
}

export interface RollbackSpec {
  /** Path of the skill's compensate.py. */
  compensate: string;
  /** Free-form parameters passed to compensate. */
  spec: unknown;
}

export interface Task {
  task_id: string; // uuid
  intent_id: string; // uuid, FK to Intent
  user_id: string;
  skill_id: string | null;
  parameters: Record<string, unknown>;
  recipe_steps: RecipeStep[];
  global_postcondition: PostconditionSpec | null;
  rollback_spec: RollbackSpec | null;
  rehearsal_required: boolean;
  irreversible: boolean;
  aevoy_confirmation_required: boolean;
  /** ISO-8601 timestamp from Supabase `created_at`. */
  created_at: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Result — executor publishes
// ─────────────────────────────────────────────────────────────────────────

export type ResultStatus = "executed" | "failed" | "rolled_back" | "refused";

export type VerifierOutput = "CERTIFIED" | "NOT_CERTIFIED";

export interface ResultEvidence {
  /** URLs (or storage paths) to screenshots taken during execution. */
  screenshots: string[];
  /** Optional DOM snapshots at key inflection points. */
  dom_snapshots: string[];
  /** Parsed confirmation emails / order pages / etc. */
  parsed_confirmations: Array<Record<string, unknown>>;
}

export interface Result {
  task_id: string; // uuid, FK to Task
  status: ResultStatus;
  executed_at: string | null; // ISO-8601 or null if refused before execution
  evidence: ResultEvidence;
  verifier_output: VerifierOutput;
  steps_completed: number;
  steps_failed: number;
  total_cost_usd: number | null;
  total_latency_ms: number | null;
  aevoy_email_sent: boolean;
  aevoy_email_id: string | null;
}

// ─────────────────────────────────────────────────────────────────────────
// Realtime channel names (the only contract for pub/sub)
// ─────────────────────────────────────────────────────────────────────────

export const channelIntentDetected = (userId: string): string =>
  `intent.detected.${userId}`;

export const channelTaskDispatched = (userId: string): string =>
  `task.dispatched.${userId}`;

export const channelTaskCompleted = (userId: string): string =>
  `task.completed.${userId}`;

// ─────────────────────────────────────────────────────────────────────────
// Runtime validators — minimal hand-rolled (deps-free).
//
// Avoid pulling in zod or io-ts here because the proactive engine is
// Python (it constructs these from Python dicts and the wire format is
// what Supabase serializes). These validators are for the TypeScript
// consumers (middle layer pieces written in TS, /engine page subscribers)
// to fail loud on unexpected shapes.
// ─────────────────────────────────────────────────────────────────────────

export function isIntent(value: unknown): value is Intent {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.intent_id === "string" &&
    typeof v.user_id === "string" &&
    typeof v.utterance_window === "object" &&
    v.utterance_window !== null &&
    typeof v.hedge_filter_decision === "string" &&
    ["COMMIT", "STORE_AS_LATENT", "REFUSE"].includes(
      v.hedge_filter_decision as string
    ) &&
    typeof v.source === "string" &&
    ["pendant", "mac_mic", "typed"].includes(v.source as string) &&
    typeof v.timestamp === "string"
  );
}

export function isTask(value: unknown): value is Task {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.task_id === "string" &&
    typeof v.intent_id === "string" &&
    typeof v.user_id === "string" &&
    typeof v.parameters === "object" &&
    Array.isArray(v.recipe_steps) &&
    typeof v.rehearsal_required === "boolean" &&
    typeof v.irreversible === "boolean" &&
    typeof v.aevoy_confirmation_required === "boolean" &&
    typeof v.created_at === "string"
  );
}

export function isResult(value: unknown): value is Result {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.task_id === "string" &&
    typeof v.status === "string" &&
    ["executed", "failed", "rolled_back", "refused"].includes(
      v.status as string
    ) &&
    typeof v.verifier_output === "string" &&
    ["CERTIFIED", "NOT_CERTIFIED"].includes(v.verifier_output as string) &&
    typeof v.steps_completed === "number" &&
    typeof v.steps_failed === "number" &&
    typeof v.aevoy_email_sent === "boolean"
  );
}
