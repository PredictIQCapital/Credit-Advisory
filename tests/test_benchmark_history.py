"""Five-year sector history from the Bundesbank editions."""

from __future__ import annotations

import json
from pathlib import Path

from credit_readiness import benchmarks
from credit_readiness.models import Sector
from credit_readiness.ratios import compute_ratios

ROOT = Path(__file__).resolve().parents[1]


def test_history_covers_the_last_five_reporting_years():
    years = benchmarks.history_years()
    assert len(years) == 5
    assert years[-1] == benchmarks.REPORTING_YEAR
    assert years == list(range(years[0], years[0] + 5))


def test_latest_history_year_equals_the_scoring_data():
    """The trend table and the scorecard must not disagree about the latest year."""
    for sector in Sector:
        cell = benchmarks.sector_cell("eigenmittel_pct_bilanzsumme", sector, 5_000_000)
        if cell is None:
            continue
        series, _ = benchmarks.history("eigenmittel_pct_bilanzsumme", sector, 5_000_000)
        assert series[-1][1] == cell[0]


def test_each_year_comes_from_the_newest_edition_that_publishes_it():
    """Editions overlap by one year and the later one carries the revision."""
    folder = ROOT / "data" / "reference" / "bundesbank"
    editions = [json.loads(p.read_text(encoding="utf-8"))
                for p in folder.glob("verhaeltniszahlen_*.json")]
    newest_for = {}
    for ed in sorted(editions, key=lambda e: e["edition"]):
        for y in ed["years"]:
            newest_for[y] = ed
    series, _ = benchmarks.history("eigenmittel_pct_bilanzsumme", Sector.RETAIL, 5_000_000)
    for year, cell in series:
        published = (newest_for[year]["sectors"]["Einzelhandel"]["alle_rechtsformen"]
                     ["eigenmittel_pct_bilanzsumme"]["2_bis_10m"][str(year)])
        assert cell == published


def test_unmapped_sector_falls_back_to_all_sectors():
    series, basis = benchmarks.history("eigenmittel_pct_bilanzsumme", Sector.OTHER, 5_000_000)
    assert len(series) == 5
    assert basis.startswith("alle Branchen")


def test_trends_reach_the_diagnostic(case_01):
    trends = benchmarks.sector_trends(case_01.profile.sector, compute_ratios(case_01))
    assert trends and all(len(t.medians) == 5 for t in trends)
    assert all(t.company_value is not None for t in trends)
    assert trends[0].basis.startswith(case_01.profile.sector.value)
