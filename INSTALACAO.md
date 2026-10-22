# Etapa 1 — Supabase Auth e vagas persistidas

Este pacote foi preparado para o esquema SQL enviado e os códigos atuais da equipe. Não inclui nem modifica arquivos HTML, CSS, templates, assets ou código dos modelos de IA. Não foi enviado ao GitHub nem executado no Supabase do grupo.

## O que entrega

- Cadastro e login usando Supabase Auth, com confirmação de e-mail quando habilitada.
- Perfil na tabela usuarios ligado ao UUID do Supabase Auth, mantendo o ID inteiro e as FKs existentes.
- Vagas gravadas em vagas, com título, descrição completa, rascunho dos requisitos e criado_por.
- Dashboard e seleção de vagas consultando o banco, incluindo persistência após reiniciar a aplicação.
- Políticas RLS por proprietário: cada recrutador vê as próprias vagas. Isso não implementa compartilhamento entre membros de uma empresa. Todos os colegas podem usar o mesmo projeto, mas com contas e vagas separadas.
- Sessão no servidor, sem colocar tokens do Supabase no cookie legível do Flask.

## Instalação, em ordem

1. Faça um commit ou cópia dos arquivos locais antes de substituí-los. Copie app/__init__.py, app/supabase_client.py, app/routes.py, app/repositories.py, tests/test_web_filters.py e requirements.backend.txt para os mesmos caminhos no projeto. O arquivo de teste substitui o antigo teste que dependia de candidatos fictícios.
2. No SQL Editor do Supabase, execute o conteúdo completo de sql/001_auth_vagas.sql. É uma migração, não uma consulta de inspeção. Ela adiciona auth_user_id, nome e empresa a usuarios e status a vagas; torna senha_hash opcional; adiciona grants e políticas apenas para usuarios/vagas. Não apaga dados, não altera IDs existentes e mantém RLS ligado. Currículos/análises continuam bloqueados como antes, até sua integração.
3. Na raiz, instale:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.backend.txt
```

Se o seu ambiente se chama .venv, use .\.venv\Scripts\python.exe. Mantenha também os requirements.txt existentes: este arquivo é complementar. A versão testada do cliente foi supabase 2.33.0 com Flask 3.1.3 e Flask-Session 0.8.0.

4. No .env já existente, mantenha SUPABASE_URL e SUPABASE_KEY (sb_publishable_) e acrescente FLASK_SECRET_KEY com uma chave aleatória. Gere localmente:

```powershell
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Copie a saída para FLASK_SECRET_KEY no seu .env, sem aspas desnecessárias. Não cole a chave no chat nem no Git. SESSION_COOKIE_SECURE=false é adequado para localhost via HTTP; use true quando publicar com HTTPS.

5. Acrescente instance/ ao .gitignore, pois contém as sessões locais. Pode usar:

```powershell
Add-Content .gitignore "`ninstance/"
```

6. Rode:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_web_filters.py"
.\venv\Scripts\python.exe -m app.run
```

Abra http://127.0.0.1:5000 e use a tela existente de cadastro. A conta fictícia anterior não autentica nesta versão. Se a confirmação de e-mail estiver habilitada no Supabase Auth, confirme o link e volte à tela de login. Cadastros de usuários da aplicação são diferentes dos convites de acesso ao dashboard administrativo.

## Teste manual no banco real

1. Cadastre uma conta e faça login.
2. Crie uma vaga com título e descrição reconhecíveis.
3. Confira a linha em vagas no Table Editor: descricao preservada, requisitos preenchido, criado_por referenciando seu perfil.
4. Reinicie o servidor e faça login novamente: a vaga deve continuar no dashboard.
5. Abra Ver ranking: a vaga deve ser a mesma do banco e não deve ter candidatos fictícios.
6. Use uma segunda conta: ela não deve ver a vaga da primeira. Este é também um teste manual necessário das políticas reais.
7. Tente abrir /vagas/999999: deve retornar 404, sem redirecionar silenciosamente para outra vaga.

## O que ainda fica pendente

- Upload e processamento de currículos não estão conectados nesta etapa. GET abre a tela original com lista vazia; POST responde 501 e não inventa candidatos/notas. Os antigos dados de demonstração foram removidos das rotas.
- Dashboard usa — para contagens de currículos, candidatos e aderência ainda não integradas; não usa 73%, nota 80 ou outras métricas inventadas. Como o HTML foi preservado, o card percentual pode mostrar —%.
- A descrição da vaga é salva integralmente. requisitos recebe um JSON em texto com status pendente_revisao e uma entrada por linha não vazia. Isto é um rascunho mecânico; não é extração por IA nem requisitos confirmados. O texto já existente no formulário sobre processamento automático ainda precisa ser alinhado quando a revisão de requisitos for implementada; nenhum texto HTML foi alterado neste pacote.
- pontuacao_aderencia é NOT NULL no esquema atual; não gravaremos uma análise sem definir sua regra. Também será preciso definir a dimensão do vector e onde persistir evidências por requisito: um único embedding_curriculo não representa todos os vetores por trecho que já produzimos.
- texto_anonimizado é obrigatório: a próxima integração deverá gerar esse texto antes de inserir currículos; não preencher com o original fingindo anonimização.
- A sessão em arquivo serve ao MVP local com uma instância. Para várias instâncias, configurar armazenamento de sessão compartilhado antes de publicar.
- Erros de cadastro/login aparecem nos locais já existentes dos templates. Erros de banco/formulário de vagas retornam páginas HTTP de erro do Flask. Isso evita sucesso falso sem alterar templates; mensagens embutidas nas telas poderão ser implementadas em uma etapa de interface autorizada.

## Perfis antigos

Linhas antigas sem auth_user_id são preservadas e não são atribuídas automaticamente a ninguém. Senhas antigas em senha_hash não são migradas para o Supabase Auth. Se já existir um perfil com o mesmo e-mail do novo cadastro, o app pode retornar conflito (409). A equipe precisa verificar a identidade e vincular manualmente o UUID correto em usuarios.auth_user_id; não apagar linhas nem vagas para contornar isso. Vagas com criado_por nulo ou pertencentes a perfis antigos não aparecem na nova conta até a associação ser revisada.

## Testes e limites de verificação

16 testes locais com cliente Supabase simulado passaram: autenticação, sessão no servidor, confirmação de e-mail, dados persistidos no repositório simulado, gravação correta de descricao/requisitos/proprietário, falhas do banco, isolamento simulado entre usuários, 404, origem de formulários, logout, filtros HTML originais e bloqueio de upload fictício. A migração foi validada sintaticamente com parser PostgreSQL. Esses testes não validam as políticas no servidor real. Nenhuma chamada ao banco do grupo foi feita. Execute o teste manual acima depois da migração.

Os templates usados para conferir a renderização foram os atuais do GitHub; nenhum template é incluído no ZIP. Modelos NER e Sentence Transformer não foram alterados.

## Arquivos substituídos/adicionados

- app/__init__.py: sessão no servidor e inicialização.
- app/supabase_client.py: cliente isolado por requisição e chave publicável.
- app/repositories.py: adaptação entre nomes do banco e campos esperados pelas telas.
- app/routes.py: Auth e rotas de vagas reais.
- tests/test_web_filters.py: testes da nova etapa, substituindo testes dos mocks.
- sql/001_auth_vagas.sql: migração preparada para executar manualmente.
- requirements.backend.txt: dependências complementares.

Referências:
https://supabase.com/docs/guides/database/postgres/row-level-security
https://supabase.com/docs/reference/python/auth-signinwithpassword
https://supabase.com/docs/reference/python/auth-signup
https://flask-session.readthedocs.io/en/latest/security.html
