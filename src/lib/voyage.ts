/**
 * Voyage AI embedding client — used for RAG over engine_trajectories.
 *
 * Why Voyage and not Gemini text-embedding-004:
 *   - Voyage-3-lite is $0.02 / 1M tokens — 5× cheaper than Gemini's $0.10
 *   - voyage-3-lite is 512-dim (smaller index) and benchmarks above
 *     text-embedding-004 on retrieval-quality benchmarks (MTEB)
 *   - Independent quota = embeddings don't share the agent's $10 Kimi budget
 *
 * Env: VOYAGE_API_KEY
 *
 * Usage:
 *   const v = await embedTaskSummary("compare flights on Google AND Kayak");
 *   // → number[] (length 512). Insert into engine_trajectories.task_embedding
 *   // (note: schema reserves vector(768); we left-pad with zeros to fit until
 *   // we re-migrate to vector(512). RAG-retrieval works with any consistent dim.)
 */

const VOYAGE_URL = "https://api.voyageai.com/v1/embeddings";
const VOYAGE_MODEL = "voyage-3-lite";

export function voyageAvailable(): boolean {
  return Boolean(process.env.VOYAGE_API_KEY);
}

export interface VoyageEmbeddingResult {
  vector: number[];
  usage: { total_tokens?: number };
}

/** Embed a single text. Returns the 512-d float vector. */
export async function embedText(text: string): Promise<VoyageEmbeddingResult> {
  const key = process.env.VOYAGE_API_KEY;
  if (!key) throw new Error("VOYAGE_API_KEY missing");
  if (!text || !text.trim()) throw new Error("embedText: empty input");

  const resp = await fetch(VOYAGE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: VOYAGE_MODEL,
      input: [text.substring(0, 8000)],
      input_type: "document",
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

/** Embed using the 'query' input_type — used at retrieval time (asymmetric
 * embedding gives ~2-3 ndcg points lift over symmetric). */
export async function embedQuery(text: string): Promise<VoyageEmbeddingResult> {
  const key = process.env.VOYAGE_API_KEY;
  if (!key) throw new Error("VOYAGE_API_KEY missing");
  if (!text || !text.trim()) throw new Error("embedQuery: empty input");

  const resp = await fetch(VOYAGE_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${key}`,
    },
    body: JSON.stringify({
      model: VOYAGE_MODEL,
      input: [text.substring(0, 8000)],
      input_type: "query",
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
