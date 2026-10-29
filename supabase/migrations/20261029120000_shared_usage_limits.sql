-- Sandbox calls must be counted in Postgres, not in one backend process.  A
-- transaction-scoped advisory lock in PostgresProjectStore serializes each
-- user's count/delete/insert sequence across every Railway replica.
create table if not exists public.sandbox_rate_events (
  user_id uuid not null references auth.users(id) on delete cascade,
  occurred_at timestamptz not null default clock_timestamp(),
  request_id uuid primary key default gen_random_uuid()
);

create index if not exists idx_sandbox_rate_events_user_time
  on public.sandbox_rate_events (user_id, occurred_at);

alter table public.sandbox_rate_events enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_rate_events'
      and policyname = 'Users can read their sandbox usage'
  ) then
    create policy "Users can read their sandbox usage"
      on public.sandbox_rate_events for select
      to nfinit_backend
      using ((select public.nfinit_request_user_id()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_rate_events'
      and policyname = 'Users can record their sandbox usage'
  ) then
    create policy "Users can record their sandbox usage"
      on public.sandbox_rate_events for insert
      to nfinit_backend
      with check ((select public.nfinit_request_user_id()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_rate_events'
      and policyname = 'Users can expire their sandbox usage'
  ) then
    create policy "Users can expire their sandbox usage"
      on public.sandbox_rate_events for delete
      to nfinit_backend
      using ((select public.nfinit_request_user_id()) = user_id);
  end if;
end
$$;

revoke all on public.sandbox_rate_events from public, anon, authenticated;
grant select, insert, delete on public.sandbox_rate_events to nfinit_backend;
