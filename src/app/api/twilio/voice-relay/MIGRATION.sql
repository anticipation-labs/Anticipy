-- Voice onboarding calls placed through the website-side Twilio broker.
-- /api/twilio/voice-relay inserts one row per outbound call. The TwiML
-- answer route (/api/twilio/onboarding/answer) updates the same row as
-- the user answers each of the 7 questions, building up the answers[]
-- array. The engine polls /api/twilio/onboarding/status for progress.
--
-- Run manually in Supabase SQL editor (project handlit /
-- ogbxpqkmsdrcuilafycn) before deploying the broker. Service-role only;
-- the engine never talks to this table directly, only the website routes.
create table if not exists public.anticipy_voice_onboarding_calls (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    account_id text not null,
    to_e164 text not null,
    twilio_sid text not null default '',
    status text not null default '',
    error text,
    question_index int not null default 0,
    question_total int not null default 7,
    answers jsonb not null default '[]'::jsonb,
    dossier_written boolean not null default false,
    placed_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists anticipy_voice_onboarding_calls_user_idx
    on public.anticipy_voice_onboarding_calls (user_id, placed_at desc);
create index if not exists anticipy_voice_onboarding_calls_account_idx
    on public.anticipy_voice_onboarding_calls (account_id, placed_at desc);
create index if not exists anticipy_voice_onboarding_calls_sid_idx
    on public.anticipy_voice_onboarding_calls (twilio_sid)
    where twilio_sid <> '';
create index if not exists anticipy_voice_onboarding_calls_placed_idx
    on public.anticipy_voice_onboarding_calls (placed_at desc);

alter table public.anticipy_voice_onboarding_calls
    enable row level security;

drop policy if exists anticipy_voice_onboarding_calls_service_role_all
    on public.anticipy_voice_onboarding_calls;
create policy anticipy_voice_onboarding_calls_service_role_all
    on public.anticipy_voice_onboarding_calls
    for all
    to service_role
    using (true)
    with check (true);

comment on table public.anticipy_voice_onboarding_calls is
    'Outbound voice onboarding calls placed through /api/twilio/voice-relay. answers[] is appended by /api/twilio/onboarding/answer as each Gather speech result lands. Service-role only.';
