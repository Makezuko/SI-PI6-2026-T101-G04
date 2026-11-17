# Fluxo contextual experimental

Currículo → NER DistilBERT e extrator híbrido → Sentence Transformer recupera
Top-5 por requisito → avaliador de sustentação → intervalo ponderado → ranking
provisório para revisão. O recrutador escreve e revisa requisitos em linguagem
natural. As condições avançadas do legado são opcionais e não participam do
avaliador contextual. A decisão de entrevista continua humana.

O NER não foi removido nem retreinado. Experiências, projetos, formação e idiomas
são preservados independentemente dos rótulos NER. A recuperação restaura o texto
completo da entrada, contexto, fonte, linhas e ID `e<input_index>`; o ID é local à
extração, rastreável pelo hash do texto/configuração. O cosseno ordena a recuperação,
mas não contribui para a nota. Segmentação recompõe continuações conservadoras e
hifenização em atividades e separa novas entradas datadas. PDFs com múltiplas
colunas ou limites ambíguos ainda exigem inspeção; a segmentação não está validada
para todos os formatos.

## Contrato e adaptador

`src/matching/contextual.py` recebe requisito completo, nível e evidências com
contexto. Valida enumerações, estrutura, citações e justificativa. Saídas inválidas,
falha do modelo e ausência de recuperação ficam indeterminadas. O campo `base`
distingue ausência, evidência, contradição e ambiguidade. Instruções no currículo
são dados não confiáveis. Essa instrução de prompt não garante resistência a todas
as injeções: isso também precisa de avaliação humana.

O adaptador Transformers opcional usa `AutoModelForCausalLM`,
`local_files_only=True`, `trust_remote_code=False` e chat template do tokenizer.
Não acessa APIs externas, não presume Ollama e não baixa pesos. A escolha é da
infraestrutura. O primeiro candidato de ensaio é Qwen2.5-1.5B-Instruct: pequeno
para execução local, suporte documentado a português e geração JSON. A documentação
justifica o experimento, não valida sustentação de requisitos. Consulte o
[model card oficial](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct).
A recuperação do ensaio usa paraphrase-multilingual-MiniLM-L12-v2. Ambos têm revisões
fixadas no script de preparação e manifesto local. Não se usa CrossEncoder de relevância
como prova de atendimento. Referência oficial para o formato de mensagens:
[Transformers Chat Templates](https://huggingface.co/docs/transformers/v4.45.1/chat_templating).

O caminho selecionado pelo inicializador usa Qwen3-4B-Instruct-2507 Q4_K_M,
conversão GGUF publicada pela Unsloth, e runtime
oficial llama.cpp b12477 Windows CPU. `src/matching/local_runtime.py` cria seu
próprio processo oculto, escuta somente em 127.0.0.1, desativa proxies no cliente
e encerra o processo na saída. Não depende de Ollama ou servidor previamente
instalado. A saída usa JSON schema com enumeração dos IDs efetivamente recuperados,
seguida pela validação independente do contrato.
Referências: [modelo original Qwen](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
e [conversão GGUF Unsloth](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF).
O modelo maior foi escolhido como segundo candidato porque o ensaio de 1,5B
confundiu evidência de ferramenta relacionada com sustentação de competência
específica. A documentação do modelo original descreve melhorias em seguir
instruções e alinhamento; somente a avaliação pode confirmar adequação aqui.

## Executar o experimento

Foi preparado `.venv-contextual`, separado da `.venv` antiga quebrada, com
Transformers, Sentence Transformers e dependências web. Os pesos públicos foram
baixados para `models/contextual` com autorização, sem envio de currículos.
O equipamento usa CPU. NER treinado e recuperação multilíngue já executaram
com os pesos reais no exemplo sintético. Os dublês de testes verificam contrato,
falhas e pontuação, não interpretação. Nenhum treinamento, push ou alteração remota.

A CPU informa AVX2 e havia somente cerca de 2 GB de RAM livre. O ensaio BF16
foi interrompido por lentidão. O ensaio dinâmico INT8 produziu texto inválido e
foi rejeitado; seus artefatos locais são `reports/contextual-int8-rejected.*`.
Esse caminho INT8 foi removido. O caminho GGUF Q4_K_M reduziu memória e produziu
decisões JSON reais em 62,3 s para quatro requisitos sintéticos, mas apresentou um
falso atendimento grave (competência específica inferida de tecnologia relacionada).
O modelo de 1,5B foi rejeitado; artefatos em `reports/contextual-1_5b-rejected.*`.
Os dois modelos pequenos e o caso exposto são apenas desenvolvimento; o par
relacionado do conjunto de verificação foi substituído antes da execução para
não reutilizar esse caso na verificação. Quantização, runtime e prompt
fazem parte do hash de configuração. A chamada GGUF tem timeout HTTP de 120 s e
limite de 384 tokens; uma resposta incompleta ou falha fica indeterminada. O
adaptador Transformers alternativo usa float32 e requer mais memória; não é o
caminho recomendado para este equipamento.

Para reproduzir a preparação (usa rede apenas para pacotes e pesos públicos):

```powershell
python -m venv --system-site-packages .venv-contextual
.\.venv-contextual\Scripts\python.exe -m pip install -r requirements.contextual.txt
.\.venv-contextual\Scripts\python.exe -m scripts.preparar_modelos_contextuais
.\.venv-contextual\Scripts\python.exe -m scripts.preparar_runtime_contextual
.\.venv-contextual\Scripts\python.exe -m scripts.testar_fluxo_contextual
```

O último comando não acessa banco; grava relatório local em
`reports/contextual-local.json`, com configuração, evidências e decisões reais,
sem assumir rótulos humanos. Por padrão usa currículo sintético versionado.
Para outro TXT local e requisitos JSON use `--input` e `--requirements`.
Saídas brutas do modelo são preservadas em `reports/contextual-local.generations.jsonl`.

### Resultado operacional observado em 17/11/2026

Qwen3-4B-Instruct-2507 Q4_K_M, llama.cpp b12477, prompt contextual-3, CPU AVX2:

| Requisito do exemplo sintético | Decisão real |
| --- | --- |
| Desenvolver APIs com Python | sustentado |
| Graduação concluída em Sistemas de Informação | sustentado |
| Inglês avançado (currículo declara intermediário) | nao_sustentado_pelas_evidencias |
| Administração de Kubernetes (recuperação encontra Docker) | nao_sustentado_pelas_evidencias |

Tempo total 161,0 s, incluindo importação e carga dos três modelos; avaliação por
requisito: 45,0 / 30,3 / 20,2 / 28,8 s. Todas as citações existiam nas entradas.
Pesos 2/2/1/1: mínimo confirmado e máximo possível 66,67%, sem pendências nesse
exemplo. O relatório registra `simulated: false` e `human_validated: false`.
Amostra de quatro casos é insuficiente para validar qualidade; a avaliação com
rótulos revisados permanece pendente. Nenhum currículo real ou banco remoto foi
usado nesse ensaio. O currículo 11 deve ser reprocessado pelo usuário para
inspeção das evidências e limites reais de seu PDF.

Prepare um ambiente funcional com `requirements.txt`, disponibilize pesos instruct
locais e revise os arquivos abaixo, incluindo o rótulo proposto. Marque
`human_reviewed: true` somente depois da revisão. Não ajuste prompt/modelo a partir
do conjunto de verificação; use desenvolvimento e congele a configuração antes
de executar verificação.

- `data/contextual/development.json`
- `data/contextual/verification.json`

```powershell
$manifest = Get-Content models/contextual/manifest.json -Raw | ConvertFrom-Json
$env:CONTEXTUAL_BACKEND = 'llama_cpp'
$env:CONTEXTUAL_MODEL_PATH = $manifest.gguf.path
$env:CONTEXTUAL_MODEL_REVISION = $manifest.gguf.revision
$env:CONTEXTUAL_RUNTIME_PATH = $manifest.gguf.runtime
$env:CONTEXTUAL_RUNTIME_REVISION = $manifest.gguf.runtime_sha256
.\.venv-contextual\Scripts\python.exe -m scripts.avaliar_contextual --annotations data/contextual/development.json --output reports/contextual-development.json
.\.venv-contextual\Scripts\python.exe -m scripts.avaliar_contextual --annotations data/contextual/verification.json --output reports/contextual-verification.json
```

O relatório guarda configuração, decisões por classe, falsos atendimentos,
sustentações perdidas, frequência de indeterminados, validade das saídas/citações
e tempo por par/total. A validade mede aceitação pelo contrato (falhas retornam
indeterminado); não mede se uma citação realmente sustenta a decisão, que exige
anotação humana. Não reutiliza rótulos Hit@k/MRR. Rótulos dos exemplos são propostas,
não verdade validada.

## Integração e ativação

Por padrão continua o avaliador legado. Para ensaio local explícito:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1
```

Somente `sustentado` soma atendimento completo. Parcial e indeterminado ficam
pendentes sem meio ponto. Pesos obrigatório 2 e desejável 1; mínimo confirmado e
máximo possível incluem pendências. `nao_sustentado_pelas_evidencias` descreve o
material recuperado, nunca incapacidade. O resultado mantém o contrato visual
legado e adiciona versão contextual da fórmula, prompt, revisão do modelo,
evidências completas, decisão e campo de revisão humana inicialmente nulo.
O script seleciona o ambiente novo, manifesto e modelos explicitamente; encerre
o servidor anterior antes de executá-lo. Reprocesse o currículo pela interface.
O parâmetro de política vale somente para esse processo PowerShell; não altera
a política permanente do Windows. Foi necessário porque a execução direta de
arquivos .ps1 está bloqueada no equipamento inspecionado.
O hash de configuração invalida resultados anteriores, sem apagar histórico.
Mudanças de pesos locais exigem nova revisão imutável em CONTEXTUAL_MODEL_REVISION.
O ranking existente ordena mínimo confirmado e peso pendente; não decide entrevista.

Antes de ativar no MVP: revisar rótulos independentemente, congelar configuração,
executar verificação real, inspecionar todas as falsas sustentações e citações,
aprovar limites de erro/indeterminação/latência com a equipe e ampliar a amostra.
Como critério inicial proposto: nenhuma citação inventada aceita e nenhum falso
atendimento no pequeno conjunto; isso é necessário, mas insuficiente para produção.
Validar também anonimização, PDFs reais e persistência/histórico em ambiente de
teste autorizado. Ainda **não há validação da interpretação contextual**.

Métricas separadas: NER usa precisão/recall/F1 de entidades; recuperação usa
Hit@k/MRR; avaliador usa decisões por classe e erros de sustentação; aderência é
agregação ponderada dessas decisões, sem percentual de confiança.
