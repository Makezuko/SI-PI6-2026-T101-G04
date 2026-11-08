# 1. Contexto do Sistema — TalentMatch AI

## 1.1 Visão geral

O TalentMatch AI é uma aplicação web desenvolvida em Python, utilizando o framework Flask, para apoiar o processo de recrutamento e seleção de candidatos.

O sistema busca facilitar o gerenciamento de vagas e currículos e utiliza técnicas de processamento de linguagem natural para comparar informações de candidatos com os requisitos de oportunidades profissionais.

## 1.2 Problema a ser resolvido

Processos de recrutamento podem envolver grandes quantidades de currículos, tornando a triagem manual demorada e dificultando a comparação consistente entre candidatos e vagas.

O TalentMatch AI busca apoiar os recrutadores, permitindo organizar os dados e fornecer análises de compatibilidade sem substituir a avaliação humana.

## 1.3 Objetivos

- Permitir o cadastro e gerenciamento de vagas.
- Organizar currículos associados às vagas.
- Extrair e processar informações textuais de currículos.
- Identificar competências e requisitos profissionais.
- Calcular indicadores de compatibilidade semântica entre requisitos e evidências dos currículos.
- Apoiar a tomada de decisão dos responsáveis pelo recrutamento.

## 1.4 Atores envolvidos

**Recrutador:** utiliza a aplicação para gerenciar vagas, consultar currículos e analisar candidatos.

**Administrador ou responsável técnico:** configura e mantém a aplicação, suas integrações e o armazenamento de dados.

**Candidato:** pessoa cujas informações profissionais são analisadas. Sua participação direta no sistema depende das funcionalidades disponíveis na aplicação.

## 1.5 Tecnologias e componentes

- **Python:** linguagem utilizada no backend e no processamento de dados.
- **Flask:** framework responsável pela aplicação web e suas rotas.
- **Supabase:** serviço utilizado para autenticação e persistência.
- **NLP e embeddings:** técnicas utilizadas para extração de competências e comparação semântica.
- **HTML e templates:** apresentação das informações ao usuário.

## 1.6 Limites do sistema

O TalentMatch AI é responsável pela aplicação de recrutamento, processamento dos currículos e apresentação dos resultados.

O armazenamento e a autenticação dependem de um serviço externo, o Supabase.

A análise de compatibilidade fornece informações de apoio, mas não deve ser interpretada como decisão automática de contratação.

## 1.7 Escopo do trabalho de Arquitetura de Software

Este trabalho analisa a arquitetura existente do TalentMatch AI e propõe melhorias de organização, manutenção, qualidade e extensibilidade, aplicando princípios SOLID, Clean Code, padrões GoF e práticas de documentação arquitetural.

## 1.8 O que já existia no Projeto Integrador e o que mudou

O TalentMatch AI já estava sendo desenvolvido como parte do Projeto Integrador, com o objetivo de apoiar processos de recrutamento e seleção por meio de uma aplicação web.

Antes do trabalho específico da disciplina de Arquitetura de Software, o projeto já contava com uma estrutura em Python e Flask, integração com o Supabase, funcionalidades relacionadas ao gerenciamento de vagas e currículos e módulos de processamento de linguagem natural e análise de compatibilidade semântica.

Portanto, essas funcionalidades não foram criadas especificamente para a disciplina de Arquitetura de Software, mas aproveitadas como base para a análise e evolução do sistema.

### Melhorias realizadas na disciplina de Arquitetura de Software

A partir do sistema existente, foram iniciadas as seguintes melhorias:

- **Documentação do contexto:** identificação do problema, objetivos, atores envolvidos, tecnologias e limites do sistema.
- **Análise dos atributos de qualidade:** definição de prioridades relacionadas à segurança, manutenibilidade e desempenho.
- **Documentação arquitetural:** descrição da organização modular do sistema e análise de alternativas arquiteturais.
- **Registro de decisões:** criação do ADR-0001, que propõe a manutenção de uma aplicação web modular e a melhoria gradual da separação de responsabilidades.
- **Refatoração orientada a SOLID:** extração da função `format_display_date()` para centralizar a formatação de datas utilizada na apresentação de vagas e currículos.
- **Testes automatizados:** inclusão de testes para verificar a preservação do comportamento da formatação de datas.

As alterações da disciplina buscam melhorar a organização, a compreensão e a manutenção do código existente, sem substituir a arquitetura do Projeto Integrador ou reimplementar suas funcionalidades principais.

### Evidências das contribuições

- [PR #21 — Contexto e atributos de qualidade](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/21)
- [PR #22 — Documentação arquitetural e ADR-0001](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/22)
- [PR #23 — Refatoração SRP, testes e documentação SOLID](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/23)

As demais melhorias previstas para a disciplina serão documentadas conforme forem implementadas e validadas pelos integrantes do grupo.