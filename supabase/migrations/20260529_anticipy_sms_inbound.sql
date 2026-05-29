-- Inbound SMS queue for Twilio replies. The website's Twilio webhook
-- inserts every inbound SMS here; each engine polls the table on a
-- 10s interval (filtered by phone-to-account mapping) and forwards the
-- payload to its own local /api/sms/inbound. Because engines run on
-- 127.0.0.1 on user laptops, they are not reachable from Twilio's
-- public webhook surface; this table is the relay.
create table if not exists public.anticipy_sms_inbound (
    id bigserial primary key,
    received_at timestamptz not null default now(),
    from_number text not null,
    to_number text not null,
    body text not null,
    message_sid text unique,
    twilio_account_sid text,
    raw_form jsonb not null default '{}'::jsonb,
    -- account_id is set if we can map the From number to a known user;
    -- otherwise it stays NULL and an engine can still pull "unmapped"
    -- replies in dev environments where the dossier link is absent.
    account_id text,
    -- consumed_at + consumed_by are set the first time an engine
    -- successfully pulls this row through /api/sms/inbound. Per-row
    -- single-consumer semantics. Future polls return only NULL rows.
    consumed_at timestamptz,
    consumed_by text
);

create index if not exists anticipy_sms_inbound_received_idx
    on public.anticipy_sms_inbound (received_at desc);
create index if not exists anticipy_sms_inbound_unconsumed_idx
    on public.anticipy_sms_inbound (received_at desc)
    where consumed_at is null;
create index if not exists anticipy_sms_inbound_account_idx
    on public.anticipy_sms_inbound (account_id, received_at desc)
    where consumed_at is null;
create index if not exists anticipy_sms_inbound_from_idx
    on public.anticipy_sms_inbound (from_number, received_at desc)
    where consumed_at is null;

alter table public.anticipy_sms_inbound enable row level security;

-- Only the service role writes (the website Twilio webhook) and reads
-- (the engine poller via SUPABASE_SERVICE_ROLE_KEY). No anon access.
drop policy if exists anticipy_sms_inbound_service_role_all
    on public.anticipy_sms_inbound;
create policy anticipy_sms_inbound_service_role_all
    on public.anticipy_sms_inbound
    for all
    to service_role
    using (true)
    with check (true);

comment on table public.anticipy_sms_inbound is
    'Inbound SMS replies posted by Twilio to the website webhook, polled by engines on 127.0.0.1 (which cannot accept inbound webhooks directly). One row per Twilio MessageSid. Service-role only.';
