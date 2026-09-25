"""A small Supabase client over HTTPS, standard library only.

Three services, one class:

  * Data API (PostgREST) on the private `app` schema, with the secret key;
  * Storage, for the files in the private `case-files` bucket;
  * Auth, for accounts: admin calls with the secret key, password sign-in
    with the publishable key.

No SDK on purpose: the portal keeps zero runtime dependencies, which also
keeps a Vercel function small and quick to start.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

SCHEMA = "app"
BUCKET = "case-files"
TIMEOUT = 20


class SupabaseError(RuntimeError):
    def __init__(self, status: int, body: Any, what: str = ""):
        self.status, self.body = status, body
        msg = body.get("message") or body.get("msg") or body.get("error_description") or body.get("error") \
            if isinstance(body, dict) else body
        super().__init__(f"Supabase {what} HTTP {status}: {msg}")


def base_url(url: str) -> str:
    """The project URL, also when the Data API address (.../rest/v1/) was given."""
    return re.sub(r"/(rest|auth|storage)/v1/?$", "", (url or "").strip().rstrip("/"))


class Supabase:
    def __init__(self, url: str, secret_key: str, publishable_key: str = ""):
        if not url or not secret_key:
            raise ValueError("SUPABASE_URL und SUPABASE_SECRET_KEY sind noetig")
        self.url = base_url(url)
        self.secret = secret_key
        self.publishable = publishable_key or secret_key

    # ------------------------------------------------------------------ http
    @staticmethod
    def _auth_headers(key: str) -> dict:
        h = {"apikey": key}
        if not key.startswith("sb_"):          # legacy JWT keys go in Authorization too
            h["Authorization"] = f"Bearer {key}"
        return h

    def _request(self, method: str, path: str, *, key: Optional[str] = None, body: Any = None,
                 raw: Optional[bytes] = None, headers: Optional[dict] = None, what: str = "") -> tuple[int, Any, dict]:
        h = self._auth_headers(key or self.secret)
        data = None
        if raw is not None:
            data = raw
        elif body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                payload = r.read()
                ctype = r.headers.get("Content-Type", "")
                return r.status, (json.loads(payload) if payload and "json" in ctype else payload), dict(r.headers)
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                parsed = json.loads(payload)
            except ValueError:
                parsed = payload.decode("utf-8", "replace")[:300]
            raise SupabaseError(e.code, parsed, what) from None

    # ------------------------------------------------------------------ data
    def select(self, table: str, query: str = "") -> list[dict]:
        _, rows, _ = self._request("GET", f"/rest/v1/{table}?{query}",
                                   headers={"Accept-Profile": SCHEMA}, what=f"select {table}")
        return rows or []

    def insert(self, table: str, rows: Any, *, upsert: bool = False, returning: bool = True) -> list[dict]:
        prefer = ["return=representation" if returning else "return=minimal"]
        if upsert:
            prefer.append("resolution=merge-duplicates")
        _, out, _ = self._request("POST", f"/rest/v1/{table}", body=rows,
                                  headers={"Content-Profile": SCHEMA, "Prefer": ",".join(prefer)},
                                  what=f"insert {table}")
        return out or []

    def update(self, table: str, query: str, values: dict) -> list[dict]:
        _, out, _ = self._request("PATCH", f"/rest/v1/{table}?{query}", body=values,
                                  headers={"Content-Profile": SCHEMA, "Prefer": "return=representation"},
                                  what=f"update {table}")
        return out or []

    def delete(self, table: str, query: str) -> None:
        if not query:
            raise ValueError("delete without a filter")
        self._request("DELETE", f"/rest/v1/{table}?{query}", headers={"Content-Profile": SCHEMA},
                      what=f"delete {table}")

    def rpc(self, fn: str, args: dict) -> Any:
        _, out, _ = self._request("POST", f"/rest/v1/rpc/{fn}", body=args,
                                  headers={"Content-Profile": SCHEMA}, what=f"rpc {fn}")
        return out

    # --------------------------------------------------------------- storage
    def upload(self, path: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        self._request("POST", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}", raw=content,
                      headers={"Content-Type": content_type, "x-upsert": "true"}, what="upload")

    def download(self, path: str) -> bytes:
        _, data, _ = self._request("GET", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(path)}",
                                   what="download")
        return data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")

    def remove(self, paths: list[str]) -> None:
        if paths:
            self._request("DELETE", f"/storage/v1/object/{BUCKET}", body={"prefixes": paths}, what="remove")

    def list_folder(self, prefix: str) -> list[str]:
        """Every object path under `prefix`, descending into sub-folders."""
        out, stack = [], [prefix.strip("/")]
        while stack:
            folder = stack.pop()
            _, items, _ = self._request("POST", f"/storage/v1/object/list/{BUCKET}",
                                        body={"prefix": folder, "limit": 1000}, what="list")
            for it in items or []:
                full = f"{folder}/{it['name']}" if folder else it["name"]
                (out if it.get("id") else stack).append(full)
        return out

    # ------------------------------------------------------------------ auth
    def admin_create_user(self, email: str, password: str, name: str) -> dict:
        _, user, _ = self._request("POST", "/auth/v1/admin/users", body={
            "email": email, "password": password, "email_confirm": True,
            "user_metadata": {"name": name}}, what="create user")
        return user

    def admin_update_user(self, auth_id: str, **fields: Any) -> dict:
        _, user, _ = self._request("PUT", f"/auth/v1/admin/users/{auth_id}", body=fields, what="update user")
        return user

    def admin_delete_user(self, auth_id: str) -> None:
        self._request("DELETE", f"/auth/v1/admin/users/{auth_id}", what="delete user")

    def sign_in(self, email: str, password: str) -> Optional[dict]:
        """The Auth user on a correct password, None on a wrong one."""
        try:
            _, out, _ = self._request("POST", "/auth/v1/token?grant_type=password", key=self.publishable,
                                      body={"email": email, "password": password}, what="sign in")
        except SupabaseError as e:
            if e.status in (400, 401):
                return None
            raise
        return out.get("user")


def q(value: Any) -> str:
    """A value for a PostgREST filter, URL-encoded."""
    return urllib.parse.quote(str(value), safe="")
