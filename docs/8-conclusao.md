# 8. Conclusão

## 8.1 Considerações finais

O desenvolvimento do TalentMatch AI teve como objetivo apoiar o processo de recrutamento e seleção por meio da análise de currículos e da identificação de compatibilidade entre candidatos e requisitos de vagas. O sistema já possuía funcionalidades de gerenciamento de vagas, currículos e processamento de linguagem natural antes do início das atividades da disciplina de Arquitetura de Software.

Durante a disciplina, o trabalho concentrou-se na análise da arquitetura existente e na implementação de melhorias que favorecessem a manutenibilidade, a organização dos componentes, a extensibilidade e a qualidade do software, sem exigir uma reestruturação completa da aplicação.

## 8.2 Resultados alcançados

A análise arquitetural identificou o sistema como uma aplicação monolítica modular desenvolvida em Flask, com responsabilidades distribuídas entre aplicação web, processamento, persistência e testes.

A partir dessa análise, foram realizadas melhorias e documentadas decisões relacionadas à evolução da arquitetura, incluindo:

- Separação de responsabilidades por meio de refatorações pontuais.
- Aplicação de princípios SOLID em componentes identificados.
- Implementação de padrões de projeto GoF em etapas do processamento de currículos.
- Criação e manutenção de testes automatizados para verificar comportamentos e contratos.
- Documentação das decisões arquiteturais por meio de ADRs.
- Análise e documentação de atributos de qualidade, considerando segurança, manutenibilidade e desempenho.
- Documentação do padrão transversal de observabilidade, incluindo rastreamento de execuções e eventos técnicos.
- Organização da documentação técnica e dos procedimentos de execução do projeto.

As melhorias realizadas contribuíram para tornar partes do sistema mais organizadas, testáveis e extensíveis, permitindo que novas funcionalidades e alterações sejam incorporadas de maneira mais controlada.

## 8.3 Contribuições arquiteturais

A aplicação dos princípios SOLID e dos padrões GoF permitiu identificar e tratar pontos de acoplamento presentes no sistema.

A extração da função `format_display_date()` contribuiu para a centralização de uma responsabilidade compartilhada, evitando duplicação de lógica de formatação e possibilitando a validação de seu comportamento por testes automatizados.

A implementação do padrão Strategy no cálculo de aderência documental possibilitou a utilização de diferentes estratégias de pontuação por meio de um contrato comum. Essa abordagem favorece a extensão das regras de cálculo sem exigir alterações diretas na função central.

O padrão Factory Method foi aplicado à criação dos adaptadores de avaliação contextual, reduzindo o acoplamento entre o fluxo de processamento e os backends de inferência.

O padrão Facade foi utilizado para centralizar a orquestração do pipeline de análise de currículos, reunindo etapas de extração, anonimização, processamento semântico, avaliação contextual e geração de justificativas.

Essas mudanças demonstram como princípios e padrões arquiteturais podem ser aplicados a problemas concretos do sistema, contribuindo para sua evolução incremental.

## 8.4 Qualidade e validação

Os testes automatizados foram utilizados para verificar comportamentos específicos das refatorações, regras de cálculo, contratos entre estratégias e etapas do processamento contextual.

As suítes documentadas apresentam resultados positivos para os testes específicos de SOLID, aderência e processamento contextual. Durante a execução adicional de testes de integração da aplicação web, entretanto, foram identificadas falhas e erros que ainda precisam ser investigados.

Assim, embora existam evidências de validação de componentes específicos, a aprovação integral da suíte de testes e a validação de todos os atributos de qualidade ainda não podem ser consideradas concluídas.

A documentação das decisões arquiteturais também permitiu registrar justificativas, alternativas consideradas, consequências e limitações, contribuindo para a rastreabilidade das mudanças realizadas.

## 8.5 Limitações e trabalhos futuros

O TalentMatch AI permanece em estágio de MVP, com execução local documentada e dependência de serviços externos para persistência e autenticação. A arquitetura atual atende ao contexto de desenvolvimento e demonstração, mas ainda apresenta oportunidades de evolução.

Entre os trabalhos futuros, destacam-se:

- Investigar e corrigir falhas identificadas nos testes de integração.
- Ampliar a separação entre regras de negócio e infraestrutura.
- Evoluir os contratos de persistência para reduzir o acoplamento à API concreta do Supabase.
- Fortalecer a validação das políticas de autenticação, autorização e acesso aos dados.
- Avaliar o desempenho das operações de análise por meio de medições quantitativas.
- Investigar estratégias de processamento assíncrono para tarefas computacionalmente intensivas.
- Avaliar containerização e implantação em infraestrutura remota, conforme a necessidade de disponibilização do sistema.
- Ampliar a cobertura de testes automatizados e a validação de cenários de integração.

## 8.6 Conclusão

O trabalho realizado demonstrou a importância da análise arquitetural e da aplicação gradual de boas práticas de engenharia de software em um sistema existente.

As refatorações, os padrões de projeto, os testes automatizados e a documentação arquitetural contribuíram para melhorar a organização e a capacidade de evolução do TalentMatch AI, mantendo as funcionalidades previamente desenvolvidas.

A abordagem incremental adotada permitiu realizar melhorias sem exigir uma reestruturação completa do sistema, evidenciando que decisões arquiteturais fundamentadas, acompanhadas de testes e documentação, são essenciais para a manutenção e evolução contínua de aplicações de software.

Dessa forma, o projeto alcançou avanços na organização arquitetural e na qualidade de seus componentes, mantendo como objetivo futuro a validação mais abrangente dos requisitos de qualidade e a evolução de sua estrutura conforme novas necessidades sejam identificadas.
