# Avaliação semântica ampliada

Este experimento mede recuperação de evidências, sem calcular aderência,
classificar candidatos ou modificar modelos, extração, anonimização ou aplicação.
Branch: `feature/avaliacao-semantica-ampliada`. Base da integração:
`33a0f6c885e97dc09f77db7643727c5eaef2332d`, pipeline `web-2-offset-privacy`.
Esse commit ainda não pertence à `main` no momento da preparação; a avaliação
depende dele. Não houve push ou merge. Não foi encontrado AGENTS.md no
repositório ou nos caminhos ancestrais conferidos.

## Preparação independente de ranking

Na raiz do projeto, em PowerShell:

```powershell
.\venv\Scripts\python.exe -m scripts.preparar_avaliacao_semantica --output-dir reports/avaliacao_semantica_ampliada
```

Usa exclusivamente `data/processed/splits/validation.json`, seed 42 e dez
índices sem reposição, excluindo os cinco IDs especificados. Os IDs são
`cv_{source_index:03d}_{sha256(content)[:8]}`, conforme o preparador anterior;
não são IDs nativos do dataset. Os hashes dos cinco IDs foram conferidos
contra os textos da validação. As pastas anteriores existem localmente,
mas não contêm curriculo.txt nem manifest.json; essa limitação da conferência
está registrada no novo manifesto. Nenhum conjunto de teste é acessado.
Currículos vazios não são substituídos: permanecem na amostra. Falhas de execução
interrompem a preparação, deixando manifesto incompleto, que a avaliação recusa.

O preparador usa os módulos atuais e um adaptador explícito do bloco de
`app.analysis.analyze` anterior aos embeddings: anonimização por offsets,
validação das SKILLS no texto original e `extract_skills`. Não importa Flask,
não lê .env e não executa `compare`, métricas ou pontuação. Esse adaptador evita
inicializar a aplicação e seu acesso a configurações/banco. Os hashes dos
arquivos do pipeline integrado ficam congelados para detectar divergências.

Os modelos são os atuais: NER `models/ner/augmented/best_model` e embeddings
`sentence-transformers/all-mpnet-base-v2`, sem treino. A execução exige cache
local e bloqueia downloads. O manifesto registra commit, versão do pipeline,
hashes do código/textos/entradas/embeddings, arquivos NER, pesos e tokenizer do
embedder, janela, sobreposição, normalização e política de comparação.
O NER mantém seus defaults de janela 512, stride 128 e confiança mínima 0.0;
os arquivos de inferência e configuração do modelo estão identificados por hash.

Cada pasta de currículo contém:

- `curriculo.txt`: currículo completo para revisão humana.
- `extracao.json`: extração profissional do pipeline avaliado.
- `entradas.json` e `entradas.md`: entradas originais numeradas a partir de zero,
  com texto e origem; esses índices identificam as evidências humanas.
- `embeddings.json`: contrato real de ResumeEmbedder, incluindo chunks, offsets,
  origens e vetores. Chunks de uma mesma entrada não criam novos índices humanos.
- `anotacoes.json`: seis espaços de requisito e revisão, sem gold preenchido.

O destino existente é recusado para não sobrescrever anotações. Para repetir uma
preparação, escolha outro `--output-dir` dentro de `reports/`; não altere os índices
de uma amostra anotada. Se o pipeline mudar, gere outra amostra e refaça o gold.

## Arquivo a preencher primeiro

`reports/avaliacao_semantica_ampliada/cv_000_d0a00fc9/anotacoes.json`.

Antes de consultar ranking, leia `curriculo.txt` completo e `entradas.md` da
mesma pasta. Depois faça o mesmo para os outros nove currículos do manifesto.
As seis posições sugerem dois requisitos literais, dois de paráfrase/contexto,
um relacionado não comprovado e um sem evidência suficiente. Escreva requisitos
curtos e atômicos. Essa distribuição é uma meta: se não couber no currículo,
altere as categorias e explique em `human_review.distribution_limitations`.
Não invente experiências para completar a distribuição.

Contrato por requisito:

- `acceptable_input_indices: [0, 3]`: entradas extraídas aceitáveis, anotadas
  por uma pessoa. Não escolha por cosseno ou pelo ranking.
- `acceptable_input_indices: []`: nenhuma entrada extraída é aceitável.
  Normalmente indica ausência de evidência suficiente no currículo; consulte o
  campo adicional abaixo para distinguir uma perda de extração.
- `acceptable_input_indices: null` ou ausente: ainda não anotado; bloqueia avaliação.
- `evidence_in_original`: confirme com `true` ou `false` após ler o currículo
  completo. `null` significa que essa verificação está pendente.
- Se a evidência existe no original mas foi perdida pela extração, use `[]`,
  `evidence_in_original: true` e `extraction_failure: true`. Preencha
  `expected_evidence` e explique a perda em `notes`. Esse caso é **positivo**
  na avaliação ponta a ponta, sem nenhuma evidência recuperável. Não o rotule
  como ausência no currículo.
- Em positivos recuperáveis, use índices válidos, `evidence_in_original: true`,
  `extraction_failure: false` e descreva a evidência em `expected_evidence`.
- Em ausência no original: `[]`, `evidence_in_original: false`,
  `extraction_failure: false`.

Preserve `resume_id` e `inputs_sha256`. Preencha `human_review.reviewer`,
`notes` e, ao concluir, `completed: true`. Os campos `human_analysis` permitem
registrar falha de extração/ranking, confusão com competência relacionada,
ambiguidade e possível dificuldade de idioma. Deixe diagnósticos de ranking
pendentes até a avaliação; hipóteses humanas não são explicações causais
comprovadas. A anotação original é copiada e tem seu hash registrado no relatório.

Exemplo **sintético** preenchido para uma entrada I0 de origem `experience`
com o texto `Built REST APIs with Python` (não copiar como anotação real):

```json
{
  "id": "R1",
  "text": "Develop REST APIs using Python",
  "category": "paráfrase",
  "acceptable_input_indices": [0],
  "evidence_in_original": true,
  "extraction_failure": false,
  "expected_evidence": "Built REST APIs with Python",
  "notes": "Revisado no currículo sintético completo e na entrada I0.",
  "human_analysis": {
    "extraction_failure": "",
    "ranking_failure": "",
    "related_confusion": "",
    "annotation_ambiguity": "",
    "language_difficulty": ""
  }
}
```

Isso ilustra um requisito; o arquivo real exige seis, além da revisão humana
concluída. Nenhuma evidência aceitável foi preenchida automaticamente.

## Avaliação posterior à anotação humana

Somente depois de anotar e revisar os dez arquivos:

```powershell
.\venv\Scripts\python.exe -m scripts.avaliar_amostra_semantica --sample-dir reports/avaliacao_semantica_ampliada --output-dir reports/avaliacao_semantica_ampliada_resultados
```

A CLI valida todos os arquivos antes de carregar o modelo de consulta. Recusa
preparação incompleta, revisão pendente, requisitos não anotados, hashes/índices
incompatíveis e alterações nos módulos avaliados, modelo ou tokenizer.
Usa as entradas e embeddings congelados, sem reextrair. Só `id` e `text` do
requisito entram em `compare`: gold, categorias e diagnósticos humanos não
influenciam o ranking. Requisitos longos que gerem mais de um chunk são recusados.

`evaluate_ranking` fornece Hit@1, Hit@3 e MRR. As métricas gerais reúnem os
requisitos positivos de todos os currículos; não são médias simples das médias
por currículo. Na visão ponta a ponta, positivos perdidos pela extração recebem
contribuição zero. A visão somente ranking os exclui explicitamente e informa
outro denominador. Internamente, uma cópia exclusiva para a métrica usa o
sentinela impossível -1 para representar um positivo sem entrada recuperável;
esse sentinela nunca é aceito no arquivo humano nem enviado à comparação.

Casos sem evidência no original ficam fora de Hit@k/MRR, mas seu Top3 continua
visível. O sistema retorna os trechos mais próximos se houver entradas; isso
não mede capacidade de abstenção e não confirma competência. Métricas sem
positivos elegíveis são `null` em JSON e `N/A` em HTML/CSV.

Saídas em `reports/avaliacao_semantica_ampliada_resultados/`:

- `relatorio.html`: gráficos geral/por currículo, denominadores, categorias,
  exemplos de acertos/erros e tabela esperado → Top3 com cosseno e origem.
- `resultados.json`: manifesto, anotações, rankings e métricas completas.
- `comparacao.csv`: requisitos, evidência esperada, diagnóstico e Top3.
- `metricas.csv`: métricas e denominadores gerais, por currículo e categoria.
- `agregados_sem_dados_pessoais.json`: contagens e métricas gerais sem textos
  ou identificadores de currículos, para futura documentação.

Todos os dados pessoais, entradas, anotações e relatórios ficam em `reports/`,
ignorado pelo Git. Só scripts, testes sintéticos e instruções são versionáveis.

## Verificação

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_expanded_semantic.py'
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
```

Os testes usam exclusivamente exemplos sintéticos e modelos simulados.
Verificam posições conhecidas, agregação com denominadores diferentes, positivos
perdidos na extração, ausência de evidência, anotação pendente, hashes e índices,
bloqueio anterior à revisão, seleção reproduzível sem reposição e relatórios.
A execução real desta entrega foi somente de preparação. Não há resultados
reais de recuperação antes da anotação humana e da avaliação posterior.

Verificação local em 12/11/2026: **138 testes passaram**, incluindo dez testes
novos desta etapa; `git diff --check` passou. A preparação real terminou com
dez currículos, 60 requisitos ainda não preenchidos e estado
`awaiting_human_review`. Todos os hashes dos módulos do pipeline conferem.
Não foi criado relatório de avaliação real. Não houve acesso ao conjunto de
teste, alteração no banco remoto, push ou merge.
