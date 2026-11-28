
# ADR-0004 — Estratégia de Implantação do TalentMatch AI

- **Status:** Proposto
- **Data:** 28/11/2026
- **Autor:** Juliana Prado Ferreira

---

## Contexto

O TalentMatch AI é uma aplicação web desenvolvida em Python com Flask, que integra funcionalidades de cadastro, gerenciamento de vagas, upload de currículos e análise de aderência utilizando modelos de inteligência artificial.

O sistema depende de componentes locais para processamento de linguagem natural, recuperação semântica e avaliação contextual, além de serviços externos para persistência de dados e, opcionalmente, geração de justificativas textuais.

A implantação atual está documentada para execução local, com configuração individual dos integrantes, preparação dos modelos e inicialização controlada do servidor.

A equipe necessita de uma estratégia de implantação que permita reproduzir o ambiente, executar o sistema para demonstrações e testes e reduzir problemas relacionados a dependências, modelos e configuração.

## Decisão

Manter a execução local da aplicação como estratégia de implantação do MVP, utilizando ambiente Python isolado, configuração por variáveis de ambiente, modelos preparados localmente e inicialização por script.

O servidor Flask será executado como um único processo, sem habilitação de debug ou reloader, utilizando a porta 5002 por padrão.

A inicialização do fluxo contextual será realizada pelo script `scripts/iniciar_contextual.ps1`, que verifica a existência do ambiente Python, do manifesto de modelos e do runtime contextual antes de iniciar a aplicação.

A persistência e autenticação dependem da configuração do Supabase externo, enquanto a geração de justificativas textuais pode utilizar a API Gemini, de forma opcional.

A estratégia não representa uma implantação em produção. A disponibilização pública, automatização de deploy e configuração de infraestrutura de produção permanecem fora do escopo da implantação atual.

## Alternativas consideradas

**Implantação em servidor de nuvem:** permitiria disponibilizar a aplicação remotamente e centralizar o acesso, mas exigiria configuração de infraestrutura, gerenciamento de modelos, recursos computacionais, segurança e custos operacionais.

**Containerização com Docker:** facilitaria a padronização do ambiente e a reprodução das dependências, mas exigiria configuração e validação adicionais para os modelos locais, runtime contextual e recursos computacionais.

**Arquitetura distribuída com serviços independentes:** permitiria escalar separadamente o processamento de currículos e a aplicação web, porém aumentaria a complexidade operacional e de comunicação entre serviços.

## Justificativa

A execução local permite que os integrantes desenvolvam, testem e demonstrem o sistema sem depender da disponibilidade de uma infraestrutura de produção.

O script de inicialização contextual centraliza a seleção do avaliador, backend, caminhos e revisões dos modelos a partir do manifesto local, reduzindo divergências na configuração do ambiente.

A verificação da identidade do processo durante a opção de reinicialização também evita encerrar processos que não correspondam ao servidor esperado.

Como o processamento contextual depende de modelos e runtimes locais, a implantação em infraestrutura remota exigiria avaliação adicional dos requisitos computacionais, consumo de memória, latência e compatibilidade.

A estratégia atual é adequada ao escopo do MVP e pode ser reavaliada conforme os requisitos de acesso, desempenho e disponibilidade evoluam.

## Consequências positivas

- Menor complexidade de infraestrutura para desenvolvimento e demonstrações.
- Possibilidade de execução controlada em ambiente Python isolado.
- Configuração explícita dos modelos e do backend contextual.
- Redução da dependência de infraestrutura de hospedagem.
- Facilidade de diagnóstico durante a execução local.
- Aproveitamento da estrutura e dos scripts existentes.

## Consequências negativas

- A aplicação não possui disponibilização pública de produção documentada.
- Cada integrante precisa preparar individualmente o ambiente, dependências, modelos e variáveis de configuração.
- A execução local depende dos recursos computacionais disponíveis na máquina.
- A configuração do Supabase e suas políticas de segurança precisam ser validadas no ambiente externo.
- A estratégia atual não oferece escalabilidade horizontal ou alta disponibilidade.
- O script contextual documentado é específico para Windows e PowerShell.

## Evidências

- [README.md](../README.md): documenta instalação, configuração, preparação de modelos, execução local e testes.
- [Script de inicialização contextual](../scripts/iniciar_contextual.ps1): verifica ambiente Python, manifesto e runtime, configura o avaliador e inicia a aplicação.
- [Aplicação Flask](../app/run.py): ponto de entrada do servidor web.
- [Configuração da aplicação](../app/__init__.py): criação e configuração da aplicação Flask.
- [Manifesto contextual](../models/contextual/manifest.json): arquivo utilizado pelo script para identificar modelos e runtime preparados localmente.
- [Configuração do Supabase](../app/supabase_client.py): integração com o banco externo.
- [Configuração de dependências](../requirements.txt) e [dependências contextuais](../requirements.contextual.txt): definem os pacotes necessários para os ambientes de execução.

## Limitações e evolução futura

A estratégia de implantação deverá ser reavaliada caso o sistema passe a exigir acesso remoto, maior disponibilidade, processamento simultâneo de múltiplos currículos ou execução em ambiente de produção.

Como evolução, poderão ser avaliadas containerização, implantação em nuvem, processamento assíncrono e automatização de integração e implantação contínuas (CI/CD), considerando os requisitos computacionais dos modelos, segurança das credenciais, políticas de acesso ao banco e custos operacionais.

