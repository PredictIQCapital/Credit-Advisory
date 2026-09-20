"""Scorecard mechanics: interpolation, banding, weight renormalisation."""

from __future__ import annotations

import pytest

from credit_readiness import benchmarks
from credit_readiness.ratios import compute_ratios
from credit_readiness.scorecard import (
    FACTORS,
    FACTORS_BY_KEY,
    Band,
    band_for,
    evaluate,
    interpolate,
    payment_behaviour_index,
)


def test_factor_weights_sum_to_one():
    assert sum(f.weight for f in FACTORS) == pytest.approx(1.0)


def test_factor_breakpoints_are_sorted():
    """An unsorted breakpoint table silently produces wrong scores."""
    for f in FACTORS:
        xs = [x for x, _ in f.breakpoints]
        assert xs == sorted(xs), f"{f.key} breakpoints not ascending"


def test_interpolate_clamps_at_both_ends():
    bp = ((0.0, 0.0), (1.0, 100.0))
    assert interpolate(-5.0, bp) == 0.0
    assert interpolate(99.0, bp) == 100.0


def test_interpolate_is_linear_between_points():
    bp = ((0.0, 0.0), (1.0, 100.0))
    assert interpolate(0.25, bp) == pytest.approx(25.0)
    assert interpolate(0.5, bp) == pytest.approx(50.0)


def test_band_boundaries():
    assert band_for(78.0) is Band.A
    assert band_for(77.9) is Band.B
    assert band_for(65.0) is Band.B
    assert band_for(64.9) is Band.C
    assert band_for(52.0) is Band.C
    assert band_for(37.9) is Band.E
    assert band_for(0.0) is Band.E


def test_every_band_has_an_interpretation():
    for band in Band:
        assert band.interpretation


def test_payment_index_penalties():
    from credit_readiness.models import BehavioralData, ClientCase

    class _Stub:
        pass

    case = _Stub()
    case.behavior = BehavioralData()
    assert payment_behaviour_index(case) == 100.0

    case.behavior = BehavioralData(tax_arrears=True)
    assert payment_behaviour_index(case) == 70.0

    case.behavior = BehavioralData(days_beyond_terms=40, returned_direct_debits_12m=5)
    # -min(45, 100) = -45, -min(30, 60) = -30  ->  25
    assert payment_behaviour_index(case) == 25.0

    case.behavior = BehavioralData(
        days_beyond_terms=100, returned_direct_debits_12m=10, tax_arrears=True
    )
    assert payment_behaviour_index(case) == 0.0  # floored, never negative


def test_missing_factors_renormalise_weights(minimal_case):
    """A thin file must not be punished for data it simply has not supplied."""
    minimal_case.behavior.creditreform_bonitaetsindex = None
    result = evaluate(minimal_case, compute_ratios(minimal_case))

    missing = {f.key for f in result.missing_factors}
    assert "creditreform_bonitaetsindex" in missing
    assert result.coverage < 1.0

    applied = sum(f.weight for f in result.factors if f.score is not None)
    assert applied == pytest.approx(1.0), "renormalised weights must still sum to 1"


def test_score_is_bounded(case_01, case_03, case_06):
    for case in (case_01, case_03, case_06):
        result = evaluate(case, compute_ratios(case))
        assert 0.0 <= result.total_score <= 100.0


def test_negative_ebitda_scores_leverage_at_zero_not_skipped():
    """Dropping the factor would flatter a distressed borrower. It must be scored 0."""
    from datetime import date

    from credit_readiness.models import (
        BalanceSheet,
        ClientCase,
        CompanyProfile,
        IncomeStatement,
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
    result = evaluate(case, compute_ratios(case))
    leverage = result.factor("dynamischer_verschuldungsgrad")
    assert leverage.score == 0.0
    assert leverage.weight > 0


def test_ranked_weaknesses_ordered_by_points_lost(case_01):
    result = evaluate(case_01, compute_ratios(case_01))
    losses = [f.points_lost for f in result.ranked_weaknesses]
    assert losses == sorted(losses, reverse=True)


def test_strong_case_outranks_weak_case(case_03, case_06):
    weak = evaluate(case_03, compute_ratios(case_03))
    strong = evaluate(case_06, compute_ratios(case_06))
    assert strong.total_score > weak.total_score
    assert strong.band is Band.A
    assert weak.band is Band.E


# ---------------------------------------------------------------------------
# Calibration against the Bundesbank distribution
# ---------------------------------------------------------------------------

#: factor key -> (metric in the Bundesbank dataset, conversion to our unit)
CALIBRATED = {
    "eigenkapitalquote": ("eigenmittel_pct_bilanzsumme", lambda v: v / 100),
    "liquiditaet_2_grades": ("liquiditaet_2_pct", lambda v: v / 100),
    "ebit_marge": ("ergebnis_vor_steuern_pct_umsatz",
                   lambda v: v / 100 + benchmarks.EBT_TO_EBIT_ADJUSTMENT),
}
ANCHORS = {"q25": 58.0, "q50": 70.0, "q75": 82.0}


def _sme_quartile(metric: str, quartile: str) -> float:
    """All sectors, the two size classes that straddle our target segment."""
    data = benchmarks._dataset()["sectors"]["__alle__"]
    values = [data[size][metric][quartile] for size in ("2_bis_10m", "10_bis_50m")]
    return sum(values) / len(values)


@pytest.mark.parametrize("factor_key", sorted(CALIBRATED))
def test_bundesbank_anchors(factor_key):
    """The calibrated curves must still meet the published quartiles.

    This is the guard that stops the breakpoints and the Bundesbank dataset
    drifting apart: re-import a new edition and this fails until the
    breakpoints are moved with it (see the CALIBRATION note in scorecard.py).
    """
    metric, convert = CALIBRATED[factor_key]
    factor = FACTORS_BY_KEY[factor_key]
    for quartile, expected in ANCHORS.items():
        value = convert(_sme_quartile(metric, quartile))
        assert interpolate(value, factor.breakpoints) == pytest.approx(expected, abs=0.5), (
            f"{factor_key} at {quartile} ({value:.4f}) scores "
            f"{interpolate(value, factor.breakpoints):.1f}, expected {expected}"
        )


def test_median_sme_lands_in_band_b():
    """A company at the median of every calibrated factor is a typical one.

    Typical must not read as borderline: that is the whole point of anchoring
    the median at band B rather than at the midpoint of the scale.
    """
    assert band_for(ANCHORS["q50"]) is Band.B
    assert band_for(ANCHORS["q25"]) is Band.C
    assert band_for(ANCHORS["q75"]) is Band.A


def test_uncalibrated_factors_are_declared_as_such():
    """Anything not in CALIBRATED is convention, and the module says so."""
    import credit_readiness.scorecard as sc

    assert "Convention, not calibration" in sc.__doc__
    for key in CALIBRATED:
        assert "Bundesbank" in FACTORS_BY_KEY[key].note, f"{key} does not name its source"
