# ADR-0001 — Manutenção de uma aplicação web modular

**Status:** Proposto

**Data:** A definir pelo grupo

## Contexto

O TalentMatch AI é desenvolvido como uma aplicação web em Python com Flask, utilizando módulos para gerenciamento de vagas, currículos, persistência e processamento de linguagem natural.

O projeto precisa evoluir para atender novos requisitos e demonstrar boas práticas de arquitetura, mantendo uma estrutura compreensível e viável para a equipe.

## Decisão

Propõe-se manter o TalentMatch AI como uma aplicação monolítica, com uma única unidade principal de execução, e evoluir gradualmente sua organização interna para uma arquitetura mais modular.

A evolução deverá priorizar a separação das responsabilidades de gerenciamento de vagas, currículos e análise de compatibilidade, reduzindo o acoplamento entre rotas, regras de negócio e persistência.

As fronteiras entre módulos deverão ser explicitadas e verificadas progressivamente por meio de testes e regras de dependência, sem exigir a adoção imediata de microsserviços ou a reescrita das funcionalidades existentes.

Essa decisão representa uma evolução arquitetural proposta. A organização atual já apresenta separação inicial em módulos Python, mas ainda não possui todas as fronteiras exigidas por um monólito modular rigoroso.

## Alternativas consideradas

**Microsserviços:** oferecem independência de implantação, mas introduzem complexidade operacional e de comunicação.

**Arquitetura orientada a eventos como estrutura principal:** pode beneficiar operações assíncronas, mas exige mecanismos adicionais de mensageria, tratamento de falhas e consistência.

## Justificativa

A aplicação já reúne as rotas Flask em `app/`, o acesso ao Supabase em `app/repositories.py` e funções de preparação de dados e processamento de linguagem em `src/`. No fluxo de upload, a rota chama diretamente a extração do PDF e a persistência, sem comunicação entre serviços internos. Manter essa estrutura permite melhorar a separação de responsabilidades sem reescrever o fluxo existente.

O projeto é desenvolvido em grupo, com configuração e execução locais documentadas para os integrantes. Manter uma única aplicação reduz o trabalho de configuração e coordenação de implantações enquanto a equipe evolui e testa as funcionalidades. Não há, no estado documentado do projeto, uma necessidade comprovada de implantar vagas, currículos e processamento de forma independente; essa necessidade deve ser reavaliada se os ciclos de evolução dos componentes passarem a divergir.

O processamento de currículos pode se tornar o principal limite de capacidade: a rota atual percorre os PDFs enviados e extrai o texto durante a requisição, enquanto os módulos de NLP e comparação semântica podem demandar recursos adicionais. Ainda não há medições de carga suficientes para justificar uma separação em serviços. Se o volume ou a latência se tornarem um problema, a equipe deverá medir o fluxo e avaliar processamento assíncrono, filas ou uma implantação separada para essa etapa, considerando também o custo operacional e o tratamento de falhas.

## Consequências positivas

- Aproveitamento do código existente.
- Menor complexidade de implantação.
- Possibilidade de refatoração gradual.
- Maior facilidade para executar testes locais.

## Consequências negativas

- Os módulos continuam compartilhando o mesmo processo de aplicação.
- O isolamento de falhas é menor do que em serviços independentes.
- A equipe precisará monitorar o acoplamento entre componentes.

## Evidências

- [Configuração da aplicação Flask e registro das rotas](../app/__init__.py) e [instruções de execução local](../README.md#executar): mostram a aplicação web e como iniciá-la.
- [Rota de upload de currículos](../app/routes.py): a função `adicionar_curriculos` percorre os arquivos, chama `parse_resume_pdf` e usa `create_resume` na mesma requisição.
- [Repositórios](../app/repositories.py), [extração e limpeza de dados](../src/data/clean.py) e [comparação semântica](../src/matching/semantic.py): ilustram as responsabilidades já distribuídas em módulos Python e a integração externa com o Supabase.
- [Testes de upload de PDF](../tests/test_pdf_upload.py) e [testes da etapa semântica](../tests/test_semantic_stage.py): exemplificam a verificação de componentes. Esses testes não comprovam capacidade sob carga nem eliminam a necessidade de testes de integração.
