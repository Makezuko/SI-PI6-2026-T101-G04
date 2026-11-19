# Resultados visuais para apresentação acadêmica

O gerador lê arquivos já existentes, sem importar Flask, inicializar o banco,
carregar modelos, executar inferência ou alterar as fontes. Ele gera HTML
autônomo com SVG local, figuras PNG a 300 dpi, tabelas CSV e `fontes.json`.
O HTML abre sem servidor; os links de referência só são acessados se clicados.

Na raiz do projeto, em PowerShell, com o ambiente local preparado:

```powershell
.\.venv-contextual\Scripts\python.exe -m pip install -r requirements.visualization.txt
.\.venv-contextual\Scripts\python.exe -m scripts.gerar_resultados_visuais
Start-Process .\reports\resultados_visuais\relatorio.html
```

O primeiro comando só é necessário se Matplotlib não estiver instalado.
`python -m scripts.gerar_resultados_visuais --help` lista os caminhos de entrada
e saída configuráveis. Reexecutar substitui os arquivos gerados no destino;
escolha um destino novo para preservar uma geração anterior. Não direcione a
saída para dentro das pastas de origem. `reports/` permanece ignorado pelo Git.

## Inventário desta máquina, 18/11/2026

| Fonte | Situação e interpretação |
|---|---|
| `reports/ner_documentacao/{baseline,augmented}/{train_original,validation,test}/` | Seis avaliações existentes, com `metrics.json`, métricas por entidade e matrizes BIO absolutas e normalizadas. `evaluation_scope=document_consolidated`; 154 currículos de treino original, 33 de validação e 33 de teste para cada modelo. Perda é por janela. Dataset e contagens coincidem entre os dois modelos; identidade de conteúdo do dataset e commit da avaliação não foram comprovados por hash nos relatórios. |
| `reports/ner/` | Diretório encontrado sem arquivos; nenhuma métrica extraída. |
| `reports/ner_consolidated/` | Não encontrado. Não confundir com o protocolo consolidado presente em `ner_documentacao`. |
| `models/ner/{baseline,augmented}/best_model/config.json`, `training_args.bin` e `checkpoint-*/trainer_state.json` | Os `training_args.bin` dos dois melhores modelos registram batch por dispositivo de treino 2, avaliação 4, acumulação 4, learning rate 2e-5, cinco épocas, seed 42 e zero GPUs registradas. Os campos são lidos como literais do pickle, sem desserializar objetos. Históricos registram 255 atualizações baseline e 745 augmented ao final. Esses arquivos não são vinculados por hash histórico aos relatórios; dispositivo efetivo e revisão do modelo-base permanecem não comprovados. Os defaults atuais de batch 4/8 e acumulação 2 não são a configuração registrada nesses checkpoints. As diferenças não provam que augmentation isoladamente causou os ganhos. |
| `data/processed/huggingface_ner/preparation_metadata.json` | Preparação local registra `distilbert-base-cased`, janela 512, sobreposição 128 e dez entidades BIO. Sem hash do dataset nos relatórios, não se pode provar identidade dos dados usados na avaliação apenas pelo caminho. |
| `data/processed/splits/manifest.json` | Registra 220 currículos de entrada, 154 no treino original, 33 na validação, 33 no teste e 301 sintéticos acrescentados apenas ao treino. Registra seed 42 e ausência de vazamento detectado. O carregador atual aponta para `dataturks/resume-entities-for-ner` no Kaggle; o manifesto não comprova versão ou origem histórica. O idioma não está declarado. O código de limpeza prevê correção de offsets, remoção de duplicatas e resolução de sobreposições, sem registro individual das alterações neste inventário. |
| `reports/avaliacao_semantica_ampliada_resultados/agregados_sem_dados_pessoais.json` e `resultados.json` | Avaliação histórica em dez currículos do split validation, 60 requisitos e commit `33a0f6c885e97dc09f77db7643727c5eaef2332d`, pipeline `web-2-offset-privacy`. Os metadados do manifesto no relatório identificam `sentence-transformers/all-mpnet-base-v2`, hashes locais do modelo/tokenizer e revisão de anotações antes do ranking. Três positivos foram perdidos na extração: contam na visão ponta a ponta e são excluídos da visão só ranking. Não se mede abstenção pela exclusão de 21 itens sem evidência. O idioma dos dados não está declarado no agregado; não inferir uma distribuição linguística. |
| `reports/contextual-local.json` | Um ensaio com quatro requisitos e tempo total do fluxo; não é avaliação de qualidade. Pode conter dados privados, por isso o gerador só publica tempo e contagem. |
| `reports/contextual-operational.json` e `tests/fixtures/contextual_operational.json` | Três casos sintéticos; tempos por chamada e citações são exibidos como ensaio operacional, não como acurácia. As evidências fornecidas só são exibidas se coincidirem com a fixture sintética versionada; os IDs efetivamente citados pelo modelo aparecem em coluna separada. |
| `models/contextual/manifest.json` | Recuperação atual: `paraphrase-multilingual-MiniLM-L12-v2`; ensaio GGUF: Qwen3-4B-Instruct-2507 Q4_K_M e runtime llama.cpp CPU. Registra revisões e hash do runtime. A entrada Transformers Qwen2.5 de 1,5B não é o GGUF efetivamente escolhido. O manifesto sozinho não demonstra qualidade nem compara modelos. |

Cada arquivo efetivamente lido é registrado com SHA-256 em `fontes.json`, junto
do HEAD e hash do código do gerador. Antes de commit, HEAD identifica a base e
o hash identifica o conteúdo efetivamente executado; após um commit, regenere
para registrar o novo HEAD. **Hashes calculados agora identificam os arquivos
atuais e não comprovam sua procedência histórica.** A listagem de ausências só cobre os arquivos esperados
pelo gerador; os diretórios vazios ou ausentes acima constam deste inventário.
Se dados forem ausentes, o relatório indica indisponibilidade, sem fabricar zero.
Se as fontes NER comparadas tiverem dataset, contagens ou subconjunto distintos,
ou se o agregado semântico divergir do relatório completo, a geração falha.

As matrizes reproduzem os JSONs existentes: linhas são tags verdadeiras e colunas
previstas. A normalização por linha é a da fonte; linhas sem suporte não devem ser
interpretadas como desempenho zero. O histórico de validação durante o treinamento
é por janela e não deve ser comparado numericamente com o F1 consolidado dos
currículos. O gráfico de categorias inclui apenas categorias com positivos.
Identificadores de currículo são substituídos por numeração no gráfico; exemplos
textuais da avaliação real são omitidos porque sua anonimização não foi verificada.

No adaptador llama.cpp, a janela é 4096, o limite de saída 384 tokens e o timeout
HTTP 120 segundos. O campo `max_seconds=90` é usado pelo adaptador Transformers;
não significa que llama.cpp tenha esse limite de geração. A validade do JSON e
das citações não comprova que as decisões estejam corretas. O prompt da versão
`contextual-3` está em `src/matching/contextual.py`.

Fontes oficiais das características: [DistilBERT cased](https://huggingface.co/distilbert/distilbert-base-cased),
[MPNet](https://huggingface.co/sentence-transformers/all-mpnet-base-v2),
[MiniLM multilíngue](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
[Qwen3](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) e
[llama.cpp](https://github.com/ggml-org/llama.cpp). Essas fontes descrevem as
tecnologias; os resultados desta equipe vêm dos arquivos locais identificados.
