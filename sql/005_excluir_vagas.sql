-- Permite que cada usuário exclua vagas próprias e seus dados vinculados.
-- A função executa a remoção inteira em uma transação e respeita o RLS.
begin;

grant delete on public.vagas, public.curriculos, public.analises_aderencia to authenticated;

drop policy if exists talentmatch_vagas_delete_guard on public.vagas;
create policy talentmatch_vagas_delete_guard on public.vagas as restrictive
  for delete to authenticated
  using (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ));

drop policy if exists talentmatch_vagas_delete_own on public.vagas;
create policy talentmatch_vagas_delete_own on public.vagas
  for delete to authenticated
  using (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ));

create or replace function public.delete_job_with_candidates(p_job_id integer)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  delete from public.analises_aderencia where vaga_id = p_job_id;
  delete from public.curriculos where vaga_id = p_job_id;
  delete from public.vagas where id = p_job_id;
  if not found then
    raise exception 'Vaga não encontrada ou sem acesso.' using errcode = 'P0002';
  end if;
end;
$$;

drop policy if exists talentmatch_curriculos_delete_own on public.curriculos;
create policy talentmatch_curriculos_delete_own on public.curriculos
  for delete to authenticated
  using (vaga_id in (
    select v.id
    from public.vagas v
    join public.usuarios u on u.id = v.criado_por
    where u.auth_user_id = (select auth.uid())
  ));

drop policy if exists talentmatch_analises_delete_own on public.analises_aderencia;
create policy talentmatch_analises_delete_own on public.analises_aderencia
  for delete to authenticated
  using (vaga_id in (
    select v.id
    from public.vagas v
    join public.usuarios u on u.id = v.criado_por
    where u.auth_user_id = (select auth.uid())
  ));

create or replace function public.delete_candidate(p_job_id integer, p_candidate_id integer)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  delete from public.analises_aderencia
   where vaga_id = p_job_id and curriculo_id = p_candidate_id;
  delete from public.curriculos
   where vaga_id = p_job_id and id = p_candidate_id;
  if not found then
    raise exception 'Candidato não encontrado nesta vaga ou sem acesso.' using errcode = 'P0002';
  end if;
end;
$$;

revoke all on function public.delete_job_with_candidates(integer) from public, anon;
grant execute on function public.delete_job_with_candidates(integer) to authenticated;
revoke all on function public.delete_candidate(integer, integer) from public, anon;
grant execute on function public.delete_candidate(integer, integer) to authenticated;

commit;
