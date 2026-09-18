"""DATEV Summen- und Saldenliste (SuSa) intake.

DATEV is the near-universal German SME accounting standard, so parsing its
export is the highest-leverage intake path: it covers most clients and avoids
generic PDF extraction entirely.

CALIBRATION WARNING
===================
The account-range mapping below follows the SKR04 standard chart of accounts as
commonly published. It has NOT yet been validated against a real DATEV export
from a real Steuerberater, and DATEV exports vary by:

  * chart of accounts (SKR03 vs SKR04 -- the ranges differ substantially),
  * individual Steuerberater customisations to the account plan,
  * export column layout and locale (decimal comma, thousands dot),
  * whether balances arrive as debit/credit columns or one signed column.

Validate against three real client exports before any production use, and treat
`UNMAPPED_THRESHOLD` breaches as a hard stop rather than a warning: silently
dropping 15% of the balance sheet produces a confident, wrong diagnostic, which
is the worst possible failure mode for this business.

SKR03 support is deliberately unimplemented rather than guessed at -- see
`parse_datev_susa(kontenrahmen=...)`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from ..models import BalanceSheet, IncomeStatement

UNMAPPED_THRESHOLD = 0.05  # >5% of total volume unmapped -> raise


class DatevMappingError(RuntimeError):
    """Raised when too much of the trial balance could not be mapped."""


@dataclass(frozen=True)
class AccountRange:
    low: int
    high: int
    target: str          # attribute name on BalanceSheet or IncomeStatement
    statement: str       # "balance" | "income"
    sign: int = 1        # multiply the DATEV balance by this


# SKR04 ranges. Edit here, not in the parser.
SKR04_MAP: tuple[AccountRange, ...] = (
    # --- Aktiva ---
    AccountRange(100, 199, "immaterielle_vermoegensgegenstaende", "balance"),
    AccountRange(200, 699, "sachanlagen", "balance"),
    AccountRange(700, 999, "finanzanlagen", "balance"),
    AccountRange(1000, 1199, "vorraete", "balance"),
    AccountRange(1200, 1299, "forderungen_ll", "balance"),
    AccountRange(1300, 1499, "sonstige_vermoegensgegenstaende", "balance"),
    AccountRange(1500, 1599, "wertpapiere", "balance"),
    AccountRange(1600, 1899, "liquide_mittel", "balance"),
    AccountRange(1900, 1949, "aktive_rap", "balance"),
    # --- Passiva (credit balances arrive negative in a signed export) ---
    AccountRange(2000, 2099, "gezeichnetes_kapital", "balance", sign=-1),
    AccountRange(2100, 2199, "kapitalruecklage", "balance", sign=-1),
    AccountRange(2200, 2299, "gewinnruecklagen", "balance", sign=-1),
    AccountRange(2300, 2399, "gewinnvortrag", "balance", sign=-1),
    AccountRange(3000, 3099, "rueckstellungen", "balance", sign=-1),
    AccountRange(3100, 3149, "pensionsrueckstellungen", "balance", sign=-1),
    AccountRange(3150, 3199, "verb_kreditinstitute_kurz", "balance", sign=-1),
    AccountRange(3200, 3249, "verb_kreditinstitute_lang", "balance", sign=-1),
    AccountRange(3300, 3399, "verb_ll", "balance", sign=-1),
    AccountRange(3400, 3499, "sonstige_verbindlichkeiten_kurz", "balance", sign=-1),
    AccountRange(3500, 3599, "sonstige_verbindlichkeiten_lang", "balance", sign=-1),
    AccountRange(3600, 3699, "gesellschafterdarlehen", "balance", sign=-1),
    AccountRange(3900, 3949, "passive_rap", "balance", sign=-1),
    # --- GuV ---
    AccountRange(4000, 4499, "umsatzerloese", "income", sign=-1),
    AccountRange(4500, 4699, "bestandsveraenderungen", "income", sign=-1),
    AccountRange(4700, 4999, "sonstige_betriebliche_ertraege", "income", sign=-1),
    AccountRange(5000, 5999, "materialaufwand", "income"),
    AccountRange(6000, 6199, "personalaufwand", "income"),
    AccountRange(6200, 6299, "abschreibungen", "income"),
    AccountRange(6300, 6999, "sonstige_betriebliche_aufwendungen", "income"),
    AccountRange(7000, 7099, "zinsertraege", "income", sign=-1),
    AccountRange(7100, 7299, "zinsaufwand", "income"),
    AccountRange(7600, 7699, "steuern", "income"),
)


def _parse_german_number(raw: str) -> float:
    """Parse '1.234.567,89' and '-1234.56' alike."""
    s = (raw or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return 0.0
    neg = s.startswith("-") or (s.endswith("-") and not s.startswith("-"))
    s = s.strip("-")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        value = float(s)
    except ValueError:
        return 0.0
    return -value if neg else value


def _find_column(header: list[str], candidates: Iterable[str]) -> Optional[int]:
    lowered = [h.strip().lower() for h in header]
    for cand in candidates:
        for i, h in enumerate(lowered):
            if cand in h:
                return i
    return None


def parse_datev_susa(
    path: str | Path,
    period_end: date,
    period_months: int = 12,
    kontenrahmen: str = "SKR04",
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> tuple[BalanceSheet, IncomeStatement, dict[str, float]]:
    """Parse a DATEV SuSa CSV into (BalanceSheet, IncomeStatement, diagnostics).

    Returns a diagnostics dict carrying `mapped_volume`, `unmapped_volume` and
    `unmapped_share` so the caller can see exactly how much of the trial balance
    the mapping understood.

    Raises DatevMappingError when the unmapped share exceeds UNMAPPED_THRESHOLD.
    """
    if kontenrahmen.upper() != "SKR04":
        raise DatevMappingError(
            f"Kontenrahmen {kontenrahmen} nicht implementiert. Nur SKR04 wird "
            "unterstuetzt; SKR03 verwendet abweichende Kontenbereiche und muss "
            "gegen echte Exporte kalibriert werden, bevor es geraten wird."
        )

    rows = list(csv.reader(Path(path).read_text(encoding=encoding).splitlines(), delimiter=delimiter))
    if not rows:
        raise DatevMappingError("Leere Datei")

    header = rows[0]
    konto_idx = _find_column(header, ("konto", "account"))
    saldo_idx = _find_column(header, ("saldo", "balance", "betrag", "amount"))
    if konto_idx is None or saldo_idx is None:
        raise DatevMappingError(
            f"Spalten 'Konto' und 'Saldo' nicht gefunden. Kopfzeile: {header}"
        )

    balance = BalanceSheet(period_end=period_end)
    income = IncomeStatement(period_end=period_end, period_months=period_months)

    mapped_volume = 0.0
    unmapped_volume = 0.0
    unmapped_accounts: list[str] = []

    for row in rows[1:]:
        if len(row) <= max(konto_idx, saldo_idx):
            continue
        konto_raw = row[konto_idx].strip()
        if not konto_raw or not konto_raw.lstrip("-").isdigit():
            continue
        konto = int(konto_raw)
        saldo = _parse_german_number(row[saldo_idx])
        if saldo == 0.0:
            continue

        target_range = next(
            (r for r in SKR04_MAP if r.low <= konto <= r.high), None
        )
        if target_range is None:
            unmapped_volume += abs(saldo)
            unmapped_accounts.append(konto_raw)
            continue

        obj = balance if target_range.statement == "balance" else income
        current = getattr(obj, target_range.target)
        setattr(obj, target_range.target, current + saldo * target_range.sign)
        mapped_volume += abs(saldo)

    # A SuSa carries no "Jahresueberschuss" account -- the result lives in the
    # GuV accounts we just summed. Carry it into equity, or the balance sheet
    # will not balance and every equity ratio will be understated by the year's
    # profit. This is the correct accounting treatment, not a fudge.
    balance.jahresueberschuss = income.jahresueberschuss

    total = mapped_volume + unmapped_volume
    share = (unmapped_volume / total) if total else 0.0

    diagnostics = {
        "mapped_volume": round(mapped_volume, 2),
        "unmapped_volume": round(unmapped_volume, 2),
        "unmapped_share": round(share, 4),
        "unmapped_account_count": float(len(unmapped_accounts)),
    }

    if share > UNMAPPED_THRESHOLD:
        raise DatevMappingError(
            f"{share*100:.1f}% des Volumens konnten nicht zugeordnet werden "
            f"(Schwelle {UNMAPPED_THRESHOLD*100:.0f}%). Nicht zugeordnete Konten: "
            f"{sorted(set(unmapped_accounts))[:20]}. Kontenrahmen pruefen, bevor "
            "das Ergebnis verwendet wird."
        )

    return balance, income, diagnostics
