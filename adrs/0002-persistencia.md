# ADR-0002 — Persistência separada do fluxo de edição de perfil

**Status:** Aceito

**Responsável:** Julia

**Data:** 21/11/2026

## 1. Contexto

A edição de perfil envolve dados armazenados no Supabase Auth e dados armazenados na tabela `usuarios`. A rota `editar_perfil()` precisava manter esses dados sincronizados sem misturar todas as regras com validação e apresentação.

O sistema já usa um repositório em [app/repositories.py](../app/repositories.py) para operações de persistência, mas a rota ainda repetia a coordenação da atualização.

## 2. Decisão

Manter o Supabase Auth e a tabela `usuarios` como duas fontes atualizadas pelo fluxo da aplicação:

1. validar os dados antes da integração externa;
2. calcular apenas os campos que mudaram;
3. enviar atributos de autenticação ao Supabase;
4. atualizar o perfil no repositório quando necessário;
5. sincronizar os dados atualizados na sessão.

A separação foi implementada com funções da rota em [app/routes.py](../app/routes.py):

- `validate_profile_form()`;
- `profile_changes()`;
- `auth_profile_attributes()`;
- `update_profile_account()`;
- `sync_profile_session()`.

A atualização persistida foi conectada a um contrato pequeno
`ProfilePersistence` em [app/repositories.py](../app/repositories.py). A
implementação `SupabaseProfilePersistence` adapta esse contrato ao Supabase,
permitindo que a regra de atualização use uma operação específica em vez de
depender diretamente de todas as consultas disponíveis no cliente.

## 3. Alternativas consideradas

### Continuar com a lógica dentro de `editar_perfil()`

Foi descartada porque aumentaria o tamanho da rota e misturaria validação, comunicação externa e estado da sessão.

### Criar um repositório único para todo o usuário

Foi descartada neste estágio porque exigiria uma abstração maior entre Supabase Auth e banco relacional. O projeto ainda não tem um contrato completo que justificasse essa camada adicional.

### Atualizar apenas o banco

Foi descartada porque nome, empresa, e-mail e senha possuem responsabilidades no Supabase Auth. Atualizar apenas a tabela `usuarios` deixaria dados diferentes entre os sistemas.

## 4. Consequências positivas

- Regras de validação ficam separadas da integração.
- Campos alterados são calculados uma única vez.
- Mudanças de senha não exigem atualização desnecessária no banco.
- Erros conhecidos podem ser apresentados de forma específica.
- Fluxos são testados com Supabase simulados.

## 5. Consequências negativas

- Autenticação e banco continuam sendo atualizados em chamadas separadas, sem transação distribuída.
- Uma falha entre as duas atualizações pode exigir correção ou revisão manual.
- A aplicação depende dos formatos e respostas dos dois serviços do Supabase.

## 6. Implementação e validação

A implementação está em [app/routes.py](../app/routes.py). Os testes estão em [tests/test_web_filters.py](../tests/test_web_filters.py).

Para validar o comportamento da edição de perfil:

```powershell
python -m unittest discover -s tests -p "test_web_filters.py"
```

Resultado: 38 testes executados, todos passando.

Os testes simulam o Supabase e não substituem a validação das políticas RLS e da integração real.

## 7. Pull Request

A decisão foi implementada e documentada no [PR #38](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/38).

O Pull Request também relaciona a mudança à documentação em [docs/5-clean-code.md](../docs/5-clean-code.md).
