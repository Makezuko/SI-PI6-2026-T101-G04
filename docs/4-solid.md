# 4. Aplicação e análise dos princípios SOLID

Esta análise consolida as evidências práticas dos princípios **SOLID** no repositório do **TalentMatch AI**, somando a refatoração inicial de SRP (PR #23), as implementações de **OCP** e **LSP** sobre o cálculo atual de aderência documental (`src/matching/adherence.py` e `src/matching/aggregators.py`) e a contribuição de **ISP** e **DIP** na atualização de perfil.

## 4.1 SRP — Princípio da Responsabilidade Única

O SRP recomenda que uma unidade de código tenha uma responsabilidade coesa e um motivo principal para mudar.

No código original, `job_for_template()` e `resume_for_template()` repetiam a conversão de datas ISO para o formato `DD/MM/AAAA`, incluindo o tratamento de valores ausentes e inválidos. Uma mudança nessa regra exigia modificar dois locais.

Foi extraída a função `format_display_date(value)` em [app/repositories.py](../app/repositories.py). As duas funções de transformação passaram a utilizá-la. O tratamento do sufixo `Z`, as exceções `ValueError` e `AttributeError` e o retorno `—` foram preservados. A data continua sendo apresentada conforme o valor recebido, sem conversão de fuso horário.

Essa mudança centraliza a regra de apresentação e permite testá-la diretamente. É uma evidência pontual de aplicação de SRP, mas não torna todo o módulo aderente ao princípio. O módulo ainda reúne consultas ao Supabase, validação de vagas, preparação de requisitos, extração de informações dos currículos e montagem de dados para templates. Uma separação futura entre persistência e apresentação deverá ser avaliada em outra tarefa.

Os testes de [tests/test_format_display_date.py](../tests/test_format_display_date.py) verificam datas ISO, `None`, texto vazio, entradas inválidas e sufixo `Z`. Também verificam os campos `created_at` e `submitted_at` nas transformações, inclusive quando as chaves de data estão ausentes. Os currículos usados nesses testes têm texto vazio, dispensando extratores e serviços externos. Nenhum outro campo retornado foi modificado.

## 4.2 OCP — Princípio Aberto/Fechado

- **Problema antes:** em [src/matching/adherence.py](../src/matching/adherence.py), `calculate_adherence()` fixava uma única regra de cálculo da aderência documental (`FORMULA_VERSION = "3.1-experimental"`). Qualquer variação na política de pontuação (como impor teto quando um requisito obrigatório tem estado `nao_identificado`, ou ponderar parcialmente itens em `revisao_necessaria`) obrigava editar diretamente a função central já validada.
- **Solução aplicada (depois):** foi criado o contrato `AdherenceScoreStrategy` em [src/matching/aggregators.py](../src/matching/aggregators.py) e o parâmetro opcional `strategy` em `calculate_adherence()` ([src/matching/adherence.py](../src/matching/adherence.py)). Novas políticas (`StrictMandatoryAdherence`, `ProvisionalWeightedAdherence` ou classes externas como `CustomCeilingAdherenceStrategy` nos testes) estendem o cálculo sem modificar `adherence.py`.
- **Efeito no código:** preservou 100% da compatibilidade com a fórmula `3.1-experimental` (`WeightedConfirmedAdherence` é o padrão quando `strategy=None`), mantendo intactos os contratos do avaliador contextual e da interface web.

```python
# src/matching/adherence.py
def calculate_adherence(requirements, decisions, weights=None, strategy=None):
    """Cossenos não entram no cálculo. Ausência de decisão é erro, nunca zero."""
    active_strategy = WeightedConfirmedAdherence() if strategy is None else strategy
    if not isinstance(active_strategy, AdherenceScoreStrategy):
        raise TypeError('strategy deve implementar o protocolo AdherenceScoreStrategy.')
    ...
    score, maximum_score, contributions = active_strategy.compute(details, scale)
```

> *Links permanentes (substituir `<COMMIT_HASH>` após o merge do PR #33 na `main`):*
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/<COMMIT_HASH>/src/matching/adherence.py#L13-L64`
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/<COMMIT_HASH>/src/matching/aggregators.py#L8-L35`

## 4.3 LSP — Princípio da Substituição de Liskov

- **Problema antes:** não havia abstrações com múltiplas implementações reais nem testes de contrato garantindo que implementações alternativas mantivessem as mesmas pré e pós-condições exigidas pelos consumidores.
- **Solução aplicada (depois):** todas as implementações de `AdherenceScoreStrategy` (`WeightedConfirmedAdherence`, `StrictMandatoryAdherence` e `ProvisionalWeightedAdherence`, além de `CustomCeilingAdherenceStrategy`) em [src/matching/aggregators.py](../src/matching/aggregators.py) cumprem o mesmo contrato: recebem `details` validados e `scale > 0`, e retornam `(score, maximum_score, contributions)` com `0.0 <= score <= maximum_score <= 100.0`, sem mutar os dados de entrada e preservando `len(contributions) == len(details)` e `sum(contributions) == score`.
- **Efeito no código:** qualquer estratégia pode substituir a padrão dentro de `calculate_adherence()` sem quebrar relatórios, ordenação ou invariantes numéricas. Isso é comprovado pela suíte de contrato `test_lsp_contract_for_all_adherence_strategies` em [tests/test_solid_matching.py](../tests/test_solid_matching.py).

```python
# tests/test_solid_matching.py
strategies: list[AdherenceScoreStrategy] = [
    WeightedConfirmedAdherence(),
    StrictMandatoryAdherence(),
    ProvisionalWeightedAdherence(),
    CustomCeilingAdherenceStrategy(),
]
for strategy in strategies:
    output = calculate_adherence(req_copy, dec_copy, strategy=strategy)
    self.assertGreaterEqual(output["score"], 0.0)
    self.assertLessEqual(output["score"], output["maximum_score"] + 1e-9)
    self.assertAlmostEqual(math.fsum(contributions), output["score"], places=6)
```

> *Link permanente (substituir `<COMMIT_HASH>` após o merge do PR #33 na `main`):*
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/<COMMIT_HASH>/tests/test_solid_matching.py#L108-L143`

## 4.4 ISP — Princípio da Segregação de Interfaces

O ISP recomenda contratos pequenos e específicos, de forma que os consumidores dependam apenas das operações de que necessitam.

- **Problema antes:** `update_profile_account()` dependia de um cliente amplo do Supabase e chamava diretamente `update_profile()`, embora precisasse apenas de uma operação de autenticação e outra de persistência.
- **Solução aplicada:** foram separados `ProfileAuthWriter.update_user()` em [app/routes.py](../app/routes.py) e `ProfilePersistence.update_profile()` em [app/repositories.py](../app/repositories.py). Cada contrato contém somente a operação necessária ao fluxo.
- **Efeito no código:** a coordenação pode ser testada com objetos mínimos. O teste `test_profile_account_update_depends_on_small_contracts` usa um escritor de autenticação e um repositório de perfil independentes, sem o cliente completo do Supabase.

## 4.5 DIP — Princípio da Inversão de Dependência

O DIP recomenda que regras de alto nível e detalhes de infraestrutura dependam de abstrações, e que essas abstrações expressem as necessidades das regras de negócio.

- **Problema antes:** `update_profile_account()` conhecia diretamente a API da rota, do repositório funcional e do Supabase.
- **Solução aplicada:** a função recebe `ProfileAuthWriter` e `ProfilePersistence` por parâmetro. `SupabaseProfilePersistence` adapta o cliente concreto a `ProfilePersistence`, enquanto `g.supabase.auth` atende ao contrato mínimo de autenticação.
- **Efeito no código:** a regra de coordenação da conta depende dos contratos de negócio, não da implementação completa do cliente. Isso permite substituir os serviços em testes e diminui o acoplamento da atualização de perfil.
- **Limitação:** outros repositórios continuam usando `client.table()` diretamente. Este é um exemplo localizado de DIP, não uma reescritura completa de toda a persistência.

## 4.6 Resultados

### Alterações realizadas

- **SRP (PR #23):** [app/repositories.py](../app/repositories.py) (`format_display_date()`) e [tests/test_format_display_date.py](../tests/test_format_display_date.py).
- **OCP e LSP (PR #33):** [src/matching/aggregators.py](../src/matching/aggregators.py) (`AdherenceScoreStrategy`, `WeightedConfirmedAdherence`, `StrictMandatoryAdherence`, `ProvisionalWeightedAdherence`), [src/matching/adherence.py](../src/matching/adherence.py) (`calculate_adherence(..., strategy=None)`) e [tests/test_solid_matching.py](../tests/test_solid_matching.py).
- **ISP e DIP:** [app/routes.py](../app/routes.py) (`ProfileAuthWriter`, `update_profile_account()`), [app/repositories.py](../app/repositories.py) (`ProfilePersistence`, `SupabaseProfilePersistence`) e [tests/test_web_filters.py](../tests/test_web_filters.py) (`test_profile_account_update_depends_on_small_contracts`). Esta contribuição está pronta localmente e aguarda PR e merge.
- **Documentação:** atualização de [docs/4-solid.md](4-solid.md) com as evidências de OCP e LSP aplicadas à aderência documental atual.

### Validação executada

```powershell
python -m unittest discover -s tests -p "test_solid_matching.py"
# Resultado: Ran 4 tests — OK

python -m unittest discover -s tests -p "test_adherence.py"
# Resultado: Ran 6 tests — OK

python -m unittest discover -s tests -p "test_contextual.py"
# Resultado: Ran 11 tests — OK
```

### Pull Requests

- **[PR #23 — Refatoração SRP, testes automatizados e documentação SOLID](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/23):** implementação da função `format_display_date()` e análise inicial.
- **[PR #22 — Documentação arquitetural e ADR-0001](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/22)** e **[PR #21 — Contexto do sistema e atributos de qualidade](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/21)**.
- **[PR #33 — Refatoração OCP e LSP na aderência documental (Kauê Farias Lourenço)](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/33):** implementação de `AdherenceScoreStrategy` em `src/matching/aggregators.py`, extensão em `src/matching/adherence.py`, suíte `tests/test_solid_matching.py` e atualização de `docs/4-solid.md` *(substituir `<COMMIT_HASH>` nos links permanentes após o merge na `main`)*.
- **PR de ISP e DIP (Julia Kimura):** implementação pronta localmente em `app/routes.py`, `app/repositories.py` e `tests/test_web_filters.py`; *inserir link após abrir e mergear o PR*.

