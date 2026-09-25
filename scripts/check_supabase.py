"""Check the Supabase connection configured in .env -- without printing any key.

    python scripts/check_supabase.py

Reads .env from the project root, then asks the project three questions with
the secret key: is it reachable, does Storage answer, does Auth answer. Each
line says OK or what to fix. Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_DB_PASSWORD")


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def base_url(url: str) -> str:
    """The project URL, also when the Data API address (.../rest/v1/) was copied."""
    return re.sub(r"/(rest|auth|storage)/v1/?$", "", url.strip().rstrip("/"))


def masked(key: str) -> str:
    return f"{key[:12]}... ({len(key)} characters)" if key else "(empty)"


def call(url: str, key: str, path: str) -> tuple[int, object]:
    headers = {"apikey": key}
    if not key.startswith("sb_"):          # legacy JWT keys also go in Authorization
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url.rstrip("/") + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body[:200].decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)


def main() -> int:
    path = ROOT / ".env"
    if not path.exists():
        print("No .env yet. Copy .env.example to .env and fill it in.")
        return 1
    env = load_env(path)
    ok = True
    for k in REQUIRED:
        if not env.get(k):
            print(f"MISSING  {k}")
            ok = False
    if not ok:
        return 1

    url, secret = base_url(env["SUPABASE_URL"]), env["SUPABASE_SECRET_KEY"]
    if not re.fullmatch(r"https://[a-z0-9]{20}\.supabase\.co/?", url):
        print(f"CHECK    SUPABASE_URL looks unusual: {url} (expected https://<20-letter-ref>.supabase.co)")
    if secret == env["SUPABASE_PUBLISHABLE_KEY"]:
        print("FIX      The secret and the publishable key are the same value.")
        return 1
    if secret.startswith("sb_publishable_"):
        print("FIX      SUPABASE_SECRET_KEY holds a publishable key; use the secret (sb_secret_...) one.")
        return 1
    print(f"KEY      secret key {masked(secret)}")

    status, body = call(url, secret, "/storage/v1/bucket")
    if status == 200:
        names = [b.get("name") for b in body] if isinstance(body, list) else []
        print(f"OK       Storage answers ({len(names)} bucket(s){': ' + ', '.join(names) if names else ''})")
    else:
        ok = False
        print(f"FAIL     Storage: HTTP {status} {body}")

    status, body = call(url, secret, "/auth/v1/admin/users?per_page=1")
    if status == 200:
        print("OK       Auth answers with admin rights (the key is the secret one)")
    else:
        ok = False
        print(f"FAIL     Auth admin: HTTP {status} {body}")

    print("\nAll good." if ok else "\nSomething to fix above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
