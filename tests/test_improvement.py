"""Improvement potential: sector-typical targets, weighted gains, euro gaps."""

from __future__ import annotations

import copy

import pytest

from credit_readiness.improvement import TARGET_SCORE, inverse, plan
from credit_readiness.ratios import compute_ratios
from credit_readiness.scorecard import FACTORS_BY_KEY, curve_for, evaluate, interpolate


def _plan(case):
    ratios = compute_ratios(case)
    card = evaluate(case, ratios)
    return plan(case, ratios, card), card, ratios


@pytest.mark.parametrize("key", ["eigenkapitalquote", "kreditorenlaufzeit_tage",
                                 "kapitaldienstfaehigkeit_inkl_neu", "kontokorrent_auslastung"])
def test_inverse_hits_the_target_on_rising_and_falling_curves(key):
    bps = FACTORS_BY_KEY[key].breakpoints
    x = inverse(TARGET_SCORE, bps)
    assert interpolate(x, bps) == pytest.approx(TARGET_SCORE)


def test_inverse_returns_none_when_unreachable():
    assert inverse(90.0, ((0.0, 0.0), (1.0, 82.0))) is None


def test_target_on_a_sector_curve_is_the_sector_median(case_01):
    """'Sector norms' in the spec: the equity target is the sector median."""
    from credit_readiness import benchmarks
    p, card, ratios = _plan(case_01)
    item = next(i for i in p.items if i.key == "eigenkapitalquote")
    cell, _ = benchmarks.sector_cell("eigenmittel_pct_bilanzsumme",
                                     case_01.profile.sector, ratios.umsatz)
    assert item.target == pytest.approx(cell["q50"] / 100)


def test_gains_are_weighted_and_ranked(case_03):
    p, card, _ = _plan(case_03)
    assert p.items, "a distressed case has room to improve"
    gains = [i.points_gain for i in p.items]
    assert gains == sorted(gains, reverse=True)
    for i in p.items:
        f = card.factor(i.key)
        assert i.points_gain == pytest.approx(f.weight * (TARGET_SCORE - f.score))


def test_factors_already_typical_are_not_listed(case_06):
    p, card, _ = _plan(case_06)
    listed = {i.key for i in p.items}
    for f in card.factors:
        if f.score is not None and f.score >= TARGET_SCORE:
            assert f.key not in listed


def test_equity_gap_in_euros_closes_the_ratio(case_03):
    """Adding the stated equity (balance sheet constant) lands on the target."""
    p, _, _ = _plan(case_03)
    item = next(i for i in p.items if i.key == "eigenkapitalquote")
    bs = case_03.balance_sheet
    assert (bs.wirtschaftliches_eigenkapital + item.euro_gap) / bs.bilanzsumme == \
        pytest.approx(item.target)


def test_path_to_next_band_adds_up(case_01):
    p, _, _ = _plan(case_01)
    path = p.reaching_next_band()
    if p.points_to_next_band is not None and path:
        assert sum(i.points_gain for i in path) >= p.points_to_next_band
        assert sum(i.points_gain for i in path[:-1]) < p.points_to_next_band


def test_report_and_summary_carry_the_plan(case_03):
    from credit_readiness.engine import run_diagnostic
    from credit_readiness.reporting.report import render_markdown
    from credit_readiness.reporting.summary import result_summary

    res = run_diagnostic(case_03, strict=False)
    assert result_summary(res)["improvements"]
    assert "### Verbesserungspotenzial" in render_markdown(res)
