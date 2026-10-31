## Na raiz do projeto, com venv ativo
```powershell
python -m pip install "numpy>=1.24,<3" "matplotlib>=3.7,<4"
python -m unittest discover -s tests -p "test_semantic_stage.py"
python -m scripts.analisar_similaridade
Start-Process .\reports\semantic_ranking\relatorio.html
```
Registre numpy e matplotlib no requirements.txt se ainda não estiverem presentes. Não remova scikit-learn do projeto se outras etapas o utilizam; esta etapa não o importa mais.

## Medidas e interpretação
| Medida | O que é | O que mostra |
|---|---|---|
| Cosseno | Proximidade angular dos vetores, de -1 a 1 | Quanto cada requisito está próximo de cada texto |
| Margem Top1–Top2 | Score Top1 menos Top2, de 0 a 2 | Quanto a primeira evidência se destaca; não é confiança |
| Hit@1 | Fração dos positivos anotados com evidência aceitável em primeiro lugar | Utilidade do primeiro resultado |
| Hit@3 | Fração dos positivos anotados com evidência aceitável entre as três primeiras entradas | Utilidade de revisar até três resultados |
| MRR | Média de 1/posição da primeira evidência aceitável, zero se ausente | Quão cedo se encontra a evidência correta |

Cosseno e margem são medidas descritivas. Hit@k e MRR são métricas de recuperação/ranking, não medidas de similaridade nem classificação. Ranking varia de 0 a 1; maior é melhor. Hit@3 não é Recall@3: basta recuperar uma evidência aceitável. Chunks são agrupados por input_index usando o maior score antes do ranking.

Exemplo: evidência correta em segundo lugar → Hit@1=0, Hit@3=1, contribuição ao MRR=0,5. Nenhuma evidência recuperada para positivo → contribuição zero. Sem positivos anotados → N/A, não zero.

## Saídas
- relatorio.html: guia das medidas, mapa de similaridade, comparação só skills versus contexto, margem, métricas de ranking e tabela Top3.
- resultados.json: matriz, ranking completo, diagnóstico, métricas e embeddings dos requisitos.
- comparacao.csv: melhor resultado e diagnóstico por requisito.

## Anotações
examples/requisitos_exemplo.json tem 6 requisitos didáticos vinculados ao currículo anterior: input 0=Python; 1=SQL; 2=experiência; 3=projeto. Revise o gold ao alterar currículo.

acceptable_input_indices indica as entradas consideradas evidências suficientes. [] significa sem evidência suficiente; null ou campo ausente significa não anotado. Itens sem evidência não entram no denominador de Hit@k/MRR, porque não existe um resultado correto para recuperar, mas aparecem no relatório para revisão. Eles não são automaticamente julgados corretos: este sistema sempre mostra o trecho mais próximo.

Pandas fica como caso relacionado não confirmado: análise com Python não prova domínio dessa biblioteca. Nenhum score gera uma decisão de atendimento ao requisito.

## Limites
Exemplos são didáticos, anotados manualmente e não validam desempenho geral. Gold por entrada, não por trecho: blocos longos exigem anotações mais precisas no futuro. Requisitos precisam ser curtos e atômicos. Exemplos/modelo inicial em inglês; não conclua qualidade em português.

Score máximo com contexto é sempre >= só skills porque há mais opções. Isso não comprova melhora de ranking. Margem pequena pode refletir duas evidências boas; margem grande pode selecionar uma evidência errada.

Para ampliar: vários currículos/vagas; anotações revisadas pela equipe; casos literais, paráfrases e relacionados; teste independente. Não há classificação, nota final ou ranking de candidatos nesta etapa.

## Verificação
Três testes determinísticos: cosseno e entradas inválidas; agrupamento de chunks; métricas com posições conhecidas e ausência de anotação. Geração do relatório conferida com fixture sintética, sem apresentar scores dela como saída real do modelo. Execute no seu ambiente para obter a inferência real.

Referência: https://www.sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html
