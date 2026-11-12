# Integração web da compatibilidade semântica

Implementação síncrona local em `app/analysis.py`. O upload PDF existente é
reutilizado; currículos cadastrados usam `texto_extraido`. Requisitos passam
por `parse_requirements`: todos devem estar classificados, com status derivado
`revisado`. Não são usadas anotações de avaliação.

O NER usa BIO normalizado (`NAME`, `SKILLS`, `EMAIL_ADDRESS`, `LOCATION`),
conforme `src/nlp/labels.py` e `ResumeNERPredictor`. São removidos nome,
contatos e localização pessoal antes da extração híbrida/comparação; empresas,
cargos e responsabilidades são preservados. A anonimização é heurística e
não garante remoção de todo dado pessoal. Não há texto integral em logs.

`ResumeEmbedder.encode`, `semantic.compare` e `calculate_similarity_index`
são chamados diretamente. Instâncias são carregadas sob demanda e reutilizadas
por processo, com lock para o processamento local. Não há treino ou alteração
de pesos. Falha de carga produz mensagem explícita, sem índice substituto.

O JSON `result` persiste índice sem arredondar, detalhes por requisito,
melhor evidência, origem, cosseno, contribuições, pesos e versão da fórmula.
Não são persistidos embeddings. Hashes SHA-256 identificam texto bruto,
requisitos estruturados e configuração do pipeline. Resultado antigo aparece
como desatualizado e não participa do ranking numérico ou da média. Arquivos
de modelos devem ser imutáveis no caminho configurado: ao trocar pesos, use
outro caminho/identificador para invalidar resultados e reinicie o processo.
Mudanças no código de extração/anonimização exigem incrementar PIPELINE_VERSION.

`curriculos.status` continua sendo a decisão manual. A análise possui estado
próprio, derivado de resultados salvos. Reprocessamento não modifica Aprovado
ou Descartado. Reenvio idêntico usa o currículo existente por texto/hash; novas
gravações concorrentes são protegidas por índice único. Arquivos antigos sem
hash são reconhecidos pelo texto; duplicidades históricas são preservadas.

## Banco: verificação obrigatória antes de aplicar

O esquema remoto **não foi confirmado** e nenhum SQL foi executado no Supabase.
Os SQLs 001–003 não definem `curriculos` nem `analises_aderencia`. A migração
incremental é `sql/004_integracao_aderencia.sql`; executar uma vez, após revisão.
Pressupõe IDs numéricos compatíveis com bigint, `curriculos.vaga_id`, colunas
de currículo usadas por RESUME_FIELDS, vínculo vagas.criado_por → usuarios.id,
e `analises_aderencia.pontuacao_aderencia` do tipo float8. As sequences são
descobertas por `pg_get_serial_sequence`; seus nomes não são presumidos.

Execute primeiro a consulta somente de leitura em
[`sql/conferir_integracao_aderencia.sql`](../sql/conferir_integracao_aderencia.sql).
`curriculos.vaga_id` precisa existir **antes** dos índices e das políticas.
Os SQLs 001–003 não a criam: se foi adicionada manualmente pela equipe,
confirme sua presença, tipo, vínculo e preenchimento. Se estiver ausente, a
migração 004 aborta com mensagem específica. A equipe deve fornecer a alteração
anterior e o mapeamento correto dos currículos para vagas; esta migração não
atribui vagas arbitrárias aos dados antigos.

Se `analises_aderencia` já existir, ela é estendida, sem descartar dados. Colunas
legadas NOT NULL sem default (além da pontuação tratada abaixo), tipos incompatíveis ou constraints adicionais
podem exigir adaptar a migração e o payload antes de usar. Não preencher
campos legados com notas fictícias. Qualquer erro deve resultar em rollback.
As novas constraints NOT VALID preservam linhas antigas, mas verificam novas
gravações. Resultados legados sem hashes não são considerados análises atuais.

A coluna legada `pontuacao_aderencia` passa a aceitar NULL e perde eventual
default para não inventar pontuação. Nenhum valor legado é atualizado. Para
novas análises, `save_analysis` envia explicitamente:

| Status | `pontuacao_aderencia` (SQL) | `result.score` (JSON) |
|---|---|---|
| `calculado` | pontuação real float8, inclusive zero se calculado | mesmo número de 0 a 100 |
| `analise_incompleta` | NULL | null explícito |

Esquema confirmado pela equipe: IDs/vínculos de currículos e análises são int4;
`analisado_em` legado é timestamp sem fuso. A migração aceita `timestamp` e
`timestamptz`, preservando tipo, default e valores da coluna existente. Só cria
`timestamptz` quando a coluna não existe; não aplica ALTER TYPE nem AT TIME ZONE.
A persistência envia novas datas em ISO 8601 UTC com offset explícito. Em
`timestamptz`, isso identifica o instante; em `timestamp`, PostgreSQL conserva
os campos da data UTC sem armazenar o offset. Essa convenção vale para novas
gravações, sem atribuir fuso às datas legadas. A leitura devolve o valor da API
sem converter datas sem fuso; a ordenação é feita pelo banco na própria coluna.
O histórico sem fuso não permite afirmar uma cronologia absoluta entre fusos
enquanto sua convenção original não for confirmada.

Ambos os casos enviam `vaga_id`, `curriculo_id`, `requirements_hash`, `text_hash`,
`config_hash`, `result`, `ner_model`, `embedding_model`, `formula_version`,
`weights`, `pipeline_version` e `analisado_em`. `result` contém status, score,
detalhes e avisos retornados pela fórmula, sem preencher pontuações ausentes.

A CHECK exige objeto JSON com chaves status/score presentes e coerência com a
coluna float8. `IS TRUE` impede que SQL NULL aprove campos ausentes. CASEs
verificam os tipos antes dos casts. JSON string numérica, booleano, status
desconhecido, score null em calculado e score numérico em incompleta são rejeitados.
Atualizações de registros legados também terão que satisfazer as novas CHECKs;
não há conversão automática de linhas antigas nem VALIDATE sobre o histórico.

A migração é reexecutável: verifica a FK pelo nome e tabela, substitui somente
sua própria CHECK (para corrigir a versão anterior) e recria apenas as quatro
políticas que pertencem a ela. As demais políticas e os dados são preservados.
CREATE TABLE IF NOT EXISTS não garante formato: as colunas adicionais são
adicionadas individualmente e os tipos de metadados/pontuação são conferidos,
com falha transacional em caso de incompatibilidade. Confira também todas as
constraints, índices e colunas legadas obrigatórias na consulta de inspeção.

O erro `42703: requirements_hash does not exist` observado antes de aplicar
004 significa que a aplicação nova está consultando o esquema antigo. A
aplicação agora responde 503 com instrução de conferir/aplicar a migração,
sem transformar a falha em lista vazia ou nota fictícia.

Consulta de inspeção (somente leitura, executar pela equipe no SQL Editor):

```sql
select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema='public' and table_name in
 ('usuarios','vagas','curriculos','analises_aderencia')
order by table_name, ordinal_position;
select tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies where schemaname='public' and tablename in
 ('usuarios','vagas','curriculos','analises_aderencia');
select conrelid::regclass, conname, pg_get_constraintdef(oid)
from pg_constraint where conrelid in
 (to_regclass('public.curriculos'),to_regclass('public.analises_aderencia'));
select pg_get_serial_sequence('public.curriculos','id'),
       pg_get_serial_sequence('public.analises_aderencia','id');
```

A migração habilita RLS e acrescenta guardas restritivas de proprietário tanto
em currículos quanto em análises, mesmo se existirem políticas permissivas
antigas. A FK composta impede associar currículo de outra vaga. Usa o cliente
autenticado da requisição, nunca service role. Confirmar com dois usuários reais
que leitura, insert e upsert não atravessam proprietários. Os testes simulados
verificam o fluxo da aplicação, não a execução das políticas PostgreSQL.

## Variáveis e inicialização PowerShell

Variáveis existentes necessárias: `FLASK_SECRET_KEY`, `SUPABASE_URL`,
`SUPABASE_KEY` (publishable). `SESSION_COOKIE_SECURE` depende do uso de HTTPS.
Novas variáveis opcionais: `NER_MODEL_PATH` (default
`models/ner/augmented/best_model`) e `EMBEDDING_MODEL` (default
`sentence-transformers/all-mpnet-base-v2`). Valores de ambiente/.env não devem
ser versionados. É necessário disponibilizar o modelo NER treinado e o modelo
de embeddings/cache local, sem incluí-los no Git. O primeiro carregamento pode
tentar baixar embeddings; falha de rede/modelo será informada, sem fallback.

Neste workspace `venv` está funcional; `.venv` não está funcional. Usar:

```powershell
Set-Location 'C:\Users\anabe\OneDrive\Documentos\Curriculo_AI\SI-PI6-2026-T101-G04'
# Se precisar instalar dependências no ambiente:
.\venv\Scripts\python.exe -m pip install -r requirements.txt
$env:NER_MODEL_PATH = 'models/ner/augmented/best_model'
$env:EMBEDDING_MODEL = 'sentence-transformers/all-mpnet-base-v2'
.\venv\Scripts\python.exe -m flask --app app run
```

Abrir http://127.0.0.1:5000. Configurar os segredos localmente antes de iniciar.

## Roteiro manual: uma vaga e dois currículos

1. Aplicar 001–003 se necessário, conferir o esquema acima e aplicar 004 pela
   equipe. Disponibilizar os modelos. Entrar com o primeiro usuário.
2. Criar vaga `Python API developer`, descrição `Build and maintain APIs`,
   requisitos revisados `Develop APIs with Python` (técnico obrigatório) e
   `Collaborate with product teams` (comportamental desejável).
3. Criar dois PDFs com texto selecionável em inglês: A com seção SKILLS
   `Python, Flask` e EXPERIENCE `Built Python APIs with product teams`;
   B com SKILLS `SQL, Excel` e EXPERIENCE `Prepared financial spreadsheets`.
4. Enviar ambos e clicar em Processar Aderência dos Selecionados. Conferir
   mensagens individuais, índice real, ordenação, evidências, origem e cosseno
   no detalhe. Não exigir nota ou ordem predeterminada dos modelos reais.
5. Reenviar A e selecionar B existente, sem novo arquivo. Confirmar ausência
   de currículo duplicado e recuperação do resultado após recarregar/logar.
6. Aprovar A manualmente e reanalisar: a decisão deve permanecer. Alterar um
   requisito: resultados anteriores devem aparecer desatualizados e sair da
   média. Reanalisar e confirmar nova versão persistida.
7. Criar requisito pendente e tentar analisar: exigir revisão. Configurar
   caminho NER inválido e reiniciar: erro explícito, sem nota fictícia. Enviar
   um PDF inválido junto de um válido: o válido deve continuar processando.
8. Entrar com segundo usuário: vaga, currículos e análises do primeiro não
   devem ser acessíveis, inclusive por URLs diretas.

Os exemplos em inglês são referência operacional. Os modelos foram trabalhados
em inglês; a qualidade em português não foi validada. Índice/cosseno não
confirmam competência, requisito atendido/ausente, qualidade ou qualificação.
Não há aprovação, descarte ou classes alto/médio/baixo automáticos.

## Verificação automatizada

`tests/test_analysis_web.py` usa Flask, upload PDF, extrator, comparador e fórmula
reais, com modelos determinísticos e banco simulados. Não valida qualidade dos
modelos, disponibilidade de pesos ou RLS remoto. Execução com:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Ainda dependem de execução real: compatibilidade do esquema legado, aplicação
da migração, políticas RLS PostgreSQL, inferência dos modelos, revisão das
evidências e teste visual no navegador. CSS e identidade visual foram preservados.

Verificação local em 12/11/2026: a suíte `test_*.py` passou com **106 testes**,
incluindo os 11 novos testes de integração. `git diff --check` passou. Não houve
inferência com modelos reais, execução SQL remota, push ou merge. Não foi
encontrado AGENTS.md no repositório nem em seus diretórios ancestrais.

Revisão de compatibilidade em 12/11/2026: **114 testes passaram**, incluindo
19 testes focados em integração/persistência. Foram acrescentados casos de
pontuação real, incompleta com NULL explícito, JSON sem status/score, tipos
inválidos, limites e resposta 503 quando falta a migração. `git diff --check`
passou. Os casos de JSON testam a validação Python antes do envio; as CHECKs
SQL e a reexecução da migração ainda **não foram executadas em PostgreSQL**.
`psql`/`postgres` não foram encontrados no PATH e o daemon Docker estava
indisponível. Não houve tentativa de conexão ao banco remoto. A equipe deve
validar em PostgreSQL local/de homologação a aplicação duas vezes, preservação
das linhas legadas e rejeição dos payloads inválidos pela própria CHECK.
