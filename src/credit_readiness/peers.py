"""Peer comparison from BACH: same country, same WZ division, same size, same year.

Context for the report, never an input to the score. The scorecard stays on
the Bundesbank curves (ADR-002, ADR-005); this module answers the question a
client actually asks -- "how did firms like mine do in the year of my
accounts?" -- with the finest cell BACH publishes.

DATA
====
BACH (Bank for the Accounts of Companies Harmonized), ECCBSO / Banque de
France: firm-level quartiles by country, NACE division, turnover class and
year, built by the national central banks from company accounts. The extract
is built by `scripts/import_bach.py` into data/reference/bach/bach.json, or
wherever BACH_DATA_FILE points.

The BACH terms prohibit redistributing the data, so the extract is not in
version control. Without it `compare()` returns None and the report leaves the
section out. Whether printing quartiles in a client report counts as
redistribution is to be cleared with the ECCBSO before this runs in
production (ADR-006).

MATCHING
========
Each step falls back when a cell is empty -- BACH blanks a cell with too few
firms (Germany: under 12):

  * sector   WZ division (C28) -> section (C) -> all sectors (Zc). Without a
             WZ code, the division behind our sector bucket, then Zc.
  * size     turnover < 10M, 10-50M or >= 50M -> all sizes. The small class
             includes micro firms; the Bundesbank's 2-10M class does not.
  * year     the year of the uploaded accounts; if BACH has not published it
             yet, the newest year it has. The newest year is usually
             provisional (see FINAL_RELEASE).
  * country  the client's own, or no comparison. Another country's firms are
             not "firms like mine".

Only the quartiles are used. BACH's weighted mean is dominated by the largest
firms in a cell -- it describes the market leader, not a Mittelstaendler.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from . import benchmarks, nace
from .models import ClientCase, Sector

_DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "bach" / "bach.json"


def _data_file() -> Path:
    return Path(os.environ.get("BACH_DATA_FILE") or _DEFAULT_FILE)


@lru_cache(maxsize=1)
def _dataset() -> Optional[dict]:
    path = _data_file()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def available() -> bool:
    return _dataset() is not None


#: (label, BACH measure, RatioSet attribute, published unit -> ours, higher is better)
#: Each pair has the same definition on both sides: balance-sheet equity (not
#: the scorecard's economic equity), and receivables over turnover times 365,
#: which is exactly how ratios.py computes Debitorenlaufzeit.
METRICS = (
    ("Eigenkapitalquote (bilanziell)", "E", "eigenkapitalquote_bilanziell", 0.01, True),
    ("EBITDA-Marge", "r33", "ebitda_marge", 0.01, True),
    ("EBIT-Marge", "r35", "ebit_marge", 0.01, True),
    ("Umsatzrendite vor Steuern", "r36", "umsatzrendite_vor_steuern", 0.01, True),
    ("Debitorenlaufzeit", "r52", "debitorenlaufzeit_tage", 3.65, False),
)

#: When each country publishes its final figures for reporting year n, as
#: (years after n, month) -- BACH userguide 2024, release calendar. A year
#: whose final release falls after the extract's download date is provisional.
FINAL_RELEASE = {
    "AT": (2, 7), "BE": (2, 3), "DE": (2, 11), "ES": (2, 6), "FR": (2, 12),
    "HR": (1, 7), "HU": (2, 4), "IT": (2, 3), "LU": (2, 12), "PL": (1, 12),
    "PT": (1, 11), "SK": (1, 10),
}

COUNTRY_NAMES = {
    "AT": "Oesterreich", "BE": "Belgien", "DE": "Deutschland", "ES": "Spanien",
    "FR": "Frankreich", "HR": "Kroatien", "HU": "Ungarn", "IT": "Italien",
    "LU": "Luxemburg", "PL": "Polen", "PT": "Portugal", "SK": "Slowakei",
}

SIZE_LABELS = {
    "unter_10m": "Umsatz unter 10 Mio. EUR",
    "10_bis_50m": "Umsatz 10-50 Mio. EUR",
    "ab_50m": "Umsatz ab 50 Mio. EUR",
    "insgesamt": "alle Groessenklassen",
}

#: Our sector buckets -> the BACH cell closest to them, used only when the
#: client gave no WZ code. None: no single BACH cell covers the bucket.
_SECTOR_CODES = {
    Sector.MANUFACTURING: "C",
    Sector.CONSTRUCTION: "F",
    Sector.WHOLESALE: "G46",
    Sector.RETAIL: "G47",
    Sector.TRANSPORT: "H",
    Sector.HOSPITALITY: "I",
    Sector.IT_SERVICES: "J",
    Sector.PROFESSIONAL_SERVICES: "Mc",
    Sector.HEALTHCARE: "Q86",
    Sector.OTHER_SERVICES: None,
    Sector.OTHER: None,
}

ALL_SECTORS = "Zc"


def sector_codes(nace_code: Optional[str], sector: Optional[Sector]) -> list[str]:
    """BACH sector codes to try, finest first, always ending at all sectors."""
    codes: list[str] = []
    parsed = nace.parse(nace_code)
    if parsed:
        if parsed.division == 70:
            # BACH splits division 70 into head offices (70.1, published only
            # without size detail) and management consultancy (70.2).
            group = parsed.code.split(".")[1][:1] if "." in parsed.code else ""
            codes.append({"1": "M701", "2": "M702"}.get(group, "M70"))
        codes.append(f"{parsed.section}{parsed.division:02d}")
        # Section M is published by size only without head offices ("Mc").
        codes.append("Mc" if parsed.section == "M" else parsed.section)
    elif sector is not None and _SECTOR_CODES.get(sector):
        codes.append(_SECTOR_CODES[sector])
    codes.append(ALL_SECTORS)
    return list(dict.fromkeys(codes))


def size_key(revenue: Optional[float]) -> Optional[str]:
    if not revenue or revenue <= 0:
        return None
    if revenue < 10_000_000:
        return "unter_10m"
    if revenue < 50_000_000:
        return "10_bis_50m"
    return "ab_50m"


def is_provisional(country: str, year: int, edition: date) -> bool:
    rule = FINAL_RELEASE.get(country)
    if rule is None:
        return False
    years_after, month = rule
    # Released "in" that month: until the month is over, treat it as pending.
    return (edition.year, edition.month) <= (year + years_after, month)


def statement_year(case: ClientCase) -> Optional[int]:
    """Reporting year of the uploaded accounts: the year the period ends in."""
    for period_end in (case.income_statement.period_end, case.balance_sheet.period_end):
        if period_end:
            return period_end.year
    return None


@dataclass
class PeerMetric:
    label: str
    company_value: Optional[float]      # our unit (decimal, or days)
    quartiles: tuple[float, float, float]   # our unit
    firms: int
    percentile: Optional[float]
    higher_is_better: bool
    basis: str                          # the cell this row came from


@dataclass
class PeerComparison:
    country: str
    requested_year: Optional[int]
    year: int
    provisional: bool
    metrics: list[PeerMetric] = field(default_factory=list)
    citation: str = ""

    @property
    def year_note(self) -> str:
        parts = []
        if self.requested_year and self.requested_year != self.year:
            parts.append(f"Fuer {self.requested_year} liegen noch keine BACH-Daten vor; "
                         f"verglichen wird mit {self.year}, dem neuesten verfuegbaren Jahr.")
        if self.provisional:
            parts.append(f"Die Werte fuer {self.year} sind vorlaeufig.")
        return " ".join(parts)

    @property
    def common_basis(self) -> Optional[str]:
        """The basis when every row shares it, so the report prints it once."""
        bases = {m.basis for m in self.metrics}
        return bases.pop() if len(bases) == 1 else None


def _pick_year(years: list[str], wanted: Optional[int]) -> Optional[int]:
    if not years:
        return None
    ints = sorted(int(y) for y in years)
    if wanted is None or wanted > ints[-1]:
        return ints[-1]
    if wanted < ints[0]:
        return ints[0]
    # Years are contiguous in BACH; a gap would fall back to the one before.
    return max(y for y in ints if y <= wanted)


def _basis(country: str, code: str, size: str, year: int) -> str:
    label = "alle Branchen" if code == ALL_SECTORS else f"WZ {code}"
    return f"{COUNTRY_NAMES.get(country, country)}, {label}, {SIZE_LABELS[size]}, {year}"


def compare(case: ClientCase, ratios) -> Optional[PeerComparison]:
    """Peer quartiles for the case, or None without data for its country.

    `ratios` is a RatioSet, typed loosely to avoid an import cycle.
    """
    data = _dataset()
    if data is None:
        return None
    country = (case.profile.country or "DE").upper()
    by_year = data["cells"].get(country)
    if not by_year:
        return None

    wanted = statement_year(case)
    year = _pick_year(list(by_year), wanted)
    cells = by_year[str(year)]
    codes = sector_codes(case.profile.nace_code, case.profile.sector)
    size = size_key(getattr(ratios, "umsatz", None))
    sizes = [size, "insgesamt"] if size else ["insgesamt"]

    metrics = []
    for label, measure, attr, scale, higher in METRICS:
        hit = next(((code, s, cells[code][s][measure])
                    for code in codes for s in sizes
                    if measure in cells.get(code, {}).get(s, {})), None)
        if hit is None:
            continue
        code, s, cell = hit
        value = getattr(ratios, attr, None)
        metrics.append(PeerMetric(
            label=label,
            company_value=value,
            quartiles=tuple(cell[k] * scale for k in ("q25", "q50", "q75")),
            firms=cell.get("n", 0),
            percentile=(benchmarks.percentile(value / scale, cell, higher)
                        if value is not None else None),
            higher_is_better=higher,
            basis=_basis(country, code, s, year),
        ))
    if not metrics:
        return None

    edition = date.fromisoformat(data["edition"]) if data.get("edition") else date.today()
    return PeerComparison(
        country=country,
        requested_year=wanted,
        year=year,
        provisional=is_provisional(country, year, edition),
        metrics=metrics,
        citation=data.get("citation", ""),
    )
