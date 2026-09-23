"""Load .env as early as possible so every entrypoint sees TRACCIA_API_KEY / TRACCIA_ENDPOINT
without the viewer having to `source .env`. Import this FIRST in any runnable module.

Real environment variables always win (override=False), so CI and explicit exports still
work. python-dotenv is optional; if it is not installed, real env vars still function.
"""
from __future__ import annotations

try:
    from pathlib import Path
    from dotenv import load_dotenv
    _ENV = Path(__file__).resolve().parent.parent / ".env"   # repo-root/.env
    if _ENV.exists():
        load_dotenv(_ENV, override=False)
except Exception:
    pass
