import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise RuntimeError(
        "Configure SUPABASE_URL e SUPABASE_KEY no arquivo .env."
    )


def create_supabase_client():
    return create_client(url, key)