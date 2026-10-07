-- The latest built mesh (GLB) of each project, with its geometry facts, so
-- the studio can show a part without building it again. One row per project:
-- the most recently viewed revision. Other revisions rebuild on demand.
create table if not exists public.project_meshes (
  project_id uuid primary key references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  code_hash text not null,
  glb bytea not null,
  inspection_json jsonb not null
    check (jsonb_typeof(inspection_json) = 'object'),
  updated_at timestamptz not null default now()
);

alter table public.project_meshes enable row level security;

create policy "Users can read their meshes"
  on public.project_meshes for select
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id);

create policy "Users can create meshes for their projects"
  on public.project_meshes for insert
  to nfinit_backend
  with check (
    (select public.nfinit_request_user_id()) = user_id
    and exists (
      select 1 from public.projects
      where projects.id = project_meshes.project_id
        and projects.user_id = (select public.nfinit_request_user_id())
    )
  );

create policy "Users can update their meshes"
  on public.project_meshes for update
  to nfinit_backend
  using ((select public.nfinit_request_user_id()) = user_id)
  with check ((select public.nfinit_request_user_id()) = user_id);

revoke all on public.project_meshes from anon, authenticated;
grant select, insert, update on public.project_meshes to nfinit_backend;
