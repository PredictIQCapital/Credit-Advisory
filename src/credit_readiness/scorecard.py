"""Transparent rules-and-ratios scorecard.

REGULATORY GUARDRAIL -- read before changing anything here.

This module produces a *directional readiness indication*, not a credit rating
and not a probability of default. That distinction is what keeps the business on
the advisory side of the EU CRA Regulation line (see docs/regulatory-guardrails.md).
Three rules follow from it, and they are enforced in code, not just in prose:

  1. No output is ever labelled a rating, a score in basis points, or a PD.
     The vocabulary is "readiness band" and "indicative".
  2. Every number is traceable: each factor exposes its raw value, its
     breakpoints, its weight, and the points it cost. Nothing is a black box.
  3. No machine-learned component. Piecewise-linear interpolation over published
     thresholds only, so any output can be defended to a client or their
     Steuerberater line by line.

REGULATORY BASIS
================
The factor set is mapped to two supervisory sources, and the mapping is the
answer to "why these ratios and not others":

  * **EBA/GL/2020/06** (Guidelines on loan origination and monitoring),
    Annex 3 section B -- the metrics a lender is expected to consider when
    assessing an enterprise. Covered here: equity ratio (6), EBITDA (8),
    interest-bearing debt/EBITDA (10), total debt service coverage (14),
    current-asset coverage (16), return on assets (18), debt service (19),
    interest coverage (21), net profit margin (24).
  * **Bundesbank credit assessment system (ICAS)**, ratio table, December 2023
    -- the ratios a central bank actually uses to estimate a German SME's PD
    from HGB accounts. Covered here: EBITDA, adjusted total debt ratio,
    liquidity, return on sales, debt repayment capability, adjusted equity
    ratio, accounts payable turnover in days.

Neither source publishes threshold *values*. EBA Annex 1 requires an institution
to define "acceptable ... ratio limits" but leaves the numbers to the
institution; MaRisk BTO 1.2 prescribes process, not figures. So the metric set
comes from the regulators and the thresholds come from the Bundesbank
distribution -- the two are separate decisions and are documented separately.

Two supervisory requirements shape the design beyond the factor list.
MaRisk BTO 1.2.1 Tz. 1 puts Kapitaldienstfaehigkeit under "besondere
Beruecksichtigung", which is why the DSCR carries the single largest weight.
EBA paragraph 120 says collateral must not be a predominant criterion, which is
why no factor here scores collateral at all.

Left deliberately unscored: EBA Annex 3 metrics 9, 11, 12, 20 and 22 (debt
yield, enterprise value, capitalisation rate, loan-to-cost, return on equity)
are either real-estate/listed-company measures or -- in the case of return on
equity -- unstable to the point of being misleading for owner-managed firms with
thin or negative book equity, which is a large part of this segment.

CALIBRATION
===========
Two kinds of factor live in this file, and the difference matters when someone
asks where a number comes from.

**Calibrated against published data** -- eigenkapitalquote, ebit_marge,
liquiditaet_2_grades, gesamtkapitalrentabilitaet_bbk, anlagendeckungsgrad_ii,
kreditorenlaufzeit_tage. Their breakpoints are anchored to the firm-level quartiles
of the Deutsche Bundesbank Jahresabschlussstatistik (Verhaeltniszahlen), all
sectors, the 2-10M and 10-50M EUR revenue classes averaged, latest reporting
year. See benchmarks.py for the dataset and its caveats.

The anchor points are 25th percentile -> 58, median -> 70, 75th percentile -> 82,
and the reasoning is one step long: the ECB SAFE survey puts roughly 14% of
applicants in significant difficulty, so a company at the median of its size
class should land in band B ("financeable, terms improvable"), the lower
quartile in band C ("borderline"), and the upper quartile at the band A line.
Percentile anchoring alone would put the median firm at 50 points, which would
wrongly imply that half of German SMEs are borderline cases.

Tails beyond the published quartiles stay conventional: the distribution gives
three points, not a distribution, so the ends are drawn to economically
meaningful limits (zero equity, negative margin) rather than extrapolated.

Three of the six are calibrated without any translation step, because the
Bundesbank's definition and ours are identical: anlagendeckungsgrad_ii is its
"langfristig verfuegbares Kapital / Anlagevermoegen", kreditorenlaufzeit_tage is
its "Verbindlichkeiten aus LuL / Materialaufwand", and for return on assets we
adopted the published definition (result after tax plus interest) rather than
bending the EBIT variant onto it -- see ratios.py, where both live side by side.
kreditorenlaufzeit_tage is also the one calibrated factor whose curve is capped
below 100: paying suppliers quickly is the absence of a warning sign, not
evidence of strength, so its best attainable score is the upper-quartile anchor.

**Direction matters.** For "lower is better" ratios the anchors invert -- the
25th percentile is the good end. kreditorenlaufzeit_tage is the only such
factor here (q25 -> 82, median -> 70, q75 -> 58).

**Convention, not calibration** -- everything else. The publication carries no
comparable series for debt service capacity, overdraft utilisation, reporting
cadence, credit-agency index or payment behaviour, and its leverage measure
(cash flow in % of total liabilities less cash) is not our net financial debt
over EBITDA: different numerator, much wider denominator. Translating one into
the other would be a guess dressed as a calibration, so those curves are
unchanged and remain the first candidates for revision once the outcome log
holds real placements.

Re-run `python scripts/import_bundesbank_ratios.py <pdf-folder>` after each new
Bundesbank edition, then check tests/test_scorecard.py::test_bundesbank_anchors,
which re-derives the anchors from the shipped dataset and fails if the
breakpoints and the data have drifted apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from .models import ClientCase
from .ratios import RatioSet
from .formatting import de


class Band(str, Enum):
    """Indicative readiness bands. NOT a credit rating."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"

    @property
    def interpretation(self) -> str:
        return {
            "A": "Voraussichtlich zu Standardkonditionen finanzierbar",
            "B": "Finanzierbar; Konditionen wahrscheinlich verbesserbar",
            "C": "Grenzfall - typische Ablehnungs- und Fehlbepreisungszone",
            "D": "Ablehnung wahrscheinlich ohne Restrukturierung oder Buergschaft",
            "E": "Substanzielle Bonitaetsschwaeche",
        }[self.value]


BAND_THRESHOLDS: list[tuple[float, Band]] = [
    (78.0, Band.A),
    (65.0, Band.B),
    (52.0, Band.C),
    (38.0, Band.D),
    (0.0, Band.E),
]


def band_for(score: float) -> Band:
    for threshold, band in BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return Band.E


def interpolate(value: float, breakpoints: Sequence[tuple[float, float]]) -> float:
    """Piecewise-linear lookup, clamped at both ends.

    `breakpoints` must be sorted ascending by input value. Returns 0-100.
    """
    if value <= breakpoints[0][0]:
        return breakpoints[0][1]
    if value >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return y1
            frac = (value - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return breakpoints[-1][1]


@dataclass(frozen=True)
class FactorDefinition:
    key: str
    label: str
    weight: float
    breakpoints: tuple[tuple[float, float], ...]
    unit: str = "ratio"        # ratio | percent | x | days | months | index
    source: str = "ratios"     # ratios | behavior | derived
    note: str = ""


# ---------------------------------------------------------------------------
# Factor definitions. Weights sum to 1.00 across all factors; when a factor
# cannot be computed, the remaining weights are renormalised (see evaluate()).
# ---------------------------------------------------------------------------

FACTORS: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        key="eigenkapitalquote",
        label="Eigenkapitalquote (wirtschaftlich)",
        weight=0.16,
        unit="percent",
        breakpoints=(
            (-0.20, 0.0), (0.0, 25.0), (0.05, 38.0),
            (0.148, 58.0), (0.351, 70.0), (0.569, 82.0),
            (0.80, 95.0), (1.00, 100.0),
        ),
        note="Wirtschaftliches EK inkl. nachrangiger Gesellschafterdarlehen. "
             "Stuetzstellen 14,8/35,1/56,9% = Quartile der Bundesbank-Statistik.",
    ),
    FactorDefinition(
        key="kapitaldienstfaehigkeit_inkl_neu",
        label="Kapitaldienstfaehigkeit inkl. neuer Finanzierung (DSCR)",
        weight=0.20,
        unit="x",
        breakpoints=(
            (0.7, 0.0), (0.9, 12.0), (1.0, 25.0), (1.1, 42.0),
            (1.2, 58.0), (1.3, 72.0), (1.5, 88.0), (2.0, 100.0),
        ),
        note="EBITDA / (Zins + Tilgung), inkl. des beantragten Engagements.",
    ),
    FactorDefinition(
        key="dynamischer_verschuldungsgrad",
        label="Dynamischer Verschuldungsgrad (Nettoverschuldung / EBITDA)",
        weight=0.11,
        unit="x",
        breakpoints=(
            (0.0, 100.0), (1.0, 95.0), (2.0, 88.0), (3.0, 75.0), (3.5, 65.0),
            (4.0, 55.0), (5.0, 38.0), (6.0, 25.0), (8.0, 10.0), (12.0, 0.0),
        ),
    ),
    FactorDefinition(
        key="ebit_marge",
        label="EBIT-Marge",
        weight=0.09,
        unit="percent",
        breakpoints=(
            (-0.10, 0.0), (-0.05, 12.0), (-0.02, 28.0), (0.0, 45.0),
            (0.0135, 58.0), (0.0475, 70.0), (0.0995, 82.0),
            (0.18, 95.0), (0.25, 100.0),
        ),
        note="Stuetzstellen 1,35/4,75/9,95% = Bundesbank-Quartile des "
             "Ergebnisses vor Steuern, um 0,5 Punkte auf EBIT-Basis angehoben.",
    ),
    FactorDefinition(
        key="liquiditaet_2_grades",
        label="Liquiditaet 2. Grades",
        weight=0.07,
        unit="percent",
        breakpoints=(
            (0.0, 0.0), (0.20, 25.0), (0.30, 40.0),
            (0.458, 58.0), (0.917, 70.0), (2.163, 82.0),
            (4.00, 95.0), (6.00, 100.0),
        ),
        note="Stuetzstellen 45,8/91,7/216,3% = Quartile der Bundesbank-Statistik.",
    ),
    FactorDefinition(
        key="zinsdeckungsgrad",
        label="Zinsdeckungsgrad (EBIT / Zinsaufwand)",
        weight=0.05,
        unit="x",
        breakpoints=(
            (0.0, 0.0), (1.0, 20.0), (1.5, 35.0), (2.0, 50.0),
            (3.0, 70.0), (5.0, 88.0), (8.0, 100.0),
        ),
    ),
    FactorDefinition(
        key="gesamtkapitalrentabilitaet_bbk",
        label="Gesamtkapitalrentabilitaet (Jahresergebnis + Zinsaufwand)",
        weight=0.05,
        unit="percent",
        breakpoints=(
            (-0.05, 0.0), (0.0, 30.0),
            (0.024, 58.0), (0.0685, 70.0), (0.1335, 82.0),
            (0.22, 95.0), (0.30, 100.0),
        ),
        note="EBA-Leitlinien Anhang 3 Nr. 18 (Return on assets). Stuetzstellen "
             "2,4/6,85/13,35% = Bundesbank-Quartile, Definition uebernommen.",
    ),
    FactorDefinition(
        key="anlagendeckungsgrad_ii",
        label="Anlagendeckungsgrad II",
        weight=0.05,
        unit="percent",
        breakpoints=(
            (0.5, 0.0), (0.8, 12.0), (1.0, 30.0),
            (1.2205, 58.0), (2.182, 70.0), (4.6445, 82.0),
            (8.0, 95.0), (12.0, 100.0),
        ),
        note="Langfristiges Kapital / Anlagevermoegen. Unter 100% ist die "
             "goldene Bilanzregel verletzt. Stuetzstellen 122,1/218,2/464,5% "
             "= Bundesbank-Quartile.",
    ),
    FactorDefinition(
        key="kreditorenlaufzeit_tage",
        label="Kreditorenlaufzeit",
        weight=0.04,
        unit="days",
        breakpoints=(
            (0.0, 82.0), (15.1, 82.0), (27.2, 70.0), (49.5, 58.0),
            (75.0, 38.0), (100.0, 20.0), (120.0, 0.0),
        ),
        note="Verb. aus LuL / Materialaufwand x 365. Zusatzkennzahl des "
             "Bundesbank-Bonitaetsanalysesystems. Gedeckelt bei 82 Punkten: "
             "schnelles Zahlen ist kein Bonitaetsbeleg, nur das Fehlen eines "
             "Warnsignals. Stuetzstellen 15,1/27,2/49,5 Tage = Quartile.",
    ),
    FactorDefinition(
        key="kontokorrent_auslastung",
        label="Kontokorrent-Auslastung",
        weight=0.05,
        unit="percent",
        source="derived",
        breakpoints=(
            (0.0, 100.0), (0.3, 92.0), (0.5, 80.0), (0.7, 62.0),
            (0.8, 45.0), (0.9, 28.0), (1.0, 10.0), (1.1, 0.0),
        ),
        note="Dauerhafte Ausschoepfung >80% gilt als klassisches Warnsignal.",
    ),
    FactorDefinition(
        key="bwa_age_months",
        label="Aktualitaet der BWA",
        weight=0.04,
        unit="months",
        source="behavior",
        breakpoints=(
            (1.0, 100.0), (2.0, 90.0), (3.0, 72.0), (4.0, 55.0),
            (6.0, 32.0), (9.0, 12.0), (12.0, 0.0),
        ),
    ),
    FactorDefinition(
        key="creditreform_bonitaetsindex",
        label="Creditreform Bonitaetsindex",
        weight=0.05,
        unit="index",
        source="behavior",
        breakpoints=(
            (100.0, 100.0), (150.0, 95.0), (200.0, 85.0), (250.0, 72.0),
            (300.0, 55.0), (350.0, 35.0), (400.0, 18.0), (500.0, 5.0),
            (600.0, 0.0),
        ),
    ),
    FactorDefinition(
        key="zahlungsverhalten",
        label="Zahlungsverhalten",
        weight=0.04,
        unit="index",
        source="derived",
        breakpoints=((0.0, 0.0), (100.0, 100.0)),
        note="Aggregat aus Zahlungsverzug, Ruecklastschriften, Steuerrueckstaenden.",
    ),
)

FACTORS_BY_KEY = {f.key: f for f in FACTORS}


def payment_behaviour_index(case: ClientCase) -> float:
    """Collapse payment signals into a 0-100 index (100 = clean).

    Weights here are judgement, not published thresholds -- flagged as such
    because this is one of the factors most in need of outcome validation.
    """
    idx = 100.0
    b = case.behavior
    idx -= min(45.0, b.days_beyond_terms * 2.5)
    idx -= min(30.0, b.returned_direct_debits_12m * 12.0)
    if b.tax_arrears:
        idx -= 30.0
    if b.overdraft_days_at_limit_12m > 60:
        idx -= 15.0
    elif b.overdraft_days_at_limit_12m > 20:
        idx -= 7.0
    return max(0.0, idx)


@dataclass
class FactorScore:
    key: str
    label: str
    value: Optional[float]
    score: Optional[float]           # 0-100, None when not computable
    weight: float                    # renormalised weight actually applied
    nominal_weight: float
    unit: str
    note: str = ""
    missing_reason: str = ""

    @property
    def points_lost(self) -> float:
        """Weighted points given up versus a perfect factor.

        This is the ranking key for 'what is hurting this file the most',
        which is the single most useful line in the whole diagnostic.
        """
        if self.score is None:
            return 0.0
        return self.weight * (100.0 - self.score)

    @property
    def contribution(self) -> float:
        if self.score is None:
            return 0.0
        return self.weight * self.score

    def format_value(self) -> str:
        if self.value is None:
            return "n/a"
        if self.unit == "percent":
            return f"{de(self.value * 100, 1)}%"
        if self.unit == "x":
            return f"{de(self.value, 2)}x"
        if self.unit in ("months", "days"):
            return f"{de(self.value, 1)}"
        if self.unit == "index":
            return f"{de(self.value)}"
        return f"{de(self.value, 2)}"


@dataclass
class ScorecardResult:
    total_score: float
    band: Band
    factors: list[FactorScore] = field(default_factory=list)
    coverage: float = 1.0            # share of nominal weight actually scored

    @property
    def ranked_weaknesses(self) -> list[FactorScore]:
        """Factors ordered by weighted points lost, worst first."""
        scored = [f for f in self.factors if f.score is not None]
        return sorted(scored, key=lambda f: f.points_lost, reverse=True)

    @property
    def missing_factors(self) -> list[FactorScore]:
        return [f for f in self.factors if f.score is None]

    def factor(self, key: str) -> Optional[FactorScore]:
        return next((f for f in self.factors if f.key == key), None)


def _raw_value(key: str, case: ClientCase, ratios: RatioSet) -> tuple[Optional[float], str]:
    """Resolve a factor's raw input value, plus a reason when unavailable."""
    if key == "zahlungsverhalten":
        return payment_behaviour_index(case), ""
    if key == "bwa_age_months":
        return case.behavior.bwa_age_months, ""
    if key == "creditreform_bonitaetsindex":
        v = case.behavior.creditreform_bonitaetsindex
        return (float(v), "") if v is not None else (None, "Keine Creditreform-Auskunft vorliegend")
    if key == "kontokorrent_auslastung":
        v = ratios.kontokorrent_auslastung
        return (v, "") if v is not None else (None, "Kein Kontokorrentlimit hinterlegt")

    v = getattr(ratios, key, None)
    if v is not None:
        return v, ""

    reasons = {
        "dynamischer_verschuldungsgrad": "EBITDA <= 0, Kennzahl nicht aussagekraeftig",
        "kapitaldienstfaehigkeit_inkl_neu": "Kein Kapitaldienst bekannt",
        "zinsdeckungsgrad": "Kein Zinsaufwand ausgewiesen",
        "anlagendeckungsgrad_ii": "Kein Anlagevermoegen ausgewiesen",
        # Dienstleister weisen haeufig keinen Materialaufwand aus; dann faellt
        # die Kennzahl weg und ihr Gewicht wird umverteilt.
        "kreditorenlaufzeit_tage": "Kein Materialaufwand ausgewiesen",
        "gesamtkapitalrentabilitaet_bbk": "Bilanzsumme oder Jahresergebnis fehlt",
    }
    return None, reasons.get(key, "Nicht berechenbar aus den vorliegenden Daten")


def evaluate(case: ClientCase, ratios: RatioSet) -> ScorecardResult:
    """Score a case against the factor set.

    Missing factors are excluded and the remaining weights renormalised, so a
    thin file is not silently punished for data the client has not supplied yet.
    The exception is a negative-EBITDA case: leaving the leverage factor out
    entirely would flatter a genuinely distressed borrower, so it is floored at
    zero rather than dropped.
    """
    raw: list[tuple[FactorDefinition, Optional[float], Optional[float], str]] = []

    for fd in FACTORS:
        value, reason = _raw_value(fd.key, case, ratios)

        if value is None and fd.key == "dynamischer_verschuldungsgrad" and ratios.ebitda <= 0:
            # Negative EBITDA cannot service debt at all: score it, do not skip it.
            raw.append((fd, None, 0.0, "EBITDA <= 0: Verschuldungsgrad mit 0 bewertet"))
            continue

        if value is None:
            raw.append((fd, None, None, reason))
            continue

        raw.append((fd, value, interpolate(value, fd.breakpoints), ""))

    scorable_weight = sum(fd.weight for fd, _, s, _ in raw if s is not None)
    nominal_total = sum(fd.weight for fd in FACTORS)
    renorm = (nominal_total / scorable_weight) if scorable_weight > 0 else 0.0

    factors: list[FactorScore] = []
    for fd, value, score, reason in raw:
        applied_weight = fd.weight * renorm if score is not None else 0.0
        factors.append(
            FactorScore(
                key=fd.key,
                label=fd.label,
                value=value,
                score=score,
                weight=applied_weight,
                nominal_weight=fd.weight,
                unit=fd.unit,
                note=fd.note,
                missing_reason=reason if score is None else "",
            )
        )

    total = sum(f.contribution for f in factors)
    return ScorecardResult(
        total_score=round(total, 1),
        band=band_for(total),
        factors=factors,
        coverage=round(scorable_weight / nominal_total, 3) if nominal_total else 0.0,
    )
