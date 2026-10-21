# TalentMatch AI

Aplicação Flask para triagem de currículos. As instruções abaixo são para Windows.

## Instalação

Clone o repositório e entre na pasta:
```powershell
git clone <LINK_DO_REPOSITORIO>
cd SI-PI6-2026-T101-G04
```

Crie um ambiente virtual, ative-o e instale as dependências:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Se o PowerShell impedir a ativação, use `.\.venv\Scripts\python.exe` no lugar de `python` nos próximos comandos.

## Supabase

Crie um arquivo `.env` na raiz do projeto com a URL e a chave publicável do projeto Supabase:

```env
SUPABASE_URL=https://SEU-PROJETO.supabase.co
SUPABASE_KEY=SUA_CHAVE_PUBLICAVEL
```

Cada integrante precisa configurar seu próprio `.env`. Esse arquivo não deve ser enviado ao Git nem compartilhado. Não use chaves `service_role` ou `sb_secret` na aplicação.

O cliente é criado em `app/supabase_client.py` e pode ser usado nas rotas:

```python
from app.supabase_client import create_supabase_client

supabase = create_supabase_client()
resultado = supabase.table("vagas").select("*").limit(10).execute()
```

As consultas dependem das políticas RLS configuradas no Supabase. Não desative o RLS para contornar erros de permissão.

Por enquanto, as telas de login, vagas e candidatos ainda usam dados de demonstração; elas não leem nem gravam no banco.

## Executar

Com o ambiente virtual ativado:
```powershell
python -m app.run
```

Depois, acesse http://127.0.0.1:5000. Para encerrar, pressione `Ctrl+C` no terminal.

## Testes

```powershell
python -m unittest discover -s tests
```
