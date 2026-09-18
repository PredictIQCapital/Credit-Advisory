"""Bank statement CSV parsing and behavioural signal extraction."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from credit_readiness.ingest.bank_csv import (
    BankCsvError,
    analyse_bank_csv,
    analyse_transactions,
    parse_bank_csv,
)

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "samples" / "intake" / "kontoumsaetze_kontokorrent.csv"


def test_preamble_newest_first_and_cp1252_are_handled():
    raw = (
        "Umsatzanzeige;Konto 123\n"
        "Zeitraum;Januar\n"
        "\n"
        "Buchungstag;Buchungstext;Verwendungszweck;Betrag;Saldo\n"
        "03.01.2025;Überweisung;Miete;-1.000,00;-3.000,00\n"
        "02.01.2025;Gutschrift;Kunde;500,00;-2.000,00\n"
        "01.01.2025;Überweisung;Lieferant;-2.500,00;-2.500,00\n"
    ).encode("cp1252")
    txs = parse_bank_csv(raw)
    assert [t.booking_date.day for t in txs] == [1, 2, 3]
    assert txs[0].amount == -2500.0
    assert txs[-1].balance == -3000.0


def test_separate_soll_haben_columns():
    raw = (
        "Datum,Text,Soll,Haben,Kontostand\n"
        "01.01.2025,A,100.00,,900.00\n"
        "02.01.2025,B,,50.00,950.00\n"
    )
    txs = parse_bank_csv(raw)
    assert [t.amount for t in txs] == [-100.0, 50.0]


def test_days_at_limit_carry_balance_over_days_without_bookings():
    raw = (
        "Buchungstag;Betrag;Saldo;Verwendungszweck\n"
        "01.01.2025;-96.000,00;-96.000,00;Lieferant\n"      # at limit from 1st ...
        "05.01.2025;50.000,00;-46.000,00;Kunde\n"           # ... until 4th = 4 days
        "10.01.2025;-50.000,00;-96.000,00;Lieferant\n"      # 10th only = 1 day
    )
    a = analyse_transactions(parse_bank_csv(raw), kontokorrent_limit=100_000)
    assert a.days_covered == 10
    assert a.days_at_limit == 5
    assert a.min_balance == -96_000


def test_only_returned_debits_that_hit_the_client_are_counted():
    raw = (
        "Buchungstag;Betrag;Saldo;Verwendungszweck\n"
        "01.01.2025;-1.000,00;0,00;Lastschrift Versicherung\n"
        "02.01.2025;1.000,00;1.000,00;RUECKLASTSCHRIFT Versicherung mangels Deckung\n"
        "03.01.2025;-200,00;800,00;Rücklastschrift Kunde XY (eigener Einzug)\n"
    )
    a = analyse_transactions(parse_bank_csv(raw))
    assert a.returned_direct_debits == 1


def test_no_balance_column_means_no_limit_days_not_a_guess():
    raw = "Buchungstag;Betrag;Verwendungszweck\n01.01.2025;-10,00;x\n31.03.2025;5,00;y\n"
    a = analyse_transactions(parse_bank_csv(raw), kontokorrent_limit=1000)
    assert a.days_at_limit is None
    assert a.days_at_limit_12m is None
    assert any("Saldospalte" in w for w in a.warnings)


def test_short_history_is_flagged():
    raw = "Buchungstag;Betrag;Saldo\n01.01.2025;-10,00;-10,00\n15.01.2025;5,00;-5,00\n"
    a = analyse_transactions(parse_bank_csv(raw), kontokorrent_limit=1000)
    assert any("Hochrechnung" in w for w in a.warnings)


def test_overdraft_beyond_the_limit_is_flagged():
    raw = "Buchungstag;Betrag;Saldo\n01.01.2025;-110,00;-110,00\n"
    a = analyse_transactions(parse_bank_csv(raw), kontokorrent_limit=100)
    assert any("Ueberziehung" in w for w in a.warnings)


def test_unrecognisable_file_raises():
    with pytest.raises(BankCsvError):
        parse_bank_csv("foo;bar\n1;2\n")
    with pytest.raises(BankCsvError):
        parse_bank_csv(b"")


def test_sample_export_annualises_to_a_full_year():
    a = analyse_bank_csv(SAMPLE, kontokorrent_limit=500_000)
    assert a.first_date == date(2025, 1, 1) and a.last_date == date(2025, 12, 31)
    assert a.end_balance == pytest.approx(-420_000)
    assert a.days_at_limit_12m == a.days_at_limit
    assert 50 <= a.days_at_limit <= 120
