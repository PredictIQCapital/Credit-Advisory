"""Fixability classification, remediation rules, and simulation safety."""

from __future__ import annotations

import copy

import pytest

from credit_readiness.engine import run_diagnostic
from credit_readiness.ratios import compute_ratios
from credit_readiness.remediation import (
    FixCategory,
    Verdict,
    classify,
    diagnose,
    simulate,
)
from credit_readiness.scorecard import evaluate


def _diagnose(case):
    ratios = compute_ratios(case)
    card = evaluate(case, ratios)
    return diagnose(case, ratios, card), ratios, card


def test_rangruecktritt_rule_fires_and_lifts_equity(case_01):
    findings, _, _ = _diagnose(case_01)
    r01 = next(f for f in findings if f.rule_id == "R01")
    assert r01.category is FixCategory.PRESENTATION
    assert r01.requires_steuerberater and r01.requires_legal
    assert r01.caveat, "a reclassification recommendation must carry its caveat"

    before = compute_ratios(case_01).eigenkapitalquote
    working = copy.deepcopy(case_01)
    r01.simulate(working)
    after = compute_ratios(working).eigenkapitalquote
    assert after > before
    # 600.000 / 4.385.000 = 13,7 Punkte Uplift
    assert after - before == pytest.approx(600_000 / 4_385_000, rel=1e-3)


def test_rangruecktritt_rule_silent_when_already_subordinated(case_01):
    case_01.balance_sheet.gesellschafterdarlehen_rangruecktritt = True
    findings, _, _ = _diagnose(case_01)
    assert not any(f.rule_id == "R01" for f in findings)


def test_genuine_risk_case_is_flagged_and_declined(case_03):
    findings, _, card = _diagnose(case_03)
    assert any(f.rule_id == "R08" for f in findings)
    assert classify(findings, card) is Verdict.GENUINE_RISK

    r08 = next(f for f in findings if f.rule_id == "R08")
    assert not r08.category.is_fixable
    assert r08.simulate is None, "substantive weakness must not be simulatable away"


def test_genuine_risk_dominates_cosmetic_findings(case_03):
    """Even with several fixable findings present, one substantive one wins."""
    findings, _, card = _diagnose(case_03)
    assert any(f.category.is_fixable for f in findings)
    assert classify(findings, card) is Verdict.GENUINE_RISK


def test_tax_arrears_flagged_as_knockout(case_03):
    findings, _, _ = _diagnose(case_03)
    r09 = next(f for f in findings if f.rule_id == "R09")
    assert r09.category is FixCategory.GENUINE_RISK
    assert r09.severity == "kritisch"


def test_collateral_rule_requires_serviceable_debt(case_04):
    """A collateral gap is only a collateral gap if the debt can be serviced."""
    findings, _, _ = _diagnose(case_04)
    assert any(f.rule_id == "R07" for f in findings)

    # Crush earnings: the same file is now a capacity problem, not a pledge problem.
    case_04.income_statement.personalaufwand = 7_500_000
    findings2, _, _ = _diagnose(case_04)
    assert not any(f.rule_id == "R07" for f in findings2)


def test_simulation_never_mutates_the_original_case(case_01):
    """The before/after comparison IS the deliverable -- 'before' must survive."""
    snapshot = copy.deepcopy(case_01)
    findings, _, _ = _diagnose(case_01)
    simulate(case_01, findings)

    assert case_01.balance_sheet.gesellschafterdarlehen_rangruecktritt == (
        snapshot.balance_sheet.gesellschafterdarlehen_rangruecktritt
    )
    assert case_01.balance_sheet.kontokorrent_inanspruchnahme == pytest.approx(
        snapshot.balance_sheet.kontokorrent_inanspruchnahme
    )
    assert case_01.behavior.bwa_age_months == snapshot.behavior.bwa_age_months
    assert case_01.balance_sheet.forderungen_ll == pytest.approx(
        snapshot.balance_sheet.forderungen_ll
    )


def test_simulation_improves_a_fixable_case(case_01):
    findings, _, _ = _diagnose(case_01)
    sim = simulate(case_01, findings)
    assert sim.delta > 0
    assert sim.after_score > sim.before_score
    assert sim.applied


def test_simulation_cannot_rescue_a_genuinely_weak_case(case_03):
    """Cosmetic fixes must not lift a distressed borrower into a healthy band."""
    findings, _, _ = _diagnose(case_03)
    sim = simulate(case_03, findings)
    assert sim.after_band in ("D", "E")
    skipped = " ".join(sim.skipped)
    assert "R08" in skipped


def test_findings_sorted_by_severity(case_01):
    findings, _, _ = _diagnose(case_01)
    order = {"kritisch": 0, "wesentlich": 1, "gering": 2}
    ranks = [order[f.severity] for f in findings]
    assert ranks == sorted(ranks)


def test_every_finding_has_observation_and_remediation(case_01, case_03, case_04):
    for case in (case_01, case_03, case_04):
        findings, _, _ = _diagnose(case)
        for f in findings:
            assert f.observation.strip(), f"{f.rule_id} lacks an observation"
            assert f.remediation.strip(), f"{f.rule_id} lacks a remediation"
            assert f.title.strip()


def test_strong_control_case_is_already_bankable(case_06):
    result = run_diagnostic(case_06)
    assert result.verdict is Verdict.ALREADY_BANKABLE
    assert result.scorecard.band.value == "A"
    assert not result.is_engageable, "a healthy company is not an engagement"
