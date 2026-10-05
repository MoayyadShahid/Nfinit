-- Background CAD runs: a paid agent run is recorded before it starts, and
-- its result (or partial work on failure) is kept even if nobody is polling.
create table if not exists public.cad_runs (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid references public.projects(id) on delete set null,
  status text not null check (status in ('running', 'succeeded', 'failed')),
  prompt text not null default '',
  model_id text not null default '',
  result_json jsonb check (result_json is null or jsonb_typeof(result_json) = 'object'),
  error text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists idx_cad_runs_user_created
  on public.cad_runs (user_id, created_at desc);

alter table public.cad_runs enable row level security;

create policy "Users can read their runs"
  on public.cad_runs for select
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can create their runs"
  on public.cad_runs for insert
  to nfinit_backend
  with check ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can update their runs"
  on public.cad_runs for update
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id)
  with check ((select public.nfinit_request_user_id()) = user_id);

revoke all on public.cad_runs from anon, authenticated;
grant select, insert, update on public.cad_runs to nfinit_backend;

-- Small rendered preview for the parts dashboard, captured by the studio.
alter table public.projects
  add column if not exists thumbnail bytea,
  add column if not exists thumbnail_content_type text,
  add column if not exists thumbnail_updated_at timestamptz;
