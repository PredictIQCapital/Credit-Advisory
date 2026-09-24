"""Forward projection of revenue, EBITDA and debt service coverage."""

from __future__ import annotations

import copy

import pytest

from credit_readiness.models import LoanFacility
from credit_readiness.projection import DAMPING, DSCR_FLOOR, MAX_GROWTH, project


def test_projection_starts_the_year_after_the_balance_sheet(case_01):
    p = project(case_01)
    base = case_01.balance_sheet.period_end.year
    assert [y.year for y in p.years] == [base + 1, base + 2, base + 3]


def test_growth_fades_geometrically(case_01):
    p = project(case_01)
    rev0 = case_01.income_statement.annualised(case_01.income_statement.umsatzerloese)
    revs = [rev0] + [y.umsatz for y in p.years]
    growth = [b / a - 1 for a, b in zip(revs, revs[1:])]
    assert growth[0] == pytest.approx(p.growth_start * DAMPING)
    for a, b in zip(growth, growth[1:]):
        assert b == pytest.approx(a * DAMPING)


def test_without_prior_year_revenue_is_flat(case_01):
    case = copy.deepcopy(case_01)
    case.prior_year_income = None
    p = project(case)
    rev0 = case.income_statement.annualised(case.income_statement.umsatzerloese)
    assert all(y.umsatz == pytest.approx(rev0) for y in p.years)
    assert p.history_years == 1
    assert any("konstant" in a for a in p.assumptions)


def test_one_off_growth_is_clamped(case_01):
    case = copy.deepcopy(case_01)
    case.prior_year_income.umsatzerloese = case.income_statement.umsatzerloese / 3
    assert project(case).growth_start == pytest.approx(MAX_GROWTH)


def test_margin_is_the_average_of_the_years(case_01):
    p = project(case_01)
    for y in p.years:
        assert y.ebitda / y.umsatz == pytest.approx(p.ebitda_margin)


def test_matured_facility_drops_out(case_01):
    case = copy.deepcopy(case_01)
    base = case.balance_sheet.period_end.year
    case.facilities = [LoanFacility("Bank", "Tilgungsdarlehen", 300_000, 200_000, 0.05,
                                    100_000, maturity_year=base + 2)]
    case.request = None
    p = project(case)
    assert p.years[0].kapitaldienst == pytest.approx(200_000 * 0.05 + 100_000)
    assert p.years[1].kapitaldienst == pytest.approx(100_000 * 0.05 + 100_000)
    assert p.years[2].kapitaldienst == 0 and p.years[2].dscr is None


def test_distressed_case_is_flagged_every_year(case_03):
    p = project(case_03)
    assert len(p.years_below_floor) == len(p.years)
    assert p.min_dscr < DSCR_FLOOR


def test_diagnostic_carries_the_projection(case_01):
    from credit_readiness.engine import run_diagnostic
    from credit_readiness.reporting.report import render_markdown
    from credit_readiness.reporting.summary import result_summary

    res = run_diagnostic(case_01)
    assert res.projection is not None and res.projection.years
    assert result_summary(res)["projection"]["years"]
    assert "### Fortschreibung (Basisfall)" in render_markdown(res)
