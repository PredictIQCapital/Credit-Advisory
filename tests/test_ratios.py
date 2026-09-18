"""Ratio arithmetic. Golden values are hand-computed in the docstrings."""

from __future__ import annotations

from datetime import date

import pytest

from credit_readiness.models import BalanceSheet, IncomeStatement
from credit_readiness.ratios import compute_ratios


def test_balance_sheet_totals(minimal_case):
    bs = minimal_case.balance_sheet
    assert bs.anlagevermoegen == 200_000
    assert bs.umlaufvermoegen == 200_000
    assert bs.bilanzsumme == 400_000
    assert bs.bilanzielles_eigenkapital == 100_000


def test_ebitda_and_ebit(minimal_case):
    """1.000.000 - 500.000 - 300.000 - 100.000 = 100.000 EBITDA; -50.000 AfA."""
    gu = minimal_case.income_statement
    assert gu.ebitda == 100_000
    assert gu.ebit == 50_000
    assert gu.ebt == 40_000


def test_core_ratios(minimal_case):
    r = compute_ratios(minimal_case)
    assert r.eigenkapitalquote == pytest.approx(0.25)          # 100k / 400k
    assert r.ebit_marge == pytest.approx(0.05)                 # 50k / 1.000k
    assert r.ebitda_marge == pytest.approx(0.10)
    assert r.zinsdeckungsgrad == pytest.approx(5.0)            # 50k / 10k
    # Nettofinanzverbindlichkeiten = 200k Bank - 100k Kasse = 100k; /100k EBITDA
    assert r.dynamischer_verschuldungsgrad == pytest.approx(1.0)
    # Kapitaldienst = 200k*5% + 20k = 30k; 100k/30k
    assert r.kapitaldienstfaehigkeit == pytest.approx(100_000 / 30_000)


def test_debitorenlaufzeit(minimal_case):
    """100.000 / 1.000.000 * 365 = 36,5 Tage."""
    r = compute_ratios(minimal_case)
    assert r.debitorenlaufzeit_tage == pytest.approx(36.5)


def test_liquiditaet_2_grades(minimal_case):
    """(100k Forderungen + 100k Kasse) / (100k Bank kurz + 100k LuL) = 1,0."""
    r = compute_ratios(minimal_case)
    assert r.liquiditaet_2_grades == pytest.approx(1.0)


def test_rangruecktritt_shifts_debt_to_equity():
    """The single most important reclassification in the whole engine."""
    bs = BalanceSheet(
        period_end=date(2025, 12, 31),
        sachanlagen=1_000_000,
        gezeichnetes_kapital=100_000,
        gesellschafterdarlehen=400_000,
        verb_kreditinstitute_lang=500_000,
    )
    assert bs.wirtschaftliches_eigenkapital == 100_000
    assert bs.finanzverbindlichkeiten == 900_000

    bs.gesellschafterdarlehen_rangruecktritt = True
    assert bs.wirtschaftliches_eigenkapital == 500_000
    assert bs.finanzverbindlichkeiten == 500_000


def test_partial_year_bwa_is_annualised():
    """A 6-month BWA must not halve the apparent margin against the balance sheet."""
    half = IncomeStatement(
        period_end=date(2025, 6, 30),
        period_months=6,
        umsatzerloese=500_000,
        materialaufwand=250_000,
        personalaufwand=150_000,
        sonstige_betriebliche_aufwendungen=50_000,
        abschreibungen=25_000,
    )
    assert half.annualisation_factor == pytest.approx(2.0)
    assert half.annualised(half.ebitda) == pytest.approx(100_000)


def test_partial_year_ratios_match_full_year(minimal_case):
    """Same business, half-year BWA: flow/stock ratios must be identical."""
    full = compute_ratios(minimal_case)

    gu = minimal_case.income_statement
    minimal_case.income_statement = IncomeStatement(
        period_end=date(2025, 6, 30),
        period_months=6,
        umsatzerloese=gu.umsatzerloese / 2,
        materialaufwand=gu.materialaufwand / 2,
        personalaufwand=gu.personalaufwand / 2,
        sonstige_betriebliche_aufwendungen=gu.sonstige_betriebliche_aufwendungen / 2,
        abschreibungen=gu.abschreibungen / 2,
        zinsaufwand=gu.zinsaufwand / 2,
    )
    half = compute_ratios(minimal_case)

    assert half.ebit_marge == pytest.approx(full.ebit_marge)
    assert half.dynamischer_verschuldungsgrad == pytest.approx(
        full.dynamischer_verschuldungsgrad
    )
    assert half.debitorenlaufzeit_tage == pytest.approx(full.debitorenlaufzeit_tage)


def test_negative_ebitda_suppresses_leverage_ratio():
    """Net debt / EBITDA is misleading when EBITDA <= 0, so it must be None."""
    from credit_readiness.models import (
        ClientCase,
        CompanyProfile,
        LegalForm,
        Sector,
    )

    case = ClientCase(
        profile=CompanyProfile(
            name="Verlust GmbH",
            legal_form=LegalForm.GMBH,
            sector=Sector.RETAIL,
            employees=10,
            founded_year=2020,
        ),
        balance_sheet=BalanceSheet(
            period_end=date(2025, 12, 31),
            sachanlagen=500_000,
            verb_kreditinstitute_lang=400_000,
        ),
        income_statement=IncomeStatement(
            period_end=date(2025, 12, 31),
            umsatzerloese=1_000_000,
            materialaufwand=600_000,
            personalaufwand=500_000,
            sonstige_betriebliche_aufwendungen=100_000,
        ),
    )
    r = compute_ratios(case)
    assert r.ebitda < 0
    assert r.dynamischer_verschuldungsgrad is None


def test_missing_denominators_return_none():
    """No facilities, no interest -> ratios are absent, not zero and not a crash."""
    from credit_readiness.models import (
        ClientCase,
        CompanyProfile,
        LegalForm,
        Sector,
    )

    case = ClientCase(
        profile=CompanyProfile(
            name="Duenn GmbH",
            legal_form=LegalForm.GMBH,
            sector=Sector.IT_SERVICES,
            employees=5,
            founded_year=2022,
        ),
        balance_sheet=BalanceSheet(period_end=date(2025, 12, 31), liquide_mittel=10_000),
        income_statement=IncomeStatement(
            period_end=date(2025, 12, 31), umsatzerloese=100_000
        ),
    )
    r = compute_ratios(case)
    assert r.kapitaldienstfaehigkeit is None
    assert r.zinsdeckungsgrad is None
    assert r.kontokorrent_auslastung is None
