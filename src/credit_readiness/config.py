"""Which storage the portal uses: local folders or Supabase.

    CRA_STORE=supabase   Supabase (needs SUPABASE_URL and SUPABASE_SECRET_KEY)
    CRA_STORE=local      folders under data/ (tests, offline work)
    unset                Supabase when SUPABASE_URL is configured, else local

Variables come from the environment (Vercel: project settings) or, when
running locally, from the .env file in the project root. A value already in
the environment always wins over .env.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Optional[Path] = None) -> None:
    path = path or ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def use_supabase() -> bool:
    load_dotenv()
    choice = os.environ.get("CRA_STORE", "").lower()
    if choice == "local":
        return False
    if choice == "supabase":
        return True
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SECRET_KEY"))


def supabase_client():
    from .supa import Supabase

    load_dotenv()
    return Supabase(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SECRET_KEY", ""),
                    os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""))


def backends(data_dir: Optional[str] = None, local: Optional[bool] = None) -> tuple[Any, Any, Any, str]:
    """(case store, user store, session manager, description)."""
    if local is None:
        local = not use_supabase()
    if not local:
        from .auth_supabase import DbSessionManager, SupabaseUserStore
        from .casefile_supabase import SupabaseCaseStore

        sb = supabase_client()
        return (SupabaseCaseStore(sb), SupabaseUserStore(sb), DbSessionManager(sb),
                f"Supabase {sb.url}")
    from .auth import SessionManager, UserStore
    from .casefile import LocalCaseStore

    store = LocalCaseStore(data_dir)
    return store, UserStore(store.root), SessionManager(), f"Ordner {store.root}"
