-- Ralph loop state persistence schema.
-- Per planning/00-handoff/RALPH_LOOP.md, replaces unbounded memory.jsonl (bug-hunter B477).
-- DB lives at ~/.anticipy/v7/ralph.db with WAL mode (enabled at runtime by store.py).

CREATE TABLE IF NOT EXISTS goals (
  goal_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  goal_text TEXT NOT NULL,
  origin TEXT,                    -- 'asr' | 'inject' | 'proactive' | 'mp3'
  status TEXT NOT NULL,           -- 'pending' | 'running' | 'wait_user' | 'wait_retry' | 'done' | 'failed' | 'cancelled'
  cost_usd REAL NOT NULL DEFAULT 0,
  cost_cap_usd REAL NOT NULL DEFAULT 0.05,
  consecutive_failures INT NOT NULL DEFAULT 0,
  next_attempt_at INTEGER,        -- unix ts; NULL if not scheduled
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  surface TEXT,                   -- 'web' | 'sms_out' | 'voice_out' | 'search' | 'memory'
  channel_payload TEXT,           -- JSON: SMS body, email html, etc.
  final_artifact_path TEXT        -- screenshot / receipt id when done
);

CREATE TABLE IF NOT EXISTS goal_steps (
  step_id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(goal_id),
  step_index INT NOT NULL,
  action TEXT NOT NULL,           -- 'navigate' | 'click' | 'type' | 'extract' | 'screenshot' | 'send_sms' | etc.
  action_payload TEXT,            -- JSON
  pre_state_hash TEXT,            -- normalized DOM + URL hash before action
  post_state_hash TEXT,           -- after action
  result TEXT,                    -- 'pass' | 'fail'
  failure_class TEXT,             -- one of the failure classes in RALPH_LOOP.md
  failure_detail TEXT,
  retry_count INT NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  duration_ms INT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_goals_next_attempt ON goals(next_attempt_at) WHERE next_attempt_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
CREATE INDEX IF NOT EXISTS idx_goal_steps_goal ON goal_steps(goal_id, step_index);
