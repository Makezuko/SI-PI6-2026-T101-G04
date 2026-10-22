-- Etapa 1: Supabase Auth + vagas do próprio usuário.
-- Executar uma vez no SQL Editor. Não apaga linhas nem desativa RLS.
begin;

-- A senha passa a ser gerenciada pelo Supabase Auth.
-- Valores antigos de senha_hash são preservados, mas não usados pelo novo login.
alter table public.usuarios alter column senha_hash drop not null;
alter table public.usuarios
  add column if not exists auth_user_id uuid references auth.users(id),
  add column if not exists nome text,
  add column if not exists empresa text;
create unique index if not exists usuarios_auth_user_id_uidx
  on public.usuarios(auth_user_id);

alter table public.vagas
  add column if not exists status text not null default 'Aberta';

alter table public.usuarios enable row level security;
alter table public.vagas enable row level security;

-- Nenhuma leitura/gravação pública nas tabelas desta etapa.
revoke all on public.usuarios, public.vagas from anon;
revoke all on public.usuarios, public.vagas from authenticated;
grant usage on schema public to authenticated;
-- senha_hash não é exposta pela API, mesmo ao próprio usuário.
grant select (id, email, auth_user_id, nome, empresa, criado_em)
  on public.usuarios to authenticated;
grant insert (email, auth_user_id, nome, empresa)
  on public.usuarios to authenticated;
grant select on public.vagas to authenticated;
grant insert (titulo, descricao, requisitos, criado_por)
  on public.vagas to authenticated;
grant usage, select on sequence public.usuarios_id_seq, public.vagas_id_seq
  to authenticated;

-- Recria somente as políticas pertencentes a este pacote, para permitir reexecução.
drop policy if exists talentmatch_usuarios_select_self on public.usuarios;
create policy talentmatch_usuarios_select_self on public.usuarios
  for select to authenticated
  using (auth_user_id = (select auth.uid()));

drop policy if exists talentmatch_usuarios_insert_self on public.usuarios;
create policy talentmatch_usuarios_insert_self on public.usuarios
  for insert to authenticated
  with check (
    auth_user_id = (select auth.uid())
    and lower(email) = lower((select auth.jwt()->>'email'))
  );

drop policy if exists talentmatch_vagas_select_own on public.vagas;
create policy talentmatch_vagas_select_own on public.vagas
  for select to authenticated
  using (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ));

drop policy if exists talentmatch_vagas_insert_own on public.vagas;
create policy talentmatch_vagas_insert_own on public.vagas
  for insert to authenticated
  with check (criado_por in (
    select id from public.usuarios where auth_user_id = (select auth.uid())
  ));

commit;
