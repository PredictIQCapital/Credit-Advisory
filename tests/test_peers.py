"""BACH peer comparison: matching, fallbacks, and the report section.

Runs on a small synthetic extract, so it needs neither the licensed BACH file
nor any particular edition of it.
"""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from credit_readiness import peers
from credit_readiness.engine import run_diagnostic
from credit_readiness.ingest.json_intake import load_case
from credit_readiness.models import Sector
from credit_readiness.ratios import compute_ratios
from credit_readiness.reporting.report import render_markdown

from tests.test_coach import SAMPLE


def _cell(q50: float, n: int = 100) -> dict:
    return {"q25": q50 - 10, "q50": q50, "q75": q50 + 10, "n": n}


def _measures(e: float) -> dict:
    return {"E": _cell(e), "r33": _cell(8.0), "r35": _cell(5.0),
            "r36": _cell(4.0), "r52": _cell(15.0)}


FIXTURE = {
    "citation": "BACH database: test",
    "edition": "2026-09-14",
    "cells": {"DE": {
        "2022": {"Zc": {"insgesamt": _measures(30.0)}},
        "2023": {
            "C28": {"unter_10m": _measures(40.0)},
            "C": {"unter_10m": _measures(35.0), "insgesamt": _measures(34.0)},
            "G45": {"insgesamt": _measures(26.0)},
            "Zc": {"insgesamt": _measures(33.0), "unter_10m": _measures(32.0)},
        },
        "2024": {"Zc": {"insgesamt": _measures(31.0)}},
    }},
}


@pytest.fixture(autouse=True)
def bach_file(tmp_path, monkeypatch):
    path = tmp_path / "bach.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    monkeypatch.setenv("BACH_DATA_FILE", str(path))
    peers._dataset.cache_clear()
    yield path
    peers._dataset.cache_clear()


def _case(nace=None, period_end="2023-12-31", country="DE", sector=None):
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))   # Mueller, revenue 8.2M
    raw = copy.deepcopy(raw)
    raw["profile"]["nace_code"] = nace
    raw["profile"]["country"] = country
    if sector:
        raw["profile"]["sector"] = sector.value
    raw["income_statement"]["period_end"] = period_end
    raw["balance_sheet"]["period_end"] = period_end
    return load_case(raw)


def _compare(case):
    return peers.compare(case, compute_ratios(case))


def _equity_basis(p):
    return next(m.basis for m in p.metrics if m.label.startswith("Eigenkapital"))


# ------------------------------------------------------------------ matching


def test_wz_division_size_and_year_of_the_accounts():
    p = _compare(_case(nace="C28.41"))
    assert p.year == 2023 and p.requested_year == 2023 and not p.year_note
    assert _equity_basis(p) == "Deutschland, WZ C28, Umsatz unter 10 Mio. EUR, 2023"
    assert p.metrics[0].quartiles[1] == pytest.approx(0.40)


def test_falls_back_from_division_to_section():
    p = _compare(_case(nace="C25.62"))
    assert _equity_basis(p) == "Deutschland, WZ C, Umsatz unter 10 Mio. EUR, 2023"


def test_falls_back_to_all_sizes_when_the_size_cell_is_blank():
    # Car dealers: the only cell is "all sizes" -- the sector the scorecard
    # itself has no Bundesbank cell for (it scores them generically).
    p = _compare(_case(nace="G45.11"))
    assert _equity_basis(p) == "Deutschland, WZ G45, alle Groessenklassen, 2023"


def test_without_wz_code_uses_the_sector_bucket():
    p = _compare(_case(sector=Sector.MANUFACTURING))
    assert _equity_basis(p) == "Deutschland, WZ C, Umsatz unter 10 Mio. EUR, 2023"


def test_bucket_without_a_bach_cell_goes_to_all_sectors():
    p = _compare(_case(sector=Sector.OTHER_SERVICES))
    assert _equity_basis(p) == "Deutschland, alle Branchen, Umsatz unter 10 Mio. EUR, 2023"


def test_accounts_newer_than_bach_use_the_newest_year_and_say_so():
    p = _compare(_case(nace="C28.41", period_end="2025-12-31"))
    assert p.year == 2024 and p.requested_year == 2025
    assert "2025" in p.year_note and "2024" in p.year_note
    assert p.provisional and "vorlaeufig" in p.year_note     # DE final: Nov 2026


def test_older_accounts_are_compared_with_their_own_year():
    p = _compare(_case(nace="C28.41", period_end="2022-12-31"))
    assert p.year == 2022 and _equity_basis(p).startswith("Deutschland, alle Branchen")


def test_another_countrys_firms_are_not_peers():
    assert _compare(_case(nace="C28.41", country="FR")) is None


def test_no_extract_no_comparison(monkeypatch, tmp_path):
    monkeypatch.setenv("BACH_DATA_FILE", str(tmp_path / "missing.json"))
    peers._dataset.cache_clear()
    assert not peers.available()
    assert _compare(_case(nace="C28.41")) is None


# ------------------------------------------------------------------ details


@pytest.mark.parametrize("year,edition,expected", [
    (2023, date(2026, 9, 14), False),
    (2024, date(2026, 9, 14), True),       # Germany publishes 2024 final in Nov 2026
    (2024, date(2026, 12, 1), False),
])
def test_provisional_follows_the_release_calendar(year, edition, expected):
    assert peers.is_provisional("DE", year, edition) is expected


def test_head_offices_and_consultancy_are_told_apart():
    assert peers.sector_codes("70.10", None)[0] == "M701"
    assert peers.sector_codes("70.22", None)[:3] == ["M702", "M70", "Mc"]


def test_days_receivable_counts_longer_as_worse():
    p = _compare(_case(nace="C28.41"))
    days = next(m for m in p.metrics if m.label == "Debitorenlaufzeit")
    assert days.quartiles[1] == pytest.approx(15.0 * 3.65)
    assert not days.higher_is_better
    # Mueller waits ~51 days against a 55-day median: better than half.
    assert days.percentile > 50


def test_peers_never_move_the_score(monkeypatch, tmp_path):
    case = _case(nace="C28.41")
    with_peers = run_diagnostic(case)
    monkeypatch.setenv("BACH_DATA_FILE", str(tmp_path / "missing.json"))
    peers._dataset.cache_clear()
    without = run_diagnostic(case)
    assert with_peers.peer_comparison and without.peer_comparison is None
    assert with_peers.scorecard.total_score == without.scorecard.total_score


# ------------------------------------------------------------------ report


def test_report_prints_the_section_with_its_source():
    md = render_markdown(run_diagnostic(_case(nace="C28.41")))
    assert "### Vergleich mit Unternehmen wie Ihrem (2023)" in md
    assert "Deutschland, WZ C28, Umsatz unter 10 Mio. EUR, 2023" in md
    assert "Quelle: BACH database: test" in md


def test_report_leaves_the_section_out_without_data(monkeypatch, tmp_path):
    monkeypatch.setenv("BACH_DATA_FILE", str(tmp_path / "missing.json"))
    peers._dataset.cache_clear()
    md = render_markdown(run_diagnostic(_case(nace="C28.41")))
    assert "Vergleich mit Unternehmen wie Ihrem" not in md
