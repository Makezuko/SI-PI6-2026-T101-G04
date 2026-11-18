# TalentMatch AI

Aplicação Flask para triagem de currículos. As instruções abaixo são para Windows.

O [fluxo contextual experimental](docs/avaliacao-contextual.md) prepara avaliação
de sustentação por modelo local, separada da recuperação semântica. Está desativado
por padrão; a qualidade das decisões ainda precisa de avaliação humana.

Para o bloqueio de processo/porta e a comprovação de POST, modelo, gravação e tela,
veja o [diagnóstico operacional](docs/diagnostico-operacional-contextual.md).
Para reiniciar com identidade do processo verificada, use o mesmo comando abaixo
com `-Restart`. O [diagnóstico de login](docs/diagnostico-login-contextual.md)
explica a correção do bloqueio de rede do processo e o rastreio sanitizado de Auth.

Para testar o fluxo com modelos locais preparados, encerre o servidor atual e execute:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1
```

Esse comando seleciona explicitamente o avaliador contextual e a recuperação
multilíngue do manifesto local. Depois, selecione o currículo na aplicação e
reprocesse: análises anteriores não são atualizadas automaticamente. Para testar
sem acessar o banco, use `.\.venv-contextual\Scripts\python.exe -m scripts.testar_fluxo_contextual`.

A regra experimental de [aderência documental](docs/aderencia.md) usa pesos por
requisito: obrigatório **2**, desejável/não obrigatório **1**, sem rejeição
automática. Veja também o [estado do projeto](docs/estado-do-projeto.md).

## Instalação

Clone o repositório e entre na pasta:
```powershell
git clone https://github.com/Makezuko/SI-PI6-2026-T101-G04.git
cd SI-PI6-2026-T101-G04
```

Crie um ambiente virtual, ative-o e instale as dependências:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Se o PowerShell impedir a ativação, use `.\.venv\Scripts\python.exe` no lugar de `python` nos próximos comandos.

## Configuração

Crie um arquivo `.env` na raiz do projeto com as credenciais do Supabase e uma chave secreta local do Flask:

```env
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_KEY=SUA_CHAVE_PUBLICAVEL
FLASK_SECRET_KEY=UMA_CHAVE_ALEATORIA_LONGA
```

Cada integrante precisa configurar seu próprio `.env`. Não envie nem compartilhe esse arquivo. Use uma chave publicável do Supabase; não use `service_role` ou `sb_secret` na aplicação. Gere `FLASK_SECRET_KEY` localmente, por exemplo com `python -c "import secrets; print(secrets.token_hex(32))"`.

## Banco Supabase

Antes de usar a aplicação com um projeto Supabase, revise as migrações no diretório `sql/` e aplique as necessárias pelo SQL Editor:

1. [`sql/001_auth_vagas.sql`](sql/001_auth_vagas.sql): autenticação e propriedade das vagas.
2. [`sql/002_editar_vagas.sql`](sql/002_editar_vagas.sql): edição de vagas.
3. [`sql/003_editar_perfil.sql`](sql/003_editar_perfil.sql): edição de perfil.
4. [`sql/004_integracao_aderencia.sql`](sql/004_integracao_aderencia.sql): persistência de currículos e análises.

A migração 004 depende do esquema legado, especialmente da existência e do vínculo de `curriculos.vaga_id`. Antes de aplicá-la, siga a inspeção e as pré-condições descritas em [`docs/integracao-aderencia.md`](docs/integracao-aderencia.md). Não execute migrações sem autorização/revisão e não desative RLS para contornar erros. A aplicação das migrações e as políticas RLS no Supabase real ainda precisam ser confirmadas pela equipe; os testes locais usam um cliente simulado.

## Modelos de IA

O caminho padrão do modelo NER é `models/ner/augmented/best_model`. Esse diretório não é versionado; disponibilize localmente os pesos treinados. O modelo de embeddings padrão é `sentence-transformers/all-mpnet-base-v2` e pode ser baixado/cacheado na primeira análise, o que pode exigir conexão à internet.

Para configurar caminhos ou identificadores diferentes no PowerShell:

```powershell
$env:NER_MODEL_PATH = 'models/ner/augmented/best_model'
$env:EMBEDDING_MODEL = 'sentence-transformers/all-mpnet-base-v2'
```

Defina essas variáveis antes de iniciar o servidor. Falhas ao carregar os modelos são informadas pela aplicação; não há índice substituto.

O cliente é criado em `app/supabase_client.py` e pode ser usado nas rotas:

```python
from app.supabase_client import create_supabase_client

supabase = create_supabase_client()
resultado = supabase.table("vagas").select("*").limit(10).execute()
```

As consultas dependem das políticas RLS configuradas no Supabase. Não desative o RLS para contornar erros de permissão.

## Funcionalidades e limites atuais

As telas de cadastro/login, perfil, vagas e currículos estão ligadas às rotas da aplicação. As vagas e os perfis usam Supabase; currículos e análises também dependem da migração de integração e das permissões correspondentes. A tela de análise aceita arquivos PDF, exige requisitos cadastrados e revisados manualmente e apresenta decisões documentais e evidências para revisão humana. No modo contextual, a recuperação semântica fornece trechos ao avaliador local; condições manuais legadas são opcionais e não participam dessa avaliação.

O índice não é uma probabilidade de contratação nem uma decisão sobre o candidato. O arquivo PDF original não é exibido na tela de detalhes. A qualidade dos modelos em português e a integração com o Supabase real ainda precisam de validação ponta a ponta.

## Executar

Para o fluxo contextual, o comando oficial é `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\iniciar_contextual.ps1`, após preparar os modelos e o runtime conforme [o guia contextual](docs/avaliacao-contextual.md). Para iniciar com a configuração padrão (legada), com o ambiente virtual ativado:
```powershell
python -m app.run
```

Depois, acesse http://127.0.0.1:5002. O servidor usa processo único sem debug/reloader.
Para encerrar, pressione `Ctrl+C` no terminal.

## Testes

```powershell
python -m unittest discover -s tests
```

## Avaliações e ferramentas

Métricas de [NER](docs/avaliacao_ner.md) medem extração de entidades; métricas de [recuperação](docs/avaliacao-semantica-ampliada.md) medem a posição de evidências anotadas; a [avaliação contextual](docs/avaliacao-contextual.md) examina decisões fundamentadas em evidências. São etapas distintas. Resultados locais são diagnósticos, não validação geral do modelo. Consulte o [índice de scripts](scripts/README.md) para comandos e dependências.
