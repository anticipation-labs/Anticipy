-- Sessions get stuck in 'recording' or 'processing' when a tab is
-- closed mid-recording or the lambda processing them dies. They never
-- expire on their own and accumulate forever — at the time of writing
-- there were 39 'recording' and 2 'processing' rows, 20 of them older
-- than 7 days. Stale sessions have second-order pollution: the
-- inflight-locks pattern reaps locks but the session row stays open,
-- and intent dedup never sees the session as terminal so its intents
-- are eligible to recur.
--
-- One-shot cleanup: flip everything older than 24h from
-- 'recording'/'processing' to 'ended' with ended_at set so the
-- training corpus and dedup paths see them as closed.
--
-- Going forward, /api/engine/analyze does the same scoped reap on
-- every call (per-user, never touches the in-flight session). So
-- stale sessions never re-accumulate. This file documents the
-- one-shot for the migration history.
UPDATE public.anticipy_sessions
SET status = 'ended',
    ended_at = COALESCE(ended_at, NOW())
WHERE status IN ('recording', 'processing')
  AND started_at < NOW() - INTERVAL '24 hours';
