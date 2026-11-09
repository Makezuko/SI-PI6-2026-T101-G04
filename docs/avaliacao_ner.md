# Avaliação dos checkpoints NER

Esta entrega avalia somente checkpoints salvos, sem treinamento. Não altera pesos,
splits, tokenização, augmentation ou regra de predição. Não calcula AUC-ROC.

## Execução em PowerShell

Na raiz do projeto, com as dependências de requirements.txt instaladas:

```powershell
# Opcional, necessário apenas para os PNGs:
python -m pip install matplotlib

# Testes sintéticos, sem downloads nem carregamento de pesos:
python -m unittest discover -s tests -p test_ner_evaluation.py -v

# Seis avaliações principais (executar manualmente):
python -m src.nlp.evaluate --model-dir models/ner/baseline/best_model --split train --train-subset original
python -m src.nlp.evaluate --model-dir models/ner/baseline/best_model --split validation
python -m src.nlp.evaluate --model-dir models/ner/baseline/best_model --split test
python -m src.nlp.evaluate --model-dir models/ner/augmented/best_model --split train --train-subset original
python -m src.nlp.evaluate --model-dir models/ner/augmented/best_model --split validation
python -m src.nlp.evaluate --model-dir models/ner/augmented/best_model --split test

# Diagnóstico opcional, separado:
python -m src.nlp.evaluate --model-dir models/ner/augmented/best_model --split train --train-subset all
```

O dataset padrão é `data/processed/huggingface_ner`; para outro caminho, acrescente
`--dataset-dir CAMINHO`. Use o mesmo dataset na comparação dos dois checkpoints.
`train_original` mantém todas as janelas com `is_augmented=False`, exigindo essa
coluna explicitamente. `train_all` mantém originais e sintéticos. O filtro não se
aplica à validação ou ao teste. Metadados permanecem disponíveis para consolidar.

## Saídas

Em `reports/ner/<baseline ou augmented>/<train_original, train_all, validation ou test>/`:

- `metrics.json`: micro Precision, Recall e F1 de entidades, acurácia por token,
  macro e weighted, perda, caminhos, split/subconjunto, versões e contagens.
- `classification_report.json`: relatório seqeval existente, com as dez entidades,
  médias micro, macro e ponderada. Entidades ausentes têm métricas e support zero.
- `entity_metrics.json` e `.csv`: tabela das dez entidades, sem O; `f1-score` é F1.
- `confusion_matrix.json` e `.csv`: contagens por tag BIO, incluindo O, na ordem
  fixa das 21 tags de `src/nlp/labels.py`; linhas verdadeiras, colunas previstas.
- `confusion_matrix_normalized.json` e `.csv`: divisão pelo suporte de cada linha;
  linhas sem suporte ficam zeradas, sem NaN. Os JSONs incluem a ordem dos eixos.
- `confusion_matrix.png` e `confusion_matrix_normalized.png`: quando matplotlib
  está disponível; caso contrário, aviso e arquivos numéricos continuam disponíveis.
- `error_examples.json` e `consolidation_statistics.json`: saídas existentes.

Diretórios com relatórios são recusados antes da inferência. Para repetir, prefira
`--output-dir reports/ner_nova_execucao`; `--overwrite` permite sobrescrever com aviso.
Os relatórios e exemplos de erro podem conter dados pessoais: mantenha-os locais;
não versione reports/, modelos, datasets ou currículos.

## Interpretação acadêmica

A inferência ocorre por janela. A perda `window_loss` (também exposta no alias
legado `window_test_loss`, em qualquer split) é a perda por janela do Trainer,
não uma perda consolidada por currículo. Se indisponível, recebe null com aviso.

As métricas usam `evaluation_scope=document_consolidated`: cada token é identificado
por documento e offsets globais; a média dos logits das ocorrências sobrepostas
é seguida de argmax. Especiais, padding e tokens sem referência válida seguem as
exclusões existentes. Cada token consolidado é contado uma vez. A matriz compara
tags por token; as métricas de entidades comparam spans BIO pelo seqeval em modo
padrão, sem strict, reparo BIO ou mudança de esquema, com zero_division=0.

Treino original é a comparação principal dos dois modelos no mesmo conjunto;
treino com sintéticos é diagnóstico separado, sem substituir train_original.
Métricas de treino são diagnósticas e não medem generalização. Use validação para
análise de desenvolvimento e teste para avaliação final; não altere o modelo após
olhar o teste. Nenhuma das avaliações reais é executada pelos testes desta entrega.
