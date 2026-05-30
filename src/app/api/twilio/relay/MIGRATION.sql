-- Outbound SMS audit log for the website-side Twilio broker.
-- /api/twilio/relay inserts one row per send so we can trace abuse,
-- bill cost back to user_id, and reconcile against Twilio's
-- StatusCallback updates if/when we wire that route up.
--
-- Run manually in Supabase SQL editor (project handlit /
-- ogbxpqkmsdrcuilafycn) before deploying the broker. Service-role only;
-- the engine never talks to this table directly, only the website route.
create table if not exists public.anticipy_twilio_sends (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    to_e164 text not null,
    body_len int not null,
    kind text not null,
    twilio_sid text not null default '',
    status text not null default '',
    sent_at timestamptz not null default now()
);

create index if not exists anticipy_twilio_sends_user_idx
    on public.anticipy_twilio_sends (user_id, sent_at desc);
create index if not exists anticipy_twilio_sends_sent_idx
    on public.anticipy_twilio_sends (sent_at desc);
create index if not exists anticipy_twilio_sends_sid_idx
    on public.anticipy_twilio_sends (twilio_sid)
    where twilio_sid <> '';

alter table public.anticipy_twilio_sends enable row level security;

drop policy if exists anticipy_twilio_sends_service_role_all
    on public.anticipy_twilio_sends;
create policy anticipy_twilio_sends_service_role_all
    on public.anticipy_twilio_sends
    for all
    to service_role
    using (true)
    with check (true);

comment on table public.anticipy_twilio_sends is
    'Outbound SMS sent through the /api/twilio/relay broker. One row per Messages.json POST. user_id is the Supabase user the engine authenticated as; body is NOT stored, only its length, so the audit trail does not leak the actual SMS body. Service-role only.';
