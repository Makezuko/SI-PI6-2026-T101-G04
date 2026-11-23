# Diagnóstico da avaliação documental

## Causa do resultado todo pendente

A versão 3.0 exigia que o texto completo do requisito fosse uma tecnologia do
vocabulário pequeno e que a evidência fosse uma lista composta exclusivamente
por essas tecnologias, com `source=skill`. Textos como “Conhecimento em Python”,
atividades, idiomas, formação e compostos não passavam. A avaliação não recebia
as entradas originais completas. `semantic.compare` já retorna um ranking com
o melhor chunk de cada entrada: não havia um corte exclusivo de Top1 no código.
O problema era a regra restritiva e a falta das entradas completas no avaliador,
não um limiar de cosseno baixo. Top1 SQL não prova ausência de Python.

Na versão 3.1, `app.analysis.analyze` passa tanto o ranking quanto todas as
entradas profissionais anonimizadas ao avaliador. `diagnostic` por requisito
registra regra, número de entradas/candidatos, termos reconhecidos/pendentes e
contextos descartados. Não contém novos logs de dados pessoais. Evidências
selecionadas guardam texto literal e fonte; uma evidência literal sem cosseno
não recebe artificialmente o cosseno do Top1 de outro trecho.

## Reprodução sintética

```powershell
.\venv\Scripts\python.exe -m scripts.diagnosticar_aderencia
```

Fixture: `tests/fixtures/documental_resume.txt`. A recuperação sintética oferece
apenas SQL como Top1 para todos os requisitos, deliberadamente errado para
Python. O diagnóstico completo está em
[examples/diagnostico_documental_sintetico.json](../examples/diagnostico_documental_sintetico.json).

| ID | Requisito | Decisão | Evidência/regra |
|---|---|---|---|
| R1 | Python | atendido | Menção literal, habilidades e uso |
| R2 | SQL com alternativa PostgreSQL | atendido | Condição OU explícita |
| R3 | Pandas e NumPy | atendido | Ambos presentes, condição E |
| R4 | Git e Docker | atendido | Ambos presentes, condição E |
| R5 | Desenvolver APIs em Python | atendido | “Desenvolvi APIs em Python”, experiência |
| R6 | Inglês intermediário | atendido | “Inglês intermediário (B2)”, idiomas |
| R7 | Bacharelado em Sistemas de Informação | atendido | Área e conclusão explícitas, formação |
| R8 | Experiência de cinco anos em liderança | revisão necessária | Duração/liderança não comprovadas por regra |
| R9 | React | revisão necessária | Nenhuma menção suficiente, sem inferência por outra tecnologia |

As condições E/OU são configuradas explicitamente na fixture, não deduzidas
automaticamente de listas. Os pesos permanecem 2/1. Não se exige uma nota
específica de nenhum candidato real.

## Extração e privacidade

O mesmo extrator de seções alimenta o pipeline e a extração de formação; não
há um segundo pipeline. Novos títulos PT/EN impedem que experiência absorva
projetos, habilidades, formação e idiomas. Atividades sem marcadores são
separadas por linha; experiência com marcadores preserva o cabeçalho do emprego.
Janelas por tokens expandem offsets até fronteiras de palavras.

Nomes completos com offsets válidos ou previamente ocultados no cabeçalho pelo
upload são removidos em ocorrências literais completas, com fronteiras, também
em rodapés. Fragmentos NER não geram substituições globais. Campos de habilidades
e formação enviados ao HTML também são extraídos do texto tratado. Isso reduz
vazamentos conhecidos, mas não garante anonimização de nomes não detectados.

Não houve leitura do PDF real, consulta ao banco ou inspeção do JSON da vaga do
teste nesta tarefa. Não é possível afirmar a origem histórica de “xperiência” ou
da formação ausente sem esses dados. O caminho atual foi testado com PDF
sintético e preserva “Experiência”; se o JSON já contém “xperiência”, a interface
aponta o texto salvo e pede correção explícita. Se a descrição menciona formação
e o JSON confirmado não a inclui, aparece alerta de divergência. Nenhum texto
ou requisito é corrigido/adicionado silenciosamente.

## Reanálise e limites

Fórmula `3.1-experimental`; pipeline `web-4-documental-literal-sections`.
Análises anteriores ficam desatualizadas e permanecem no histórico. Revise as
condições na vaga, salve e use **Adicionar / Analisar Currículos**, selecionando
o currículo existente e **Processar Aderência dos Selecionados**. Não precisa
reenviar PDF. Falhas técnicas não são convertidas em ausência de evidência.

O servidor local foi reiniciado e as rotas novas responderam. `python -m app.run`
agora usa o reloader `stat`: nesta pasta do OneDrive, o observador Windows não
havia registrado as mudanças enquanto os templates já estavam atualizados.
Isso evita depender apenas dos eventos de alteração de arquivo.

Permanecem para revisão: negação, hipótese, requisitos compostos sem estrutura,
duração/senioridade, competências comportamentais, atividade não coberta pelas
regras e equivalências acadêmicas/profissionais. As regras de atividade atuais
cobrem uso descrito e desenvolvimento de API na mesma oração; não compõem
palavras dispersas. Evidências com frases quebradas ou seção desconhecida
podem continuar pendentes. Não há LLM/API paga ou troca de modelo.

Verificação: suíte completa com 171 testes, 168 passaram e três erros já
observados anteriormente em `test_expanded_semantic` e `test_semantic_stage`
(anotações com índice -1 e IDs/ordem inconsistentes). Testes novos cobrem
decisões, fontes, condições persistidas, invalidação, apresentação pendente,
PDF PT/EN, nomes repetidos e cobertura/fronteiras de janelas. Não houve teste
de qualidade com modelos reais, push, merge ou SQL remoto.
