"""NACE Rev. 2 / WZ 2008 codes -> the sector buckets the benchmarks use.

WHY
===
Clients rarely know which of our ten sector labels they belong to, but every
German company has a WZ 2008 code (the national version of NACE Rev. 2): it is
on the Gewerbeanmeldung, in the Handelsregister data and on every Creditreform
report. Lenders classify by it. Taking the code and deriving the sector makes
the sector a fact rather than a self-assessment -- and the sector now moves the
score (ADR-005), so it has to be a fact.

MAPPING
=======
Follows the section numbering of the Bundesbank Jahresabschlussstatistik, which
is itself built on WZ 2008 (see scripts/import_bundesbank_ratios.py):

  C 10-33            Verarbeitendes Gewerbe
  F 41-43            Baugewerbe
  G 46               Grosshandel
  G 47               Einzelhandel
  H 49-53            Verkehr und Lagerei
  I 55-56            Gastgewerbe
  J 58-63            Information und Kommunikation
  M 69-75, N 77-82   Freiberufliche und technische Dienstleistungen
                     (the Bundesbank's "Unternehmensdienstleistungen" covers both)
  Q 86               Gesundheitswesen
  P 85, Q 87-88,
  R 90-93, S 94-96   Sonstige Dienstleistungen

Everything else -- agriculture, mining, energy, water, motor-vehicle trade (45,
which the Bundesbank publishes only inside "Handel" as a whole), finance, real
estate, public administration -- has no sector cell of its own and maps to
Sector.OTHER, which the scorecard scores on the generic curves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .models import Sector

_RANGES: tuple[tuple[int, int, Sector], ...] = (
    (10, 33, Sector.MANUFACTURING),
    (41, 43, Sector.CONSTRUCTION),
    (46, 46, Sector.WHOLESALE),
    (47, 47, Sector.RETAIL),
    (49, 53, Sector.TRANSPORT),
    (55, 56, Sector.HOSPITALITY),
    (58, 63, Sector.IT_SERVICES),
    (69, 75, Sector.PROFESSIONAL_SERVICES),
    (77, 82, Sector.PROFESSIONAL_SERVICES),
    (85, 85, Sector.OTHER_SERVICES),
    (86, 86, Sector.HEALTHCARE),
    (87, 88, Sector.OTHER_SERVICES),
    (90, 96, Sector.OTHER_SERVICES),
)

#: NACE section letter for each division range (for display and validation).
_SECTIONS: tuple[tuple[int, int, str], ...] = (
    (1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"),
    (41, 43, "F"), (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"),
    (64, 66, "K"), (68, 68, "L"), (69, 75, "M"), (77, 82, "N"), (84, 84, "O"),
    (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"), (94, 96, "S"), (97, 98, "T"),
    (99, 99, "U"),
)

# "C25.62", "25.62", "25.6", "25", "C 25.62.0", "2562"
_PATTERN = re.compile(
    r"^\s*([A-Ua-u])?\s*(\d{2})(?:\.(\d{1,2})(?:\.(\d))?|(\d{2}))?\s*$"
)


@dataclass(frozen=True)
class NaceCode:
    section: str          # "C"
    division: int         # 25
    code: str             # normalised, e.g. "C25.62"
    sector: Sector


def section_of(division: int) -> Optional[str]:
    return next((s for lo, hi, s in _SECTIONS if lo <= division <= hi), None)


def sector_for_division(division: int) -> Sector:
    return next((s for lo, hi, s in _RANGES if lo <= division <= hi), Sector.OTHER)


def parse(code: Optional[str]) -> Optional[NaceCode]:
    """Parse a WZ 2008 / NACE Rev. 2 code; None when it is not one.

    Accepts the usual spellings. A leading section letter, when given, must
    match the division -- "F25" is a typo, not a code.
    """
    if not code:
        return None
    m = _PATTERN.match(str(code))
    if not m:
        return None
    letter, div_s, rest, sub, compact = m.groups()
    rest = rest or compact
    division = int(div_s)
    section = section_of(division)
    if section is None:
        return None
    if letter and letter.upper() != section:
        return None
    normalised = f"{section}{division:02d}"
    if rest:
        normalised += f".{rest}"
        if sub:
            normalised += f".{sub}"
    return NaceCode(section, division, normalised, sector_for_division(division))


def sector_for(code: Optional[str]) -> Optional[Sector]:
    """The benchmark sector for a code, or None when the code is invalid."""
    parsed = parse(code)
    return parsed.sector if parsed else None
