# Diagnóstico operacional em 17/11/2026

Branch `feature/avaliador-contextual`. Fórmula, pesos, prompt, critérios e design
preservados. Nenhuma consulta ou gravação remota no Supabase nesta tarefa.

## Causa comprovada

Havia dois processos `app.run` escutando em `127.0.0.1:5000`:

| PID observado | Início | Ambiente contextual herdado |
| --- | --- | --- |
| 29420 | 11:36:48 | Variáveis contextuais ausentes; modo legado |
| 22512 | 15:22:21 | experimental / llama_cpp / Qwen3-4B-Instruct-2507 |

Três conexões TCP sem requisição HTTP foram aceitas pelo PID 29420. Portanto,
iniciar outro Flask não fez a porta encaminhar para o processo configurado.
O diagnóstico leu exclusivamente as variáveis contextuais permitidas, sem
imprimir linha de comando completa ou outros valores do ambiente.

`load_dotenv(..., override=False)` preserva as variáveis do script. Não foi
encontrada sobrescrita pelo `.env`. O reloader preserva o ambiente de seu
processo pai; editar código não transfere o ambiente de outro terminal.
A porta 5001 também estava ocupada durante a preparação. Nenhum processo
existente foi encerrado; a execução isolada usa a porta **5002**.

## Correção

O inicializador chama o servidor sem debug e sem reloader. O bind é exclusivo
no Windows: um segundo processo recebe erro de porta ocupada, em vez de iniciar
outro listener concorrente. `app/run.py` informa a configuração do processo real,
e as respostas incluem `X-TalentMatch-PID` e `X-Analysis-Execution-ID`.

O POST de seleção de currículo existente já chamava `process_resume`; esse
contrato foi preservado e ganhou testes de regressão. Agora o resultado grava
`execution_id` dentro do JSON existente, e a seleção exige configuração e
contrato contextuais compatíveis, além dos hashes. Resultados legados com hash
aparentemente atual são rejeitados. A escolha considera a data mais recente.
O pipeline mudou para `web-7-contextual-traced-strict`, invalidando reaproveitamento
anterior sem apagar o histórico. O cache do modelo inclui backend, runtime e revisão.

Carregamento, inferência e validação têm códigos técnicos separados. Falha no
processamento contextual aborta a nova gravação: não chama regras legadas nem
salva uma agregação de falhas como pendências normais. Indeterminação e parcial
legítimos continuam sendo pendências, com os mesmos critérios e fórmula.

## Validação executada

Primeiro, o avaliador existente foi executado com modelo real Qwen3-4B-Instruct-2507
Q4_K_M, runtime llama.cpp local, sem Flask nem banco:

| Caso sintético | Decisão real | Citações | Tempo |
| --- | --- | --- | --- |
| Desenvolver APIs com Python; estágio descreve essas APIs | sustentado | e1 | 27,312 s |
| Administrar Kubernetes; projeto descreve apenas Docker | nao_sustentado_pelas_evidencias | e1 | 12,836 s |
| Inglês avançado; duas seções sem datas declaram avançado e básico | parcialmente_sustentado | e1 | 17,979 s |

No último caso, o modelo identificou o conflito, retornou base `contradicao` e
limitação explícita. O parcial continua pendente para revisão, sem meio ponto.
A entrada desse caso continha e1 (avançado) e e2 (básico); a lista de citações
retornada pelo modelo incluiu somente e1. Isso permanece uma limitação observável
da justificativa, sem fingir validação de qualidade ou alterar o resultado.

Resultado completo, evidências e configuração: `reports/contextual-operational.json`.
Execução reproduzível: `.\.venv-contextual\Scripts\python.exe -m scripts.diagnosticar_contextual`.

Depois foram executados **188 testes automatizados**, todos aprovados. Os testes
Flask usaram NER, embeddings, adaptador e persistência simulados e verificaram:
POST de currículo existente → modelo → validação → JSON salvo → leitura → template;
mesmo ID de execução no POST e na gravação; ID correto da análise na leitura;
rejeição de legado com hash forjado; falhas sem gravação/fallback; recuperação do
carregamento após falha sem cache negativo. Isso **não valida Supabase real**.

O servidor isolado foi iniciado, e `GET /login` sem cookies retornou 200 com PID
25156, o mesmo PID anunciado na configuração efetiva. O segundo bind na porta
5002 foi rejeitado com Windows 10048. Esse GET só renderiza login e não consulta
Supabase; não foi usado como comprovação de processamento ou persistência.

## Ação autenticada pendente

O ambiente está pronto em **http://127.0.0.1:5002/login**. O PID pode mudar quando
o servidor for reiniciado. Para iniciar novamente depois de encerrá-lo, use
somente este comando na raiz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1
```

Entre com sua conta e abra **http://127.0.0.1:5002/vagas/9/adicionar-curriculos**.
Marque o currículo existente **11** e clique em **Processar Aderência dos Selecionados**.
Depois abra **http://127.0.0.1:5002/vagas/9/candidato/11**.
Confira o texto de avaliação contextual, o ID da análise e o ID da execução.
As análises anteriores ficam desatualizadas até que esse POST termine com sucesso.

O terminal e `reports/contextual-server.jsonl` devem mostrar, com o mesmo `run_id`:

```text
ANALYSIS_POST_START
ANALYSIS_TARGETS
ANALYSIS_EFFECTIVE_CONFIG  enabled=true backend=llama_cpp pipeline=web-7-contextual-traced-strict
MODEL_LOAD_START
MODEL_LOAD_OK
MODEL_CALL_START          requirement_id=...
MODEL_CALL_END            requirement_id=... seconds=...
VALIDATION_OK             requirement_id=...
... repetir para os requisitos com evidência recuperada ...
ANALYSIS_SAVE_START
ANALYSIS_SAVED            analysis_id=... persisted_run_id=...
```

Ao abrir o candidato, uma nova requisição terá outro `run_id`, mas o evento
`ANALYSIS_SELECTED` deverá trazer **o mesmo `analysis_id` e `persisted_run_id`**
do salvamento, `found=true` e `method=contextual`.
Se não houver evidências recuperadas para um requisito, não há chamada ao modelo
para ele e a ausência continua indeterminada pelo contrato existente.

Falhas esperadas aparecem como `MODEL_CALL_ERROR`, `VALIDATION_ERROR`,
`ANALYSIS_TECHNICAL_ERROR` ou `ANALYSIS_SAVE_ERROR`, com código seguro, sem textos
do currículo, segredos ou mensagens brutas de exceção. Nesses casos não deve haver
`ANALYSIS_SAVED` para aquela execução. A tela informa a falha e o ID de execução.

Somente a ação autenticada do usuário pode comprovar o trecho restante com o
banco real: permissões, gravação retornando ID, consulta e exibição do candidato 11.
