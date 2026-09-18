"""Local client portal (standard library only). See server.py for scope."""

from .server import make_server, serve

__all__ = ["make_server", "serve"]
