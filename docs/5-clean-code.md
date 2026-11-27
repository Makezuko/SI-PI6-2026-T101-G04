# 5. Aplicação das práticas de Clean Code

Esta análise considera o código disponível no ramo `refactor/separar-editar-perfil`. O objetivo é registrar evidências concretas da aplicação de Clean Code na edição de perfil, sem alterar outras áreas do sistema.

## 5.1 Responsabilidade única e funções pequenas

A rota `editar_perfil()` de [app/routes.py](../app/routes.py) concentrava três responsabilidades: ler e validar dados do formulário, calcular mudanças no perfil e atualizar autenticação, banco e sessão.

Essa organização dificultava testar cada regra separadamente e misturava validação, integração externa e apresentação.

## Antes

Antes da refatoração, toda a lógica estava dentro de `editar_perfil()`:

```python
@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def editar_perfil():
    form = {
        'name': g.profile.get('nome') or '',
        'email': g.profile.get('email') or '',
        'company': g.profile.get('empresa') or '',
    }
    if request.method == 'POST':
        form.update({
            'name': request.form.get('name', '').strip(),
            'email': request.form.get('email', '').strip().lower(),
            'company': request.form.get('company', '').strip(),
        })
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        error = None

        if not all(form.values()):
            error = 'Preencha nome, e-mail e empresa.'
        elif len(form['name']) > 120 or len(form['company']) > 120:
            error = 'Nome e empresa devem ter no máximo 120 caracteres.'
        elif len(form['email']) > 254 or not re.fullmatch(
            r'[^@\s]+@[^@\s]+\.[^@\s]+',
            form['email'],
        ):
            error = 'Informe um endereço de e-mail válido.'
        elif password and password != password_confirm:
            error = 'As senhas não coincidem.'
        elif password and (len(password) < 8 or len(password) > 128):
            error = 'A nova senha deve ter entre 8 e 128 caracteres.'

        if error:
            return render_template(
                'editar_perfil.html',
                active_page='configuracoes',
                form=form,
                error=error,
            ), 400

        profile_changes = {}
        if form['name'] != (g.profile.get('nome') or ''):
            profile_changes['nome'] = form['name']
        if form['company'] != (g.profile.get('empresa') or ''):
            profile_changes['empresa'] = form['company']
        if form['email'] != (g.profile.get('email') or '').lower():
            profile_changes['email'] = form['email']

        attributes = {}
        if 'nome' in profile_changes or 'empresa' in profile_changes:
            attributes['data'] = {
                'name': form['name'],
                'company': form['company'],
            }
        if 'email' in profile_changes:
            attributes['email'] = form['email']
        if password:
            attributes['password'] = password

        try:
            if attributes:
                response = g.supabase.auth.update_user(attributes)
                if not response.user:
                    raise RuntimeError(
                        'Supabase não retornou o usuário atualizado.'
                    )
                if 'email' in profile_changes:
                    effective_email = (
                        response.user.email or g.profile['email']
                    ).lower()
                    profile_changes['email'] = effective_email
            updated_profile = g.profile
            if profile_changes:
                updated_profile = update_profile(
                    g.supabase,
                    g.profile['id'],
                    session['auth_user_id'],
                    profile_changes,
                )
        except AuthApiError:
            return render_template(
                'editar_perfil.html',
                active_page='configuracoes',
                form=form,
                error='Não foi possível atualizar o perfil. '
                      'Confira o e-mail e os requisitos da nova senha.',
            ), 400
        except Exception as error:
            app.logger.warning(
                'Falha ao atualizar perfil (%s, código=%s): %s',
                type(error).__name__,
                getattr(error, 'code', None),
                getattr(error, 'message', str(error)),
            )
            abort(
                503,
                description='Não foi possível confirmar a atualização do '
                            'perfil. Reabra a tela antes de tentar novamente.',
            )

        g.profile = updated_profile
        session['user_profile'] = updated_profile
        session['user_name'] = updated_profile['nome']
        session['user_email'] = updated_profile['email']
        session['user_initials'] = ''.join(
            part[0]
            for part in updated_profile['nome'].split()[:2]
        ).upper()
        if updated_profile['email'] != form['email']:
            flash(
                'Perfil atualizado. Confirme o link enviado ao novo '
                'e-mail para concluir a alteração.',
                'success',
            )
        else:
            flash('Perfil atualizado com sucesso.', 'success')
        return redirect(url_for('editar_perfil'))

    return render_template(
        'editar_perfil.html',
        active_page='configuracoes',
        form=form,
        error=None,
    )
```

## Depois

A refatoração criou funções com responsabilidades únicas:

```python
def profile_form(profile, submitted=None):
    form = {
        'name': profile.get('nome') or '',
        'email': profile.get('email') or '',
        'company': profile.get('empresa') or '',
    }
    if submitted is not None:
        form.update({
            'name': submitted.get('name', '').strip(),
            'email': submitted.get('email', '').strip().lower(),
            'company': submitted.get('company', '').strip(),
        })
    return form
```

```python
def validate_profile_form(form, password, password_confirm):
    if not all(form.values()):
        return 'Preencha nome, e-mail e empresa.'
    if len(form['name']) > 120 or len(form['company']) > 120:
        return 'Nome e empresa devem ter no máximo 120 caracteres.'
    if len(form['email']) > 254 or not re.fullmatch(
        r'[^@\s]+@[^@\s]+\.[^@\s]+', form['email']
    ):
        return 'Informe um endereço de e-mail válido.'
    if password and password != password_confirm:
        return 'As senhas não coincidem.'
    if password and (len(password) < 8 or len(password) > 128):
        return 'A nova senha deve ter entre 8 e 128 caracteres.'
    return None
```

As funções `profile_changes()`, `auth_profile_attributes()` e `update_profile_account()` foram separadas para comparar os dados, construir atributos do Supabase e executar a atualização. `sync_profile_session()` passou a concentrar a atualização da sessão.

> *Links permanentes:*
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/22790f2698ada0d14efd3b103a95982c9b09d68e/app/routes.py#L363-L447`
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/22790f2698ada0d14efd3b103a95982c9b09d68e/app/routes.py#L462-L480`
> - `https://github.com/Makezuko/SI-PI6-2026-T101-G04/blob/22790f2698ada0d14efd3b103a95982c9b09d68e/tests/test_web_filters.py#L307-L355`

    ## 5.2 Nomes claros

Os nomes expressam a responsabilidade de cada unidade:

- `profile_form`: monta os valores exibidos no formulário.
- `validate_profile_form`: valida o formulário.
- `profile_changes`: calcula somente os campos alterados.
- `auth_profile_attributes`: prepara os dados enviados ao Supabase Auth.
- `update_profile_account`: coordena persistência de autenticação e perfil.
- `sync_profile_session`: atualiza os dados da sessão.

## 5.3 Funções pequenas e coesão

`editar_perfil()` deixou de repetir validações e montagem de atributos. Agora ela:

1. cria o formulário inicial;
2. valida um POST;
3. chama a atualização;
4. sincroniza a sessão;
5. informa o usuário.

O código continua integrado ao Flask, mas cada regra pode ser encontrada em uma unidade pequena.

As unidades foram obtidas com a técnica **Extract Method** do catálogo de
refatorações do Refactoring Guru: cada bloco antigo que tinha uma intenção
independente passou a ser chamado por nome. Isso transforma um método longo
com muitas responsabilidades em uma sequência curta de operações coerentes.
O code smell relacionado é o **Long Method**, acompanhado de parte do
**Duplicated Code** que recalculava diferenças e atributos do perfil.

## 5.4 Ausência de duplicação relevante

A rota anterior recalculava os dados enviados em várias comparações. A função `profile_changes()` centraliza essas diferenças. O mesmo `form` é reutilizado para autenticação, banco e resposta ao usuário, evitando transformações e validações duplicadas.

## 5.5 Tratamento explícito de erros

A atualização não usa mais um `except Exception` nesta rota. Os casos conhecidos são tratados separadamente:

- `AuthApiError`: credenciais ou requisitos da nova senha inválidos;
- `LookupError`: nenhuma linha de perfil foi atualizada;
- `APIError`: falha reportada pelo Supabase;
- `RuntimeError`: falha operacional ou resposta ausente do Supabase.

Os erros conhecidos produzem respostas HTTP explícitas. Uma exceção não prevista não é transformada em uma falsa confirmação de sucesso.

## 5.6 Testes automatizados

Os testes existentes em [tests/test_web_filters.py](../tests/test_web_filters.py) cobrem:

- apresentação dos valores atuais;
- atualização conjunta de nome, e-mail, empresa, senha e perfil;
- mudança de senha sem atualização desnecessária no banco;
- rejeição de senhas diferentes;
- rejeição de e-mail inválido;
- rejeição de senha curta.

Os testes são executados com clientes Supabase simulados, sem depender de credenciais reais.

### 5.6.1 Validação executada

```powershell
python -m unittest discover -s tests -p "test_web_filters.py"
```

Resultado: 38 testes executados, todos passando.

## 5.7 Alterações realizadas

- [app/routes.py](../app/routes.py): separação da montagem, validação, comparação, atualização e sincronização da edição de perfil.
- [tests/test_web_filters.py](../tests/test_web_filters.py): inclusão de testes para e-mail inválido e senha curta.
- [docs/5-clean-code.md](5-clean-code.md): documentação do antes e depois da refatoração.
- [adrs/0002-persistencia.md](../adrs/0002-persistencia.md): registro da decisão sobre persistência da edição de perfil.
- [app/repositories.py](../app/repositories.py): contrato específico `ProfilePersistence` e adaptador `SupabaseProfilePersistence` para isolamento da persistência do perfil.
- [tests/test_web_filters.py](../tests/test_web_filters.py): teste das interfaces mínimas usadas pela atualização da conta.

O benefício principal é concentrar cada regra em uma unidade pequena e testável. A mudança preserva a atualização de autenticação, banco e sessão.

## 5.8 Limitações e continuidade

A refatoração melhora a organização da edição de perfil, mas não separa todo o sistema em repositórios ou serviços independentes.

Os testes usam `FakeClient` e `FakeQuery`. Eles não validam a configuração real do Supabase, especialmente confirmação de e-mail, políticas RLS e indisponibilidade temporária do serviço.

Ainda é possível melhorar outros métodos grandes de [app/routes.py](../app/routes.py) e reduzir demais usos genéricos de `except Exception`. Essas mudanças não foram incluídas nesta refatoração para manter o PR pequeno.

## 5.9 SOLID relacionado

### ISP

`ProfilePersistence` e `ProfileAuthWriter` são contratos separados:
`ProfilePersistence` expõe apenas a escrita necessária no banco de perfil,
enquanto `ProfileAuthWriter` expõe apenas `update_user()`. A coordenação da
conta não recebe um cliente amplo que permita todas as operações de banco,
Autenticação, RPC e sessão.

### DIP

`update_profile_account()` recebe contratos por parâmetro. A infraestrutura
concreta é fornecida pela rota por `g.supabase.auth` e
`SupabaseProfilePersistence(g.supabase)`. Os testes simulam essas duas
dependências com clientes mínimos, provando a atualização sem acoplar a regra
de coordenação à implementação completa do Supabase.

## 5.10 Pull Request

As alterações e análises desta seção estão relacionadas ao [PR #38](https://github.com/Makezuko/SI-PI6-2026-T101-G04/pull/38).

Elas incluem a separação das responsabilidades, os testes de e-mail inválido e senha curta, esta documentação e a ligação com [ADR-0002 — Persistência separada do fluxo de edição de perfil](../adrs/0002-persistencia.md).
