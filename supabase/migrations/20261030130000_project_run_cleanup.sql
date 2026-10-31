-- Deleting a project must delete every associated run prompt/result as part of
-- project history, including in-flight records that must not recreate data.
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'cad_runs'
      and policyname = 'Users can delete their project runs'
  ) then
    create policy "Users can delete their project runs"
      on public.cad_runs for delete
      to nfinit_backend
      using ((select public.nfinit_request_user_id()) = user_id);
  end if;
end
$$;

grant delete on public.cad_runs to nfinit_backend;
