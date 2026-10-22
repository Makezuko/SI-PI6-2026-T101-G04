import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import ClientOptions, create_client

load_dotenv(Path(__file__).resolve().parent.parent / '.env')


def create_supabase_client():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError('Configure SUPABASE_URL e SUPABASE_KEY no .env.')
    if not key.startswith('sb_publishable_'):
        raise RuntimeError('Esta etapa usa uma chave sb_publishable_ do Supabase.')
    # Cada requisição cria seu cliente: sessões não se misturam entre usuários.
    return create_client(
        url, key,
        options=ClientOptions(persist_session=False, auto_refresh_token=False),
    )
