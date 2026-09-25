"""The scoring model as data: stable versions, faithful curves, stored results.

The last test compares the SQL functions in the `scoring` schema with the
Python engine on the live project; it runs only with CRA_SUPABASE_TESTS=1
and after scripts/publish_scoring_model.py.
"""

from __future__ import annotations

import os
import random
from dataclasses import replace

import pytest

from credit_readiness import model_export
from credit_readiness.models import Sector
from credit_readiness.scorecard import CALIBRATION, FACTORS, band_for, curve_for, interpolate

from tests.test_workflow import TODAY, full_case, store  # noqa: F401  (fixtures)

LIVE = os.environ.get("CRA_SUPABASE_TESTS") == "1"


def test_same_rules_same_version():
    a, b = model_export.build_model(), model_export.build_model()
    assert model_export.fingerprint(a) == model_export.fingerprint(b)
    assert model_export.model_version().startswith("m-") and len(model_export.model_version()) == 14


def test_a_changed_weight_is_a_new_version(monkeypatch):
    before = model_export.fingerprint(model_export.build_model())
    changed = (replace(FACTORS[0], weight=FACTORS[0].weight + 0.01),) + FACTORS[1:]
    monkeypatch.setattr(model_export, "FACTORS", changed)
    assert model_export.fingerprint(model_export.build_model()) != before


def test_generic_curves_are_the_scorecard_breakpoints():
    curves = model_export.build_model()["curves"]
    for fd in FACTORS:
        rows = [(r["x"], r["score"]) for r in curves
                if r["factor_key"] == fd.key and r["sector"] == model_export.GENERIC]
        assert rows == [(round(x, 6), round(y, 6)) for x, y in fd.breakpoints]


def test_every_sector_curve_is_exported():
    curves = model_export.build_model()["curves"]
    for key in CALIBRATION:
        fd = next(f for f in FACTORS if f.key == key)
        for sector in Sector:
            for size, revenue in model_export.SIZE_REVENUE.items():
                c = curve_for(fd, sector, revenue)
                rows = [(r["x"], r["score"]) for r in curves
                        if r["factor_key"] == key and r["sector"] == sector.value and r["size_class"] == size]
                if c.basis == model_export.GENERIC_BASIS:
                    assert rows == []
                else:
                    assert rows == [(round(x, 6), round(y, 6)) for x, y in c.breakpoints]


def test_a_report_is_stored_with_its_model_version(store, full_case):  # noqa: F811
    from credit_readiness import workflow as wf

    assert wf.run_case_diagnostic(store, full_case, today=TODAY)["ok"]
    [row] = store.list_results(full_case)
    assert row["kind"] == "report" and row["model_version"] == model_export.model_version()
    assert row["summary"]["model_version"] == row["model_version"]
    assert {f["factor_key"] for f in row["factors"]} == {f.key for f in FACTORS}
    assert row["score"] == row["summary"]["score"]


# ------------------------------------------------------------------ live: SQL == Python


@pytest.mark.skipif(not LIVE, reason="set CRA_SUPABASE_TESTS=1 to compare with the Supabase functions")
def test_sql_functions_score_like_python():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from supabase_db import connect

    version = model_export.model_version()
    rng = random.Random(7)
    conn, _ = connect(verbose=False)
    with conn, conn.cursor() as cur:
        cur.execute("select 1 from scoring.model_versions where version = %s", (version,))
        assert cur.fetchone(), f"{version} is not published -- run scripts/publish_scoring_model.py"
        checked = 0
        for fd in FACTORS:
            xs = [x for x, _ in fd.breakpoints]
            lo, hi = xs[0], xs[-1]
            span = (hi - lo) or 1.0
            sectors = list(Sector) if fd.key in CALIBRATION else [None]
            for sector in sectors:
                revenue = rng.choice(list(model_export.SIZE_REVENUE.values()))
                curve = curve_for(fd, sector, revenue).breakpoints
                for _ in range(6):
                    x = rng.uniform(lo - 0.2 * span, hi + 0.2 * span)
                    cur.execute("select scoring.factor_score(%s::text, %s::numeric, %s::text, %s::numeric, %s::text)",
                                (fd.key, x, sector.value if sector else "*", revenue, version))
                    # Curve points are stored to 6 decimals; scores agree to 0.0001
                    # points (reports show 0.1).
                    assert float(cur.fetchone()[0]) == pytest.approx(interpolate(x, curve), abs=1e-4), \
                        (fd.key, sector, revenue, x)
                    checked += 1
        for score in (0, 37.9, 38, 51.99, 52, 65, 77.9, 78, 100):
            cur.execute("select scoring.band_for(%s::numeric, %s::text)", (score, version))
            assert cur.fetchone()[0] == band_for(score).value
        from credit_readiness import nace
        for code in ("C25.62", "47.11", "46", "86.1", "45.20", "01.11", "F25", "xx"):
            cur.execute("select scoring.sector_for_nace(%s::text, %s::text)", (code, version))
            parsed = nace.parse(code)
            assert cur.fetchone()[0] == (parsed.sector.value if parsed else None), code
    assert checked > 300
