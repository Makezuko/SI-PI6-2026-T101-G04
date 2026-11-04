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