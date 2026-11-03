# SP2TG-27 — Índice de compatibilidade semântica

O índice de 0 a 100 apoia a priorização pelo recrutador a partir das
similaridades entre requisitos e evidências já recuperadas. Não é porcentagem
de requisitos atendidos, probabilidade de qualificação ou aprovação. Não há
classes alto/médio/baixo, limiar de aprovação, eliminação ou justificativa gerada.

## Fórmula inicial (versão 1.0)

Para cada requisito `i`, `s_i` é `top_similarity`, a melhor similaridade de
cosseno do ranking, e `a_i = max(0, s_i)`:

```text
índice = 100 × soma(w_i × a_i) / soma(w_i)
contribuição_i = 100 × w_i × a_i / soma(w_i)
```

Pesos iniciais são 1 para ambos os níveis, sem diferenciação por tipo técnico
ou comportamental. Limitar cossenos negativos a zero é uma escolha inicial da
regra de agregação, não uma propriedade do modelo. O cosseno original permanece
nos detalhes. Os valores JSON não são arredondados; a exibição na CLI tem duas
casas decimais. A soma das contribuições coincide com o índice antes dessa
formatação, sujeita à representação numérica de ponto flutuante.

`examples/aderencia_exemplo.json` contém três requisitos e rankings pequenos,
inteiramente sintéticos, sem dados pessoais ou vetores. Suas melhores
similaridades são `0.8`, `0.6`, `0.4`. Com pesos iguais:

```text
100 × (0.8 + 0.6 + 0.4) / 3 = 60/100
```

É uma demonstração da fórmula, não um resultado real do modelo. Os dois
obrigatórios têm índice 70 e o desejável tem índice 40. Dar peso 2 aos
obrigatórios e 1 aos desejáveis produz índice geral 64. Esses pesos opcionais
não foram validados empiricamente.

## Contratos

Função pura, sem dependências externas, Flask, modelos ou banco:

```python
from src.matching.score import calculate_similarity_index

result = calculate_similarity_index(requirements, results, weights=None)
```

`requirements` é lista não vazia de objetos com `id` e `text` textuais não
vazios e, opcionalmente, `tipo` e `nivel`. `tipo` é texto ou `null`; não altera
pesos. Níveis reconhecidos são `obrigatorio` e `desejavel`. Nível ausente ou
`null` usa peso 1, continua no índice geral e gera aviso. Outros níveis geram
erro. IDs são preservados e devem ser únicos.

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

Pesos são configurados por um objeto como:

```json
{"obrigatorio": 2.0, "desejavel": 1.0}
```

Configuração parcial usa 1 para o nível omitido. Chaves desconhecidas,
booleanos, valores não numéricos, não finitos, nulos ou não positivos são
rejeitados. A função não altera os objetos recebidos.

A saída JSON contém:

| Campo | Conteúdo |
|---|---|
| `status` | `calculado` ou `analise_incompleta` |
| `score` | Índice geral 0–100 ou `null` |
| `score_name` | `indice_compatibilidade_semantica` |
| `formula_version` | `1.0` |
| `weights` | Configuração efetiva dos dois níveis |
| `warnings` | Avisos, incluindo requisitos sem nível |
| `incomplete_requirement_ids` | IDs com ranking vazio |
| `indices_by_level` | Índices `obrigatorio` e `desejavel`, ou `null` |
| `details` | Detalhes na ordem original dos requisitos |

Cada detalhe tem `id`, `text`, `tipo`, `nivel`, `weight`, `original_cosine`,
`aggregation_value`, `contribution_points` e `best_evidence`. A melhor
evidência preserva `text`, `source` (origem), `input_index`, `chunk_index`.
`weight` registra o peso efetivamente utilizado inclusive para itens sem nível.

## Análises incompletas

O campo `ranking` é obrigatório. Um ranking explicitamente vazio torna a
análise incompleta: `score` é `null`, os IDs afetados são listados e todas
as contribuições gerais ficam `null`. O requisito não é excluído do
denominador para fabricar uma nota parcial. Para um item sem ranking,
`aggregation_value` e `best_evidence` também são `null`; `top_similarity`
pode estar ausente ou ser `null` (se numérico, é validado, mas não agregado).

Grupos de nível usam a mesma fórmula dentro do próprio grupo. Grupo vazio
ou com qualquer ranking vazio retorna `null`. Um grupo completo pode ter
índice calculado mesmo com análise geral incompleta; esse valor descreve
somente aquele grupo. Requisitos sem nível não entram em nenhum dos grupos.

Ranking vazio não prova falta de competência; ranking preenchido não prova
atendimento ao requisito. Uma análise completa também pode ter índice zero
se todas as melhores similaridades forem negativas ou zero.

## Execução no Windows/PowerShell

Na raiz do repositório:

```powershell
.\venv\Scripts\python.exe -m scripts.calcular_aderencia --input examples/aderencia_exemplo.json --output reports/aderencia/resultado.json
```

Saída do exemplo: `Índice de compatibilidade semântica: 60.00/100`.
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
Uma média alta pode esconder um requisito obrigatório com baixa similaridade;
revise os detalhes e as evidências. É necessário validar o ranking com
julgamentos humanos em exemplos representativos. Esta entrega não comprova
precisão geral nem ausência de vieses.

Use pontuações para ordenar apenas currículos da mesma vaga, calculados com
os mesmos requisitos, modelo, versão da fórmula e pesos. Guarde a proveniência
do modelo junto do resultado do analisador; este módulo não conhece nem
executa o modelo que produziu as similaridades.

A função e a CLI estão prontas para consumir a comparação existente. A chamada
no fluxo da aplicação e a apresentação ao recrutador ficam para outra tarefa.
Upload, extração, modelos, comparação semântica, rotas, banco e interface
permanecem fora do escopo desta entrega.
