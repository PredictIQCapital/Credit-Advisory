"""The financial-statements grid: one row per statement, one column per year.

WHY
===
A company thinks in "my 2025 accounts, my 2024 accounts", not in document
types. So the portal asks for the financial statements the way lenders list
them (and the way a Steuerberater hands them over): a grid with the balance
sheet, the P&L, the cash flow statement and the DATEV trial balance as rows,
and the fiscal years as columns. The company picks the latest year once; the
next columns follow on their own.

Storage does not change: every cell is an ordinary upload of an existing
document type, tagged with its fiscal year (and, for the annual accounts,
with the part it contains). That keeps the engine, the letters and the
advisor view working exactly as before.

  row           document type                   columns
  bilanz        jahresabschluesse, part bilanz   first two required, then recommended
  guv           jahresabschluesse, part guv      same
  kapitalfluss  kapitalflussrechnung            optional (few SMEs prepare one)
  susa          susa_aktuell / susa_vorjahr     first column required, second
                                                recommended, older not needed

Most German annual accounts arrive as ONE PDF with both balance sheet and P&L.
That file carries part "bilanz_guv" and fills both cells; a company that
uploads it into the balance-sheet row confirms with one click that the P&L is
inside. Uploads from before this grid carry no part and are read the same way.

A cell can also be *explained* instead of filled: "founded 2024, no 2023
accounts". An explained cell no longer counts as missing for the company; the
advisor sees the explanation and decides.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

ANNUAL = "jahresabschluesse"
CASHFLOW = "kapitalflussrechnung"
SUSA_CURRENT = "susa_aktuell"
SUSA_PRIOR = "susa_vorjahr"

PART_BS = "bilanz"
PART_PL = "guv"
PART_BOTH = "bilanz_guv"
PARTS = (PART_BS, PART_PL, PART_BOTH)

MIN_YEARS, MAX_YEARS = 2, 6
DEFAULT_YEARS = 2


@dataclass(frozen=True)
class Row:
    id: str
    title_de: str
    title_en: str
    hint_de: str
    hint_en: str
    doc_type: str               # SUSA_CURRENT stands for both trial-balance types
    required_columns: int       # leading columns that are required
    max_columns: Optional[int]  # columns beyond this are "not needed"


ROWS: tuple[Row, ...] = (
    Row("bilanz", "Bilanz", "Balance sheet",
        "Teil des Jahresabschlusses, als PDF oder Foto.",
        "Part of the annual accounts, as a PDF or photo.",
        ANNUAL, 2, None),
    Row("guv", "Gewinn- und Verlustrechnung", "Profit & loss",
        "Meist im selben PDF wie die Bilanz -- dann genuegt ein Klick.",
        "Usually in the same PDF as the balance sheet -- then one click is enough.",
        ANNUAL, 2, None),
    Row("kapitalfluss", "Kapitalflussrechnung", "Cash flow statement",
        "Nur falls vorhanden -- fuer kleine GmbHs keine Pflicht.",
        "Only if you have one -- not mandatory for small companies.",
        CASHFLOW, 0, None),
    Row("susa", "Summen- und Saldenliste (DATEV)", "Trial balance (DATEV)",
        "CSV-Export aus DATEV -- wird automatisch ausgewertet.",
        "CSV export from DATEV -- read automatically.",
        SUSA_CURRENT, 1, 2),
)
ROWS_BY_ID = {r.id: r for r in ROWS}
ROW_DOC_TYPES = {ANNUAL, CASHFLOW, SUSA_CURRENT, SUSA_PRIOR}

_YEAR_IN_NAME = re.compile(r"(?<!\d)(19[89]\d|20\d\d)(?!\d)")


# ---------------------------------------------------------------- settings


def fiscal_year_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def last_completed_year(today: date, fy_end_month: int) -> int:
    """Label of the latest fiscal year that has ended by `today`."""
    y = today.year
    return y if fiscal_year_end(y, fy_end_month) < today else y - 1


def settings(meta: dict, today: date) -> dict:
    s = dict(meta.get("doc_matrix") or {})
    month = int(s.get("fy_end_month") or 12)
    return {
        "fy_end_month": month,
        "first_year": int(s.get("first_year") or last_completed_year(today, month)),
        "years": max(MIN_YEARS, min(MAX_YEARS, int(s.get("years") or DEFAULT_YEARS))),
    }


def validate_settings(raw: dict, today: date) -> dict:
    out = {}
    if "fy_end_month" in raw:
        m = int(raw["fy_end_month"])
        if not 1 <= m <= 12:
            raise ValueError("Monat des Geschaeftsjahresendes ungueltig")
        out["fy_end_month"] = m
    if "first_year" in raw:
        y = int(raw["first_year"])
        if not 1990 <= y <= today.year:
            raise ValueError("Geschaeftsjahr ungueltig")
        out["first_year"] = y
    if "years" in raw:
        n = int(raw["years"])
        if not MIN_YEARS <= n <= MAX_YEARS:
            raise ValueError(f"Zwischen {MIN_YEARS} und {MAX_YEARS} Jahre")
        out["years"] = n
    return out


# ---------------------------------------------------------------- files


def fiscal_year_of(entry: dict) -> Optional[int]:
    """Fiscal year of an upload: stated, else from the balance date, else the name."""
    meta = entry.get("meta") or {}
    if meta.get("fiscal_year"):
        return int(meta["fiscal_year"])
    if meta.get("period_end"):
        return int(str(meta["period_end"])[:4])
    m = _YEAR_IN_NAME.search(entry.get("filename", ""))
    return int(m.group(1)) if m else None


def part_of(entry: dict) -> str:
    """Which statements an annual-accounts file holds. No tag = the usual combined PDF."""
    part = (entry.get("meta") or {}).get("part")
    return part if part in PARTS else PART_BOTH


def covers(entry: dict, row_id: str) -> bool:
    if row_id == "bilanz":
        return part_of(entry) in (PART_BS, PART_BOTH)
    if row_id == "guv":
        return part_of(entry) in (PART_PL, PART_BOTH)
    return True


def row_files(row: Row, docs: list[dict]) -> list[dict]:
    types = {SUSA_CURRENT, SUSA_PRIOR} if row.doc_type == SUSA_CURRENT else {row.doc_type}
    return [d for d in docs if d["doc_type"] in types and covers(d, row.id)]


def upload_target(row_id: str, year: int, cfg: dict) -> tuple[str, dict]:
    """(document type, metadata) for a file dropped into a grid cell."""
    row = ROWS_BY_ID[row_id]
    meta: dict = {"fiscal_year": year}
    if row.id in ("bilanz", "guv"):
        meta["part"] = row.id
        return ANNUAL, meta
    if row.id == "kapitalfluss":
        return CASHFLOW, meta
    col = cfg["first_year"] - year
    if col < 0 or col >= (row.max_columns or 99):
        raise ValueError("Fuer dieses Jahr wird keine Saldenliste benoetigt")
    meta["period_end"] = fiscal_year_end(year, cfg["fy_end_month"]).isoformat()
    meta["period_months"] = 12
    return (SUSA_CURRENT if col == 0 else SUSA_PRIOR), meta


# ---------------------------------------------------------------- notes


def note_key(row_id: str, year: int) -> str:
    return f"{row_id}:{year}"


def note_doc_type(key: str) -> Optional[str]:
    """Document type a note key belongs to, or None when the key is invalid."""
    head, _, year = key.partition(":")
    if head in ROWS_BY_ID:
        return ROWS_BY_ID[head].doc_type if re.fullmatch(r"(19|20)\d\d", year) else None
    return None if year else head


# ---------------------------------------------------------------- the grid


def build(docs: list[dict], notes: dict, cfg: dict) -> dict:
    """Everything the portal needs to draw the grid, plus per-type completion."""
    years = [cfg["first_year"] - i for i in range(cfg["years"])]
    # Files for years outside the visible columns still show, in extra columns.
    seen = {fiscal_year_of(d) for d in docs if d["doc_type"] in ROW_DOC_TYPES}
    for y in sorted((y for y in seen if y and y not in years), reverse=True):
        if y < years[-1]:
            years.append(y)
    rows = []
    for row in ROWS:
        files = row_files(row, docs)
        cells = []
        for col, y in enumerate(years):
            in_year = [f for f in files if fiscal_year_of(f) == y]
            note = notes.get(note_key(row.id, y), "")
            needed = row.max_columns is None or col < row.max_columns
            required = col < row.required_columns
            if in_year:
                state = "ok"
            elif not needed:
                state = "na"
            elif note:
                state = "explained"
            elif required:
                state = "missing"
            else:
                state = "open"
            cells.append({
                "year": y, "state": state, "required": required, "needed": needed,
                "files": in_year, "note": note,
                # A combined file sitting in the balance-sheet row can be
                # declared to hold the P&L as well.
                "combined_candidate": (row.id == "guv" and not in_year and next(
                    (f["doc_id"] for f in docs if f["doc_type"] == ANNUAL
                     and fiscal_year_of(f) == y and part_of(f) == PART_BS), None)),
            })
        rows.append({"id": row.id, "title_de": row.title_de, "title_en": row.title_en,
                     "hint_de": row.hint_de, "hint_en": row.hint_en,
                     "doc_type": row.doc_type, "cells": cells})
    # Files the grid cannot place: no year, or a year after the latest column
    # (an interim trial balance, say). Listed below the grid, never dropped.
    other = [d for d in docs if d["doc_type"] in ROW_DOC_TYPES
             and (fiscal_year_of(d) is None or fiscal_year_of(d) > years[0])]
    return {**cfg, "columns": years, "rows": rows, "other": other}


def completion(grid: dict) -> dict[str, dict]:
    """Per document type: (satisfied, count) as the grid sees it.

    Overrides the plain file count for the annual accounts, where two files
    for one year (balance sheet + P&L) must not pass for two years.
    """
    by_id = {r["id"]: r for r in grid["rows"]}
    done = lambda c: c["state"] in ("ok", "explained")  # noqa: E731
    annual_years = [
        (b, g) for b, g in zip(by_id["bilanz"]["cells"], by_id["guv"]["cells"])
    ]
    annual_ok = sum(1 for b, g in annual_years if done(b) and done(g))
    required_annual = [(b, g) for b, g in annual_years if b["required"]]
    susa = by_id["susa"]["cells"]
    return {
        ANNUAL: {"count": annual_ok,
                 "satisfied": all(done(b) and done(g) for b, g in required_annual)},
        SUSA_CURRENT: {"satisfied": bool(susa) and done(susa[0])},
        SUSA_PRIOR: {"satisfied": len(susa) > 1 and done(susa[1])},
    }
