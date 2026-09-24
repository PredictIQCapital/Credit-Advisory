"""Sector benchmarks, from the Bundesbank Jahresabschlussstatistik.

Purpose: distinguish "this company is weak" from "this company is normal for a
genuinely difficult sector". That distinction changes the advice completely --
a 12% equity ratio in Einzelhandel sits near the sector median, the same ratio
in Unternehmensdienstleistungen sits in the bottom quartile.

DATA
====
Deutsche Bundesbank, Statistische Fachreihe "Jahresabschlussstatistik
(Verhaeltniszahlen)". The dataset shipped with the package is built by
`scripts/import_bundesbank_ratios.py` from the published PDFs; the per-edition
extracts stay in data/reference/bundesbank/ as provenance.

We use the **Quartilswerte**, not the weighted averages. The averages weight
each firm by its share of the reference base, so they describe the largest
company in the group, not a Mittelstaendler. The quartiles are the firm-level
distribution.

Two caveats that belong in any client-facing use, and are carried in VINTAGE
and CAVEAT below:

  * Coverage of our target size class is thin. The Bundesbank's own comparison
    against the Unternehmensregister puts the 2-10M EUR revenue class at ~14%
    and the 10-50M class at ~42% of turnover. Smaller firms are
    under-represented, and the ones that are present reached the pool through
    banks and credit insurers -- a population already in credit relationships.
  * Quartiles are not additive. The median equity ratio and the median debt
    ratio do not add up to a balance sheet; each distribution stands alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .models import Sector

_DATA_FILE = Path(__file__).with_name("reference") / "bundesbank_quartiles.json"

# Revenue thresholds of the Bundesbank size classes, in EUR.
_SIZE_CLASSES = [
    (2_000_000, "unter_2m"),
    (10_000_000, "2_bis_10m"),
    (50_000_000, "10_bis_50m"),
    (float("inf"), "ab_50m"),
]
_DEFAULT_SIZE = "2_bis_10m"

#: Interest expense net of interest income, as a share of revenue, for the
#: 2-10M and 10-50M size classes (weighted-average table of the same
#: publication). Used to step from the published pre-tax margin to an EBIT
#: margin, because the quartile tables publish only the former.
EBT_TO_EBIT_ADJUSTMENT = 0.005


@lru_cache(maxsize=1)
def _dataset() -> dict:
    if not _DATA_FILE.exists():          # pragma: no cover - build artefact missing
        raise FileNotFoundError(
            f"{_DATA_FILE} fehlt. Erzeugen mit: "
            "python scripts/import_bundesbank_ratios.py <pdf-ordner>"
        )
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))


def vintage() -> str:
    d = _dataset()
    return (f"Deutsche Bundesbank, Jahresabschlussstatistik (Verhaeltniszahlen), "
            f"Ausgabe {d['edition']}, Berichtsjahr {d['reporting_year']}, Quartilswerte")


#: Kept as a module constant because the report prints it on every page.
VINTAGE = vintage()
CAVEAT = _dataset()["caveat"]
REPORTING_YEAR = _dataset()["reporting_year"]


def size_class(revenue: Optional[float]) -> str:
    """Bundesbank size class for a revenue figure."""
    if not revenue or revenue <= 0:
        return _DEFAULT_SIZE
    return next(key for limit, key in _SIZE_CLASSES if revenue < limit)


_SECTOR_KEYS = {s: s.value for s in Sector}


def quartiles(
    metric: str, sector: Optional[Sector] = None, revenue: Optional[float] = None
) -> Optional[dict]:
    """{'q25','q50','q75'} for a metric, or None when the cell is not published.

    Falls back from the sector to all sectors, and from the size class to the
    sector total, so a thin cell degrades rather than disappears.
    """
    data = _dataset()["sectors"]
    size = size_class(revenue)
    for sector_key in ([_SECTOR_KEYS[sector]] if sector else []) + ["__alle__"]:
        block = data.get(sector_key)
        if not block:
            continue
        for size_key in (size, "insgesamt"):
            cell = block.get(size_key, {}).get(metric)
            if cell:
                return cell
    return None


SIZE_LABELS = {
    "unter_2m": "Umsatz unter 2 Mio. EUR",
    "2_bis_10m": "Umsatz 2-10 Mio. EUR",
    "10_bis_50m": "Umsatz 10-50 Mio. EUR",
    "ab_50m": "Umsatz ab 50 Mio. EUR",
    "insgesamt": "alle Groessenklassen",
}


def sector_cell(
    metric: str, sector: Sector, revenue: Optional[float] = None
) -> Optional[tuple[dict, str]]:
    """(quartiles, size key) from the sector's own figures, or None.

    Unlike quartiles(), this never falls back to all sectors: the scorecard
    uses it to decide whether a sector-specific curve exists at all, and a
    silent fallback would label an all-sector curve as a sector one.
    """
    block = _dataset()["sectors"].get(_SECTOR_KEYS[sector])
    if not block:
        return None
    for size_key in (size_class(revenue), "insgesamt"):
        cell = block.get(size_key, {}).get(metric)
        if cell and all(k in cell for k in ("q25", "q50", "q75")):
            return cell, size_key
    return None


def percentile(value: float, cell: dict, higher_is_better: bool = True) -> float:
    """Where a value sits in the published distribution, 0-100.

    Linear between the three published quartiles; beyond them the tails are
    extended at the slope of the nearest segment and clamped. This is an
    estimate from three points, not a distribution -- it is used to phrase a
    sentence, never to compute a score.
    """
    q25, q50, q75 = cell["q25"], cell["q50"], cell["q75"]
    points = [(q25, 25.0), (q50, 50.0), (q75, 75.0)]
    if value <= q25:
        span = max(q50 - q25, 1e-9)
        pct = 25.0 - (q25 - value) / span * 25.0
    elif value >= q75:
        span = max(q75 - q50, 1e-9)
        pct = 75.0 + (value - q75) / span * 25.0
    else:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= value <= x1:
                frac = (value - x0) / max(x1 - x0, 1e-9)
                pct = y0 + frac * (y1 - y0)
                break
    pct = max(0.0, min(100.0, pct))
    return round(pct if higher_is_better else 100.0 - pct, 1)


@dataclass
class BenchmarkComparison:
    metric: str
    company_value: Optional[float]
    sector_median: Optional[float]
    verdict: str          # "ueber Branchenmedian" | "im Rahmen" | "unter Branchenmedian"
    relative_gap: Optional[float]
    percentile: Optional[float] = None
    quartiles: Optional[tuple[float, float, float]] = None


def _compare(
    metric: str,
    value: Optional[float],
    cell: Optional[dict],
    higher_is_better: bool,
    scale: float = 1.0,
) -> BenchmarkComparison:
    """`scale` converts the published unit into ours (e.g. percent -> decimal)."""
    if cell is None:
        return BenchmarkComparison(metric, value, None, "keine Branchendaten", None)
    median = cell["q50"] * scale
    if value is None or median == 0:
        return BenchmarkComparison(metric, value, median, "nicht vergleichbar", None)

    gap = (value - median) / abs(median)
    if not higher_is_better:
        gap = -gap
    if gap > 0.15:
        verdict = "ueber Branchenmedian"
    elif gap < -0.15:
        verdict = "unter Branchenmedian"
    else:
        verdict = "im Rahmen"

    return BenchmarkComparison(
        metric=metric,
        company_value=value,
        sector_median=median,
        verdict=verdict,
        relative_gap=round(gap, 3),
        percentile=percentile(value / scale, cell, higher_is_better),
        quartiles=(cell["q25"] * scale, cell["q50"] * scale, cell["q75"] * scale),
    )


def compare_all(sector: Sector, ratios) -> list[BenchmarkComparison]:
    """Compare a RatioSet against its sector. Typed loosely to avoid a cycle."""
    revenue = getattr(ratios, "umsatz", None)

    def cell(metric):
        return quartiles(metric, sector, revenue)

    margin_cell = cell("ergebnis_vor_steuern_pct_umsatz")
    if margin_cell:
        # Published figure is pre-tax margin; step it up to an EBIT basis.
        margin_cell = {k: v + EBT_TO_EBIT_ADJUSTMENT * 100 for k, v in margin_cell.items()}

    return [
        _compare("Eigenkapitalquote", ratios.eigenkapitalquote,
                 cell("eigenmittel_pct_bilanzsumme"), True, 0.01),
        _compare("EBIT-Marge", ratios.ebit_marge, margin_cell, True, 0.01),
        _compare("Liquiditaet 2. Grades", ratios.liquiditaet_2_grades,
                 cell("liquiditaet_2_pct"), True, 0.01),
        _compare("Anlagendeckungsgrad II", ratios.anlagendeckungsgrad_ii,
                 cell("langfr_kapital_pct_anlagevermoegen"), True, 0.01),
        _compare("Debitorenlaufzeit", ratios.debitorenlaufzeit_tage,
                 cell("forderungen_ll_pct_umsatz"), False, 3.65),
    ]
