-- Episode-level RAG retrieval — vector similarity over the user's past
-- intent EPISODES so a fresh dictation gets the closest past
-- transcript+decision injected into the prompt as additional context.
--
-- Architecture sits next to the existing layers:
--
--   anticipy_memory       → per-fact recency-biased recall (memory-recall.ts)
--   anticipy_preferences  → accept/reject/edit signal log (preference-recall.ts)
--   anticipy_user_profile → distilled style snapshot (meta-monitor.ts)
--   anticipy_intents      ← THIS migration: pgvector embeddings on terminal
--                            intents, queried by cosine similarity from the
--                            current transcript via episode-recall.ts.
--
-- We add the column to anticipy_intents itself (rather than a new table) so:
--   1. terminal-status updates and embedding writes happen in the same row
--   2. RLS / service-role rules already in place apply without duplication
--   3. the proactive_training_corpus view can opt into episode-similarity
--      filtering later without a join

-- pgvector ships with Supabase but is not installed by default. Enable it
-- before declaring the column type. The IF NOT EXISTS guard keeps this
-- migration idempotent even though Supabase migrations run once.
CREATE EXTENSION IF NOT EXISTS vector;

-- 768-dim matches Gemini text-embedding-004 and gemini-embedding-001 (free
-- tier). If we later switch to OpenAI text-embedding-3-small (1536) or
-- a Matryoshka-truncated 256/512-d, that's a separate migration — keeping
-- the dimension explicit lets pgvector reject mismatched writes.
ALTER TABLE public.anticipy_intents
  ADD COLUMN IF NOT EXISTS embedding vector(768);

COMMENT ON COLUMN public.anticipy_intents.embedding IS
  'Gemini text-embedding-004 vector (768d) over (summary_for_user || evidence_quote || action_type). Written when an intent transitions to a terminal status (executed/rejected/auto_proceeded/confirmed/failed). NULL until then. Read by recallSimilarEpisodes() in src/lib/episode-recall.ts.';

-- Cosine-similarity index. Strategy: HNSW.
--   - HNSW gives faster + more accurate ANN at small-to-medium scale (we
--     expect O(thousands) of intents per user, never millions).
--   - IVFFLAT requires a pre-trained centroid step that re-trains poorly
--     on incremental writes — bad fit for an always-on append workload.
--   - The build is more expensive but is amortized: we only re-index
--     when the table fills up, not per insert.
-- Parameters m=16, ef_construction=64 are pgvector defaults — tuned later
-- if recall@k drops below acceptable.
--
-- WHERE embedding IS NOT NULL keeps the index small while most rows are
-- still un-embedded (we don't bulk-backfill historical 255 rows here —
-- that's a separate manual job).
CREATE INDEX IF NOT EXISTS anticipy_intents_embedding_hnsw_idx
  ON public.anticipy_intents
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64)
  WHERE embedding IS NOT NULL;

-- A user_id-prefixed btree wouldn't help vector search (HNSW handles its
-- own scan), but recallSimilarEpisodes joins anticipy_sessions to filter
-- by user_id. That join already has an index on sessions.user_id from
-- earlier migrations; nothing extra needed here.

-- RLS posture: anticipy_intents already has service-role-only writes via
-- the route-level supabaseAdmin client. The embedding column is private
-- by the same chain — no anon/authenticated SELECT exposes it. We do NOT
-- add an explicit policy here; doing so would shadow the existing default
-- and risk widening the surface. The column is service-role-only because
-- the table is service-role-only, full stop.
