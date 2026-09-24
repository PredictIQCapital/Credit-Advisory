"""Improvement potential: which ratios are worth working on, and by how much.

WHY THIS MODULE EXISTS
======================
The scorecard ranks factors by points lost against a perfect 100. That answers
"what costs the most", but not "what is worth fixing": no company reaches 100
on everything, and a factor with a big loss may be one the owner cannot move.
A rejected or weak applicant needs a different list: for each ratio, how far it
is from what is normal in its own sector, what closing that gap would add to the
score, and what the gap means in euros on its own balance sheet.

The three inputs the product spec names map one-to-one:

  * **weight in the scoring model** -- the gain is weighted exactly as the
    scorecard weights it, so the list adds up to the score;
  * **sector norms** -- the target is the value at which the factor scores 70,
    the median anchor. For the calibrated factors on sector curves that *is*
    the sector median (ADR-005); for the others it is the conventional line
    between "typical" and "weak";
  * **the applicant's own statements** -- the gap is translated into euros
    from the balance sheet and P&L: equity to add, debt to reduce, EBITDA to
    find.

The euro figures hold everything else constant. They say how big the gap is,
not how to close it; remediation.py holds the rules for that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .models import ClientCase
from .ratios import RatioSet
from .scorecard import (
    ANCHOR_SCORES,
    BAND_THRESHOLDS,
    FACTORS_BY_KEY,
    Band,
    FactorScore,
    ScorecardResult,
    curve_for,
)

#: Score of a typical company in the sector: the median anchor.
TARGET_SCORE = ANCHOR_SCORES[1]


def inverse(target: float, breakpoints: Sequence[tuple[float, float]]) -> Optional[float]:
    """The input value at which the curve first reaches `target` points.

    Works for rising and falling curves; None when the curve never reaches it.
    """
    for (x0, y0), (x1, y1) in zip(breakpoints, breakpoints[1:]):
        lo, hi = min(y0, y1), max(y0, y1)
        if lo <= target <= hi and y0 != y1:
            return x0 + (target - y0) / (y1 - y0) * (x1 - x0)
    return None


@dataclass
class Improvement:
    key: str
    label: str
    current: Optional[float]
    target: Optional[float]
    current_score: float
    points_gain: float              # weighted, in total-score points
    euro_gap: Optional[float]       # size of the gap on this balance sheet
    lever: str                      # what the euro figure means

    def format(self, value: Optional[float]) -> str:
        fd = FACTORS_BY_KEY[self.key]
        return FactorScore(self.key, self.label, value, None, 0, 0, fd.unit).format_value()


@dataclass
class ImprovementPlan:
    score: float
    band: Band
    items: list[Improvement]

    @property
    def next_band(self) -> Optional[tuple[float, Band]]:
        better = [(t, b) for t, b in BAND_THRESHOLDS if t > self.score]
        return min(better, key=lambda tb: tb[0]) if better else None

    @property
    def points_to_next_band(self) -> Optional[float]:
        nb = self.next_band
        return nb[0] - self.score if nb else None

    def reaching_next_band(self) -> list[Improvement]:
        """The fewest items, largest gain first, that together close the gap."""
        need = self.points_to_next_band
        if need is None:
            return []
        chosen, total = [], 0.0
        for item in self.items:
            chosen.append(item)
            total += item.points_gain
            if total >= need:
                return chosen
        return []                     # the ratios alone cannot close it


def _euro_gap(key: str, target: float, case: ClientCase, r: RatioSet) -> tuple[Optional[float], str]:
    bs, gu = case.balance_sheet, case.income_statement
    if key == "eigenkapitalquote":
        return (target * bs.bilanzsumme - bs.wirtschaftliches_eigenkapital,
                "zusaetzliches wirtschaftliches Eigenkapital (z. B. Rangruecktritt, Einlage)")
    if key == "kapitaldienstfaehigkeit_inkl_neu" and case.kapitaldienst_inkl_neu > 0:
        return (target * case.kapitaldienst_inkl_neu - r.ebitda,
                "zusaetzliches EBITDA p. a. -- oder entsprechend geringerer Kapitaldienst")
    if key == "dynamischer_verschuldungsgrad":
        if r.ebitda <= 0:
            return None, "erst ein positives EBITDA macht die Verschuldung tragbar"
        return (r.nettofinanzverbindlichkeiten - target * r.ebitda,
                "Abbau der Nettofinanzverschuldung")
    if key == "ebit_marge" and r.umsatz > 0:
        return (target * r.umsatz - r.ebit, "zusaetzliches EBIT p. a.")
    if key == "liquiditaet_2_grades":
        quick = bs.forderungen_ll + bs.liquide_mittel + bs.wertpapiere
        return (target * bs.kurzfristige_verbindlichkeiten - quick,
                "mehr liquide Mittel/Forderungen -- oder weniger kurzfristige Verbindlichkeiten")
    if key == "anlagendeckungsgrad_ii":
        return (target * bs.anlagevermoegen - bs.langfristiges_kapital,
                "Umschichtung kurzfristiger in langfristige Finanzierung")
    if key == "kontokorrent_auslastung" and bs.kontokorrent_limit:
        return ((r.kontokorrent_auslastung - target) * bs.kontokorrent_limit,
                "geringere Inanspruchnahme des Kontokorrents")
    if key == "kreditorenlaufzeit_tage":
        material = gu.annualised(gu.materialaufwand)
        return ((r.kreditorenlaufzeit_tage - target) / 365.0 * material,
                "Abbau der Lieferantenverbindlichkeiten")
    if key == "gesamtkapitalrentabilitaet_bbk":
        return (target * bs.bilanzsumme - (gu.annualised(gu.jahresueberschuss)
                                           + gu.annualised(gu.zinsaufwand)),
                "zusaetzliches Ergebnis vor Zinsen p. a.")
    return None, {
        "bwa_age_months": "aktuellere BWA vorlegen",
        "creditreform_bonitaetsindex": "Auskunft pruefen und Fehler korrigieren lassen",
        "zahlungsverhalten": "Zahlungsziele einhalten, Ruecklastschriften vermeiden",
        "zinsdeckungsgrad": "hoeheres EBIT oder geringerer Zinsaufwand",
    }.get(key, "")


def plan(case: ClientCase, ratios: RatioSet, card: ScorecardResult) -> ImprovementPlan:
    """Rank the factors by what reaching the sector-typical level would add."""
    items: list[Improvement] = []
    for f in card.factors:
        if f.score is None or f.score >= TARGET_SCORE:
            continue
        fd = FACTORS_BY_KEY[f.key]
        curve = curve_for(fd, card.sector, ratios.umsatz)
        target = inverse(TARGET_SCORE, curve.breakpoints)
        gap, lever = (None, "")
        if target is not None:
            gap, lever = _euro_gap(f.key, target, case, ratios)
            if gap is not None and gap <= 0:
                gap = None
        items.append(Improvement(
            key=f.key, label=f.label, current=f.value, target=target,
            current_score=f.score,
            points_gain=f.weight * (TARGET_SCORE - f.score),
            euro_gap=gap, lever=lever,
        ))
    items.sort(key=lambda i: i.points_gain, reverse=True)
    return ImprovementPlan(card.total_score, card.band, items)

