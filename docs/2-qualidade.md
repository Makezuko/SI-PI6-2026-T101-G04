# 2. Atributos de Qualidade — TalentMatch AI

## 2.1 Manutenibilidade

A manutenibilidade representa a facilidade de corrigir problemas, modificar funcionalidades e evoluir o sistema.

No TalentMatch AI, esse atributo é importante porque o projeto possui funcionalidades distintas, como gerenciamento de vagas, processamento de currículos e análise semântica.

**Medidas propostas:**
- Separar regras de negócio das rotas e da persistência.
- Criar testes automatizados para regras importantes.
- Aplicar princípios SOLID e padrões de projeto quando justificáveis.
- Manter documentação das decisões arquiteturais.

**Cenário de qualidade:** quando uma regra de validação de vaga precisar mudar, a alteração deverá ficar concentrada no módulo responsável e os testes relacionados deverão continuar passando.

**Trade-off:** uma organização mais modular pode aumentar a quantidade de arquivos e concentração, mas tende a facilitar alterações futuras.

## 2.2 Segurança

A segurança busca proteger informações de usuários e candidatos e impedir acessos não autorizados.

O TalentMatch AI lida com currículos e informações pessoais, tornando esse atributo especialmente relevante.

**Medidas propostas:**
- Utilizar autenticação e políticas de acesso do Supabase.
- Manter credenciais e configurações sensíveis fora do repositório.
- Validar dados recebidos pela aplicação.
- Restringir o acesso às informações conforme as permissões do usuário.

**Cenário de qualidade:** um usuário não autorizado não deverá conseguir consultar informações de vagas ou currículos protegidos.

**Trade-off:** verificações de autenticação e autorização aumentam a complexidade do código e exigem testes adicionais, mas reduzem riscos de acesso indevido.

## 2.3 Desempenho

O desempenho representa a capacidade de executar operações em tempo adequado.

No TalentMatch AI, algumas operações de processamento de linguagem natural podem exigir mais recursos computacionais do que operações comuns de cadastro e consulta.

**Medidas propostas:**
- Evitar processamento repetido quando não for necessário.
- Separar operações de consulta de etapas computacionalmente intensivas.
- Medir o tempo das operações de análise de currículos.
- Avaliar otimizações com base em testes e medições.

**Cenário de qualidade:** ao consultar uma vaga já cadastrada, o sistema deverá responder sem executar novamente etapas de análise semântica desnecessárias.

**Trade-off:** otimizações como cache e processamento assíncrono podem melhorar o tempo de resposta, mas aumentam a complexidade e exigem controle da atualização dos dados.

## 2.4 Priorização

A prioridade inicial proposta para o projeto é:

1. Segurança, devido ao tratamento de informações pessoais.
2. Manutenibilidade, devido à evolução contínua do sistema.
3. Desempenho, devido ao processamento de currículos e às análises semânticas.

Essa priorização orientará a avaliação das decisões arquiteturais e poderá ser revisada conforme os resultados dos testes.