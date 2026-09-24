"""Forward projection: revenue, EBITDA and debt service coverage over the loan.

WHY THIS MODULE EXISTS
======================
The scorecard looks at one balance-sheet date. A lender's real question is
whether the company can carry the new instalment in each of the coming years,
and MaRisk BTO 1.2.1 Tz. 1 asks for exactly that: the Kapitaldienstfaehigkeit
has to be assessed looking forward. sensitivity.py answers "what if things go
wrong"; this module answers the prior question, "what if things simply carry on".

METHOD
======
Deliberately small, because the input is small -- usually two annual
statements, at most three to five. With that little history, any model with
more parameters than data points is fitting noise and presenting it as
insight. So:

  * **Revenue: damped trend.** Last year's growth rate, clamped to +/-30%,
    fading geometrically by DAMPING per year (Gardner & McKenzie's damped
    trend, which does well in forecasting competitions on short, noisy
    series precisely because it neither extends a trend forever nor ignores
    it). A company that grew 12% is projected at +7%, +4%, +3%, ...
    With no prior year, revenue is held flat.
  * **EBITDA margin: average of the available years.** One good or bad year
    is not a new normal; the mean of all years supplied is the least
    presumptuous estimate.
  * **Debt service: contractual.** Existing facilities amortise as agreed and
    drop out after their maturity year; the requested loan is added as an
    annuity at the same conservative 6.5% the rest of the engine uses.

WHAT THIS IS NOT
================
Not a forecast of what will happen and not a Planrechnung -- the company's own
plan, where one exists, is the better source and the lender will read that.
It is a mechanical continuation of the past under stated assumptions, printed
next to those assumptions, so the reader can see immediately where their own
expectation differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .formatting import de
from .models import ClientCase

#: Share of last year's growth rate that survives into each following year.
DAMPING = 0.6
#: Growth rates beyond this are one-offs (acquisition, loss of a major
#: customer), not a trend to carry forward.
MAX_GROWTH = 0.30
#: Same assumed rate as ClientCase.kapitaldienst_inkl_neu.
NEW_LOAN_RATE = 0.065
DEFAULT_YEARS = 3
MAX_YEARS = 5
#: DSCR below which a year is flagged; 1.2x is the usual bank minimum.
DSCR_FLOOR = 1.2


@dataclass
class ProjectionYear:
    year: int
    umsatz: float
    ebitda: float
    kapitaldienst: float
    dscr: Optional[float]

    @property
    def below_floor(self) -> bool:
        return self.dscr is not None and self.dscr < DSCR_FLOOR


@dataclass
class Projection:
    base_year: int
    growth_start: float
    ebitda_margin: float
    history_years: int                     # annual statements the model saw
    years: list[ProjectionYear] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def min_dscr(self) -> Optional[float]:
        values = [y.dscr for y in self.years if y.dscr is not None]
        return min(values) if values else None

    @property
    def weakest_year(self) -> Optional[ProjectionYear]:
        scored = [y for y in self.years if y.dscr is not None]
        return min(scored, key=lambda y: y.dscr) if scored else None

    @property
    def years_below_floor(self) -> list[ProjectionYear]:
        return [y for y in self.years if y.below_floor]

    def as_dict(self) -> dict:
        return {
            "base_year": self.base_year,
            "growth_start": round(self.growth_start, 4),
            "ebitda_margin": round(self.ebitda_margin, 4),
            "history_years": self.history_years,
            "min_dscr": round(self.min_dscr, 2) if self.min_dscr is not None else None,
            "years": [
                {"year": y.year, "umsatz": round(y.umsatz), "ebitda": round(y.ebitda),
                 "kapitaldienst": round(y.kapitaldienst),
                 "dscr": round(y.dscr, 2) if y.dscr is not None else None}
                for y in self.years
            ],
            "assumptions": self.assumptions,
        }


def _annuity(amount: float, rate: float, years: int) -> float:
    n = max(1, years)
    return amount * (rate * (1 + rate) ** n) / ((1 + rate) ** n - 1)


def _existing_debt_service(case: ClientCase, year: int, base_year: int) -> float:
    """Contractual debt service of the existing facilities in `year`."""
    total = 0.0
    elapsed = year - base_year
    for f in case.facilities:
        if f.maturity_year is not None and year > f.maturity_year:
            continue
        # Straight-line amortisation: interest falls as the balance does.
        outstanding = max(0.0, f.outstanding - f.annual_principal_repayment * (elapsed - 1))
        principal = min(f.annual_principal_repayment, outstanding)
        total += outstanding * f.interest_rate + principal
    return total


def project(case: ClientCase, years: Optional[int] = None) -> Projection:
    """Continue the company's own numbers over the coming years."""
    gu = case.income_statement
    base_year = case.balance_sheet.period_end.year
    tenor = case.request.tenor_years if case.request else DEFAULT_YEARS
    n = max(1, min(MAX_YEARS, years or min(tenor, DEFAULT_YEARS)))

    umsatz = gu.annualised(gu.umsatzerloese)
    statements = [gu] + ([case.prior_year_income] if case.prior_year_income else [])
    margins = [
        s.annualised(s.ebitda) / s.annualised(s.umsatzerloese)
        for s in statements if s.annualised(s.umsatzerloese) > 0
    ]
    margin = sum(margins) / len(margins) if margins else 0.0

    growth = 0.0
    if case.prior_year_income:
        prior = case.prior_year_income.annualised(case.prior_year_income.umsatzerloese)
        if prior > 0:
            growth = max(-MAX_GROWTH, min(MAX_GROWTH, (umsatz - prior) / prior))

    new_loan = 0.0
    if case.request and case.request.amount > 0:
        new_loan = _annuity(case.request.amount, NEW_LOAN_RATE, case.request.tenor_years)

    result = Projection(base_year=base_year, growth_start=growth, ebitda_margin=margin,
                        history_years=len(statements))
    g = growth
    for i in range(1, n + 1):
        g = g * DAMPING
        umsatz = umsatz * (1 + g)
        ebitda = umsatz * margin
        year = base_year + i
        kd = _existing_debt_service(case, year, base_year)
        if case.request and i <= case.request.tenor_years:
            kd += new_loan
        result.years.append(ProjectionYear(
            year=year, umsatz=umsatz, ebitda=ebitda, kapitaldienst=kd,
            dscr=ebitda / kd if kd > 0 else None,
        ))

    result.assumptions = _assumptions(case, result, new_loan)
    return result


def _assumptions(case: ClientCase, p: Projection, new_loan: float) -> list[str]:
    out = []
    if case.prior_year_income:
        out.append(
            f"Umsatz: Wachstum des letzten Jahres ({de(p.growth_start * 100, 1)}%) "
            f"laeuft gedaempft aus (jedes Jahr {de(DAMPING * 100)}% des Vorjahreswerts)."
        )
    else:
        out.append("Umsatz: konstant -- ohne Vorjahresabschluss ist kein Trend erkennbar.")
    out.append(
        f"EBITDA-Marge: {de(p.ebitda_margin * 100, 1)}%, "
        + (f"Durchschnitt der {p.history_years} vorliegenden Geschaeftsjahre."
           if p.history_years > 1 else "wie im letzten Geschaeftsjahr.")
    )
    out.append("Bestehende Kredite: vertragliche Tilgung, Wegfall nach Laufzeitende.")
    if new_loan:
        out.append(
            f"Beantragter Kredit: Annuitaet {de(new_loan)} EUR p. a. "
            f"({de(NEW_LOAN_RATE * 100, 1)}% Zins, {case.request.tenor_years} Jahre)."
        )
    if p.history_years < 3:
        out.append(
            f"Nur {p.history_years} Geschaeftsjahr{'e' if p.history_years > 1 else ''} "
            "als Grundlage -- die Fortschreibung "
            "ist entsprechend grob. Eine eigene Planrechnung ist die bessere Quelle."
        )
    return out

