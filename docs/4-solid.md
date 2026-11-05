# 4. Aplicação e análise dos princípios SOLID

Esta análise considera o código disponível na branch `refactor/ana-solid-srp`, em 04/11/2026. O objetivo é registrar evidências e limitações, sem criar uma nova arquitetura. A alteração de produção está restrita à apresentação de datas em [app/repositories.py](../app/repositories.py).

## 4.1 SRP — Princípio da Responsabilidade Única

O SRP recomenda que uma unidade de código tenha uma responsabilidade coesa e um motivo principal para mudar.

No código original, `job_for_template()` e `resume_for_template()` repetiam a conversão de datas ISO para o formato `DD/MM/AAAA`, incluindo o tratamento de valores ausentes e inválidos. Uma mudança nessa regra exigia modificar dois locais.

Foi extraída a função `format_display_date(value)` em [app/repositories.py](../app/repositories.py). As duas funções de transformação passaram a utilizá-la. O tratamento do sufixo `Z`, as exceções `ValueError` e `AttributeError` e o retorno `—` foram preservados. A data continua sendo apresentada conforme o valor recebido, sem conversão de fuso horário.

Essa mudança centraliza a regra de apresentação e permite testá-la diretamente. É uma evidência pontual de aplicação de SRP, mas não torna todo o módulo aderente ao princípio. O módulo ainda reúne consultas ao Supabase, validação de vagas, preparação de requisitos, extração de informações dos currículos e montagem de dados para templates. Uma separação futura entre persistência e apresentação deverá ser avaliada em outra tarefa.

Os testes de [tests/test_format_display_date.py](../tests/test_format_display_date.py) verificam datas ISO, `None`, texto vazio, entradas inválidas e sufixo `Z`. Também verificam os campos `created_at` e `submitted_at` nas transformações, inclusive quando as chaves de data estão ausentes. Os currículos usados nesses testes têm texto vazio, dispensando extratores e serviços externos. Nenhum outro campo retornado foi modificado.

## 4.2 OCP — Princípio Aberto/Fechado

O OCP propõe que seja possível estender comportamentos sem modificar a lógica central já validada.

Em [src/matching/semantic.py](../src/matching/semantic.py), `compare()` compara vetores e organiza evidências. Em [src/matching/score.py](../src/matching/score.py), `calculate_similarity_index()` agrega os resultados. Há separação entre essas etapas, e os pesos podem ser configurados pelo argumento `weights`. O teste `ScoreTests.test_weights_and_levels`, em [tests/test_score.py](../tests/test_score.py), verifica essa configuração.

Entretanto, configurar pesos não equivale a adicionar um novo algoritmo. Não foi identificado nesses módulos um contrato de extensão com implementações alternativas: uma nova fórmula ou forma de comparação exigiria alterar a implementação ou estabelecer outro ponto de composição. Portanto, OCP para inclusão de novos comportamentos de matching permanece pendente. Uma melhoria futura seria definir um contrato de extensão quando existir uma necessidade real, em coordenação com o integrante responsável pelos padrões de projeto. Nenhum padrão Strategy ou Factory foi implementado nesta tarefa.

## 4.3 LSP — Princípio da Substituição de Liskov

O LSP determina que implementações de uma abstração possam substituir umas às outras sem violar o contrato esperado pelos consumidores, incluindo entradas, saídas e condições de erro.

Não foram encontradas abstrações com múltiplas implementações substituíveis em `src/matching/`. O teste `ScoreTests.test_actual_compare_contract`, em [tests/test_score.py](../tests/test_score.py), verifica que a saída real de `compare()` pode alimentar `calculate_similarity_index()`. Isso comprova compatibilidade entre etapas, mas não comprova substituição entre implementações de uma abstração.

Em [tests/test_web_filters.py](../tests/test_web_filters.py), `FakeClient` e `FakeQuery` simulam parte da API do Supabase. Essa substituição é útil para testes, porém não demonstra equivalência de todos os comportamentos do cliente real, especialmente autorização e erros do serviço. Assim, LSP não está demonstrado de forma suficiente no escopo analisado. Se surgirem implementações alternativas, a melhoria necessária será explicitar o contrato e executar os mesmos testes de contrato contra cada implementação.

## 4.4 ISP — Princípio da Segregação de Interfaces

O ISP recomenda contratos pequenos e específicos, de forma que os consumidores dependam apenas das operações de que necessitam.

As funções `compare()`, `evaluate_ranking()` e `calculate_similarity_index()` expõem operações separadas para comparação, avaliação e agregação. Essa organização favorece coesão, mas a existência de funções pequenas não comprova, por si só, segregação de interfaces.

Nos repositórios, o parâmetro `client` oferece uma API ampla, e não há contratos explícitos separados para leitura e escrita de vagas ou currículos. Portanto, não foi identificada evidência suficiente para declarar ISP plenamente aplicado. Uma melhoria futura, caso a complexidade justifique, seria definir contratos mínimos orientados às operações usadas por cada consumidor. Nenhuma interface artificial foi adicionada apenas para esta documentação.

## 4.5 DIP — Princípio da Inversão de Dependência

O DIP recomenda que regras de alto nível e detalhes de infraestrutura dependam de abstrações, e que essas abstrações expressem as necessidades das regras de negócio.

Em [app/repositories.py](../app/repositories.py), funções como `list_jobs()`, `get_job()` e `create_job()` recebem `client` por parâmetro. Isso permite fornecer dependências substitutas. Os testes web usam `patch` em `app.routes.create_supabase_client` para fornecer `FakeClient`, executando fluxos de autenticação e vagas sem conectar ao Supabase real.

Essa injeção favorece testes, mas não comprova DIP completo. Os repositórios continuam acoplados às chamadas `table()`, `select()`, `eq()` e `execute()` e à estrutura `response.data`. Além disso, [app/routes.py](../app/routes.py) conhece a criação do cliente concreto e passa esse cliente às funções de persistência. O módulo de repositórios também combina validações e detalhes de persistência.

O matching recebe dados e vetores como argumentos e não consulta diretamente o banco, o que reduz seu acoplamento à persistência. Ainda assim, não foi identificado um contrato de persistência definido pelas regras de alto nível. A evidência atual é de injeção de dependência e testabilidade; a inversão arquitetural permanece parcial. Uma melhoria futura seria estabelecer, quando necessário, contratos de acesso a dados e um adaptador Supabase responsável por atendê-los.

## 4.6 Resultados

### Alterações realizadas

- [app/repositories.py](../app/repositories.py): criação de `format_display_date()` e reutilização em `job_for_template()` e `resume_for_template()`.
- [tests/test_format_display_date.py](../tests/test_format_display_date.py): criação de sete testes com `unittest`, sem conexão real com o Supabase.
- [docs/4-solid.md](4-solid.md): documentação das evidências e lacunas dos cinco princípios.

O benefício principal é centralizar a formatação de datas, preservando os valores apresentados e reduzindo duplicação. Não foram alteradas rotas, autenticação, banco, processamento de currículos, cálculo de compatibilidade nem valores de `score`, `met` ou `missing`.

### Validação executada

Os comandos solicitados foram executados inicialmente com o Python global:

```powershell
python -m unittest discover -s tests -p "test_format_display_date.py"
python -m unittest discover -s tests
```

O primeiro terminou com um erro de importação por ausência de `cachelib`. A suíte completa reportou 46 testes, com três erros de importação pelo mesmo motivo: no módulo novo e nos módulos existentes `test_requisitos` e `test_web_filters`. O problema ocorre na inicialização do pacote `app`, antes da execução da lógica alterada; trata-se de uma limitação desse ambiente Python.

O ambiente `venv` já existente contém as dependências necessárias. Sem instalar pacotes ou alterar configurações, foram executados:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_format_display_date.py"
# Resultado: Ran 7 tests — OK

.\venv\Scripts\python.exe -m unittest discover -s tests
# Resultado: Ran 87 tests — OK
```

As mensagens sobre PDF inválido e falha simulada de gravação apareceram durante cenários de erro da suíte, que terminou com sucesso. Nenhum teste existente foi modificado.

### Limitações e continuidade

A melhoria de SRP é localizada. OCP, LSP e ISP não possuem demonstração suficiente no escopo examinado; DIP possui evidências de injeção, mas ainda exige inversão por contratos. Os testes locais não validam políticas RLS nem integração com o Supabase real. A suíte depende das bibliotecas da aplicação, e os testes novos seguem o padrão existente de definir uma chave Flask de teste no processo quando ausente, sem editar `.env`.

### Pull Requests

- PR desta contribuição: **[inserir link após abertura manual]**.
- PRs do grupo com evidências adicionais de SOLID ou padrões: **[inserir links após verificar o código e os testes correspondentes]**.

Nenhum commit, push ou PR foi realizado automaticamente. A análise não presume implementações presentes em branches ou PRs não examinados.
