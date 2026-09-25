"""Publish the scoring model the code computes with into the `scoring` schema.

    python scripts/publish_scoring_model.py          # publish if new
    python scripts/publish_scoring_model.py --check  # only say whether it is published

Run after any change to weights, breakpoints, bands, the NACE mapping, the
knock-out catalogue or the Bundesbank data (a new version fingerprint), and
before deploying that change. Publishing the same model twice does nothing.
Needs `pip install "psycopg[binary]"` and SUPABASE_DB_PASSWORD in .env.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from psycopg.types.json import Jsonb  # noqa: E402

from credit_readiness.model_export import build_model, fingerprint, model_version  # noqa: E402
from supabase_db import connect  # noqa: E402

TABLES = ("factors", "curves", "bands", "settings", "sectors", "nace_ranges", "nace_sections",
          "knockouts", "benchmarks")


def main() -> int:
    model = build_model()
    version = model_version()
    conn, _ = connect(verbose=False)
    with conn:
        with conn.cursor() as cur:
            cur.execute("select published_at from scoring.model_versions where version = %s", (version,))
            row = cur.fetchone()
        if row:
            print(f"{version} is published (since {row[0]:%Y-%m-%d %H:%M} UTC) -- nothing to do")
            return 0
        if "--check" in sys.argv:
            print(f"{version} is NOT published yet -- run without --check")
            return 1
        with conn.transaction(), conn.cursor() as cur:
            cur.execute("insert into scoring.model_versions (version, content_sha256, description) "
                        "values (%s, %s, %s)",
                        (version, fingerprint(model), f"{len(model['factors'])} factors, "
                         f"{len(model['curves'])} curve points, {len(model['benchmarks'])} benchmark values"))
            for table in TABLES:
                rows = model[table]
                cols = list(rows[0])
                sql = (f"insert into scoring.{table} (version, {', '.join(cols)}) "
                       f"values (%s, {', '.join(['%s'] * len(cols))})")
                cur.executemany(sql, [(version, *[Jsonb(r[c]) if table == "settings" and c == "value" else r[c]
                                                  for c in cols]) for r in rows])
                print(f"  {table:14} {len(rows):5} rows")
        print(f"published {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
