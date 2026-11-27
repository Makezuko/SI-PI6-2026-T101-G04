# ADR 0003: organizar o núcleo de análise em fachada, fábricas e estratégias dentro do monólito modular

**Status:** proposto

**Contexto:** O TalentMatch AI opera como uma única aplicação Python/Flask, definida no ADR 0001, mas cresceu com estágios acoplados entre `app/analysis.py`, `src/data/`, `src/nlp/` e `src/matching/`. Cada requisição de análise precisava coordenar diretamente NER, anonimização, embeddings, escolha de runtime local do avaliador contextual, cálculo ponderado de aderência e justificativa via Gemini. A equipe de cinco integrantes precisava reduzir esse acoplamento interno e tornar o fluxo testável sem introduzir serviços distribuídos nem quebrar os contratos existentes da interface web.

**Decisão:** Organizar a aplicação internamente em camadas na borda web (`app/routes.py`, `app/repositories.py`, `app/analysis.py`) e módulos especializados no núcleo (`src/data/`, `src/nlp/`, `src/matching/`), concentrando a orquestração do pipeline na fachada `TalentMatchPipelineFacade`, a criação de adaptadores em `ContextualAdapterFactory` e as políticas de pontuação em `AdherenceScoreStrategy`.

**Alternativas consideradas:**
- Manter toda a orquestração procedural em `app/analysis.py` e condicionais diretas nos módulos de matching: descartada porque cada novo runtime ou política de pontuação obrigava alterar código já validado e dificultava testes unitários isolados.
- Adotar arquitetura hexagonal completa com portas e adaptadores para todos os módulos e repositórios: descartada neste estágio porque acrescentaria cerimônia e tradução de modelos em fluxos simples de cadastro que não justificam esse custo.
- Extrair o processamento de NLP e LLM contextual para um serviço separado em rede: descartada porque exigiria filas, contratos remotos e operação distribuída antes de existir gargalo de escala comprovado.

**Consequências:**
- Positivas: separação clara entre borda web, persistência e núcleo de IA; redução do acoplamento direto de `app/analysis.py` para uma interface única; testes unitários rápidos dos estágios sem subir servidor ou modelos reais; documentação fiel em `docs/3-arquitetura.md` e `diagrams/`.
- Negativas: aumento do número de arquivos e níveis de indireção em `src/matching/`; ausência atual de função de aptidão automática (como `import-linter`) no pipeline, deixando a vigilância das fronteiras entre `app/` e `src/` dependente da revisão dos Pull Requests.

**Implementação e referência:** Documentação arquitetural e diagramas estruturais em [docs/3-arquitetura.md](../docs/3-arquitetura.md) e pasta `diagrams/` *(inserir link do PR após abertura na main)*.
