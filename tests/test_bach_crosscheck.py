"""The Bundesbank dataset against BACH, an independent read of the same data.

BACH's German cells are built by the Bundesbank from the same firm-level
accounts as the Jahresabschlussstatistik, but reach us as a table rather than
through a PDF parser. Where the two describe the same population, their
quartiles must be close; a parser that files a page under the wrong sector
(ADR-006) shows up here as a gap of 15-25 points.

Skipped unless the extract exists: the BACH terms forbid redistribution, so
it is git-ignored. Build it with `python scripts/import_bach.py <bach.csv>`.
The path is fixed on purpose: BACH_DATA_FILE may point peers.py at a test
fixture, and this check must only ever run on the real data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from credit_readiness import benchmarks

BACH_FILE = Path(__file__).resolve().parent.parent / "data" / "reference" / "bach" / "bach.json"

pytestmark = pytest.mark.skipif(not BACH_FILE.exists(), reason="BACH extract not built")

#: Our sector -> BACH NACE code, only where both cover the same activities.
#: Left out: "Freiberufliche ..." (Bundesbank M+N, BACH splits them) and
#: "Sonstige Dienstleistungen" (a Bundesbank grouping BACH does not have).
SECTORS = {
    "__alle__": "Zc",
    "Verarbeitendes Gewerbe": "C",
    "Baugewerbe": "F",
    "Grosshandel": "G46",
    "Einzelhandel": "G47",
    "Verkehr und Lagerei": "H",
    "Gastgewerbe": "I",
    "Information und Kommunikation": "J",
    "Gesundheitswesen": "Q86",
}

#: Size classes with identical bounds. The Bundesbank's 2-10M has no BACH twin.
SIZES = ("insgesamt", "10_bis_50m", "ab_50m")

#: Bundesbank metric -> (BACH measure, allowed range of BACH median minus
#: Bundesbank median, in percentage points). Ranges come from the 2023 data
#: after the ADR-006 fix, with a margin; the misfiled pages were 15-25 off.
#: Equity is one-sided: the Bundesbank's "Eigenmittel" is the stricter
#: definition and comes out lower in every cell.
METRICS = {
    "eigenmittel_pct_bilanzsumme": ("E", (-1.0, 8.0)),
    "vorraete_pct_bilanzsumme": ("A2", (-7.0, 4.0)),
    "forderungen_ll_pct_umsatz": ("r52", (-1.5, 1.5)),
    "ergebnis_vor_steuern_pct_umsatz": ("r36", (-3.0, 1.5)),
}


def _bach_cells(year: str) -> dict:
    data = json.loads(BACH_FILE.read_text(encoding="utf-8"))
    germany = data["cells"].get("DE", {})
    assert year in germany, f"BACH extract has no German {year}; re-run scripts/import_bach.py"
    return germany[year]


def _pairs():
    for sector, code in SECTORS.items():
        for size in SIZES:
            for metric in METRICS:
                yield sector, code, size, metric


@pytest.mark.parametrize("sector,code,size,metric", list(_pairs()))
def test_bundesbank_median_agrees_with_bach(sector, code, size, metric):
    year = str(benchmarks.REPORTING_YEAR)
    ours = benchmarks._dataset()["sectors"][sector].get(size, {}).get(metric)
    measure, (low, high) = METRICS[metric]
    theirs = _bach_cells(year).get(code, {}).get(size, {}).get(measure)
    if ours is None or theirs is None:
        pytest.skip("cell not published in one of the two sources")
    gap = theirs["q50"] - ours["q50"]
    assert low <= gap <= high, (
        f"{sector} / {size} / {metric}: Bundesbank median {ours['q50']}, "
        f"BACH {code} {measure} {theirs['q50']} -- gap {gap:+.1f} outside "
        f"[{low}, {high}]. Check which PDF page the importer took."
    )
