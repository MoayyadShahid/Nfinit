-- Progress events of a CAD run (step started, step finished), so the studio
-- can show what the agent is doing while the user waits.
create table if not exists public.run_events (
  run_id uuid not null references public.cad_runs(id) on delete cascade,
  seq integer not null check (seq > 0),
  user_id uuid not null references auth.users(id) on delete cascade,
  stage text not null,
  status text not null,
  message text not null default '',
  attempt integer,
  duration_ms integer,
  created_at timestamptz not null default now(),
  primary key (run_id, seq)
);

alter table public.run_events enable row level security;

create policy "Users can read their run events"
  on public.run_events for select
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can add events to their runs"
  on public.run_events for insert
  to nfinit_backend
  with check (
    (select public.nfinit_request_user_id()) = user_id
    and exists (
      select 1 from public.cad_runs
      where cad_runs.id = run_events.run_id
        and cad_runs.user_id = (select public.nfinit_request_user_id())
    )
  );

revoke all on public.run_events from anon, authenticated;
grant select, insert on public.run_events to nfinit_backend;
