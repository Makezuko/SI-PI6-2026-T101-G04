# ADR-0001 — Manutenção de uma aplicação web modular

**Status:** Proposto

**Data:** A definir pelo grupo

## Contexto

O TalentMatch AI é desenvolvido como uma aplicação web em Python com Flask, utilizando módulos para gerenciamento de vagas, currículos, persistência e processamento de linguagem natural.

O projeto precisa evoluir para atender novos requisitos e demonstrar boas práticas de arquitetura, mantendo uma estrutura compreensível e viável para a equipe.

## Decisão

Propõe-se manter a aplicação como um monólito modular, aprimorando a separação de responsabilidades entre os módulos existentes.

As melhorias deverão priorizar a organização das regras de negócio, a redução do acoplamento com a persistência e a testabilidade dos componentes.

## Alternativas consideradas

**Microsserviços:** oferecem independência de implantação, mas introduzem complexidade operacional e de comunicação.

**Arquitetura orientada a eventos como estrutura principal:** pode beneficiar operações assíncronas, mas exige mecanismos adicionais de mensageria, tratamento de falhas e consistência.

## Justificativa

A evolução incremental da arquitetura existente permite que a equipe implemente melhorias reais sem reescrever todo o sistema.

Essa decisão busca equilibrar manutenibilidade, simplicidade de desenvolvimento e custo de implementação.

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

Adicionar links para os Pull Requests de refatoração, testes e documentação relacionados à decisão.