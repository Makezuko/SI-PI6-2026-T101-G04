"""Diagnóstico sanitizado de ambiente e transporte, sem credenciais de login."""
from importlib.metadata import distributions, version, PackageNotFoundError
from pathlib import Path
import json
import os
import sys


def exception_info(error):
    chain, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        row = dict(type=type(error).__name__)
        for key in ('errno', 'winerror'):
            value = getattr(error, key, None)
            if isinstance(value, int):
                row[key] = value
        chain.append(row)
        error = error.__cause__ or error.__context__
    return chain


def main():
    from dotenv import load_dotenv, dotenv_values
    root = Path(__file__).resolve().parent.parent
    path = root / '.env'
    load_dotenv(path, override=False)
    required = ['SUPABASE_URL', 'SUPABASE_KEY', 'FLASK_SECRET_KEY']
    file_values = dotenv_values(path)
    packages = ['supabase', 'supabase-auth', 'gotrue', 'httpx', 'httpcore',
                'flask', 'flask-session', 'cachelib', 'python-dotenv', 'certifi']
    current = {}
    for package in packages:
        try:
            current[package] = version(package)
        except PackageNotFoundError:
            current[package] = None
    old = {d.metadata['Name'].lower().replace('_', '-'): d.version
           for d in distributions(path=[str(root / 'venv/Lib/site-packages')])}
    print(json.dumps(dict(python=sys.executable, env_file=str(path), env_exists=path.exists(),
        required_present={k: bool(os.getenv(k)) for k in required},
        environment_matches_file={k: os.getenv(k) == file_values.get(k) for k in required},
        current=current, old={k: old.get(k) for k in packages}), ensure_ascii=True), flush=True)
    # GET público sem apikey, Authorization, cookies, e-mail, senha ou perfil.
    import httpx
    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(os.environ['SUPABASE_URL'].rstrip('/') + '/auth/v1/health')
        print(json.dumps(dict(stage='public_auth_transport', reachable=True, http_status=response.status_code)))
    except Exception as error:
        print(json.dumps(dict(stage='public_auth_transport', reachable=False, exceptions=exception_info(error))))


if __name__ == '__main__':
    main()
