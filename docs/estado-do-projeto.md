# Estado do projeto

O Flask (`app/routes.py`) recebe PDFs e requisitos revisados por vaga.
`app/requisitos.py` preserva IDs e classificação dos requisitos;
`app/repositories.py` lê e grava com o cliente autenticado, mantendo a decisão
manual de entrevista independente do processamento.

`app/analysis.py` coordena NER, anonimização (`src/data/privacy.py`), extração
(`src/nlp/skills_extractor.py`), embeddings e recuperação Top-k
(`src/matching/semantic.py`). `src/matching/adherence.py` avalia conservadoramente
cada requisito e agrega decisões com pesos 2/1. Os templates `vagas.html` e
`candidato.html` exibem ranking, evidências, pesos, alertas e intervalo provisório.
Hashes de texto, requisitos e configuração sinalizam análises desatualizadas.

NER extrai entidades; recuperação encontra trechos relacionados; aderência soma
pesos de requisitos com atendimento documental confirmado. São etapas e métricas
diferentes. O índice antigo de cossenos permanece em `src/matching/score.py`
para reprodução histórica, junto da CLI `scripts/calcular_aderencia.py`.

Experimentos: `scripts/avaliacao_semantica.py`, avaliação ampliada e relatórios
em `reports/` medem recuperação, não validam a nova decisão documental.
Não versionar currículos, modelos, segredos ou relatórios pessoais.

Pronto: cálculo ponderado, estados por requisito, intervalo provisório, ranking
sem exclusão automática, persistência JSON e invalidação por configuração.
Condições E/OU, uso, API, idioma e formação podem ser configuradas na edição da
vaga; sugestões só são aplicadas após revisão e salvamento. A avaliação literal
recebe todas as entradas, com rastreio por requisito. As seções PT/EN preservam
projetos, resumo, formação e idiomas. Janelas não cortam palavras e nomes
completos já identificados são removidos de ocorrências repetidas.
Pendente: controles e histórico de revisão humana das decisões, avaliação
contextual ampla e validação da qualidade em currículos reais PT/EN. Regras
limitadas não substituem revisão. Não houve consulta ao currículo ou JSON real
da vaga do teste nesta tarefa; divergências de formação e texto são alertadas
na interface para revisão explícita.

Execução local PowerShell (configurar ambiente conforme README):

```powershell
.\venv\Scripts\python.exe -m flask --app app run
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

A integração e as pré-condições de SQL estão em
[integração de aderência](integracao-aderencia.md). Nenhum SQL remoto é necessário
para a alteração dos pesos e da fórmula no JSON já existente.

Verificação em 17/11/2026: 6 testes de cálculo/decisões e 38 de integração de
análise passaram; `git diff --check` passou. A suíte completa apresentou três
erros fora dos arquivos alterados: dois em `test_expanded_semantic` (índice
anotado -1 rejeitado) e um em `test_semantic_stage.test_metrics` (IDs/ordem dos
requisitos). Não foi validada inferência real, interface em navegador ou banco
remoto. Não houve push ou merge.

Atualização da correção documental 3.1: 171 testes executados, 168 passaram e
permaneceram os três erros semânticos acima. O diagnóstico sintético e os limites
estão em [diagnóstico documental](diagnostico-documental.md). O servidor local
foi reiniciado; `app/run.py` usa reloader `stat` para a pasta do OneDrive.
