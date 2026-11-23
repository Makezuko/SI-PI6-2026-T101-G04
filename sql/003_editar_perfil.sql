-- Permite que cada usuário edite somente o próprio perfil.
begin;

grant update (email, nome, empresa) on public.usuarios to authenticated;

drop policy if exists talentmatch_usuarios_update_self on public.usuarios;
create policy talentmatch_usuarios_update_self on public.usuarios
  for update to authenticated
  using (auth_user_id = (select auth.uid()))
  with check (auth_user_id = (select auth.uid()));

commit;
