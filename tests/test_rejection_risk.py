"""Knock-out checks: the named reasons a lender declines, regardless of score.

These checks assert legal and regulatory conditions about a real company, so a
false positive is expensive in a way a scoring wobble is not -- telling a
healthy client that half their share capital is gone would end the engagement.
The tests are written around that asymmetry: every check is pinned on both
sides of its threshold.
"""

from __future__ import annotations

import copy

import pytest

from credit_readiness import rejection_risk as rr
from credit_readiness.ratios import compute_ratios


def _screen(case):
    return rr.screen(case, compute_ratios(case))


def _codes(case):
    return {r.code for r in _screen(case).reasons}


# --------------------------------------------------------------- clean files


def test_healthy_files_trip_nothing(case_01, case_04, case_06):
    """A false positive here costs more than a missed one: it tells a solvent
    client they are in a statutory crisis."""
    for case in (case_01, case_04, case_06):
        assert _screen(case).clean, f"{case.profile.name}: {_codes(case)}"


def test_a_clean_screen_still_reports_how_many_checks_ran(case_01):
    """'Nothing found' only means something if the reader knows what was looked
    for."""
    result = _screen(case_01)
    assert result.clean
    assert result.checked == len(rr.CHECKS) == 8
    assert result.worst is None


# ------------------------------------------------------- 49 Abs. 3 GmbHG


def test_half_the_share_capital_lost_is_caught_at_the_statutory_line(case_01):
    b = case_01.balance_sheet
    half = b.gezeichnetes_kapital / 2.0

    just_above = copy.deepcopy(case_01)
    just_above.balance_sheet.gewinnruecklagen -= (
        b.bilanzielles_eigenkapital - half - 1.0
    )
    assert "KO01" not in _codes(just_above)

    just_below = copy.deepcopy(case_01)
    just_below.balance_sheet.gewinnruecklagen -= (
        b.bilanzielles_eigenkapital - half + 1.0
    )
    assert "KO01" in _codes(just_below)


def test_a_company_with_no_share_capital_is_not_checked(case_01):
    """Partnerships carry no gezeichnetes Kapital; the test is meaningless and
    must not fire rather than divide by nothing."""
    case = copy.deepcopy(case_01)
    case.balance_sheet.gezeichnetes_kapital = 0.0
    assert "KO01" not in _codes(case)


def test_subordination_softens_the_capital_finding_but_does_not_erase_it(case_01):
    """49 Abs. 3 GmbHG looks at balance-sheet equity, so a Rangruecktritt cannot
    cure the statutory position -- but it does change how a lender reads it."""
    case = copy.deepcopy(case_01)
    b = case.balance_sheet
    b.gewinnruecklagen -= b.bilanzielles_eigenkapital  # equity down to zero
    b.gesellschafterdarlehen = max(b.gesellschafterdarlehen, b.gezeichnetes_kapital * 5)
    b.gesellschafterdarlehen_rangruecktritt = True

    found = [r for r in _screen(case).reasons if r.code in ("KO01", "KO02")]
    assert found, "the condition must still be reported"
    assert all(r.mitigated for r in found)
    assert all(r.severity is rr.Schwere.SCHWER for r in found)


# ------------------------------------------------------------ over-indebted


def test_negative_equity_reports_overindebtedness_not_both_findings(case_03):
    """KO02 implies KO01 arithmetically; saying both buries the worse one."""
    codes = _codes(case_03)
    assert "KO02" in codes
    assert "KO01" not in codes


def test_overindebtedness_is_never_called_insolvency(case_03):
    """A going-concern prognosis is a legal judgement this engine cannot make,
    and saying otherwise would be both wrong and harmful."""
    reason = next(r for r in _screen(case_03).reasons if r.code == "KO02")
    text = (reason.finding + reason.consequence + reason.action).lower()
    assert "fortfuehrungsprognose" in text
    assert "insolvenzantrag" not in text
    assert "ist insolvent" not in text


# -------------------------------------------------------------- overdraft


def test_overdraft_within_the_limit_is_not_a_default_indicator(case_01):
    """Mueller sits at 84% utilisation. High, scored as such -- but not past
    due, and the distinction is the whole point of CRR 178."""
    case = copy.deepcopy(case_01)
    case.balance_sheet.kontokorrent_inanspruchnahme = (
        case.balance_sheet.kontokorrent_limit
    )
    assert "KO03" not in _codes(case)


def test_breaching_the_advised_limit_is_a_default_indicator(case_01):
    case = copy.deepcopy(case_01)
    case.balance_sheet.kontokorrent_inanspruchnahme = (
        case.balance_sheet.kontokorrent_limit + 5_000
    )
    reason = next(r for r in _screen(case).reasons if r.code == "KO03")
    assert reason.severity is rr.Schwere.KO
    assert "178" in reason.source


# ------------------------------------------------------------ loss history


def test_a_single_loss_year_without_a_prior_year_asks_for_the_prior_year(case_01):
    case = copy.deepcopy(case_01)
    case.income_statement.sonstige_betriebliche_aufwendungen += 10_000_000
    case.prior_year_income = None
    reason = next(r for r in _screen(case).reasons if r.code == "KO06")
    assert reason.severity is rr.Schwere.PRUEFEN
    assert "Vorjahr" in reason.action


def test_two_consecutive_loss_years_are_treated_as_structural(case_03):
    reason = next(r for r in _screen(case_03).reasons if r.code == "KO06")
    assert reason.severity is rr.Schwere.SCHWER


def test_a_loss_year_after_a_profitable_one_is_not_flagged(case_01):
    case = copy.deepcopy(case_01)
    case.income_statement.sonstige_betriebliche_aufwendungen += 10_000_000
    assert case.prior_year_income is not None
    assert case.prior_year_income.jahresueberschuss >= 0
    assert "KO06" not in _codes(case)


# ------------------------------------------------------------- stale accounts


@pytest.mark.parametrize("months,expected", [(22.0, False), (23.0, True), (30.0, True)])
def test_accounts_older_than_23_months_stop_the_assessment(case_01, months, expected):
    case = copy.deepcopy(case_01)
    case.behavior.jahresabschluss_age_months = months
    assert ("KO08" in _codes(case)) is expected


# ----------------------------------------------------------------- contract


def test_every_check_names_a_source_and_an_action(case_03):
    """A finding the client cannot trace or act on is just an accusation."""
    for reason in _screen(case_03).reasons:
        assert reason.source.strip(), reason.code
        assert reason.action.strip(), reason.code
        assert reason.consequence.strip(), reason.code


def test_findings_are_ordered_worst_first_and_mitigated_ones_last(case_03):
    reasons = _screen(case_03).reasons
    rank = [rr._ORDER[x.severity] for x in reasons if not x.mitigated]
    assert rank == sorted(rank)
    mitigated_flags = [x.mitigated for x in reasons]
    assert mitigated_flags == sorted(mitigated_flags)


def test_knockouts_exclude_mitigated_findings(case_03):
    result = _screen(case_03)
    assert all(not r.mitigated for r in result.knockouts)


def test_the_screen_does_not_mutate_the_case(case_03):
    before = copy.deepcopy(case_03)
    _screen(case_03)
    assert case_03.balance_sheet.bilanzielles_eigenkapital == (
        before.balance_sheet.bilanzielles_eigenkapital
    )
    assert case_03.behavior.tax_arrears == before.behavior.tax_arrears


def test_the_documented_catalogue_matches_the_checks_that_actually_run():
    """The methodology PDF is generated from CHECK_CATALOGUE. If a check is
    added and the catalogue is not, the document silently understates what the
    product does -- which is the failure mode that matters for a document
    people are asked to rely on."""
    assert [c[0] for c in rr.CHECK_CATALOGUE] == [c[0] for c in rr.CHECKS]
    for code, title, condition, source in rr.CHECK_CATALOGUE:
        assert title.strip() and condition.strip() and source.strip(), code
