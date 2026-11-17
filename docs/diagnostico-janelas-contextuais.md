# Correção de janelas em 17/11/2026

O log da execução `c8672868beeb450ab9aba110432a4880` não continha traceback.
Não é possível atribuir retrospectivamente sua exceção a uma linha específica.
Nenhum dado da vaga 10 ou do currículo 12 foi consultado remotamente.

Antes da correção, o tokenizer local real reproduziu `ValueError` em
`src/nlp/embeddings.py`, função `_split_text`, linha 106: o trecho expandido
para completar palavras ultrapassava o limite ao ser retokenizado. O modelo
multilíngue tem limite de 128 tokens, incluindo especiais; a janela nominal era
126. Reproduziu-se tanto com frases repetidas quanto com palavras compostas
longas. Também foi confirmado o bloqueio independente em `analyze`: mais de uma
janela por requisito era rejeitada, pedindo alteração da vaga.

A divisão agora reduz o intervalo e verifica a retokenização antes de codificar.
Prefere limites de palavras; uma palavra que sozinha excede o orçamento precisa
ser dividida. Os offsets permanecem no texto original, com sobreposição e sem
lacunas. Não há truncamento no tokenizer. Todos os trechos continuam disponíveis
à recuperação de evidências.

Para requisitos, cada janela contribui igualmente para a média de seus vetores;
o vetor médio recebe normalização L2. O agrupamento usa `input_index`, confere
`requirement_id` e retorna exatamente uma linha por requisito na ordem original.
Janelas ausentes, IDs incompatíveis, matrizes inválidas e vetores médios nulos
falham tecnicamente. A recuperação de evidências mantém seu máximo por entrada.
Essa média pode diluir temas de requisitos extensos; não constitui validação de
qualidade semântica. Fórmula, pesos, critérios, prompt e modelo foram preservados.
O pipeline `web-8-contextual-window-mean` invalida o reaproveitamento de resultados
anteriores com outra estratégia, sem apagar histórico.

`ANALYSIS_STAGE_START/END` identifica extração de entradas, embeddings de requisitos,
validação de janelas, embeddings de evidências e comparação semântica.
`ANALYSIS_SHAPE` registra somente quantidades e dimensões. Em falha,
`ANALYSIS_STAGE_ERROR` inclui tipo, arquivo, função e linha, sem mensagem bruta,
texto, código-fonte, variáveis locais ou credenciais. O erro exibido após o POST
inclui o ID da execução; não grava nova análise concluída nem chama legado.

Validação: 196 testes aprovados, incluindo limites retokenizados, cobertura de
palavra maior que o orçamento, agrupamento fora de ordem, IDs, valores inválidos,
sanitização de traceback e POST de currículo existente que falha nos embeddings,
mostra execução na tela e não salva nem chama o avaliador. Flask e persistência
nesse teste são simulados.

Reprodução independente, sem banco, com embeddings reais:

```powershell
.\.venv-contextual\Scripts\python.exe -m scripts.diagnosticar_janelas
```

Fixture sintética: dois requisitos (um longo), currículo com duas páginas
separadas por form-feed. Resultado: 14 janelas de requisitos, 40 de evidências,
384 dimensões, limite 128 respeitado em todas as janelas, cobertura integral e
IDs R1/R2 preservados. Tempo total observado: 5,236 s incluindo carga do modelo.
Resumo local em `reports/window-real.json`. Não é inferência do avaliador LLM
nem validação do banco real.

Servidor reiniciado na mesma porta 5002 e no mesmo ambiente, PID observado 35452.
Comando de reinício na raiz:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1 -Restart
```

Resta o teste autenticado: entre em http://127.0.0.1:5002/login e abra
http://127.0.0.1:5002/vagas/10/adicionar-curriculos. Selecione somente o currículo
existente 12 e clique em **Processar Aderência dos Selecionados**. Não reenvie PDF.
Abra http://127.0.0.1:5002/vagas/10/candidato/12. No terminal, confira as etapas,
`MODEL_CALL_START/END`, `VALIDATION_OK`, `ANALYSIS_SAVED` e `ANALYSIS_SELECTED` com
o ID persistido correspondente. Esse teste é necessário para confirmar o caso
original e a integração autenticada; em nova falha, o traceback sanitizado agora
permite identificar a linha exata.
