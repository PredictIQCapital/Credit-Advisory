"""Tests for the EBA-mandated sensitivity analysis.

Two of these pin bugs that were live during development and would have been
invisible in the output: a rate shock that left the DSCR untouched, and a
revenue shock that booked the contribution loss twice. Both produced
plausible-looking numbers, which is exactly why they need tests.
"""

from __future__ import annotations

import copy

import pytest

from credit_readiness import sensitivity
from credit_readiness.ratios import compute_ratios


def test_rate_shock_reaches_the_debt_service_not_just_the_interest_line(case_01):
    """EBA 158(k) reprices the facilities, so the DSCR must move.

    Regression: an earlier version added the 200bp only to the P&L interest
    line. Debt service is computed from the facility schedule, so the DSCR --
    the one ratio a lender actually tests -- came out unchanged.
    """
    before = compute_ratios(case_01).kapitaldienstfaehigkeit_inkl_neu
    stressed = sensitivity._rate_shock(case_01)
    after = compute_ratios(stressed).kapitaldienstfaehigkeit_inkl_neu

    assert before is not None and after is not None
    assert after < before, "the +200bp shock left debt service untouched"
    for original, shocked in zip(case_01.facilities, stressed.facilities):
        assert shocked.interest_rate == pytest.approx(original.interest_rate + 0.02)


def test_revenue_shock_books_the_contribution_loss_exactly_once(case_01):
    """Regression: the hit was applied via the revenue line and again as a cost.

    The arithmetic is checkable by hand, which is the point -- EBITDA must fall
    by revenue lost minus the variable costs that fall away with it, and by
    nothing else.
    """
    g = case_01.income_statement
    umsatzverlust = g.umsatzerloese * sensitivity.UMSATZRUECKGANG
    ersparnis = min(umsatzverlust * sensitivity.VARIABLER_KOSTENANTEIL, g.materialaufwand)
    erwarteter_verlust = umsatzverlust - ersparnis

    ebitda_vorher = compute_ratios(case_01).ebitda
    ebitda_nachher = compute_ratios(sensitivity._revenue_shock(case_01)).ebitda

    assert ebitda_vorher - ebitda_nachher == pytest.approx(erwarteter_verlust, rel=1e-6)


def test_variable_cost_relief_cannot_exceed_the_material_cost_that_exists(case_04):
    """A consultancy has almost no Materialaufwand, so a revenue decline is
    very nearly a contribution decline. That must fall out of the cap, not
    produce a negative cost line."""
    stressed = sensitivity._revenue_shock(case_04)
    assert stressed.income_statement.materialaufwand >= 0.0

    g = case_04.income_statement
    umsatzverlust = g.umsatzerloese * sensitivity.UMSATZRUECKGANG
    verlust = compute_ratios(case_04).ebitda - compute_ratios(stressed).ebitda
    assert verlust <= umsatzverlust + 1e-6
    assert verlust >= umsatzverlust * (1.0 - sensitivity.VARIABLER_KOSTENANTEIL) - 1e-6


@pytest.mark.parametrize("scenario", [s[0] for s in sensitivity.SCENARIOS])
def test_stressed_balance_sheet_still_balances(case_01, scenario):
    """Funding the hit must not break the accounting identity.

    Cash falls by X, short-term bank debt rises by (hit - X), equity falls by
    the hit: assets and liabilities move by the same amount or the ratios
    computed afterwards are meaningless.
    """
    shock = dict((s[0], s[3]) for s in sensitivity.SCENARIOS)[scenario]
    stressed = shock(case_01)

    def gap(case) -> float:
        b = case.balance_sheet
        passiva = (
            b.bilanzielles_eigenkapital + b.rueckstellungen + b.pensionsrueckstellungen
            + b.verb_kreditinstitute_kurz + b.verb_kreditinstitute_lang + b.verb_ll
            + b.sonstige_verbindlichkeiten_kurz + b.sonstige_verbindlichkeiten_lang
            + b.gesellschafterdarlehen + b.passive_rap
        )
        return b.bilanzsumme - passiva

    assert gap(stressed) == pytest.approx(gap(case_01), abs=1.0)


def test_the_case_under_analysis_is_never_mutated(case_01):
    """The scenarios deep-copy; a stress run must not change the client's file."""
    before = copy.deepcopy(case_01)
    sensitivity.analyse(case_01)
    assert case_01.balance_sheet.liquide_mittel == before.balance_sheet.liquide_mittel
    assert case_01.income_statement.zinsaufwand == before.income_statement.zinsaufwand
    assert [f.interest_rate for f in case_01.facilities] == [
        f.interest_rate for f in before.facilities
    ]


def test_a_strong_borrower_holds_its_band_and_a_stretched_one_does_not(case_06, case_01):
    """The whole point of the exercise: it has to separate the two."""
    assert sensitivity.analyse(case_06).is_resilient
    assert not sensitivity.analyse(case_01).is_resilient


def test_every_scenario_cites_the_paragraph_it_comes_from():
    """These scenarios are not invented, and the report has to be able to say so."""
    for key, label, assumption, _ in sensitivity.SCENARIOS:
        assert "EBA/GL/2020/06" in assumption, key
    assert sensitivity.ZINSSCHOCK_BP == 0.02, "EBA 158(k) names 200 basis points"


def test_combined_scenario_is_at_least_as_severe_as_either_alone(case_01):
    result = sensitivity.analyse(case_01)
    by_key = {s.key: s for s in result.scenarios}
    assert by_key["kombiniert"].score <= by_key["zinsschock"].score + 1e-9
    assert by_key["kombiniert"].score <= by_key["umsatzrueckgang"].score + 1e-9


def test_a_loss_making_borrower_does_not_gain_a_tax_refund(case_01):
    """The tax leg may reduce the charge to zero, never below it."""
    broke = copy.deepcopy(case_01)
    broke.income_statement.steuern = 0.0
    for scenario in (sensitivity._rate_shock, sensitivity._revenue_shock):
        assert scenario(broke).income_statement.steuern >= 0.0
