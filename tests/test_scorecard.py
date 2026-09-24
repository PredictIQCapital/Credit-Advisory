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
ANCHORS = {"q25": 58.0, "q50": 70.0, "q75": 82.0}
# For a "lower is better" ratio the good end is the 25th percentile, so the
# anchors run the other way. kreditorenlaufzeit_tage is the only such factor.
ANCHORS_INVERSE = {"q25": 82.0, "q50": 70.0, "q75": 58.0}

CALIBRATED = {
    "eigenkapitalquote": ("eigenmittel_pct_bilanzsumme", lambda v: v / 100, ANCHORS),
    "liquiditaet_2_grades": ("liquiditaet_2_pct", lambda v: v / 100, ANCHORS),
    "ebit_marge": ("ergebnis_vor_steuern_pct_umsatz",
                   lambda v: v / 100 + benchmarks.EBT_TO_EBIT_ADJUSTMENT, ANCHORS),
    # Added in the EBA/Bundesbank calibration round. These three need no
    # translation at all: our definition and the published one are the same.
    "gesamtkapitalrentabilitaet_bbk": ("ergebnis_plus_zins_pct_bilanzsumme",
                                       lambda v: v / 100, ANCHORS),
    "anlagendeckungsgrad_ii": ("langfr_kapital_pct_anlagevermoegen",
                               lambda v: v / 100, ANCHORS),
    "kreditorenlaufzeit_tage": ("verb_ll_pct_materialaufwand",
                                lambda v: v * 365 / 100, ANCHORS_INVERSE),
}


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
    metric, convert, anchors = CALIBRATED[factor_key]
    factor = FACTORS_BY_KEY[factor_key]
    for quartile, expected in anchors.items():
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


# ---------------------------------------------------------------------------
# Sector-specific curves (ADR-005)
# ---------------------------------------------------------------------------

from credit_readiness.models import Sector  # noqa: E402
from credit_readiness.scorecard import (  # noqa: E402
    ANCHOR_SCORES,
    CALIBRATION,
    GENERIC_BASIS,
    curve_for,
)


def test_calibration_table_matches_the_generic_anchor_tests():
    """CALIBRATION drives the sector curves; CALIBRATED above checks the generic
    ones. They must name the same factors and the same Bundesbank metrics."""
    assert {k: v[0] for k, v in CALIBRATION.items()} == {k: v[0] for k, v in CALIBRATED.items()}


@pytest.mark.parametrize("sector", list(Sector))
@pytest.mark.parametrize("factor_key", sorted(CALIBRATION))
@pytest.mark.parametrize("revenue", [1_500_000, 5_000_000, 20_000_000])
def test_sector_curve_meets_the_sector_quartiles(sector, factor_key, revenue):
    """Every sector curve puts q25/median/q75 of its own cell at 58/70/82
    (inverted for lower-is-better) and stays sorted."""
    fd = FACTORS_BY_KEY[factor_key]
    curve = curve_for(fd, sector, revenue)
    xs = [x for x, _ in curve.breakpoints]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)

    found = benchmarks.sector_cell(CALIBRATION[factor_key][0], sector, revenue)
    if found is None:
        assert curve.basis == GENERIC_BASIS
        return
    metric, convert, higher = CALIBRATION[factor_key]
    cell, _ = found
    expected = ANCHOR_SCORES if higher else ANCHOR_SCORES[::-1]
    for q, score in zip(("q25", "q50", "q75"), expected):
        assert interpolate(convert(cell[q]), curve.breakpoints) == pytest.approx(score)
    assert sector.value in curve.basis


@pytest.mark.parametrize("sector", list(Sector))
@pytest.mark.parametrize("factor_key", sorted(CALIBRATION))
def test_sector_curve_is_monotone(sector, factor_key):
    """More equity never scores lower; more supplier days never score higher."""
    fd = FACTORS_BY_KEY[factor_key]
    ys = [y for _, y in curve_for(fd, sector, 5_000_000).breakpoints]
    higher = CALIBRATION[factor_key][2]
    assert ys == (sorted(ys) if higher else sorted(ys, reverse=True))


def test_repayment_factors_never_move_with_the_sector():
    """DSCR, leverage and interest cover measure repayment, not typicality."""
    for key in ("kapitaldienstfaehigkeit_inkl_neu", "dynamischer_verschuldungsgrad",
                "zinsdeckungsgrad"):
        fd = FACTORS_BY_KEY[key]
        for sector in Sector:
            curve = curve_for(fd, sector, 5_000_000)
            assert curve.breakpoints == fd.breakpoints
            assert curve.basis == GENERIC_BASIS


def test_weak_tail_stays_absolute():
    """Zero equity scores the same in every sector: a weak sector does not make
    insolvency less likely."""
    fd = FACTORS_BY_KEY["eigenkapitalquote"]
    generic = interpolate(0.0, fd.breakpoints)
    for sector in Sector:
        assert interpolate(0.0, curve_for(fd, sector, 5_000_000).breakpoints) == generic


def test_median_retailer_is_typical_not_borderline():
    """The case that motivated ADR-005: a retailer at the retail median equity
    ratio scores at the median anchor on the sector curve."""
    fd = FACTORS_BY_KEY["eigenkapitalquote"]
    cell, _ = benchmarks.sector_cell("eigenmittel_pct_bilanzsumme", Sector.RETAIL, 5_000_000)
    median = cell["q50"] / 100
    assert interpolate(median, fd.breakpoints) < 65.0            # generic: borderline-ish
    assert interpolate(median, curve_for(fd, Sector.RETAIL, 5_000_000).breakpoints) == \
        pytest.approx(70.0)


def test_generic_score_available_alongside_sector_score(case_01):
    ratios = compute_ratios(case_01)
    sector = evaluate(case_01, ratios)
    generic = evaluate(case_01, ratios, sector_specific=False)
    assert sector.sector_specific and not generic.sector_specific
    assert generic.basis_label == GENERIC_BASIS
    assert all(f.basis == GENERIC_BASIS for f in generic.factors)
    assert sector.total_score != generic.total_score


def test_missing_sector_cell_falls_back_to_the_generic_curve(monkeypatch):
    monkeypatch.setattr(benchmarks, "sector_cell", lambda *a, **k: None)
    fd = FACTORS_BY_KEY["eigenkapitalquote"]
    curve = curve_for(fd, Sector.RETAIL, 5_000_000)
    assert curve.breakpoints == fd.breakpoints
    assert curve.basis == GENERIC_BASIS
    assert "Standardkurve" in curve.note
