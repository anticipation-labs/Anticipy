-- US-008: one-time deep-link handoff tokens.
-- The web funnel mints a 32-byte hex token after signup. The Mac app
-- swaps it via POST /api/auth/exchange for the real Supabase access and
-- refresh tokens. Single use, 5 minute expiry.
--
-- The story description names this table auth.handoff_tokens, but the
-- auth schema is owned by supabase_auth_admin and rejects CREATE TABLE
-- from migrations. We use public.handoff_tokens with a foreign key to
-- auth.users(id), which is the supported Supabase pattern. The table
-- still represents auth-flow state; only the schema differs.
-- Applied to project handlit (ogbxpqkmsdrcuilafycn) on 2026-05-21.

create table if not exists public.handoff_tokens (
  id             text primary key,
  user_id        uuid not null references auth.users(id) on delete cascade,
  access_token   text not null,
  refresh_token  text not null,
  expires_at     timestamptz not null,
  consumed_at    timestamptz,
  created_at     timestamptz not null default now()
);

create index if not exists ix_handoff_tokens_user
  on public.handoff_tokens(user_id);
create index if not exists ix_handoff_tokens_expires
  on public.handoff_tokens(expires_at);

alter table public.handoff_tokens enable row level security;
-- No public policies; the mint and exchange endpoints use the service role
-- key. End-user clients never read this table directly.

comment on table public.handoff_tokens is
  'One-time handoff tokens swapping a Supabase web session for a Mac-app session via the anticipy://session deep-link. 5 minute TTL, single use.';
comment on column public.handoff_tokens.id is
  '32 byte hex token. Identifies the row and is the bearer the Mac app presents to /api/auth/exchange.';
comment on column public.handoff_tokens.access_token is
  'Captured at mint, replayed once at exchange so the Mac app starts with the same Supabase session the browser had.';
comment on column public.handoff_tokens.refresh_token is
  'Captured at mint, replayed once at exchange so the Mac app can rotate access tokens without re-prompting for credentials.';
comment on column public.handoff_tokens.consumed_at is
  'Set on the first successful exchange. Any later exchange of the same token returns 410 Gone.';
