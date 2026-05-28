-- V4-8: dedicated trajectory tables for the DSv4 action engine.
-- Distinct from legacy engine_trajectories. service_role-only writes
-- (consistent with engine_trajectories/skill_library); the engine
-- holds the service-role key. RLS on, no public policies.
-- Applied to project handlit (ogbxpqkmsdrcuilafycn) 2026-05-16.

create table if not exists public.action_engine_tasks (
  id            uuid primary key default gen_random_uuid(),
  task_id       text not null unique,
  goal          text not null,
  status        text not null default 'running',
  answer        text default '',
  evidence      text default '',
  n_iterations  int  default 0,
  model         text default '',
  force_model   text,
  tier          int,
  task_name     text,
  error         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table if not exists public.action_engine_steps (
  id                     uuid primary key default gen_random_uuid(),
  task_id                text not null references public.action_engine_tasks(task_id) on delete cascade,
  subtask_index          int  not null default 0,
  iteration              int  not null default 0,
  action_kind            text,
  action_ref             text,
  action_url             text,
  action_text            text,
  ax_tree                text,
  screenshot_before_url  text,
  screenshot_after_url   text,
  verifier_verdict       text,
  verifier_evidence      text,
  verifier_confidence    double precision,
  latency_decide_s       double precision,
  latency_verify_s       double precision,
  created_at             timestamptz not null default now()
);

create index if not exists ix_aes_task on public.action_engine_steps(task_id);
create index if not exists ix_aet_created on public.action_engine_tasks(created_at desc);

alter table public.action_engine_tasks enable row level security;
alter table public.action_engine_steps enable row level security;

comment on table public.action_engine_tasks is
  'V4 DSv4 action-engine: one row per task run. service_role-only. Source for future distillation. Written in real time by trajectory_logger.';
comment on table public.action_engine_steps is
  'V4 DSv4 action-engine: one row per loop iteration (screenshot URLs, AX tree, action, vision verdict). service_role-only. Real-time per-step writes.';

-- Public storage bucket for step screenshots:
-- insert into storage.buckets (id,name,public)
--   values ('action-engine-shots','action-engine-shots',true)
--   on conflict (id) do nothing;
