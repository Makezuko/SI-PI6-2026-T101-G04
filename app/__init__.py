import os
from datetime import timedelta
from pathlib import Path

from cachelib import FileSystemCache
from dotenv import load_dotenv
from flask import Flask, abort, request
from flask_session import Session

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')

app = Flask(__name__)
secret = os.getenv('FLASK_SECRET_KEY')
if not secret or secret == 'secret-key':
    raise RuntimeError('Defina FLASK_SECRET_KEY no .env com uma chave aleatória.')

session_dir = Path(app.instance_path) / 'mvp_sessions'
session_dir.mkdir(parents=True, exist_ok=True)
app.config.update(
    SECRET_KEY=secret,
    SESSION_TYPE='cachelib',
    SESSION_CACHELIB=FileSystemCache(str(session_dir), threshold=500, mode=0o600),
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true',
    MAX_CONTENT_LENGTH=10 * 1024 * 1024,
)
Session(app)


@app.before_request
def validate_form_origin():
    # Mantém os formulários existentes, sem adicionar campos ao HTML.
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return
    from urllib.parse import urlsplit
    origin = request.headers.get('Origin') or request.headers.get('Referer')
    if not origin:
        abort(403, description='Origem ausente. Reabra o formulário no navegador.')
    source, target = urlsplit(origin), urlsplit(request.host_url)
    if (source.scheme, source.netloc) != (target.scheme, target.netloc):
        abort(403, description='Origem do formulário inválida.')


from app import routes  # noqa: E402,F401
