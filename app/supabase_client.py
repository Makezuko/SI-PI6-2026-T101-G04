import os
from pathlib import Path
import threading

from dotenv import load_dotenv
import httpx
from supabase import ClientOptions, create_client

load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)

_THREAD_LOCAL = threading.local()


def _http_client():
    client = getattr(_THREAD_LOCAL, 'httpx_client', None)
    if client is None or client.is_closed:
        client = httpx.Client(timeout=20.0)
        _THREAD_LOCAL.httpx_client = client
    return client


def create_supabase_client():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError('Configure SUPABASE_URL e SUPABASE_KEY no .env.')
    if not key.startswith('sb_publishable_'):
        raise RuntimeError('Esta etapa usa uma chave sb_publishable_ do Supabase.')
    # Cada requisição cria seu cliente (sessões isoladas), reusando pool TLS da thread.
    return create_client(
        url, key,
        options=ClientOptions(
            persist_session=False,
            auto_refresh_token=False,
            httpx_client=_http_client(),
        ),
    )
