"""Sensitivity analysis: what happens to the band when conditions worsen.

WHY THIS MODULE EXISTS
======================
A point-in-time score computed from last year's accounts answers the wrong
question. The lender's question is not "how did this company look on 31
December" but "can it still service the debt if things go against it". Both
supervisory sources this product follows say so explicitly:

  * EBA/GL/2020/06 paragraph 131 (micro and small enterprises): institutions
    should assess "the sustainability and feasibility of the future repayment
    capacity under potential adverse conditions".
  * EBA/GL/2020/06 paragraphs 156-158 (medium-sized and large enterprises):
    institutions "should carry out a single- or multifactor sensitivity
    analysis, considering market and idiosyncratic events". Paragraph 158
    lists the events; 158(k) names a concrete figure -- "an increase in the
    interest rate by 200 basis points on all credit facilities of the
    borrower".
  * MaRisk BTO 1.2.1 Tz. 1: risks to the borrower's future asset and liquidity
    position must flow into the assessment of Kapitaldienstfaehigkeit.

So the scenarios below are not invented. 158(a) gives the revenue/margin
decline, 158(k) gives the +200bp, and 156 permits combining them.

HOW THE SHOCK IS APPLIED
========================
The mechanism follows the Deutsche Bundesbank's own published approach to
stressing a financial statement inside its credit assessment system (Technical
Paper 02/2023, "Including carbon taxation risk in Deutsche Bundesbank's ICAS",
section 5.2). That paper stresses a cost line for carbon prices; the plumbing
is identical whatever the shock is, and using a central bank's documented
method rather than inventing one is the whole point:

  1. compute the additional cost (or lost contribution) under the scenario;
  2. fund the gap from cash first, then from short-term bank borrowing;
  3. charge interest on that new borrowing at the borrower's existing average
     rate, because the interest burden is itself rating-relevant;
  4. reduce the tax charge in proportion to the reduced pre-tax result, using
     the borrower's own effective rate;
  5. carry the reduced result into equity via retained earnings;
  6. re-run every ratio on the stressed statements and re-score.

WHAT THIS IS NOT
================
It is not a forecast and not a probability. It says: on these stated
assumptions, the band moves from X to Y. The assumptions are printed next to
the result so the reader can disagree with them, which is the only honest way
to present a stress test to someone who knows their own business better than
we do.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from .models import ClientCase
from .ratios import compute_ratios
from .scorecard import Band, ScorecardResult, evaluate

# EBA/GL/2020/06 paragraph 158(k) names this figure explicitly.
#
# Worth knowing how severe that is: under the ESRB/EBA 2025 EU-wide stress test
# adverse scenario, German long-term rates rise from a 2.40% baseline to about
# 3.50% -- roughly 110 basis points. The origination guideline's 200bp is
# therefore close to double the supervisory macro shock, which is a point in
# the borrower's favour whenever a file survives it.
ZINSSCHOCK_BP = 0.02
ESRB_ZINSANSTIEG_BP = 0.011

# 158(a): "a severe but plausible decline in a borrower's revenues or profit
# margins". The guideline sets no size, so the calibration is ours -- but it is
# no longer a free choice. The ESRB/EBA 2025 adverse scenario puts German real
# GDP 7.5% below baseline cumulatively (-3.6%, -4.2%, +0.3%), with unemployment
# rising about 5 points. Firm-level revenue is more volatile than aggregate
# GDP, so a 10% decline for a single SME sits just beyond the supervisory
# aggregate rather than being invented at a round number.
UMSATZRUECKGANG = 0.10
ESRB_BIP_RUECKGANG = 0.075
VARIABLER_KOSTENANTEIL = 0.65

# Same scenario, for the collateral conversation: German commercial property
# is assumed to lose a third of its value, residential about an eighth. Not
# used in any calculation here -- the scorecard scores no collateral, by
# EBA Tz. 120 -- but it is the number to quote when a file argues from
# security rather than from cash flow.
ESRB_CRE_RUECKGANG = 0.333
ESRB_RRE_RUECKGANG = 0.128

# Fallback effective tax rate when the borrower's own rate cannot be derived
# (loss year, or no tax line). Roughly the German GmbH combined rate.
DEFAULT_STEUERSATZ = 0.30

# Fallback interest rate for newly drawn short-term borrowing when the case
# carries no facilities to average.
DEFAULT_ZINSSATZ = 0.06


@dataclass
class ScenarioResult:
    key: str
    label: str
    assumption: str
    score: float
    band: Band
    delta: float                     # score change vs base, negative = worse
    dscr: Optional[float] = None
    eigenkapitalquote: Optional[float] = None
    equity_wiped_out: bool = False

    @property
    def band_changed(self) -> bool:
        return False                 # set by analyse(), kept for API symmetry


@dataclass
class SensitivityResult:
    base_score: float
    base_band: Band
    scenarios: list[ScenarioResult] = field(default_factory=list)

    @property
    def worst(self) -> Optional[ScenarioResult]:
        return min(self.scenarios, key=lambda s: s.score) if self.scenarios else None

    @property
    def is_resilient(self) -> bool:
        """True when no scenario pushes the case below the 'financeable' line.

        Band C is where files start getting declined or mispriced, so holding
        at B or better under every scenario is the meaningful test.
        """
        worst = self.worst
        return worst is not None and worst.band in (Band.A, Band.B)


def _effective_tax_rate(case: ClientCase) -> float:
    g = case.income_statement
    vorsteuer = g.jahresueberschuss + g.steuern
    if vorsteuer <= 0 or g.steuern <= 0:
        return DEFAULT_STEUERSATZ
    rate = g.steuern / vorsteuer
    # Guard against implausible rates from one-off effects, as the Bundesbank
    # paper does ("we use several checks to ensure that no implausible values
    # are used").
    return min(max(rate, 0.0), 0.50)


def _average_interest_rate(case: ClientCase) -> float:
    debt = sum(f.outstanding for f in case.facilities)
    if debt <= 0:
        return DEFAULT_ZINSSATZ
    weighted = sum(f.outstanding * f.interest_rate for f in case.facilities)
    rate = weighted / debt
    return rate if rate > 0 else DEFAULT_ZINSSATZ


def _settle(stressed: ClientCase, pretax_hit: float, tax_rate: float) -> ClientCase:
    """Work a pre-tax hit -- already booked in the P&L -- through to equity.

    Steps 3-6 of the Bundesbank ICAS mechanism. The caller has already moved
    whichever P&L lines the scenario touches, so the operating result has
    changed on its own; what is left is tax, funding and equity.
    """
    g = stressed.income_statement
    b = stressed.balance_sheet

    steuerersparnis = pretax_hit * tax_rate
    g.steuern = max(0.0, g.steuern - steuerersparnis)
    nach_steuern = pretax_hit - steuerersparnis

    # Funding: cash first, then a short-term bank line (Bundesbank ICAS 5.2).
    aus_liquiditaet = min(max(b.liquide_mittel, 0.0), nach_steuern)
    b.liquide_mittel -= aus_liquiditaet
    b.verb_kreditinstitute_kurz += nach_steuern - aus_liquiditaet

    # The loss reduces equity through the result carried in the balance sheet.
    # The P&L result is a derived property and has moved already.
    b.jahresueberschuss -= nach_steuern

    return stressed


def _revenue_shock(case: ClientCase) -> ClientCase:
    """A revenue decline with only the variable share of costs following it."""
    tax_rate = _effective_tax_rate(case)
    stressed = copy.deepcopy(case)
    sg = stressed.income_statement

    umsatzverlust = sg.umsatzerloese * UMSATZRUECKGANG
    # Variable costs can only fall as far as they exist. A consultancy carries
    # almost no Materialaufwand, so for it a revenue decline is very nearly a
    # contribution decline -- which is exactly right, and falls out of the cap
    # rather than needing a separate rule.
    ersparnis = min(umsatzverlust * VARIABLER_KOSTENANTEIL, max(sg.materialaufwand, 0.0))

    sg.umsatzerloese -= umsatzverlust
    sg.materialaufwand -= ersparnis

    return _settle(stressed, umsatzverlust - ersparnis, tax_rate)


def _rate_shock(case: ClientCase) -> ClientCase:
    """EBA 158(k): +200bp on all of the borrower's credit facilities.

    The guideline repriced the *facilities*, not just the interest line, and
    that distinction is the whole point: debt service is what the DSCR divides
    by, so a shock that only touched the P&L would leave the ratio the lender
    actually tests completely unmoved.
    """
    tax_rate = _effective_tax_rate(case)
    stressed = copy.deepcopy(case)

    if stressed.facilities:
        for facility in stressed.facilities:
            facility.interest_rate += ZINSSCHOCK_BP
        basis = sum(f.outstanding for f in stressed.facilities)
    else:
        # No facility schedule: the DSCR cannot move, but the profit and
        # equity effect still can, so take the balance sheet's bank debt.
        b = stressed.balance_sheet
        basis = b.verb_kreditinstitute_kurz + b.verb_kreditinstitute_lang

    mehrzins = max(basis, 0.0) * ZINSSCHOCK_BP
    stressed.income_statement.zinsaufwand += mehrzins

    return _settle(stressed, mehrzins, tax_rate)


def _combined_shock(case: ClientCase) -> ClientCase:
    return _rate_shock(_revenue_shock(case))


SCENARIOS = (
    (
        "zinsschock",
        "Zinsanstieg +200 Basispunkte",
        "Alle Kreditlinien verteuern sich um 2,00 Prozentpunkte "
        "(EBA/GL/2020/06 Tz. 158 k). Zum Vergleich: im adversen Szenario des "
        "EU-weiten Stresstests 2025 steigen die deutschen Langfristzinsen um "
        "rund 1,1 Prozentpunkte - hier wird also haerter gerechnet.",
        _rate_shock,
    ),
    (
        "umsatzrueckgang",
        "Umsatzrueckgang 10%",
        "Umsatz -10%, davon 65% variable Kosten, die mitgehen; "
        "Fixkosten bleiben (EBA/GL/2020/06 Tz. 158 a). Groessenordnung "
        "angelehnt an das adverse Szenario des EU-weiten Stresstests 2025, "
        "das fuer Deutschland ein kumuliert 7,5% niedrigeres BIP unterstellt.",
        _revenue_shock,
    ),
    (
        "kombiniert",
        "Kombiniert: Umsatz -10% und Zins +200 bp",
        "Beide Ereignisse gleichzeitig (EBA/GL/2020/06 Tz. 156 laesst die "
        "Mehrfaktor-Betrachtung ausdruecklich zu).",
        _combined_shock,
    ),
)


def analyse(case: ClientCase, base: Optional[ScorecardResult] = None) -> SensitivityResult:
    """Run every scenario and report how far the band moves."""
    if base is None:
        base = evaluate(case, compute_ratios(case))

    result = SensitivityResult(base_score=base.total_score, base_band=base.band)

    for key, label, assumption, shock in SCENARIOS:
        stressed_case = shock(case)
        stressed_ratios = compute_ratios(stressed_case)
        stressed_score = evaluate(stressed_case, stressed_ratios)
        result.scenarios.append(
            ScenarioResult(
                key=key,
                label=label,
                assumption=assumption,
                score=stressed_score.total_score,
                band=stressed_score.band,
                delta=round(stressed_score.total_score - base.total_score, 1),
                dscr=stressed_ratios.kapitaldienstfaehigkeit_inkl_neu,
                eigenkapitalquote=stressed_ratios.eigenkapitalquote,
                equity_wiped_out=stressed_ratios.wirtschaftliches_eigenkapital <= 0,
            )
        )

    return result
