-- 1) Close direct-Supabase-REST anon access to CRM tables.
--
-- The /api/crm/* routes use crmDb() which calls createClient with
-- SUPABASE_SERVICE_ROLE_KEY (bypasses RLS) AFTER passing the
-- requireCrmGate / requireCrmAdmin cookie check. That layer is fine.
--
-- The hole was that Supabase REST is reachable directly from anywhere
-- on the internet using the public NEXT_PUBLIC_SUPABASE_ANON_KEY
-- (which ships in the browser bundle by design). Without RLS on the
-- crm_* tables, anyone could:
--
--   curl 'https://ogbxpqkmsdrcuilafycn.supabase.co/rest/v1/crm_expenses?select=*' \
--        -H "apikey: <NEXT_PUBLIC_SUPABASE_ANON_KEY>"
--
-- and read every vendor, expense, contact, file, decision, voice memo,
-- and todo. The gate cookie wouldn't help — they're going around it.
--
-- Fix: enable RLS on every crm_* table with NO policies. Service-role
-- already bypasses RLS, so the API routes keep working unchanged.
-- anon and authenticated reads/writes are denied at the database
-- level, not just at the cookie layer.
--
-- Verified via grep that no client-side code reads crm_* directly:
-- src/app/crm/layout.tsx is server-rendered and uses crmDb().

ALTER TABLE public.crm_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_vendors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_todos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_todo_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_file_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_voice_memos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crm_agent_events ENABLE ROW LEVEL SECURITY;

-- Force RLS so the table owner can't accidentally bypass it via
-- a logged-in psql session. service_role still works because it
-- has BYPASSRLS at the role level.
ALTER TABLE public.crm_users FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_contacts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_vendors FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_expenses FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_todos FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_todo_comments FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_files FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_file_comments FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_voice_memos FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_decisions FORCE ROW LEVEL SECURITY;
ALTER TABLE public.crm_agent_events FORCE ROW LEVEL SECURITY;


-- 2) Add the missing unique constraint on anticipy_memory so the
--    upsert path used by /api/engine/analyze actually deduplicates.
--
-- src/app/api/engine/analyze/route.ts:579 calls
--   .upsert(rows, { onConflict: "user_id,kind,key", ignoreDuplicates: true })
-- which requires a unique index on those three columns. Without it,
-- Postgres rejects the upsert with "no unique or exclusion constraint
-- matching the ON CONFLICT specification" — the route swallows the
-- error and the dedup never happens. Result: a long recording writes
-- the same fact 30+ times, which we observed as bloat in production
-- before this index existed.
--
-- The route uses lower(key) at the index level so casing variants
-- ("Mom's birthday" vs "mom's birthday") collapse to a single row
-- instead of two near-duplicates.

CREATE UNIQUE INDEX IF NOT EXISTS anticipy_memory_user_kind_key_uniq
ON public.anticipy_memory (user_id, kind, lower(key));

-- The existing route uses onConflict: "user_id,kind,key" which expects
-- a constraint matching those exact columns (not a lower(key) version).
-- Add a second unique index that matches the literal columns so both
-- the case-sensitive ON CONFLICT and the case-insensitive merge work.
-- Postgres uses whichever index satisfies the conflict spec.
CREATE UNIQUE INDEX IF NOT EXISTS anticipy_memory_user_kind_keytext_uniq
ON public.anticipy_memory (user_id, kind, key);
