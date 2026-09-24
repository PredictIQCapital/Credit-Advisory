"""Ratio computation.

These are the ratios a German bank's rating engine looks at for a Mittelstand
exposure. Names are kept in German because that is what appears in the client's
BWA and in the conversation with their Hausbank -- an English label would create
a translation step that helps nobody.

Every ratio returns None rather than raising when its denominator is absent.
A missing ratio is information ("we could not compute Kapitaldienstfaehigkeit
because no facility data was supplied"), not an error to swallow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import ClientCase


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator is None or abs(denominator) < 1e-9:
        return None
    return numerator / denominator


@dataclass
class RatioSet:
    """Computed ratios for one case. All values are decimals, not percents."""

    # Capital structure
    eigenkapitalquote: Optional[float] = None
    eigenkapitalquote_bilanziell: Optional[float] = None
    anlagendeckungsgrad_ii: Optional[float] = None

    # Debt capacity
    dynamischer_verschuldungsgrad: Optional[float] = None   # net debt / EBITDA
    kapitaldienstfaehigkeit: Optional[float] = None         # DSCR, existing
    kapitaldienstfaehigkeit_inkl_neu: Optional[float] = None  # DSCR incl. new
    zinsdeckungsgrad: Optional[float] = None                # EBIT / interest

    # Profitability
    ebitda_marge: Optional[float] = None
    ebit_marge: Optional[float] = None
    umsatzrendite_vor_steuern: Optional[float] = None   # EBT / revenue, Bundesbank definition
    gesamtkapitalrentabilitaet: Optional[float] = None
    gesamtkapitalrentabilitaet_bbk: Optional[float] = None  # (JU + Zins) / BS
    umsatzwachstum: Optional[float] = None

    # Liquidity / working capital
    liquiditaet_2_grades: Optional[float] = None
    liquiditaet_3_grades: Optional[float] = None
    working_capital: Optional[float] = None
    debitorenlaufzeit_tage: Optional[float] = None
    kreditorenlaufzeit_tage: Optional[float] = None
    vorratsreichweite_tage: Optional[float] = None
    cash_conversion_cycle_tage: Optional[float] = None

    # Absolute figures carried forward for reporting
    bilanzsumme: float = 0.0
    umsatz: float = 0.0
    ebitda: float = 0.0
    ebit: float = 0.0
    wirtschaftliches_eigenkapital: float = 0.0
    nettofinanzverbindlichkeiten: float = 0.0
    kapitaldienst: float = 0.0
    kontokorrent_auslastung: Optional[float] = None

    def as_dict(self) -> dict[str, Optional[float]]:
        return {k: v for k, v in self.__dict__.items()}


def compute_ratios(case: ClientCase) -> RatioSet:
    """Compute the full ratio set for a case.

    Partial-year income statements are annualised before any ratio that mixes a
    flow (GuV) with a stock (Bilanz), which is the single most common arithmetic
    mistake when working from a mid-year BWA.
    """
    bs = case.balance_sheet
    gu = case.income_statement

    # Annualise flows so flow/stock ratios compare like with like.
    umsatz = gu.annualised(gu.umsatzerloese)
    ebitda = gu.annualised(gu.ebitda)
    ebit = gu.annualised(gu.ebit)
    zinsaufwand = gu.annualised(gu.zinsaufwand)
    materialaufwand = gu.annualised(gu.materialaufwand)

    r = RatioSet()

    # --- absolutes -------------------------------------------------------
    r.bilanzsumme = bs.bilanzsumme
    r.umsatz = umsatz
    r.ebitda = ebitda
    r.ebit = ebit
    r.wirtschaftliches_eigenkapital = bs.wirtschaftliches_eigenkapital
    r.nettofinanzverbindlichkeiten = bs.nettofinanzverbindlichkeiten
    r.kapitaldienst = case.kapitaldienst
    r.kontokorrent_auslastung = bs.kontokorrent_auslastung

    # --- capital structure ----------------------------------------------
    r.eigenkapitalquote = _safe_div(bs.wirtschaftliches_eigenkapital, bs.bilanzsumme)
    r.eigenkapitalquote_bilanziell = _safe_div(
        bs.bilanzielles_eigenkapital, bs.bilanzsumme
    )
    r.anlagendeckungsgrad_ii = _safe_div(bs.langfristiges_kapital, bs.anlagevermoegen)

    # --- debt capacity ---------------------------------------------------
    # Net debt / EBITDA is meaningless (and misleadingly flattering) when EBITDA
    # is zero or negative, so it stays None and the scorecard handles the gap.
    if ebitda > 0:
        r.dynamischer_verschuldungsgrad = bs.nettofinanzverbindlichkeiten / ebitda

    if case.kapitaldienst > 0:
        r.kapitaldienstfaehigkeit = ebitda / case.kapitaldienst
    kd_neu = case.kapitaldienst_inkl_neu
    if kd_neu > 0:
        r.kapitaldienstfaehigkeit_inkl_neu = ebitda / kd_neu

    r.zinsdeckungsgrad = _safe_div(ebit, zinsaufwand)

    # --- profitability ---------------------------------------------------
    r.ebitda_marge = _safe_div(ebitda, umsatz)
    r.ebit_marge = _safe_div(ebit, umsatz)
    r.umsatzrendite_vor_steuern = _safe_div(gu.annualised(gu.ebt), umsatz)
    r.gesamtkapitalrentabilitaet = _safe_div(ebit, bs.bilanzsumme)

    # Same idea, but on the Bundesbank's own definition: result AFTER tax plus
    # interest, over total assets. Kept separate from the EBIT variant above on
    # purpose -- this is the one the scorecard scores, because the published
    # quartiles are computed this way and a translation between the two would
    # be a guess about the tax charge dressed up as a calibration.
    r.gesamtkapitalrentabilitaet_bbk = _safe_div(
        gu.annualised(gu.jahresueberschuss) + zinsaufwand, bs.bilanzsumme
    )

    if case.prior_year_income:
        py = case.prior_year_income
        prior_umsatz = py.annualised(py.umsatzerloese)
        if prior_umsatz > 0:
            r.umsatzwachstum = (umsatz - prior_umsatz) / prior_umsatz

    # --- liquidity -------------------------------------------------------
    kurzfristig = bs.kurzfristige_verbindlichkeiten
    quick_assets = bs.forderungen_ll + bs.liquide_mittel + bs.wertpapiere
    r.liquiditaet_2_grades = _safe_div(quick_assets, kurzfristig)
    r.liquiditaet_3_grades = _safe_div(bs.umlaufvermoegen, kurzfristig)
    r.working_capital = bs.umlaufvermoegen - kurzfristig

    if umsatz > 0:
        r.debitorenlaufzeit_tage = bs.forderungen_ll / umsatz * 365.0
    if materialaufwand > 0:
        r.kreditorenlaufzeit_tage = bs.verb_ll / materialaufwand * 365.0
        r.vorratsreichweite_tage = bs.vorraete / materialaufwand * 365.0

    if (
        r.debitorenlaufzeit_tage is not None
        and r.kreditorenlaufzeit_tage is not None
        and r.vorratsreichweite_tage is not None
    ):
        r.cash_conversion_cycle_tage = (
            r.debitorenlaufzeit_tage
            + r.vorratsreichweite_tage
            - r.kreditorenlaufzeit_tage
        )

    return r
