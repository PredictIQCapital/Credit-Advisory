"""Extract BACH peer quartiles: for the report, and to cross-check the Bundesbank import.

Source
------
BACH (Bank for the Accounts of Companies Harmonized), ECCBSO, hosted by the
Banque de France: https://www.bach.banque-france.fr. The full download is one
semicolon-separated CSV of ~700 MB covering twelve countries; the German rows
come from the Deutsche Bundesbank, i.e. from the same firm-level accounts as
the Jahresabschlussstatistik the scorecard is calibrated on.

What it is for
--------------
1. Peer context in the report (peers.py): the client's own country, WZ
   division, size class and the year of the accounts it uploaded.
2. An independent read of the Bundesbank numbers. Those reach us through a PDF
   parser (import_bundesbank_ratios.py); BACH arrives as a table.
   tests/test_bach_crosscheck.py compares the two, so a parser that files a
   page under the wrong sector fails a test instead of moving the score. That
   is how ADR-006 was found.

It is *not* a calibration source. BACH has no second-degree liquidity, no
fixed-asset coverage and no Bundesbank-definition return on assets, and its
smallest size class (< 10M EUR) mixes micro firms into our 2-10M segment.

Licence
-------
The BACH terms of use prohibit redistributing the data, even free of charge,
and require the citation in CITATION below. The extract therefore goes to
data/reference/bach/, which is git-ignored; without it the report leaves the
peer section out and the cross-check test skips. Clear the terms with the
ECCBSO (1356-bach-ut@banque-france.fr) before shipping it to production.

Usage
-----
    python scripts/import_bach.py <path-to-bach.csv>              # Germany
    python scripts/import_bach.py <path-to-bach.csv> DE,AT,FR     # several
    python scripts/import_bach.py <path-to-bach.csv> all          # every country

Writes data/reference/bach/bach.json. Re-running is idempotent. Name the CSV
after its download date (YYYYMMDD.csv, as BACH delivers it): that date decides
which years are still provisional.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "reference" / "bach" / "bach.json"

CITATION = (
    "BACH database: ECCBSO, Oesterreichische Nationalbank, National Bank of Belgium, "
    "Czech National Bank (in cooperation with the Czech Statistical Office), Deutsche "
    "Bundesbank, Danmarks Nationalbank, Banco de España, Banque de France, Centrale dei "
    "Bilanci - Cerved srl / Banca d'Itália, Statec Luxembourg, National Bank of Poland "
    "(calculations of National Bank of Poland on the basis of the data from the "
    "Statistics Poland), Banco de Portugal, National Bank of Slovakia (calculations "
    "based on data from the Ministry of Finance)"
)

#: BACH item -> what it is (userguide 2024). Balance-sheet items in % of total
#: assets, ratios in % of net turnover. Only what peers.py and the cross-check
#: use: our definitions match these, which is why r52 (receivables / turnover)
#: is kept rather than r55 (days, 360-day year, net of advances).
MEASURES = {
    "E": "Eigenkapital in % der Bilanzsumme",
    "A2": "Vorraete in % der Bilanzsumme",
    "r52": "Forderungen LuL in % des Umsatzes",
    "r33": "EBITDA in % des Umsatzes",
    "r35": "EBIT in % des Umsatzes",
    "r36": "EBT in % des Umsatzes",
}

#: BACH size code -> our key. 1a (< 10M) has no Bundesbank twin: the
#: Bundesbank splits it at 2M. 1 (all SMEs) is left out: 1a/1b are finer.
SIZES = {"0": "insgesamt", "1a": "unter_10m", "1b": "10_bis_50m", "2": "ab_50m"}

#: Only the variable sample: every firm reporting that year. The sliding
#: samples (1, -1) hold firms present in two consecutive years and are meant
#: for growth rates, not for levels.
SAMPLE = "0"


def _num(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _edition(path: Path) -> str:
    """The download date, from a YYYYMMDD file name, else the file's mtime."""
    stem = path.stem
    if len(stem) == 8 and stem.isdigit():
        return f"{stem[:4]}-{stem[4:6]}-{stem[6:]}"
    return date.fromtimestamp(path.stat().st_mtime).isoformat()


def extract(path: Path, countries: set[str] | None = None) -> dict:
    """{country: {year: {sector: {size: {measure: quartiles}}}}}.

    `countries` None means all of them.
    """
    cells: dict[str, dict] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        first = fh.readline()
        if not first.startswith("nb_lignes"):     # the file opens with a row count
            fh.seek(0)
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            if countries is not None and row["country"] not in countries:
                continue
            if row["sample"] != SAMPLE or row["size"] not in SIZES:
                continue
            cell = {}
            for m in MEASURES:
                q = [_num(row.get(f"{m}_q{i}")) for i in (1, 2, 3)]
                if None not in q:
                    n = _num(row.get(f"{m}_nbq"))
                    cell[m] = {"q25": q[0], "q50": q[1], "q75": q[2], "n": int(n or 0)}
            if cell:
                (cells.setdefault(row["country"], {}).setdefault(row["year"], {})
                 .setdefault(row["sector"], {}))[SIZES[row["size"]]] = cell
    return {
        "source": "BACH (ECCBSO), variable sample, firm-level quartiles",
        "citation": CITATION,
        "file": path.name,
        "edition": _edition(path),
        "measures": MEASURES,
        "countries": {c: sorted(years) for c, years in sorted(cells.items())},
        "cells": cells,
    }


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 1
    wanted = argv[2] if len(argv) == 3 else "DE"
    countries = None if wanted.lower() == "all" else {c.strip().upper() for c in wanted.split(",")}
    data = extract(Path(argv[1]), countries)
    if not data["cells"]:
        print("no matching rows -- is this the BACH CSV, and are the country codes right?")
        return 1
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    spans = ", ".join(f"{c} {y[0]}-{y[-1]}" for c, y in data["countries"].items())
    print(f"BACH -> {OUT_FILE.relative_to(ROOT)} (Stand {data['edition']}: {spans})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
