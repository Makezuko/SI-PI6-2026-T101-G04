# Índice de scripts

Execute os comandos na raiz, com o ambiente correspondente ativo. Saídas em `reports/` são locais e podem conter dados pessoais. Os parâmetros disponíveis aparecem com `--help` quando houver CLI.

| Finalidade | Comando | Entradas e modelos / banco |
|---|---|---|
| Iniciar aplicação contextual | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1` | Manifesto e modelos locais; aplicação usa Supabase configurado. |
| Preparar modelos / runtime | `python -m scripts.preparar_modelos_contextuais` e `python -m scripts.preparar_runtime_contextual` | Baixam modelos/runtime; sem banco. Consulte o guia contextual. |
| Ensaiar fluxo contextual | `python -m scripts.testar_fluxo_contextual` | Fixture padrão ou `--input`/`--requirements`; manifesto e modelos locais; sem banco. |
| Avaliar contextual | `python -m scripts.avaliar_contextual --annotations data/contextual/verification.json` | Anotações e modelos locais; sem banco. |
| Diagnósticos contextual / janelas | `python -m scripts.diagnosticar_contextual` / `python -m scripts.diagnosticar_janelas` | Manifesto e modelos locais; fixtures; sem banco. |
| Diagnóstico documental | `python -m scripts.diagnosticar_aderencia` | Fixture sintética; sem modelos ou banco. |
| Processo / login / apresentação | `python -m scripts.inspecionar_processo_contextual --pid PID`; `python -m scripts.diagnosticar_login_local`; `python -m scripts.verificar_apresentacao_aderencia` | Processo local; login consulta Auth configurado; apresentação usa navegador local; veja diagnósticos em `docs/`. |
| Embeddings de exemplo | `python -m scripts.teste_embeddings` | Texto sintético; modelo all-mpnet-base-v2 (768 dimensões), pode baixar; sem banco. |
| Ranking semântico | `python -m scripts.analisar_similaridade --resume reports/resume_embeddings_example.json --requirements examples/requisitos_exemplo.json` | Embeddings e requisitos JSON; carrega o modelo de embeddings; sem banco. |
| Comparar relatórios históricos | `python -m scripts.comparar_relatorios_semanticos --baseline CAMINHO --v4 CAMINHO --output-dir DIRETORIO` | Dois `resultados.json`; sem modelos ou banco; valores padrão reproduzem o experimento CV001. |
| Índice semântico legado 2.1 | `python -m scripts.calcular_aderencia --input examples/aderencia_exemplo.json --output reports/aderencia/resultado.json` | JSON de requisitos e resultados; sem modelos ou banco; preservado para reprodução histórica. |
| Amostra semântica | `python -m scripts.preparar_amostra_real --help`; `python -m scripts.reprocessar_cv_existente --help`; `python -m scripts.preparar_avaliacao_semantica --help`; `python -m scripts.avaliar_amostra_semantica --help` | Dados locais e modelos NER/embeddings; sem banco. Veja `docs/avaliacao-semantica-ampliada.md`. |
| Extrator híbrido | `python -m scripts.avaliar_extrator_hibrido --help` | Currículo/requisitos e modelos NER/embeddings locais; sem banco. |
| Dashboard NER | `streamlit run scripts/dashboard_ner.py` | Lê `reports/ner_consolidated/{baseline,augmented}/<split>/`; sem modelos ou banco. Dependências opcionais: `streamlit`, `pandas`, `plotly`. |

`scripts.avaliacao_semantica` é uma biblioteca auxiliar das avaliações, não uma CLI.
