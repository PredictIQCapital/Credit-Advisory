"""Bank statement CSV analysis (Kontoumsaetze).

The blueprint calls 6-12 months of bank transactions "the single highest-value
input, because it is live and cannot be dressed up the way annual statements
sometimes are". Until an open-banking aggregator (finAPI, Tink) is contracted,
the practical route is the CSV export every German online-banking portal offers.

What we extract, and why only this
==================================
Two behavioural signals a bank underwriter reads straight off the account:

  * days at (or near) the overdraft limit  -> behavior.overdraft_days_at_limit_12m
  * returned direct debits                 -> behavior.returned_direct_debits_12m

Both replace the client's self-reported estimate when a statement is supplied:
observed beats remembered.

Format tolerance
================
There is no single German bank CSV format. The parser therefore:
  * skips preamble lines until it finds a header with a date and an amount column,
  * sniffs the delimiter (; , or tab),
  * accepts one signed amount column or separate Soll/Haben columns,
  * accepts DD.MM.YYYY, DD.MM.YY and ISO dates, German or English number format,
  * handles newest-first and oldest-first exports.

The day-at-limit count needs a running balance ("Saldo" column). Without one it
is reported as unavailable rather than reconstructed from a guessed opening
balance.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from .datev import _parse_german_number
from ..formatting import de

DATE_HEADERS = ("buchungstag", "buchungsdatum", "datum", "booking date", "date", "valuta")
AMOUNT_HEADERS = ("betrag", "umsatz", "amount")
DEBIT_HEADERS = ("soll", "debit", "belastung")
CREDIT_HEADERS = ("haben", "credit", "gutschrift")
BALANCE_HEADERS = ("saldo", "kontostand", "balance")
TEXT_HEADERS = ("verwendungszweck", "buchungstext", "beschreibung", "text", "purpose")

# A direct debit on the client's account that bounced is reversed as a CREDIT
# (money comes back). A bounced collection from the client's own customer is a
# DEBIT and says nothing bad about the client, so only credits are counted.
RETURN_KEYWORDS = (
    "ruecklastschrift", "rucklastschrift", "rueckbelastung", "ruckbelastung",
    "lastschriftrueckgabe", "rueckgabe lastschrift", "retoure lastschrift",
    "lastschrift retoure", "return debit", "rls ",
)

MIN_DAYS_FOR_ANNUALISATION = 60


class BankCsvError(ValueError):
    pass


@dataclass
class BankTransaction:
    booking_date: date
    amount: float
    balance: Optional[float]
    text: str = ""


@dataclass
class BankAnalysis:
    account_label: str
    first_date: date
    last_date: date
    transaction_count: int
    inflows: float
    outflows: float
    has_balances: bool
    min_balance: Optional[float] = None
    avg_balance: Optional[float] = None
    end_balance: Optional[float] = None
    returned_direct_debits: int = 0
    days_at_limit: Optional[int] = None
    kontokorrent_limit: Optional[float] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def days_covered(self) -> int:
        return (self.last_date - self.first_date).days + 1

    def _annualise(self, count: float) -> int:
        return min(365, round(count * 365.0 / self.days_covered)) if self.days_covered else 0

    @property
    def returned_direct_debits_12m(self) -> int:
        return self._annualise(self.returned_direct_debits)

    @property
    def days_at_limit_12m(self) -> Optional[int]:
        if self.days_at_limit is None:
            return None
        return self._annualise(self.days_at_limit)

    def as_dict(self) -> dict:
        return {
            "account_label": self.account_label,
            "first_date": self.first_date.isoformat(),
            "last_date": self.last_date.isoformat(),
            "days_covered": self.days_covered,
            "transaction_count": self.transaction_count,
            "inflows": round(self.inflows, 2),
            "outflows": round(self.outflows, 2),
            "has_balances": self.has_balances,
            "min_balance": self.min_balance,
            "avg_balance": None if self.avg_balance is None else round(self.avg_balance, 2),
            "end_balance": self.end_balance,
            "returned_direct_debits": self.returned_direct_debits,
            "returned_direct_debits_12m": self.returned_direct_debits_12m,
            "days_at_limit": self.days_at_limit,
            "days_at_limit_12m": self.days_at_limit_12m,
            "kontokorrent_limit": self.kontokorrent_limit,
            "warnings": list(self.warnings),
        }


def _normalise(s: str) -> str:
    return (
        s.strip().lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )


def _find(header: list[str], candidates: tuple[str, ...]) -> Optional[int]:
    norm = [_normalise(h) for h in header]
    for cand in candidates:            # candidate order is priority order
        for i, h in enumerate(norm):
            if h == cand:
                return i
    for cand in candidates:
        for i, h in enumerate(norm):
            if cand in h:
                return i
    return None


def _parse_date(raw: str) -> Optional[date]:
    s = raw.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _looks_like_path(source: str) -> bool:
    if "\n" in source or len(source) > 1024:
        return False
    try:
        return Path(source).is_file()
    except (OSError, ValueError):
        return False


def _read_text(source: str | Path | bytes) -> str:
    """Accepts raw bytes, a path, or the CSV text itself."""
    if isinstance(source, bytes):
        raw = source
    elif isinstance(source, Path) or _looks_like_path(source):
        raw = Path(source).read_bytes()
    else:
        return str(source)
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise BankCsvError("Zeichenkodierung nicht erkannt")


def parse_bank_csv(source: str | Path | bytes) -> list[BankTransaction]:
    """Parse a bank CSV export into transactions, oldest first."""
    text = _read_text(source)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise BankCsvError("Leere Datei")

    header_idx = delimiter = None
    for i, line in enumerate(lines[:40]):
        delim = max((";", ",", "\t"), key=line.count)
        cells = next(csv.reader([line], delimiter=delim))
        if _find(cells, DATE_HEADERS) is not None and (
            _find(cells, AMOUNT_HEADERS) is not None
            or (_find(cells, DEBIT_HEADERS) is not None and _find(cells, CREDIT_HEADERS) is not None)
        ):
            header_idx, delimiter = i, delim
            break
    if header_idx is None:
        raise BankCsvError(
            "Keine Kopfzeile mit Datums- und Betragsspalte gefunden. Erwartet werden "
            "z. B. 'Buchungstag' und 'Betrag' (oder 'Soll'/'Haben')."
        )

    reader = csv.reader(io.StringIO("\n".join(lines[header_idx:])), delimiter=delimiter)
    header = next(reader)
    i_date = _find(header, DATE_HEADERS)
    i_amount = _find(header, AMOUNT_HEADERS)
    i_debit = _find(header, DEBIT_HEADERS) if i_amount is None else None
    i_credit = _find(header, CREDIT_HEADERS) if i_amount is None else None
    i_balance = _find(header, BALANCE_HEADERS)
    i_text = _find(header, TEXT_HEADERS)

    txs: list[BankTransaction] = []
    for row in reader:
        if not row or len(row) <= i_date:
            continue
        d = _parse_date(row[i_date])
        if d is None:
            continue                     # footer lines, subtotals
        cell = lambda i: row[i] if i is not None and i < len(row) else ""  # noqa: E731
        if i_amount is not None:
            amount = _parse_german_number(cell(i_amount))
        else:
            amount = abs(_parse_german_number(cell(i_credit))) - abs(
                _parse_german_number(cell(i_debit))
            )
        bal_raw = cell(i_balance).strip()
        balance = _parse_german_number(bal_raw) if bal_raw else None
        txs.append(BankTransaction(d, amount, balance, cell(i_text).strip()))

    if not txs:
        raise BankCsvError("Keine Buchungen gefunden")

    # Newest-first exports: reverse so that, within a day, file order is time order.
    if txs[0].booking_date > txs[-1].booking_date:
        txs.reverse()
    txs.sort(key=lambda t: t.booking_date)       # stable: keeps intra-day order
    return txs


def _is_returned_debit(tx: BankTransaction) -> bool:
    if tx.amount <= 0:
        return False
    t = " " + _normalise(tx.text) + " "
    return any(k in t for k in RETURN_KEYWORDS)


def analyse_transactions(
    txs: list[BankTransaction],
    kontokorrent_limit: Optional[float] = None,
    limit_threshold: float = 0.95,
    account_label: str = "",
) -> BankAnalysis:
    """Derive the behavioural signals from a transaction list.

    A day counts as "at the limit" when its closing balance is at or below
    -limit * `limit_threshold` (default: 95% utilised). Days without a
    transaction carry the previous closing balance forward.
    """
    if not txs:
        raise BankCsvError("Keine Buchungen")
    first, last = txs[0].booking_date, txs[-1].booking_date
    analysis = BankAnalysis(
        account_label=account_label,
        first_date=first,
        last_date=last,
        transaction_count=len(txs),
        inflows=sum(t.amount for t in txs if t.amount > 0),
        outflows=-sum(t.amount for t in txs if t.amount < 0),
        has_balances=all(t.balance is not None for t in txs),
        returned_direct_debits=sum(1 for t in txs if _is_returned_debit(t)),
        kontokorrent_limit=kontokorrent_limit,
    )

    if analysis.days_covered < MIN_DAYS_FOR_ANNUALISATION:
        analysis.warnings.append(
            f"Nur {analysis.days_covered} Tage Kontohistorie -- Hochrechnung auf 12 Monate "
            "ist wenig belastbar. Empfohlen sind 6-12 Monate."
        )

    if not analysis.has_balances:
        analysis.warnings.append(
            "Export ohne Saldospalte: Tage am Kontokorrentlimit nicht bestimmbar."
        )
        return analysis

    closing: dict[date, float] = {}
    for t in txs:
        closing[t.booking_date] = t.balance          # last one of the day wins
    daily: list[float] = []
    current = txs[0].balance
    d = first
    while d <= last:
        current = closing.get(d, current)
        daily.append(current)
        d += timedelta(days=1)

    analysis.min_balance = min(daily)
    analysis.avg_balance = sum(daily) / len(daily)
    analysis.end_balance = daily[-1]

    if kontokorrent_limit and kontokorrent_limit > 0:
        floor = -kontokorrent_limit * limit_threshold
        analysis.days_at_limit = sum(1 for b in daily if b <= floor)
        if analysis.min_balance < -kontokorrent_limit * 1.001:
            analysis.warnings.append(
                f"Saldo unterschreitet das Limit von {de(kontokorrent_limit)} EUR "
                f"(Tiefststand {de(analysis.min_balance)} EUR) -- geduldete "
                "Ueberziehung, fuer Banken ein eigenstaendiges Warnsignal."
            )
    else:
        analysis.warnings.append(
            "Kein Kontokorrentlimit angegeben: Tage am Limit nicht bestimmbar."
        )
    return analysis


def analyse_bank_csv(
    source: str | Path | bytes,
    kontokorrent_limit: Optional[float] = None,
    account_label: str = "",
) -> BankAnalysis:
    return analyse_transactions(
        parse_bank_csv(source), kontokorrent_limit=kontokorrent_limit,
        account_label=account_label,
    )
