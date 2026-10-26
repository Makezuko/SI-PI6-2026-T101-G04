-- Etapa 2: edição de vagas pelo próprio usuário.
-- Executar uma vez no SQL Editor, depois de 001_auth_vagas.sql. Pode ser reexecutada.
-- Não apaga linhas, não altera dados e mantém RLS ligado.
begin;

-- Apenas estas colunas podem ser alteradas pela API. criado_por, id e criado_em
-- ficam de fora: ninguém consegue transferir uma vaga para outro usuário.
-- Os requisitos (técnicos/comportamentais) ficam em vagas.requisitos, como JSON em texto.
grant update (titulo, descricao, requisitos, status)
  on public.vagas to authenticated;

drop policy if exists talentmatch_vagas_update_own on public.vagas;
create policy talentmatch_vagas_update_own on public.vagas
  for update to authenticated
  using (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ))
  with check (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ));

commit;
