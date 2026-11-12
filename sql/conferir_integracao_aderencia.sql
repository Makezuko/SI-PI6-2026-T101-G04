-- Somente leitura. Executar ANTES de 004; nenhuma tabela é criada/alterada.
select table_name, column_name, data_type, udt_name, is_nullable, column_default
from information_schema.columns
where table_schema='public' and table_name in
 ('usuarios','vagas','curriculos','analises_aderencia')
order by table_name, ordinal_position;

-- Ausência da relação ou de curriculos.vaga_id deve bloquear a migração.
select to_regclass('public.curriculos') as curriculos,
       to_regclass('public.analises_aderencia') as analises_aderencia,
       exists (select 1 from information_schema.columns
         where table_schema='public' and table_name='curriculos'
           and column_name='vaga_id') as curriculos_tem_vaga_id;

select conrelid::regclass as tabela, conname, convalidated,
       pg_get_constraintdef(oid) as definicao
from pg_constraint where conrelid in
 (to_regclass('public.curriculos'),to_regclass('public.analises_aderencia'));

select tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies where schemaname='public' and tablename in
 ('usuarios','vagas','curriculos','analises_aderencia');

select schemaname, tablename, indexname, indexdef
from pg_indexes where schemaname='public'
and tablename in ('curriculos','analises_aderencia');

-- pg_get_serial_sequence exige relação existente: usa CASE para não chamar
-- a função quando analises_aderencia ainda não foi criada.
select case when to_regclass('public.curriculos') is not null
         then pg_get_serial_sequence('public.curriculos','id') end as curriculos_sequence,
       case when to_regclass('public.analises_aderencia') is not null
         then pg_get_serial_sequence('public.analises_aderencia','id') end as analises_sequence;
