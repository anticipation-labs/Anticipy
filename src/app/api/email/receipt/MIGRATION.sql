-- Outbound email audit log for the website-side Resend broker.
-- /api/email/receipt inserts one row per send so we can trace abuse,
-- bill cost back to user_id, thread inbound replies (via goal_id), and
-- reconcile against Resend's delivery webhook.
--
-- Mirrors public.anticipy_twilio_sends (see twilio/relay/MIGRATION.sql).
--
-- Run manually in Supabase SQL editor (project handlit /
-- ogbxpqkmsdrcuilafycn) before deploying the broker. Service-role only;
-- the engine never talks to this table directly, only the website route.
create table if not exists public.anticipy_email_sends (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    to_email text not null,
    subject text not null,
    kind text not null,
    goal_id text not null,
    resend_message_id text not null default '',
    status text not null default '',
    sent_at timestamptz not null default now(),
    error text not null default ''
);

create index if not exists anticipy_email_sends_user_idx
    on public.anticipy_email_sends (user_id, sent_at desc);
create index if not exists anticipy_email_sends_sent_idx
    on public.anticipy_email_sends (sent_at desc);
create index if not exists anticipy_email_sends_goal_idx
    on public.anticipy_email_sends (goal_id, sent_at desc)
    where goal_id <> '';
create index if not exists anticipy_email_sends_resend_idx
    on public.anticipy_email_sends (resend_message_id)
    where resend_message_id <> '';

alter table public.anticipy_email_sends enable row level security;

drop policy if exists anticipy_email_sends_service_role_all
    on public.anticipy_email_sends;
create policy anticipy_email_sends_service_role_all
    on public.anticipy_email_sends
    for all
    to service_role
    using (true)
    with check (true);

comment on table public.anticipy_email_sends is
    'Outbound email sent through the /api/email/receipt broker. One row per Resend emails.send call. user_id is the Supabase user the engine authenticated as. goal_id threads inbound replies back to the originating goal. The rendered HTML body is NOT stored, only the subject + recipient + length-bearing metadata, so the audit trail does not leak message contents. Service-role only.';
