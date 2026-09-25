"""Connect to the Supabase Postgres database from .env, and apply migrations.

    python scripts/supabase_db.py check            connection + region, nothing changed
    python scripts/supabase_db.py plan             list migrations not yet applied
    python scripts/supabase_db.py apply            apply them, each in one transaction

A development tool (needs `pip install "psycopg[binary]"`); the portal itself
does not depend on it. The password is read from .env and never printed.

The direct address db.<ref>.supabase.co is often IPv6-only, which many office
and home networks cannot reach, so the session pooler (IPv4) is tried next,
region by region. The host that answers also tells us where the data lives.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "supabase" / "migrations"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_supabase import base_url, load_env  # noqa: E402

EU_REGIONS = ("eu-central-1", "eu-central-2", "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1")
OTHER_REGIONS = ("us-east-1", "us-east-2", "us-west-1", "us-west-2", "ap-southeast-1", "ap-south-1",
                 "ap-northeast-1", "ap-southeast-2", "ca-central-1", "sa-east-1")


def _ref(url: str) -> str:
    m = re.match(r"https://([a-z0-9]+)\.supabase\.co", base_url(url))
    if not m:
        raise SystemExit("SUPABASE_URL in .env is not a Supabase project URL")
    return m.group(1)


def connect(verbose: bool = True):
    import psycopg

    env = load_env(ROOT / ".env")
    ref, pw = _ref(env["SUPABASE_URL"]), env["SUPABASE_DB_PASSWORD"]
    candidates = [("direct", f"db.{ref}.supabase.co", "postgres")]
    for region in EU_REGIONS + OTHER_REGIONS:
        for prefix in ("aws-0", "aws-1"):
            candidates.append((region, f"{prefix}-{region}.pooler.supabase.com", f"postgres.{ref}"))
    last = None
    for label, host, user in candidates:
        try:
            conn = psycopg.connect(host=host, port=5432, user=user, password=pw, dbname="postgres",
                                   connect_timeout=6, sslmode="require")
        except psycopg.OperationalError as e:
            last = str(e).splitlines()[0]
            if "password authentication failed" in last:
                raise SystemExit("The database password in .env is wrong (Project Settings -> Database -> reset it).")
            continue
        if verbose:
            print(f"connected via {'direct address' if label == 'direct' else 'session pooler ' + host}")
        return conn, label
    raise SystemExit(f"No connection. Last error: {last}")


def applied(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("create schema if not exists app_meta")
        cur.execute("create table if not exists app_meta.migrations "
                    "(name text primary key, applied_at timestamptz not null default now())")
        cur.execute("select name from app_meta.migrations")
        names = {r[0] for r in cur.fetchall()}
    conn.commit()
    return names


def pending(conn) -> list[Path]:
    done = applied(conn)
    return [p for p in sorted(MIGRATIONS.glob("*.sql")) if p.name not in done]


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    conn, label = connect()
    with conn:
        if cmd == "check":
            with conn.cursor() as cur:
                cur.execute("select current_setting('server_version'), inet_server_addr()")
                version, _ = cur.fetchone()
            print(f"postgres {version}")
            if label != "direct":
                print(f"region  {label}" + ("  (EU)" if label in EU_REGIONS else "  (NOT EU -- see guardrails)"))
            else:
                print("region  not visible over the direct address; check Project Settings -> General")
        elif cmd == "plan":
            todo = pending(conn)
            print("\n".join(f"pending  {p.name}" for p in todo) or "nothing pending")
        elif cmd == "apply":
            for p in pending(conn):
                sql = p.read_text(encoding="utf-8")
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        cur.execute("insert into app_meta.migrations (name) values (%s)", (p.name,))
                print(f"applied  {p.name}")
            print("up to date")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
