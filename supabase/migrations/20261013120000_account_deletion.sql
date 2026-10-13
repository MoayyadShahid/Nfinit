-- Self-service account deletion. Deleting the auth user removes every row
-- that references it (projects and their revisions, meshes and thumbnails,
-- runs and their events, the subscription record) through ON DELETE CASCADE,
-- all in one transaction. The function deletes only the signed-in user: it
-- takes no argument and reads the user from the request.
create or replace function public.nfinit_delete_my_account()
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  target uuid := public.nfinit_request_user_id();
begin
  if target is null then
    raise exception 'No signed-in user for account deletion.';
  end if;
  delete from auth.users where id = target;
end;
$$;

revoke all on function public.nfinit_delete_my_account() from public, anon, authenticated;
grant execute on function public.nfinit_delete_my_account() to nfinit_backend;
