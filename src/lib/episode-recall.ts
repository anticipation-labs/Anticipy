/**
 * Episode-level RAG retrieval — vector similarity over the user's past
 * intent EPISODES. When the wearer dictates something close to a prior
 * interaction, the closest past transcript+decision gets injected into
 * the prompt as additional context, sitting beside the existing
 * memory + preference + profile recall layers.
 *
 * Wire-up:
 *
 *   /api/engine/analyze          (read path)
 *      ↓
 *   recallSimilarEpisodes(userId, transcript, k=3)
 *      ↓
 *   formatted "EPISODE: ..." strings → intent prompt
 *
 *   /api/engine/confirm + /api/engine/auto-proceed   (write path)
 *      ↓
 *   embedAndStoreIntent(intentId)  — fire-and-forget after terminal status
 *      ↓
 *   anticipy_intents.embedding (vector(768))
 *
 * No bulk-backfill is performed — historical rows stay null. A separate
 * one-shot job (out of scope here) can replay them later when we want
 * the cold-start cohort.
 *
 * Fail-open everywhere: any error from the embedding API or the DB
 * collapses to "" / [] so analyze never gets blocked over a recall miss.
 */
import { embedText } from "@/lib/gemini";
import { supabaseAdmin } from "@/lib/supabase-admin";

const TERMINAL_STATUSES = [
  "executed",
  "rejected",
  "auto_proceeded",
  "confirmed",
  "failed",
] as const;

interface SimilarEpisodeRow {
  intent_id: string;
  action_type: string | null;
  summary_for_user: string | null;
  evidence_quote: string | null;
  status: string | null;
  signal_reasoning: string | null;
  // 1 - cosine_distance — higher = more similar. Returned for debug logs;
  // we deliberately do NOT threshold on it (per spec: let the LLM consume
  // the top-k regardless of distance). Useful in operator dashboards.
  similarity: number | null;
}

/**
 * Build the canonical text we embed for a given intent. Stays in sync
 * with what `embedAndStoreIntent` writes so the query side and the doc
 * side use the same surface form.
 *
 * Order matters for embedding quality: lead with the human-summary, then
 * evidence, then the snake_case action type as a faint signal. Trailing
 * whitespace is fine — the API tokenizer collapses it.
 */
function buildEpisodeEmbeddingText(intent: {
  summary_for_user?: string | null;
  evidence_quote?: string | null;
  action_type?: string | null;
}): string {
  const parts = [
    String(intent.summary_for_user ?? "").trim(),
    String(intent.evidence_quote ?? "").trim(),
    String(intent.action_type ?? "").trim(),
  ].filter(Boolean);
  return parts.join(" ");
}

/**
 * Embed a terminal-status intent and persist the vector to
 * anticipy_intents.embedding. Designed to be called fire-and-forget from
 * /api/engine/confirm and /api/engine/auto-proceed AFTER the status flip.
 *
 * Skips silently when:
 *   - intentId is empty
 *   - the row's status is NOT terminal (defensive — caller should gate)
 *   - the row already has an embedding (idempotent)
 *   - embedText returns null (key missing / API failure)
 *   - the surface text is empty
 */
export async function embedAndStoreIntent(intentId: string): Promise<void> {
  if (!intentId) return;
  try {
    const { data: row, error } = await supabaseAdmin
      .from("anticipy_intents")
      .select("id, action_type, summary_for_user, evidence_quote, status, embedding")
      .eq("id", intentId)
      .maybeSingle();
    if (error || !row) {
      if (error) {
        console.warn("[episode-recall] fetch failed:", error.message);
      }
      return;
    }
    const status = String(row.status ?? "").toLowerCase();
    if (!TERMINAL_STATUSES.includes(status as (typeof TERMINAL_STATUSES)[number])) {
      // Caller raced the status update or we got handed a non-terminal id.
      // Skip — embeddings only get written for closed-out episodes.
      return;
    }
    if (row.embedding) {
      // Already embedded by a prior signal (e.g., confirm followed by an
      // auto_proceed timer that lost the race). Don't burn a second call.
      return;
    }
    const text = buildEpisodeEmbeddingText(row);
    if (!text) return;
    const vec = await embedText(text, { taskType: "RETRIEVAL_DOCUMENT" });
    if (!vec || vec.length === 0) return;

    // pgvector accepts the JSON-array literal cast to vector. The
    // Supabase JS client serializes `number[]` as JSON, which the column's
    // implicit cast resolves correctly.
    const { error: updErr } = await supabaseAdmin
      .from("anticipy_intents")
      .update({ embedding: vec as unknown as string })
      .eq("id", intentId)
      .is("embedding", null); // idempotent guard against concurrent writers
    if (updErr) {
      console.warn(
        "[episode-recall] embedding update failed:",
        updErr.message
      );
    }
  } catch (err) {
    console.warn(
      "[episode-recall] embedAndStoreIntent threw:",
      err instanceof Error ? err.message : err
    );
  }
}

/**
 * Recall the top-k similar past intents for the current transcript.
 * Returns an array of formatted strings ready to drop into the intent
 * prompt. Always fail-open: returns [] on any error so /api/engine/analyze
 * never blocks on a recall miss.
 *
 * Per spec: NO hardcoded similarity thresholds — the LLM consumes the
 * top-k regardless of cosine distance. Even a "weak" match informs the
 * second-pass extractor.
 */
export async function recallSimilarEpisodes(
  userId: string,
  transcript: string,
  k = 3
): Promise<string[]> {
  if (!userId) return [];
  const text = (transcript || "").trim();
  if (!text) return [];

  // 1) Embed the query side. taskType=RETRIEVAL_QUERY is the asymmetric
  //    variant Google recommends when the corpus side used DOCUMENT.
  const qvec = await embedText(text, { taskType: "RETRIEVAL_QUERY" });
  if (!qvec || qvec.length === 0) return [];

  // 2) Run a server-side cosine-similarity search against this user's
  //    terminal intents. We use a parameterized RPC-style query via the
  //    raw .rpc fallback would be cleanest, but to avoid adding a new
  //    SQL function we issue a single SQL via .from with a manual cast
  //    using the postgrest .filter('embedding', 'is not', null) gate
  //    plus a raw .order on the cosine-distance operator.
  //
  //    PostgREST exposes pgvector's `<=>` (cosine distance) ordering via
  //    .rpc on a stored function only — we can't invoke the operator
  //    inline through the JS client. The reliable cross-version path is
  //    a bound SQL via supabase's REST `rpc` route OR a raw call through
  //    pg's HTTP endpoint. We chose to add the SQL function in the
  //    migration to keep this file lean — but to avoid a second migration
  //    on the same day, we issue the query through a `.rpc` to a function
  //    we expect to exist OR fall back to a manual query path.
  //
  //    Simpler approach used here: issue a regular .from query that
  //    fetches a small candidate set ordered by recency, then sort by
  //    cosine similarity in JS. With LIMIT_CANDIDATES=200 the in-memory
  //    sort is O(200) and the network cost is negligible. This is good
  //    enough for the user-scale we're at and avoids any DB function
  //    dependency. When users hit ~10k+ intents we'll swap in a
  //    server-side `<=>` order via a SECURITY DEFINER SQL function in a
  //    follow-up migration.
  const LIMIT_CANDIDATES = 200;
  let rows: Array<{
    id: string;
    action_type: string | null;
    summary_for_user: string | null;
    evidence_quote: string | null;
    status: string | null;
    embedding: number[] | string | null;
    session_id: string | null;
    created_at: string | null;
  }> = [];

  try {
    // Step A: find sessions belonging to this user (cap at 500 most recent
    // sessions — anyone with more than that has way more episodes than we
    // need to consider).
    const { data: sessions } = await supabaseAdmin
      .from("anticipy_sessions")
      .select("id")
      .eq("user_id", userId)
      .order("started_at", { ascending: false })
      .limit(500);
    const sessionIds = (sessions ?? []).map((s) => s.id).filter(Boolean);
    if (sessionIds.length === 0) return [];

    // Step B: pull the most recent terminal-status intents in those
    // sessions that have an embedding. Recency bias is fine — a 6-month-
    // old episode is unlikely to be more relevant than a recent one even
    // if cosine-similar.
    const { data, error } = await supabaseAdmin
      .from("anticipy_intents")
      .select(
        "id, action_type, summary_for_user, evidence_quote, status, embedding, session_id, created_at"
      )
      .in("session_id", sessionIds)
      .in("status", [...TERMINAL_STATUSES])
      .not("embedding", "is", null)
      .order("created_at", { ascending: false })
      .limit(LIMIT_CANDIDATES);
    if (error) {
      console.warn("[episode-recall] candidate fetch failed:", error.message);
      return [];
    }
    rows = data ?? [];
  } catch (err) {
    console.warn(
      "[episode-recall] candidate fetch threw; returning []:",
      err instanceof Error ? err.message : err
    );
    return [];
  }

  if (rows.length === 0) return [];

  // 3) Score each candidate by cosine similarity to the query vector.
  //    pgvector returns the column as either a string ("[0.1,0.2,...]")
  //    or an array depending on the driver path; handle both.
  const qNorm = vectorMagnitude(qvec);
  if (qNorm === 0) return [];

  const scored: Array<SimilarEpisodeRow & { intentRowId: string }> = [];
  for (const r of rows) {
    const v = parseEmbedding(r.embedding);
    if (!v || v.length !== qvec.length) continue;
    const sim = cosineSimilarity(qvec, v, qNorm);
    scored.push({
      intentRowId: r.id,
      intent_id: r.id,
      action_type: r.action_type,
      summary_for_user: r.summary_for_user,
      evidence_quote: r.evidence_quote,
      status: r.status,
      signal_reasoning: null, // filled in below
      similarity: sim,
    });
  }
  scored.sort((a, b) => (b.similarity ?? -1) - (a.similarity ?? -1));
  const top = scored.slice(0, Math.max(1, k));
  if (top.length === 0) return [];

  // 4) Hydrate signal_reasoning from anticipy_preferences. We look up the
  //    most recent preference row whose (action_type, summary head) match
  //    the intent — the same pairing rule used by proactive_training_corpus.
  //    Failures collapse silently to an empty reasoning string.
  try {
    const actionTypes = Array.from(
      new Set(
        top
          .map((t) => (t.action_type ?? "").toString().trim())
          .filter(Boolean)
      )
    );
    if (actionTypes.length > 0) {
      const { data: prefRows } = await supabaseAdmin
        .from("anticipy_preferences")
        .select("action_type, intent_summary, reasoning, created_at")
        .eq("user_id", userId)
        .in("action_type", actionTypes)
        .order("created_at", { ascending: false })
        .limit(200);
      const prefList = prefRows ?? [];
      for (const t of top) {
        const ta = (t.action_type ?? "").toString().trim();
        const tsHead = (t.summary_for_user ?? "").toString().toLowerCase().slice(0, 80);
        if (!ta || !tsHead) continue;
        const match = prefList.find((p) => {
          const pa = (p.action_type ?? "").toString().trim();
          const ph = (p.intent_summary ?? "").toString().toLowerCase().slice(0, 80);
          return pa === ta && ph === tsHead;
        });
        if (match && match.reasoning) {
          t.signal_reasoning = match.reasoning as string;
        }
      }
    }
  } catch (err) {
    console.warn(
      "[episode-recall] preference hydration failed (non-fatal):",
      err instanceof Error ? err.message : err
    );
  }

  // 5) Format. Use the evidence_quote when present (it carries the
  //    wearer's actual phrasing); fall back to summary_for_user. Cap each
  //    snippet so the prompt stays bounded.
  const SNIPPET_MAX = 200;
  return top.map((t) => {
    const snippetSrc =
      (t.evidence_quote ?? "").trim() || (t.summary_for_user ?? "").trim();
    const snippet = snippetSrc.replace(/\s+/g, " ").slice(0, SNIPPET_MAX);
    const action = (t.action_type ?? "unknown").trim() || "unknown";
    const outcome = (t.status ?? "unknown").trim() || "unknown";
    const reasoning = (t.signal_reasoning ?? "").trim();
    const reasoningPart = reasoning ? ` reasoning="${reasoning.slice(0, 240)}"` : "";
    return `EPISODE: "${snippet}" -> action=${action} outcome=${outcome}${reasoningPart}`;
  });
}

// ─── helpers ─────────────────────────────────────────────────────────

function parseEmbedding(raw: unknown): number[] | null {
  if (!raw) return null;
  if (Array.isArray(raw)) {
    return raw.every((n) => typeof n === "number") ? (raw as number[]) : null;
  }
  if (typeof raw === "string") {
    // pgvector serializes as "[0.1,0.2,...]"
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.every((n) => typeof n === "number")) {
        return parsed as number[];
      }
    } catch {
      return null;
    }
  }
  return null;
}

function vectorMagnitude(v: number[]): number {
  let s = 0;
  for (let i = 0; i < v.length; i += 1) s += v[i] * v[i];
  return Math.sqrt(s);
}

function cosineSimilarity(a: number[], b: number[], aNorm?: number): number {
  if (a.length !== b.length) return 0;
  let dot = 0;
  let bNorm = 0;
  for (let i = 0; i < a.length; i += 1) {
    dot += a[i] * b[i];
    bNorm += b[i] * b[i];
  }
  const an = aNorm ?? vectorMagnitude(a);
  const bn = Math.sqrt(bNorm);
  if (an === 0 || bn === 0) return 0;
  return dot / (an * bn);
}

// Exported only for unit tests / debugging surface — keeps the module's
// formatting rule pinned in one place.
export const __internal__ = {
  buildEpisodeEmbeddingText,
  cosineSimilarity,
  parseEmbedding,
};
