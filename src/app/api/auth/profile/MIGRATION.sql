-- Per-user Anticipy profile: assistant_name + PIN identification +
-- per-user daily voice/SMS caps. Backs the shared Twilio broker so
-- one inbound number can serve many users by matching the From
-- E.164 in this table, then disambiguating with a DTMF PIN if
-- multiple accounts share the same phone.
--
-- Applied via the Supabase MCP apply_migration tool against project
-- handlit / ogbxpqkmsdrcuilafycn on 2026-05-29. This file is kept
-- under source control as documentation of the schema for any
-- future replay against a fresh database.
create table if not exists public.anticipy_profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    assistant_name text not null default 'Anticipy',
    pin_hash text,
    pin_set_at timestamptz,
    phone_e164 text,
    phone_verified_at timestamptz,
    daily_voice_minutes_used numeric not null default 0,
    daily_voice_minutes_cap numeric not null default 10,
    daily_sms_count_used int not null default 0,
    daily_sms_count_cap int not null default 50,
    daily_window_started_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists anticipy_profiles_phone_idx
    on public.anticipy_profiles (phone_e164)
    where phone_e164 is not null;

alter table public.anticipy_profiles enable row level security;

drop policy if exists anticipy_profiles_owner_read on public.anticipy_profiles;
create policy anticipy_profiles_owner_read on public.anticipy_profiles
  for select to authenticated using (auth.uid() = id);

drop policy if exists anticipy_profiles_owner_update on public.anticipy_profiles;
create policy anticipy_profiles_owner_update on public.anticipy_profiles
  for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists anticipy_profiles_service_role_all on public.anticipy_profiles;
create policy anticipy_profiles_service_role_all on public.anticipy_profiles
  for all to service_role using (true) with check (true);

comment on table public.anticipy_profiles is
  'Per-user assistant naming and PIN identification for the shared Twilio broker. PINs are bcrypt-hashed; phone_e164 is the canonical inbound caller match. Daily voice and SMS caps are per-user; the broker enforces them before each send.';
