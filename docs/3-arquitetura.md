# 3. Arquitetura do Sistema — TalentMatch AI

## 3.1 Estilo arquitetural

O TalentMatch AI é uma aplicação web desenvolvida com Flask, organizada em módulos Python que possuem responsabilidades distintas.

A estrutura atual apresenta características de uma arquitetura monolítica modular, pois as funcionalidades principais pertencem a uma mesma aplicação, mas são distribuídas entre diferentes módulos.

A organização por responsabilidades permite analisar e evoluir partes do sistema sem exigir a criação de serviços independentes.

## 3.2 Componentes principais

### Aplicação web — `app/`

Contém a configuração do Flask, as rotas HTTP, a validação de formulários, a integração com a persistência e o gerenciamento de sessões.

### Processamento e análise — `src/`

Contém funcionalidades relacionadas à preparação de dados, extração de informações, processamento de linguagem natural e comparação semântica.

### Persistência — Supabase

Serviço externo utilizado para armazenar informações e apoiar a autenticação.

O módulo `app/repositories.py` reúne operações de acesso aos dados e adapta informações para utilização na aplicação.

### Testes — `tests/`

Contém testes automatizados utilizados para verificar o comportamento de partes do sistema.

## 3.3 Justificativa arquitetural

A manutenção de uma aplicação web modular é adequada ao estágio atual do TalentMatch AI porque permite aproveitar a implementação existente e evoluir seus componentes gradualmente.

Entre as vantagens estão a simplicidade de desenvolvimento, a possibilidade de reutilização de funções e a facilidade de execução local.

Entretanto, é necessário controlar o acoplamento entre rotas, regras de negócio, persistência e processamento de linguagem natural.

## 3.4 Alternativas consideradas

### Microsserviços

A divisão em serviços independentes poderia permitir implantação e escalabilidade específicas.

Entretanto, exigiria maior complexidade operacional, comunicação entre serviços e gerenciamento distribuído, sem uma necessidade comprovada neste estágio do projeto.

### Arquitetura totalmente orientada a eventos

Uma arquitetura orientada a eventos poderia ser interessante para o processamento assíncrono de currículos.

Entretanto, sua adoção como arquitetura principal introduziria filas, tratamento de falhas e consistência eventual, aumentando a complexidade do sistema.

## 3.5 Melhorias arquiteturais propostas

- Reduzir a mistura de responsabilidades nas rotas.
- Melhorar a separação entre regras de negócio e persistência.
- Aplicar princípios SOLID em pontos identificados no código.
- Criar testes que comprovem o comportamento das alterações.
- Documentar decisões relevantes por meio de ADRs.

## 3.6 Diagramas arquiteturais

Os diagramas serão desenvolvidos em conjunto com Matias e deverão representar o estado real do sistema.

- C4 — Contexto.
- C4 — Contêineres.
- C4 — Componentes.
- Diagrama de sequência do fluxo de análise de currículo.

Os arquivos serão armazenados na pasta `diagrams/` e referenciados nesta documentação.