"""Vercel entry point: the portal's request handler, bound to Supabase.

Vercel runs this module as one Python function and hands it every request
(vercel.json rewrites all paths here). The handler is the same class the
local server uses; only the storage behind it differs -- Supabase, because a
serverless function keeps no files and no memory between requests.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

# The package is installed from pyproject.toml; the path is a fallback for
# `vercel dev` in a fresh checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from credit_readiness.config import backends  # noqa: E402
from credit_readiness.webapp.server import Handler  # noqa: E402

_store, _users, _sessions, _ = backends(local=False)


class handler(Handler):  # noqa: N801 -- Vercel looks for this name
    store = _store
    users = _users
    sessions = _sessions
    today = None
    demo = False
    lock = threading.Lock()
