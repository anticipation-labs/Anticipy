/**
 * Embedding client for the agent-team RAG corpus.
 *
 * Primary backend: **Gemini text-embedding-004** via the existing
 *   GOOGLE_API_KEY. 768-dim native (matches engine_trajectories column),
 *   free up to 1500 requests/day, no separate billing setup.
 * Fallback backend: **Voyage-3-lite** via VOYAGE_API_KEY (when funded).
 *   $0.02/1M tokens, 512-dim (we pad to 768 for column compat).
 *
 * The exported `embedText`/`embedQuery` API is unchanged — callers don't
 * know which backend served the call. `voyageAvailable()` retains its
 * historical name for back-compat but now answers "embedding-available"
 * (true if EITHER GOOGLE_API_KEY or VOYAGE_API_KEY is set).
 *
 * Why this design: production smoke surfaced that the user's Voyage
 * account had $0 balance — Voyage doesn't auto-grant a free trial. The
 * agent's RAG path was blocked on a single-provider dependency. Adding
 * Gemini as primary means the path works on the existing Google quota
 * with zero setup, and Voyage upgrades the quality + cost when funded.
 */

const VOYAGE_URL = "https://api.voyageai.com/v1/embeddings";
const VOYAGE_MODEL = "voyage-3-lite";
const GEMINI_EMBED_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent";

export function voyageAvailable(): boolean {
  // Either backend works. Name preserved for back-compat with existing
  // callers in /api/agent/plan and /api/engine/trajectory.
  return Boolean(process.env.GOOGLE_API_KEY) || Boolean(process.env.VOYAGE_API_KEY);
}

export interface VoyageEmbeddingResult {
  vector: number[];
  usage: { total_tokens?: number };
}

/** Internal: call Gemini text-embedding-004. 768-dim. Free up to 1500/day. */
async function _embedGemini(
  text: string,
  taskType: "RETRIEVAL_DOCUMENT" | "RETRIEVAL_QUERY"
): Promise<VoyageEmbeddingResult> {
  const key = process.env.GOOGLE_API_KEY;
  if (!key) throw new Error("GOOGLE_API_KEY missing");
  const resp = await fetch(`${GEMINI_EMBED_URL}?key=${key}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "models/text-embedding-004",
      content: { parts: [{ text: text.substring(0, 8000) }] },
      taskType,
    }),
  });
  if (!resp.ok) {
    const err = await resp.text().catch(() => String(resp.status));
    throw new Error(`Gemini-embed ${resp.status}: ${err.substring(0, 240)}`);
  }
  const data = await resp.json();
  const vec = data?.embedding?.values;
  if (!Array.isArray(vec) || vec.length === 0) {
    throw new Error("Gemini-embed returned empty");
  }
  return { vector: vec as number[], usage: { total_tokens: 0 } };
}

/** Internal: call Voyage AI. 512-dim. */
async function _embedVoyage(
  text: string,
  inputType: "document" | "query"
): Promise<VoyageEmbeddingResult> {
  const key = process.env.VOYAGE_API_KEY;
  if (!key) throw new Error("VOYAGE_API_KEY missing");
  const resp = await fetch(VOYAGE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: VOYAGE_MODEL,
      input: [text.substring(0, 8000)],
      input_type: inputType,
    }),
  });
  if (!resp.ok) {
    const err = await resp.text().catch(() => String(resp.status));
    throw new Error(`Voyage ${resp.status}: ${err.substring(0, 240)}`);
  }
  const data = await resp.json();
  const vec = data?.data?.[0]?.embedding;
  if (!Array.isArray(vec) || vec.length === 0) {
    throw new Error("Voyage returned empty embedding");
  }
  return {
    vector: vec as number[],
    usage: { total_tokens: data?.usage?.total_tokens ?? 0 },
  };
}

/** Embed a single document. Tries Gemini first (free, 768-dim, native fit
 * for the column); falls back to Voyage if Gemini errors AND Voyage is
 * configured. Throws only if both backends fail.
 */
export async function embedText(text: string): Promise<VoyageEmbeddingResult> {
  if (!text || !text.trim()) throw new Error("embedText: empty input");
  const errors: string[] = [];
  if (process.env.GOOGLE_API_KEY) {
    try {
      return await _embedGemini(text, "RETRIEVAL_DOCUMENT");
    } catch (e: any) {
      errors.push(`gemini: ${e?.message || e}`);
    }
  }
  if (process.env.VOYAGE_API_KEY) {
    try {
      return await _embedVoyage(text, "document");
    } catch (e: any) {
      errors.push(`voyage: ${e?.message || e}`);
    }
  }
  throw new Error(`Both embedding backends failed: ${errors.join(" | ")}`);
}

/** Same fallover, query side (asymmetric embedding gives a small retrieval lift). */
export async function embedQuery(text: string): Promise<VoyageEmbeddingResult> {
  if (!text || !text.trim()) throw new Error("embedQuery: empty input");
  const errors: string[] = [];
  if (process.env.GOOGLE_API_KEY) {
    try {
      return await _embedGemini(text, "RETRIEVAL_QUERY");
    } catch (e: any) {
      errors.push(`gemini: ${e?.message || e}`);
    }
  }
  if (process.env.VOYAGE_API_KEY) {
    try {
      return await _embedVoyage(text, "query");
    } catch (e: any) {
      errors.push(`voyage: ${e?.message || e}`);
    }
  }
  throw new Error(`Both embedding backends failed: ${errors.join(" | ")}`);
}

/** Pad/truncate a vector to a fixed dimension (used to fit a 512-d voyage
 * vector into the existing vector(768) column without re-migrating). */
export function padVectorTo(vec: number[], targetDim: number): number[] {
  if (vec.length === targetDim) return vec;
  if (vec.length > targetDim) return vec.slice(0, targetDim);
  return [...vec, ...Array(targetDim - vec.length).fill(0)];
}

/** Format as Postgres vector literal: "[0.1,0.2,...]" (no spaces, square brackets) */
export function vectorToPg(vec: number[]): string {
  return `[${vec.map(v => v.toFixed(6)).join(",")}]`;
}
