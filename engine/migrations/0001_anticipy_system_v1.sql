-- Anticipy System V1 multi tenant spine, Supabase migration.
--
-- This is the production scale artifact. The local single user form
-- runs the same logical model on the SQLite spine behind the adapter
-- (engine/app/anticipy/spine.py). At scale this migration is applied to
-- the Supabase project so the database layer itself enforces per user
-- isolation: even a server side bug cannot cross tenants because every
-- table below has Row Level Security enabled and an explicit per user
-- policy keyed on auth.uid() in the SAME migration that creates it.
--
-- It uses a NEW schema (anticipy_sys_v1) and NEW tables. It does NOT
-- touch any existing table. It is applied to real Supabase only behind
-- the ANTICIPY_LIVE flag, never during the autonomous build run, the
-- same rule that gates real comms and real OAuth.
--
-- Per user OAuth tokens are never stored in plaintext or in
-- application code: only an opaque vault key and Supabase Vault secret
-- reference are stored, referenced indirectly.

create schema if not exists anticipy_sys_v1;

-- ---- user profile (the warm start that fixes cold start) ----------
create table anticipy_sys_v1.user_profile (
    user_id uuid primary key references auth.users (id) on delete cascade,
    name text,
    role_title text,
    what_they_do text,
    timezone text default 'UTC',
    working_hours text,
    people jsonb default '{}'::jsonb,
    critical_software jsonb default '{}'::jsonb,
    mandate text,
    do_not_touch jsonb default '[]'::jsonb,
    autonomy_level double precision default 0.92,
    days_since_onboard int default 0,
    trajectory_confidence double precision default 0.0,
    comms_prefs jsonb default '{}'::jsonb,
    quiet_hours text,
    voice_anchor text,
    created_at timestamptz default now()
);
alter table anticipy_sys_v1.user_profile enable row level security;
create policy user_profile_owner on anticipy_sys_v1.user_profile
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- per user connected accounts (opaque vault keys only) ---------
create table anticipy_sys_v1.connected_accounts (
    user_id uuid not null references auth.users (id) on delete cascade,
    account_name text not null,
    vault_key text not null,
    scope text not null,
    read_only_context boolean not null default true,
    created_at timestamptz default now(),
    primary key (user_id, account_name)
);
alter table anticipy_sys_v1.connected_accounts enable row level security;
create policy connected_accounts_owner on anticipy_sys_v1.connected_accounts
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- durable workflow journal (event sourced, per user) ----------
create table anticipy_sys_v1.durable_workflows (
    user_id uuid not null references auth.users (id) on delete cascade,
    workflow_id text not null,
    wf_type text not null,
    input_json jsonb not null,
    status text not null,
    result_json jsonb,
    await_key text,
    await_deadline double precision,
    created_ts double precision not null,
    updated_ts double precision not null,
    primary key (user_id, workflow_id)
);
alter table anticipy_sys_v1.durable_workflows enable row level security;
create policy durable_workflows_owner on anticipy_sys_v1.durable_workflows
    using (user_id = auth.uid()) with check (user_id = auth.uid());

create table anticipy_sys_v1.durable_journal (
    user_id uuid not null references auth.users (id) on delete cascade,
    workflow_id text not null,
    idem_key text not null,
    step_name text not null,
    result_json jsonb not null,
    ts double precision not null,
    primary key (user_id, workflow_id, idem_key)
);
alter table anticipy_sys_v1.durable_journal enable row level security;
create policy durable_journal_owner on anticipy_sys_v1.durable_journal
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- Mem0 style memory (per user) --------------------------------
create table anticipy_sys_v1.memory (
    user_id uuid not null references auth.users (id) on delete cascade,
    mem_id text not null,
    kind text not null,
    mem_key text not null,
    value text not null,
    evidence text,
    ts double precision not null,
    active boolean not null default true,
    primary key (user_id, mem_id)
);
alter table anticipy_sys_v1.memory enable row level security;
create policy memory_owner on anticipy_sys_v1.memory
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- trajectory log (the flywheel substrate, per user) -----------
create table anticipy_sys_v1.trajectory (
    user_id uuid not null references auth.users (id) on delete cascade,
    rec_id bigint generated always as identity,
    ts double precision not null,
    input_text text,
    source text,
    features jsonb,
    decision text,
    confidence double precision,
    memory_state jsonb,
    profile_state jsonb,
    outcome jsonb,
    primary key (user_id, rec_id)
);
alter table anticipy_sys_v1.trajectory enable row level security;
create policy trajectory_owner on anticipy_sys_v1.trajectory
    using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---- suspended comms tasks (per user, P8 durable state) ----------
create table anticipy_sys_v1.comms_tasks (
    user_id uuid not null references auth.users (id) on delete cascade,
    task_id text not null,
    intent_json jsonb not null,
    question_sent text,
    channel text,
    sent_ts double precision,
    expected_answer_shape text,
    suspended_state jsonb,
    status text not null,
    primary key (user_id, task_id)
);
alter table anticipy_sys_v1.comms_tasks enable row level security;
create policy comms_tasks_owner on anticipy_sys_v1.comms_tasks
    using (user_id = auth.uid()) with check (user_id = auth.uid());
