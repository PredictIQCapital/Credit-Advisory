"""Sector benchmarks.

Purpose: distinguish "this company is weak" from "this company is normal for a
genuinely difficult sector". That distinction changes the advice completely --
a 6% equity ratio in Gastgewerbe is a different conversation from a 6% equity
ratio in IT services.

DATA STATUS -- IMPORTANT
========================
The figures below are PLACEHOLDER order-of-magnitude values, entered to make the
comparison logic testable. They are NOT the Bundesbank series and must not be
quoted to a client in this state.

Before first client use, replace with the real dataset:
    Deutsche Bundesbank, "Verhaeltniszahlen aus Jahresabschluessen deutscher
    Unternehmen" (published annually, free, broken down by Wirtschaftszweig and
    size class).

Replacement is a data task, not a code task: keep the shape, swap the numbers,
and record the vintage in `VINTAGE` so every report can state which year's
benchmark it compared against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Sector

VINTAGE = "PLACEHOLDER - nicht fuer Kundenberichte verwenden"


@dataclass(frozen=True)
class SectorBenchmark:
    sector: Sector
    eigenkapitalquote_median: float
    ebit_marge_median: float
    dynamischer_verschuldungsgrad_median: float
    debitorenlaufzeit_median: float


_BENCHMARKS: dict[Sector, SectorBenchmark] = {
    Sector.MANUFACTURING: SectorBenchmark(Sector.MANUFACTURING, 0.32, 0.055, 2.6, 45),
    Sector.CONSTRUCTION: SectorBenchmark(Sector.CONSTRUCTION, 0.22, 0.045, 2.3, 55),
    Sector.WHOLESALE: SectorBenchmark(Sector.WHOLESALE, 0.26, 0.030, 2.8, 42),
    Sector.RETAIL: SectorBenchmark(Sector.RETAIL, 0.20, 0.025, 3.0, 12),
    Sector.TRANSPORT: SectorBenchmark(Sector.TRANSPORT, 0.21, 0.040, 3.4, 40),
    Sector.HOSPITALITY: SectorBenchmark(Sector.HOSPITALITY, 0.12, 0.035, 4.2, 6),
    Sector.IT_SERVICES: SectorBenchmark(Sector.IT_SERVICES, 0.38, 0.080, 1.8, 48),
    Sector.PROFESSIONAL_SERVICES: SectorBenchmark(
        Sector.PROFESSIONAL_SERVICES, 0.35, 0.070, 1.9, 50
    ),
    Sector.HEALTHCARE: SectorBenchmark(Sector.HEALTHCARE, 0.28, 0.060, 2.5, 30),
    Sector.OTHER_SERVICES: SectorBenchmark(Sector.OTHER_SERVICES, 0.25, 0.045, 2.7, 38),
}


def get(sector: Sector) -> SectorBenchmark:
    return _BENCHMARKS[sector]


@dataclass
class BenchmarkComparison:
    metric: str
    company_value: Optional[float]
    sector_median: float
    verdict: str          # "ueber Branchenmedian" | "im Rahmen" | "unter Branchenmedian"
    relative_gap: Optional[float]


def _compare(
    metric: str, value: Optional[float], median: float, higher_is_better: bool
) -> BenchmarkComparison:
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
    return BenchmarkComparison(metric, value, median, verdict, round(gap, 3))


def compare_all(sector: Sector, ratios) -> list[BenchmarkComparison]:
    """Compare a RatioSet against its sector. Typed loosely to avoid a cycle."""
    b = get(sector)
    return [
        _compare("Eigenkapitalquote", ratios.eigenkapitalquote, b.eigenkapitalquote_median, True),
        _compare("EBIT-Marge", ratios.ebit_marge, b.ebit_marge_median, True),
        _compare(
            "Dynamischer Verschuldungsgrad",
            ratios.dynamischer_verschuldungsgrad,
            b.dynamischer_verschuldungsgrad_median,
            False,
        ),
        _compare(
            "Debitorenlaufzeit",
            ratios.debitorenlaufzeit_tage,
            b.debitorenlaufzeit_median,
            False,
        ),
    ]
