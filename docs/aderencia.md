# SP2TG-27 — Índice de compatibilidade semântica

O fluxo web está descrito em [integração de aderência](integracao-aderencia.md),
incluindo migração incremental, configuração e roteiro de teste manual.

O índice de 0 a 100 soma pontos de similaridade entre requisitos e evidências
recuperadas. Não é porcentagem de requisitos atendidos nem probabilidade de
qualificação. A compatibilidade individual é marcada pelo limiar abaixo.

## Fórmula (versão 2.1)

Para cada requisito `i`, `s_i` é `top_similarity`, a melhor similaridade de
cosseno do ranking. Similaridade inferior a `0.50` zera os pontos do requisito;
`0.50` ou mais usa o próprio valor como multiplicador:

```text
compatível_i = s_i >= 0.50
contribuição_i = pontos_máximos_i × (s_i se compatível_i, senão 0)
índice = soma(contribuição_i)
```

Com a alocação padrão, 90 pontos são divididos igualmente entre os obrigatórios
e 10 entre os desejáveis, independentemente da quantidade em cada grupo. Se
somente um grupo existir, ele recebe os 100 pontos. Os pesos opcionais são
proporções entre os grupos (por exemplo, 80/20), normalizadas para 100.
O cosseno original e o resultado do limiar são preservados nos detalhes.
Valores JSON não são arredondados; a CLI exibe duas casas decimais.

`examples/aderencia_exemplo.json` contém três requisitos e rankings pequenos,
inteiramente sintéticos, sem dados pessoais ou vetores. Suas melhores
similaridades são `0.8`, `0.6`, `0.4`:

```text
45 × 0.8 + 45 × 0.6 + 10 × 0 = 63/100
```

O `0.4` do desejável fica abaixo do limiar e contribui com zero. É uma
demonstração da fórmula, não um resultado real do modelo.

Além da nota, a saída inclui `mandatory_status`. Se algum obrigatório ficar
abaixo de `0.50`, o currículo fica no grupo incompatível; na lista da vaga,
esse grupo aparece sempre abaixo dos currículos que atingiram o limiar em todos
os obrigatórios, mesmo que sua soma de pontos seja maior. O índice é a soma
dos pontos; o estado dos obrigatórios controla a ordem de priorização.

## Contratos

Função pura, sem dependências externas, Flask, modelos ou banco:

```python
from src.matching.score import calculate_similarity_index

result = calculate_similarity_index(requirements, results, weights=None)
```

`requirements` é lista não vazia de objetos com `id` e `text` textuais não
vazios e, opcionalmente, `tipo` e `nivel`. `tipo` é texto ou `null`; não altera
a pontuação. Níveis reconhecidos são `obrigatorio` e `desejavel`. Nível ausente
ou `null` é tratado como obrigatório e gera aviso. Outros níveis geram erro.
IDs são preservados e devem ser únicos.

`results` segue o contrato de `compare` em `src/matching/semantic.py`: cada
objeto tem `id`, `top_similarity` e `ranking`. A associação é por ID, nunca
pela posição; resultados extras, ausentes ou duplicados são rejeitados.
Campos adicionais do analisador são ignorados. Cada evidência do ranking
tem `similarity`, `text`, `source`, `input_index` e `chunk_index`, sendo os
índices inteiros não negativos. O ranking deve estar em ordem decrescente,
com `top_similarity` coerente com a primeira evidência. A agregação usa o
ranking já agrupado por entrada original pelo comparador; não recalcula
similaridade nem gera novas evidências.

Cossenos precisam ser numéricos finitos entre -1 e 1; booleanos são
rejeitados. A tolerância absoluta é `1e-9` para pequenos excessos nos limites,
ordenação e coerência do topo. Excessos aceitos nos limites são normalizados
para -1 ou 1 antes da agregação; `original_cosine` preserva o valor recebido.
Todos os itens do ranking são validados, mesmo em análises incompletas.
`acceptable_input_indices`, `annotation_reason`, `category`, Hit@k e MRR não
participam da pontuação.

Pesos são proporções de pontos por nível:

```json
{"obrigatorio": 90.0, "desejavel": 10.0}
```

Configuração parcial mantém o padrão para o nível omitido. Chaves
desconhecidas, booleanos, valores não numéricos, não finitos, nulos ou não
positivos são rejeitados. Se só houver requisitos de um nível, ele recebe
100 pontos. A função não altera os objetos recebidos.

A saída JSON contém:

| Campo | Conteúdo |
|---|---|
| `status` | `calculado` ou `analise_incompleta` |
| `score` | Índice geral 0–100 ou `null` |
| `score_name` | `indice_compatibilidade_semantica` |
| `formula_version` | `2.1` |
| `weights` | Proporção de pontos configurada por nível |
| `similarity_threshold` | Limiar inclusivo (`0.50`) |
| `mandatory_status` | `atendido`, `incompativel` ou `incompleto` |
| `warnings` | Avisos, incluindo requisitos sem nível |
| `incomplete_requirement_ids` | IDs com ranking vazio |
| `indices_by_level` | Índices `obrigatorio` e `desejavel`, ou `null` |
| `details` | Detalhes na ordem original dos requisitos |

Cada detalhe tem `id`, `text`, `tipo`, `nivel`, `compatible`, `max_points`,
`original_cosine`, `aggregation_value`, `contribution_points` e
`best_evidence`. A melhor evidência preserva `text`, `source` (origem),
`input_index`, `chunk_index`. `compatible` é `true` a partir de `0.50`,
`false` abaixo disso e `null` quando não há ranking.

## Análises incompletas

O campo `ranking` é obrigatório. Um ranking explicitamente vazio torna a
análise incompleta: `score` é `null`, os IDs afetados são listados e todas
as contribuições gerais ficam `null`. O requisito não é excluído do
denominador para fabricar uma nota parcial. Para um item sem ranking,
`aggregation_value` e `best_evidence` também são `null`; `top_similarity`
pode estar ausente ou ser `null` (se numérico, é validado, mas não agregado).

`indices_by_level` contém a soma dos pontos contribuídos por cada grupo; grupo
vazio ou com qualquer ranking vazio retorna `null`. Um grupo completo pode ter
pontos calculados mesmo com análise geral incompleta; esse valor descreve
somente aquele grupo.

Ranking vazio não prova falta de competência; ranking preenchido também não
prova atendimento. O limiar de `0.50` é uma regra operacional, não uma
propriedade garantida pelo modelo, e deve ser avaliado com exemplos
representativos.

## Execução no Windows/PowerShell

Na raiz do repositório:

```powershell
.\venv\Scripts\python.exe -m scripts.calcular_aderencia --input examples/aderencia_exemplo.json --output reports/aderencia/resultado.json
```

Saída do exemplo: `Índice de compatibilidade semântica: 63.00/100`.
`--weights` é o caminho para um arquivo JSON com o objeto de pesos:

```powershell
.\venv\Scripts\python.exe -m scripts.calcular_aderencia --input examples/aderencia_exemplo.json --output reports/aderencia/resultado_ponderado.json --weights "C:\caminho\pesos.json"
```

Para usar um JSON já produzido pelo analisador:

```powershell
.\venv\Scripts\python.exe -m scripts.calcular_aderencia --input reports/semantic_ranking/resultados.json --output reports/aderencia/resultado_real.json
```

A CLI lê `requirements` e `results`, cria a pasta de saída e grava UTF-8
indentado sem NaN/Infinity. Entrada inválida produz mensagem de erro e código
de saída 1. Em análise incompleta, informa os IDs sem imprimir nota zero.
Não carrega modelos nem acessa Supabase. `reports/` permanece local e ignorado
pelo Git; não versione relatórios, currículos, embeddings ou modelos.

Testes sem downloads, modelos ou banco:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_score.py"
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_semantic_stage.py"
```

## Limitações e integração

Uma correspondência relacionada pode pontuar sem comprovar o requisito:
Python não confirma Pandas e competências relacionadas não são equivalentes.
O grupo de obrigatórios reduz o risco de desejáveis elevarem um currículo que
falhou em obrigatório acima dos currículos que passaram no limiar. Ainda é
necessário validar embeddings e o limiar com exemplos representativos; esta
regra não comprova precisão geral nem ausência de vieses.

Use pontuações para ordenar apenas currículos da mesma vaga, calculados com
os mesmos requisitos, modelo, versão da fórmula e pesos. Guarde a proveniência
do modelo junto do resultado do analisador; este módulo não conhece nem
executa o modelo que produziu as similaridades.

O fluxo web chama esta fórmula depois da extração e da comparação semântica.
A lista da vaga ordena primeiro os currículos que atingiram o limiar em todos
os requisitos obrigatórios; a tela de detalhes mostra compatibilidade,
contribuição e melhor evidência por requisito.
