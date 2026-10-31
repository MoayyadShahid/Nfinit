-- Direct CAD endpoints and signed event streams can run concurrently. Keep
-- one subscriber from occupying every worker or opening unbounded database-
-- polling streams across replicas. Expiry recovers a lease after a crash.
create table if not exists public.sandbox_active_leases (
  lease_id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('sandbox', 'run-stream')),
  expires_at timestamptz not null
);

create index if not exists idx_sandbox_active_leases_user_expiry
  on public.sandbox_active_leases (user_id, kind, expires_at);

alter table public.sandbox_active_leases enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_active_leases'
      and policyname = 'Users can read their sandbox leases'
  ) then
    create policy "Users can read their sandbox leases"
      on public.sandbox_active_leases for select
      to nfinit_backend
      using ((select public.nfinit_request_user_id()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_active_leases'
      and policyname = 'Users can create their sandbox leases'
  ) then
    create policy "Users can create their sandbox leases"
      on public.sandbox_active_leases for insert
      to nfinit_backend
      with check ((select public.nfinit_request_user_id()) = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'sandbox_active_leases'
      and policyname = 'Users can release their sandbox leases'
  ) then
    create policy "Users can release their sandbox leases"
      on public.sandbox_active_leases for delete
      to nfinit_backend
      using ((select public.nfinit_request_user_id()) = user_id);
  end if;
end
$$;

revoke all on public.sandbox_active_leases from public, anon, authenticated;
grant select, insert, delete on public.sandbox_active_leases to nfinit_backend;
