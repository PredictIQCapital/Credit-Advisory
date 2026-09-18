"""Lender-fit matching.

Routes a (corrected) profile to the lender types most likely to approve it.

Scope limit, deliberate: this ranks lender *types*, not named institutions, and
it produces a recommendation, never a placement. The moment a success fee is
earned for placing a loan, 34c GewO (Kreditvermittlung) plausibly applies --
see docs/regulatory-guardrails.md. Keeping this module at the level of
"which kind of lender, and why" is what lets the diagnostic be sold standalone.

Criteria below are drawn from publicly stated programme conditions and
conventional underwriting practice. They change -- KfW Merkblaetter in
particular -- and must be re-checked before any client recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import ClientCase
from .ratios import RatioSet
from .scorecard import ScorecardResult


@dataclass(frozen=True)
class LenderProfile:
    key: str
    name: str
    description: str
    min_band: str                  # worst acceptable readiness band
    min_dscr: float
    min_equity_ratio: float
    amount_min: float
    amount_max: float
    typical_weeks: int
    indicative_cost: str
    purposes: tuple[str, ...]      # empty = any
    notes: str = ""


LENDERS: tuple[LenderProfile, ...] = (
    LenderProfile(
        key="hausbank",
        name="Hausbank (Sparkasse / Volksbank)",
        description="Klassischer Betriebsmittel- oder Investitionskredit.",
        min_band="C",
        min_dscr=1.20,
        min_equity_ratio=0.12,
        amount_min=25_000,
        amount_max=5_000_000,
        typical_weeks=8,
        indicative_cost="guenstigste Kondition bei ausreichender Bonitaet",
        purposes=(),
        notes=(
            "Erste Adresse, wenn Kennzahlen und Sicherheiten tragen. Bestehende "
            "Kontoverbindung und Kennntnis des Hauses wirken real preisbildend."
        ),
    ),
    LenderProfile(
        key="kfw_haftungsfreistellung",
        name="KfW-Programm mit Haftungsfreistellung (ueber die Hausbank)",
        description=(
            "Foerderkredit, bei dem die KfW die Hausbank teilweise vom Risiko "
            "freistellt. Adressiert Besicherungsluecken, nicht Ertragsschwaeche."
        ),
        min_band="D",
        min_dscr=1.10,
        min_equity_ratio=0.05,
        amount_min=25_000,
        amount_max=25_000_000,
        typical_weeks=12,
        indicative_cost="zinsguenstig, aber laengere Bearbeitungszeit",
        purposes=("Investition", "Wachstum", "Betriebsmittel"),
        notes=(
            "Antrag laeuft zwingend ueber die Hausbank und muss VOR Vorhabenbeginn "
            "gestellt werden. Wird von Hausbanken selten aktiv angeboten -- aktiv "
            "einfordern. Konditionen gegen das aktuelle Merkblatt pruefen."
        ),
    ),
    LenderProfile(
        key="buergschaftsbank",
        name="Buergschaftsbank des Bundeslandes",
        description="Ausfallbuergschaft bis typischerweise 80% der Kreditsumme.",
        min_band="D",
        min_dscr=1.10,
        min_equity_ratio=0.05,
        amount_min=25_000,
        amount_max=1_250_000,
        typical_weeks=10,
        indicative_cost="Buergschaftsprovision zusaetzlich zum Kreditzins",
        purposes=(),
        notes=(
            "Fuer tragfaehige Vorhaben ohne ausreichende Sicherheiten. "
            "Regional unterschiedlich; Buergschaft ohne Bank ('BoB') in einigen "
            "Bundeslaendern auch direkt beantragbar."
        ),
    ),
    LenderProfile(
        key="factoring",
        name="Factoring-Gesellschaft",
        description="Laufender Forderungsverkauf statt Kreditlinie.",
        min_band="E",
        min_dscr=0.0,
        min_equity_ratio=-1.0,
        amount_min=50_000,
        amount_max=10_000_000,
        typical_weeks=6,
        indicative_cost="1-3% vom Umsatz, abhaengig von Debitorenqualitaet",
        purposes=("Betriebsmittel",),
        notes=(
            "Bonitaet des Debitors zaehlt mehr als die des Kunden -- deshalb auch "
            "bei schwacher eigener Bilanz darstellbar. Abtretungsverbote und "
            "Klumpenrisiken sind die haeufigsten Ausschlussgruende."
        ),
    ),
    LenderProfile(
        key="leasing",
        name="Leasing / Sale-and-lease-back",
        description="Objektfinanzierung, Sicherheit ist das Objekt selbst.",
        min_band="D",
        min_dscr=1.00,
        min_equity_ratio=0.0,
        amount_min=10_000,
        amount_max=5_000_000,
        typical_weeks=4,
        indicative_cost="hoeher als Bankkredit, dafuer schnell und objektbesichert",
        purposes=("Investition",),
        notes=(
            "Sale-and-lease-back hebt stille Reserven im Anlagevermoegen, "
            "verschlechtert aber die Anlagendeckung. Bilanzwirkung vorher rechnen."
        ),
    ),
    LenderProfile(
        key="alt_lender",
        name="Digitaler Mittelstandsfinanzierer",
        description="Schnelle, datengetriebene Kreditentscheidung.",
        min_band="D",
        min_dscr=1.05,
        min_equity_ratio=0.0,
        amount_min=25_000,
        amount_max=1_500_000,
        typical_weeks=2,
        indicative_cost="deutlich teurer als Hausbank",
        purposes=("Betriebsmittel", "Wachstum", "Umschuldung"),
        notes=(
            "Sinnvoll bei echtem Zeitdruck oder als Ueberbrueckung. Als Dauerloesung "
            "teuer -- und eine laufende Finanzierung dort kann die spaetere "
            "Hausbankbeurteilung belasten."
        ),
    ),
    LenderProfile(
        key="mezzanine",
        name="Mezzanine / Mittelstaendische Beteiligungsgesellschaft (MBG)",
        description="Nachrangkapital, staerkt das wirtschaftliche Eigenkapital.",
        min_band="C",
        min_dscr=1.10,
        min_equity_ratio=0.0,
        amount_min=100_000,
        amount_max=2_500_000,
        typical_weeks=16,
        indicative_cost="teuer, aber eigenkapitalwirksam",
        purposes=("Wachstum", "Investition"),
        notes=(
            "Der eigentliche Hebel: Nachrangkapital zaehlt als wirtschaftliches "
            "Eigenkapital und verbessert dadurch die Rating-Kennzahlen fuer ALLE "
            "weiteren Finanzierungen."
        ),
    ),
)

_BAND_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


@dataclass
class RoutingOption:
    lender: LenderProfile
    fit_score: float               # 0-100
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def route(
    case: ClientCase,
    ratios: RatioSet,
    scorecard: ScorecardResult,
    label: str = "aktuell",
) -> list[RoutingOption]:
    """Rank lender types for this profile. `label` is cosmetic (before/after)."""
    options: list[RoutingOption] = []
    req = case.request
    band_rank = _BAND_ORDER[scorecard.band.value]
    dscr = ratios.kapitaldienstfaehigkeit_inkl_neu or ratios.kapitaldienstfaehigkeit
    eqr = ratios.eigenkapitalquote

    for lp in LENDERS:
        reasons: list[str] = []
        blockers: list[str] = []
        score = 60.0

        if band_rank > _BAND_ORDER[lp.min_band]:
            blockers.append(
                f"Readiness-Band {scorecard.band.value} unter dem ueblichen "
                f"Mindestniveau {lp.min_band}"
            )
        else:
            score += 12

        if dscr is not None:
            if dscr < lp.min_dscr:
                blockers.append(f"DSCR {dscr:.2f}x < {lp.min_dscr:.2f}x")
            else:
                score += 10
                reasons.append(f"Kapitaldienstfaehigkeit {dscr:.2f}x ausreichend")

        if eqr is not None and lp.min_equity_ratio > -1.0:
            if eqr < lp.min_equity_ratio:
                blockers.append(
                    f"EK-Quote {eqr*100:.1f}% < {lp.min_equity_ratio*100:.0f}%"
                )
            else:
                score += 8

        if req:
            if req.amount < lp.amount_min or req.amount > lp.amount_max:
                blockers.append(
                    f"Volumen {req.amount:,.0f} EUR ausserhalb "
                    f"{lp.amount_min:,.0f}-{lp.amount_max:,.0f} EUR"
                )
            else:
                score += 6
            if lp.purposes and req.purpose not in lp.purposes:
                blockers.append(f"Zweck '{req.purpose}' untypisch fuer dieses Instrument")
            elif lp.purposes:
                score += 6
                reasons.append(f"Zweck '{req.purpose}' passend")
            if req.urgency_weeks is not None:
                if lp.typical_weeks > req.urgency_weeks:
                    blockers.append(
                        f"Bearbeitungsdauer ca. {lp.typical_weeks} Wochen > "
                        f"Bedarf in {req.urgency_weeks} Wochen"
                    )
                else:
                    score += 8
                    reasons.append(f"Zeitrahmen ca. {lp.typical_weeks} Wochen passt")
            coverage = req.collateral_available / req.amount if req.amount else 0.0
            if coverage < 0.6 and lp.key in ("kfw_haftungsfreistellung", "buergschaftsbank"):
                score += 15
                reasons.append(
                    f"adressiert die Besicherungsluecke (Deckung nur {coverage*100:.0f}%)"
                )

        # Targeted boosts where the instrument solves the specific weakness.
        if lp.key == "factoring" and (ratios.debitorenlaufzeit_tage or 0) > 45:
            score += 14
            reasons.append(
                f"Debitorenlaufzeit {ratios.debitorenlaufzeit_tage:.0f} Tage - "
                "Forderungsbestand ist finanzierbar"
            )
        if lp.key == "mezzanine" and eqr is not None and eqr < 0.12:
            score += 12
            reasons.append("staerkt das wirtschaftliche Eigenkapital strukturell")
        if lp.key == "alt_lender" and req and req.urgency_weeks and req.urgency_weeks <= 4:
            score += 10

        score -= 18 * len(blockers)
        options.append(
            RoutingOption(
                lender=lp,
                fit_score=max(0.0, min(100.0, round(score, 1))),
                eligible=not blockers,
                reasons=reasons,
                blockers=blockers,
            )
        )

    return sorted(options, key=lambda o: (o.eligible, o.fit_score), reverse=True)
