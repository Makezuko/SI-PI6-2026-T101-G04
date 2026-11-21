# ADR-0005: Estratégia Extensível de Aderência, Fábrica Contextual e Fachada de Análise

- **Status:** Aceito
- **Data:** 21/11/2026
- **Autor:** Kauê Farias Lourenço
- **PR de implementação:** [PR #34](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/34)

---

## Contexto

Com a consolidação do avaliador contextual local com Qwen (`src/matching/contextual.py`), da aderência documental (`3.1-experimental` em `src/matching/adherence.py`) e da justificativa via Gemini (`src/matching/llm_justification.py`), o núcleo de análise do **TalentMatch AI** passou a apresentar três acoplamentos relevantes:

1. Em `src/matching/adherence.py`, `calculate_adherence()` fixava uma única política de cálculo de pontuação documental, impedindo extensões sem editar a função central.
2. Em `src/matching/contextual.py`, `create_adapter()` selecionava os backends (`transformers` e `llama_cpp`) via condicionais rígidas `if/elif`.
3. Em `app/analysis.py`, `analyze()` coordenava diretamente extração NER, anonimização, geração de embeddings em janela, recuperação semântica, avaliação contextual com Qwen, telemetria e geração de justificativa via Gemini.

## Decisão

Aplicar três padrões GoF complementares sobre o fluxo contextual atual de `src/matching/` e `app/analysis.py`:

1. **Strategy (`AdherenceScoreStrategy` em `src/matching/aggregators.py`):** encapsular políticas de cálculo de aderência (`WeightedConfirmedAdherence`, `StrictMandatoryAdherence`, `ProvisionalWeightedAdherence`) preservando `WeightedConfirmedAdherence` (`3.1-experimental`) como padrão em `calculate_adherence()` e propagando `strategy` via `evaluate_batch()`.
2. **Factory Method (`ContextualAdapterFactory` em `src/matching/factory.py`):** substituir a seleção condicional direta em `src/matching/contextual.py` por fábricas concretas (`TransformersAdapterFactory`, `LlamaCppAdapterFactory`).
3. **Facade (`TalentMatchPipelineFacade` em `src/matching/facade.py`):** unificar a orquestração completa do pipeline contextual (NER, anonimização, embeddings, avaliador contextual Qwen e justificativa Gemini) por trás de `analyze_resume()`.

## Alternativas Consideradas e Motivo do Descarte

- **Refatorar a fórmula legada em `src/matching/score.py`:** descartado porque a aplicação atual opera exclusivamente sobre o avaliador contextual e `aderencia_documental` (`3.1-experimental`); `score.py` permanece apenas para reprodução histórica.
- **Manter condicionais `if/elif` em `calculate_adherence()` e `create_adapter()`, e toda a orquestração em `app/analysis.py`:** descartado por violar OCP e manter alto acoplamento entre a camada web e os módulos de IA/privacidade.

## Consequências

### Positivas
- Extensão segura da aderência documental sem risco de regressão na fórmula `3.1-experimental`.
- Criação extensível dos adaptadores contextuais (`transformers` e `llama_cpp`).
- Desacoplamento da camada `app/analysis.py` em relação às etapas internas de NLP, privacidade, Qwen e Gemini, validado por suítes dedicadas (`tests/test_gof_patterns.py` e `tests/test_solid_matching.py`).

### Negativas
- Aumento do número de módulos em `src/matching/` (`aggregators.py`, `factory.py`, `facade.py`).
- Um nível adicional de indireção para rastrear a fábrica ou estratégia ativa em tempo de execução.
