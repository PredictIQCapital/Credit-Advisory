from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from credit_readiness.ingest import load_case_file
from credit_readiness.models import (
    BalanceSheet,
    BehavioralData,
    ClientCase,
    CompanyProfile,
    FinancingRequest,
    IncomeStatement,
    LegalForm,
    LoanFacility,
    Sector,
)

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"


@pytest.fixture
def sample_dir() -> Path:
    return SAMPLES


@pytest.fixture
def case_01() -> ClientCase:
    return load_case_file(SAMPLES / "case_01_mueller_praezisionstechnik.json")


@pytest.fixture
def case_03() -> ClientCase:
    return load_case_file(SAMPLES / "case_03_gastro_rheinblick.json")


@pytest.fixture
def case_04() -> ClientCase:
    return load_case_file(SAMPLES / "case_04_datenwerk_consulting.json")


@pytest.fixture
def case_06() -> ClientCase:
    return load_case_file(SAMPLES / "case_06_hoffmann_medizintechnik.json")


@pytest.fixture
def minimal_case() -> ClientCase:
    """A deliberately tiny, perfectly balanced case for arithmetic tests.

    Aktiva  = 200k Sachanlagen + 100k Forderungen + 100k Kasse = 400k
    Passiva = 100k EK + 100k Bank lang + 100k Bank kurz + 100k LuL = 400k
    """
    return ClientCase(
        case_id="MIN",
        profile=CompanyProfile(
            name="Testfall GmbH",
            legal_form=LegalForm.GMBH,
            sector=Sector.MANUFACTURING,
            employees=20,
            founded_year=2015,
        ),
        balance_sheet=BalanceSheet(
            period_end=date(2025, 12, 31),
            sachanlagen=200_000,
            forderungen_ll=100_000,
            liquide_mittel=100_000,
            gezeichnetes_kapital=100_000,
            verb_kreditinstitute_lang=100_000,
            verb_kreditinstitute_kurz=100_000,
            verb_ll=100_000,
        ),
        income_statement=IncomeStatement(
            period_end=date(2025, 12, 31),
            period_months=12,
            umsatzerloese=1_000_000,
            materialaufwand=500_000,
            personalaufwand=300_000,
            sonstige_betriebliche_aufwendungen=100_000,
            abschreibungen=50_000,
            zinsaufwand=10_000,
        ),
        facilities=[
            LoanFacility(
                lender="Testbank",
                facility_type="Tilgungsdarlehen",
                original_amount=200_000,
                outstanding=200_000,
                interest_rate=0.05,
                annual_principal_repayment=20_000,
            )
        ],
        behavior=BehavioralData(bwa_age_months=1, creditreform_bonitaetsindex=200),
        request=FinancingRequest(
            amount=100_000, purpose="Investition", tenor_years=5,
            collateral_available=100_000,
        ),
    )
