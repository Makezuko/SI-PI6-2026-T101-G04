# 7. Padrão Transversal — Observabilidade

## 7.1 Objetivo

O TalentMatch AI utiliza observabilidade para acompanhar a execução
do pipeline de análise de currículos, registrar eventos técnicos,
identificar falhas e auxiliar no diagnóstico de problemas.

A implementação utiliza logs estruturados, identificadores de
execução e rastreamento das etapas do processamento.

O padrão foi aplicado transversalmente aos componentes responsáveis
pela análise, inferência contextual, persistência e requisições HTTP.

## 7.2 Identificação das execuções

O módulo `src/matching/telemetry.py` utiliza `ContextVar` para
armazenar o identificador da execução corrente.

A função `new_execution()` gera um identificador único utilizando
UUID. Esse identificador é associado ao contexto da execução e
incluído nos eventos registrados.

O identificador permite relacionar os eventos de uma mesma análise,
facilitando o rastreamento do processamento e o diagnóstico de falhas.

## 7.3 Registro estruturado de eventos

Os eventos são registrados em formato JSON por meio do logger
`talentmatch.analysis`.

A função `event()` centraliza o registro dos eventos e utiliza
uma lista de campos permitidos (`ALLOWED`) para restringir os
dados que podem ser incluídos no rastreamento técnico.

Os eventos incluem informações como:

- Identificador da execução;
- Identificador do requisito;
- Identificador da análise persistida;
- Etapa do processamento;
- Código de erro;
- Tempo de execução;
- Quantidade de entradas e janelas;
- Dimensão dos vetores.

A restrição de campos contribui para evitar o registro acidental
de informações pessoais, textos de currículos, tokens ou conteúdos
sensíveis.

## 7.4 Rastreamento das etapas

A função `stage()` implementa um context manager para acompanhar
etapas do processamento.

Para cada etapa, são registrados eventos de início e conclusão.
Caso ocorra uma exceção, a função `failure()` registra informações
técnicas sobre a falha, incluindo:

- Nome da etapa;
- Tipo da exceção;
- Arquivo de origem;
- Função de origem;
- Linha de origem.

A mensagem original da exceção não é registrada, reduzindo o risco
de exposição de dados sensíveis.

Após registrar a falha, a exceção é propagada para que o fluxo
responsável possa realizar o tratamento adequado.

## 7.5 Aplicação no pipeline

A fachada `TalentMatchPipelineFacade`, em
`src/matching/facade.py`, utiliza o rastreamento nas seguintes etapas:

- `input_extraction`: extração e preparação das entradas;
- `requirement_embeddings`: geração de embeddings dos requisitos;
- `requirement_window_validation`: agregação e validação das janelas dos requisitos;
- `evidence_embeddings`: geração dos embeddings das evidências;
- `semantic_comparison`: comparação semântica entre requisitos e evidências.

O pipeline também registra eventos relacionados ao carregamento
dos modelos e à execução das etapas de análise.

## 7.5 Aplicação no pipeline

A fachada `TalentMatchPipelineFacade`, em
`src/matching/facade.py`, utiliza o rastreamento nas seguintes etapas:

- `input_extraction`: extração e preparação das entradas;
- `requirement_embeddings`: geração de embeddings dos requisitos;
- `requirement_window_validation`: agregação e validação das janelas dos requisitos;
- `evidence_embeddings`: geração dos embeddings das evidências;
- `semantic_comparison`: comparação semântica entre requisitos e evidências.

O pipeline também registra eventos relacionados ao carregamento
dos modelos e à execução das etapas de análise.

## 7.7 Persistência e rastreamento HTTP

O módulo `app/analysis.py` registra eventos relacionados ao início
da persistência, falhas de gravação e conclusão do salvamento
da análise.

O módulo `app/__init__.py` associa um identificador de execução
às requisições HTTP e disponibiliza os seguintes cabeçalhos:

- `X-TalentMatch-PID`: identificador do processo;
- `X-Analysis-Execution-ID`: identificador da execução.

O contexto de rastreamento é encerrado ao final da requisição.

## 7.8 Armazenamento dos logs

O servidor configurado em `app/run.py` registra os eventos técnicos
em:

`reports/contextual-server.jsonl`

Os registros são armazenados em formato JSON Lines, permitindo
a inspeção e análise individual dos eventos.

O handler HTTP personalizado registra o método da requisição e
o código de resposta. O logger de diagnóstico de autenticação
também utiliza o arquivo de rastreamento. Os testes automatizados
verificam que dados pessoais e mensagens sensíveis de exceções
não sejam expostos nos logs analisados.

## 7.9 Privacidade e segurança

A observabilidade foi implementada considerando a proteção das
informações pessoais presentes nos currículos.

As principais medidas são:

- Restrição dos campos permitidos nos eventos;
- Não registro de textos de currículos ou tokens;
- Não registro de mensagens brutas de exceções;
- Registro de informações técnicas necessárias ao diagnóstico;
- Utilização de identificadores de execução para correlacionar eventos.

A observabilidade não deve ser utilizada para armazenar ou expor
dados pessoais dos candidatos.

## 7.10 Testes e validação

A implementação é verificada por testes automatizados, incluindo:

- `tests/test_requirement_windows.py`: quatro testes executados
  com sucesso, incluindo a validação de que informações técnicas
  da exceção são registradas sem exposição da mensagem original;

- `tests/test_analysis_web.py`: 28 testes executados, com 18
  aprovados, 8 falhas e 2 erros. Os testes verificam aspectos
  relacionados ao rastreamento de eventos, identificação das
  execuções, persistência, tratamento de falhas e proteção
  de informações sensíveis.

Os resultados dos testes de análise web indicam pendências
de validação no estado atual do projeto, que não foram
corrigidas nesta atividade de documentação.

## 7.11 Considerações finais

A observabilidade é aplicada transversalmente ao fluxo de análise
do TalentMatch AI, permitindo rastrear execuções, identificar
etapas de processamento, diagnosticar falhas e verificar eventos
de persistência.

A implementação centraliza o registro técnico em um módulo
específico, promovendo consistência e facilitando a manutenção
do sistema.
