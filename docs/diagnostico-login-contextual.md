# Login no ambiente contextual — 17/11/2026

O log do processo 25156 registrou `AuthRetryableError` em quatro POSTs de login.
O SDK transforma falhas HTTP de transporte nessa exceção. O diagnóstico local
reproduziu `ConnectError → ConnectError → PermissionError`, errno 13, Windows
10013. O servidor havia sido iniciado pelo agente dentro do sandbox com rede
restrita. A mesma instalação Python, os mesmos valores efetivos e o mesmo GET
público `/auth/v1/health`, executados fora do sandbox, receberam HTTP 401.
Esse 401 era esperado sem apikey: comprova conexão HTTP/TLS, não login válido.
Não foram enviados e-mail, senha, token ou chave nesse teste de transporte.

Portanto a causa comprovada era a restrição de rede do processo, antes da
resposta de autenticação e antes de acessar perfil ou criar a sessão de login.
Não há evidência de migração faltante. Não houve SQL, alteração de RLS, dados,
credenciais, fórmula ou avaliador.

## Ambiente

O `.env` carregado é o da raiz, resolvido a partir de `__file__`, com
`override=False`. As três variáveis necessárias estavam presentes e coincidiam
com o arquivo. Somente esses resultados booleanos foram impressos.
O ambiente antigo com dependências é `venv`; `.venv` contém apenas pip e não é
o ambiente antigo funcional.

| Pacote | venv antigo | .venv-contextual |
| --- | --- | --- |
| supabase / supabase-auth | 2.33.0 | 2.34.1 |
| HTTPX / httpcore | 0.28.1 / 1.0.9 | 0.28.1 / 1.0.9 |
| Flask | 3.1.3 | 3.1.2 |
| Flask-Session / cachelib | 0.8.0 / 0.13.0 | 0.8.0 / 0.13.0 |
| python-dotenv | 1.2.4 | 1.2.4 |
| certifi | 2026.7.22 | 2025.8.3 |

Nenhum pacote foi trocado: a instalação nova conectou ao Auth assim que saiu
da restrição. O avaliador e sua configuração foram preservados.

## Correção e rastreio

O servidor restrito foi encerrado por PID confirmado via HTTP e pelo registro
local, e reiniciado fora do sandbox na mesma porta 5002. O PID novo observado
foi 33136, com `enabled=true`, backend `llama_cpp` e pipeline
`web-7-contextual-traced-strict`. PIDs mudam a cada reinício.

O inicializador agora aceita `-Restart`. Ele confirma a identidade do listener
antes de encerrar o processo e só considera runtimes filhos desse PID dentro
do diretório local esperado. Não encerra processos Python indiscriminadamente.

No seu PowerShell, na raiz do projeto:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1 -Restart
```

`AUTH_STAGE` e `AUTH_ERROR` vão ao terminal e a
`reports/contextual-server.jsonl`. Etapas: `CLIENT_CREATE`, `AUTH_SIGN_IN`,
`AUTH_RESPONSE`, `AUTH_VERIFY_USER`, `PROFILE_READ`, eventualmente
`PROFILE_CREATE`/`PROFILE_UPDATE`/`PROFILE_READ_AFTER_CREATE`, `SESSION_CREATE`
e `SESSION_READY`. O erro contém somente ID de execução, etapa, classes das
exceções, códigos numéricos e localização dos frames, sem mensagens brutas,
variáveis locais, payload, credenciais ou dados de perfil.

A mensagem genérica deixou de presumir migração faltante e passou a informar
o ID de diagnóstico local.

## Verificação e ação pendente

191 testes automatizados passaram. Os três testes novos verificam transporte
falhando antes de perfil/sessão, leitura de perfil falhando na etapa correta e
sucesso com perfil simulado e armazenamento real da sessão em cache temporário.
Também verificam ausência de credenciais e mensagens sensíveis nos logs.
Esses testes não validam credenciais nem perfil remoto do usuário.

O servidor está pronto em **http://127.0.0.1:5002/login**. Tente entrar novamente
com sua conta. Essa interação autenticada é necessária para verificar seu Auth
e perfil reais. Se houver outra falha, o ID exibido permitirá localizar a etapa
precisa em `reports/contextual-server.jsonl`, sem pedir senha ou tokens.
