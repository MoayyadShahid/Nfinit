create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(trim(name)) between 1 and 120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.project_revisions (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  revision_number integer not null check (revision_number > 0),
  state_json jsonb not null check (jsonb_typeof(state_json) = 'object'),
  created_at timestamptz not null default now(),
  unique (project_id, revision_number)
);

create index if not exists idx_projects_user_updated
  on public.projects (user_id, updated_at desc);

create index if not exists idx_project_revisions_project
  on public.project_revisions (project_id, revision_number desc);

alter table public.projects enable row level security;
alter table public.project_revisions enable row level security;

do $$
begin
  create role nfinit_backend nologin noinherit;
exception
  when duplicate_object then null;
end
$$;

grant nfinit_backend to postgres;

create policy "Users can read their projects"
  on public.projects for select
  to nfinit_backend
  using ((select auth.uid()) = user_id);

create policy "Users can create their projects"
  on public.projects for insert
  to nfinit_backend
  with check ((select auth.uid()) = user_id);

create policy "Users can update their projects"
  on public.projects for update
  to nfinit_backend
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete their projects"
  on public.projects for delete
  to nfinit_backend
  using ((select auth.uid()) = user_id);

create policy "Users can read revisions for their projects"
  on public.project_revisions for select
  to nfinit_backend
  using (
    exists (
      select 1
      from public.projects
      where projects.id = project_revisions.project_id
        and projects.user_id = (select auth.uid())
    )
  );

create policy "Users can create revisions for their projects"
  on public.project_revisions for insert
  to nfinit_backend
  with check (
    exists (
      select 1
      from public.projects
      where projects.id = project_revisions.project_id
        and projects.user_id = (select auth.uid())
    )
  );

revoke all on public.projects, public.project_revisions from anon, authenticated;
grant usage on schema public to nfinit_backend;
grant select, insert, update, delete on public.projects to nfinit_backend;
grant select, insert on public.project_revisions to nfinit_backend;
