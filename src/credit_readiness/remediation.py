"""Fixability classification and remediation simulation.

This is the core intellectual property of the business. The scorecard says *how
weak* a file looks; this module says *why*, and crucially whether the weakness is
an artefact of presentation, the wrong product, a collateral gap, or genuine
credit risk that no amount of restatement will fix.

That last category matters more than the other three. The blueprint's central
planning assumption -- that 5,000-8,000 German SMEs a year are rejected for
fixable reasons -- is unvalidated. Every engagement run through this module
produces a data point for or against it. Declining a case honestly because it
lands in GENUINE_RISK is a feature, not lost revenue: it is what keeps the
advisory defensible and the outcome dataset worth anything.

Each rule states its trigger, its remediation, and a `simulate` mutation that
shows the client the before/after. Simulations are deliberately conservative and
every one carries a caveat naming what could stop it working in practice.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .models import ClientCase
from .ratios import RatioSet, compute_ratios
from .scorecard import ScorecardResult, evaluate
from .formatting import de


class FixCategory(str, Enum):
    PRESENTATION = "Darstellung"
    DOCUMENTATION = "Unterlagen"
    PRODUCT_FIT = "Produktwahl"
    COLLATERAL = "Besicherung"
    GENUINE_RISK = "Substanzielles Kreditrisiko"

    @property
    def is_fixable(self) -> bool:
        return self is not FixCategory.GENUINE_RISK


class Effort(str, Enum):
    LOW = "gering"
    MEDIUM = "mittel"
    HIGH = "hoch"


@dataclass
class Finding:
    """One diagnosed weakness plus, where one exists, its remediation."""

    rule_id: str
    title: str
    category: FixCategory
    severity: str                      # kritisch | wesentlich | gering
    observation: str                   # what the numbers show
    remediation: str                   # the concrete action, or why there is none
    affected_factors: tuple[str, ...] = ()
    effort: Effort = Effort.MEDIUM
    weeks_to_effect: int = 4
    requires_steuerberater: bool = False
    requires_legal: bool = False
    caveat: str = ""
    simulate: Optional[Callable[[ClientCase], None]] = field(
        default=None, repr=False, compare=False
    )

    @property
    def is_simulatable(self) -> bool:
        return self.simulate is not None


# ---------------------------------------------------------------------------
# Rules. Each takes (case, ratios, scorecard) and returns a Finding or None.
# ---------------------------------------------------------------------------


def _rule_rangruecktritt(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    bs = case.balance_sheet
    if bs.gesellschafterdarlehen <= 0 or bs.gesellschafterdarlehen_rangruecktritt:
        return None
    if (r.eigenkapitalquote or 0) >= 0.20:
        return None

    uplift = bs.gesellschafterdarlehen / bs.bilanzsumme if bs.bilanzsumme else 0.0

    def sim(c: ClientCase) -> None:
        c.balance_sheet.gesellschafterdarlehen_rangruecktritt = True

    return Finding(
        rule_id="R01",
        title="Gesellschafterdarlehen ohne Rangruecktritt",
        category=FixCategory.PRESENTATION,
        severity="kritisch" if (r.eigenkapitalquote or 0) < 0.10 else "wesentlich",
        observation=(
            f"Gesellschafterdarlehen von {de(bs.gesellschafterdarlehen)} EUR wird "
            f"mangels Rangruecktritt als Fremdkapital gewertet. Die wirtschaftliche "
            f"Eigenkapitalquote liegt dadurch bei {de((r.eigenkapitalquote or 0)*100, 1)}% "
            f"statt bei rund {de(((r.eigenkapitalquote or 0) + uplift)*100, 1)}%."
        ),
        remediation=(
            "Qualifizierten Rangruecktritt schriftlich vereinbaren und der Bank "
            "vorlegen. Das Darlehen wird dann von nahezu allen deutschen Kreditgebern "
            "als wirtschaftliches Eigenkapital behandelt -- ohne dass ein Euro "
            "frisches Kapital zugefuehrt werden muss."
        ),
        affected_factors=("eigenkapitalquote", "dynamischer_verschuldungsgrad"),
        effort=Effort.LOW,
        weeks_to_effect=2,
        requires_steuerberater=True,
        requires_legal=True,
        caveat=(
            "Ein qualifizierter Rangruecktritt hat insolvenz- und steuerrechtliche "
            "Folgen und muss vom Steuerberater und einem Rechtsanwalt geprueft werden. "
            "Nie einseitig empfehlen."
        ),
        simulate=sim,
    )


def _rule_stale_bwa(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    b = case.behavior
    if b.bwa_age_months <= 3:
        return None

    def sim(c: ClientCase) -> None:
        c.behavior.bwa_age_months = 1.0
        c.behavior.bwa_frequency = "monatlich"

    return Finding(
        rule_id="R02",
        title="BWA nicht aktuell",
        category=FixCategory.DOCUMENTATION,
        severity="wesentlich" if b.bwa_age_months > 6 else "gering",
        observation=(
            f"Die juengste BWA ist {de(b.bwa_age_months)} Monate alt "
            f"(Frequenz: {b.bwa_frequency}). Kreditgeber werten eine veraltete BWA "
            f"regelmaessig als Hinweis auf schwaches internes Reporting und legen "
            f"im Zweifel konservativere Annahmen zugrunde."
        ),
        remediation=(
            "Monatliche BWA-Erstellung mit dem Steuerberater vereinbaren und vor "
            "Antragstellung eine BWA vorlegen, die nicht aelter als zwei Monate ist. "
            "Billigste Einzelmassnahme im gesamten Katalog."
        ),
        affected_factors=("bwa_age_months",),
        effort=Effort.LOW,
        weeks_to_effect=4,
        requires_steuerberater=True,
        simulate=sim,
    )


def _rule_missing_forecast(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    if case.behavior.has_planning_forecast:
        return None
    if not case.request or case.request.amount < 100_000:
        return None

    return Finding(
        rule_id="R03",
        title="Keine integrierte Planrechnung",
        category=FixCategory.DOCUMENTATION,
        severity="wesentlich",
        observation=(
            f"Fuer ein Finanzierungsvolumen von {de(case.request.amount)} EUR liegt "
            "keine Planrechnung vor. Ohne Plan-GuV, Liquiditaets- und Bilanzplanung "
            "kann der Kreditgeber die Kapitaldienstfaehigkeit nur rueckwaerts "
            "gewandt beurteilen."
        ),
        remediation=(
            "Integrierte 24-Monats-Planrechnung erstellen (Plan-GuV, Liquiditaet, "
            "Planbilanz), inklusive Szenario mit dem neuen Kapitaldienst. "
            "Kein Ratio-Effekt, aber in der Praxis haeufig entscheidungsrelevant."
        ),
        affected_factors=(),
        effort=Effort.MEDIUM,
        weeks_to_effect=3,
        requires_steuerberater=True,
        caveat="Verbessert keine Kennzahl -- wirkt ueber die qualitative Beurteilung.",
    )


def _rule_kontokorrent_dauerinanspruchnahme(
    case: ClientCase, r: RatioSet, s: ScorecardResult
) -> Optional[Finding]:
    bs = case.balance_sheet
    util = r.kontokorrent_auslastung
    if util is None or util < 0.80:
        return None
    if r.ebitda <= 0:
        return None  # genuine distress, not a product-fit issue -- see R08

    drawn = bs.kontokorrent_inanspruchnahme
    term_out = drawn * 0.70

    def sim(c: ClientCase) -> None:
        b = c.balance_sheet
        moved = b.kontokorrent_inanspruchnahme * 0.70
        b.kontokorrent_inanspruchnahme -= moved
        b.verb_kreditinstitute_kurz = max(0.0, b.verb_kreditinstitute_kurz - moved)
        b.verb_kreditinstitute_lang += moved

    return Finding(
        rule_id="R04",
        title="Dauerinanspruchnahme des Kontokorrents",
        category=FixCategory.PRODUCT_FIT,
        severity="kritisch" if util > 0.95 else "wesentlich",
        observation=(
            f"Der Kontokorrent ist zu {de(util*100)}% ausgeschoepft "
            f"({de(drawn)} von {de(bs.kontokorrent_limit)} EUR), an "
            f"{case.behavior.overdraft_days_at_limit_12m} Tagen der letzten 12 Monate "
            "am Limit. Der Kontokorrent finanziert damit faktisch Anlagevermoegen "
            "oder dauerhaftes Working Capital -- das teuerste denkbare Instrument "
            "dafuer, und fuer die Bank ein Warnsignal."
        ),
        remediation=(
            f"Rund {de(term_out)} EUR der Dauerinanspruchnahme in ein "
            "Tilgungsdarlehen mit passender Laufzeit umschulden. Das senkt die "
            "Zinslast, stellt die Betriebsmittellinie als echte Reserve wieder her "
            "und beseitigt das Warnsignal, ohne die Gesamtverschuldung zu erhoehen."
        ),
        affected_factors=("kontokorrent_auslastung", "liquiditaet_2_grades"),
        effort=Effort.MEDIUM,
        weeks_to_effect=8,
        caveat=(
            "Setzt voraus, dass die Kapitaldienstfaehigkeit die zusaetzliche Tilgung "
            "traegt. Bei DSCR < 1,1 zuerst R05/R06 pruefen."
        ),
        simulate=sim,
    )


def _rule_factoring(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    dso = r.debitorenlaufzeit_tage
    bs = case.balance_sheet
    if dso is None or dso < 45:
        return None
    if bs.forderungen_ll < 50_000:
        return None
    if case.profile.sector in ():
        return None

    released = bs.forderungen_ll * 0.80

    def sim(c: ClientCase) -> None:
        b = c.balance_sheet
        proceeds = b.forderungen_ll * 0.80
        b.forderungen_ll -= proceeds
        repay = min(proceeds, b.verb_kreditinstitute_kurz)
        b.verb_kreditinstitute_kurz -= repay
        b.liquide_mittel += proceeds - repay
        b.kontokorrent_inanspruchnahme = max(
            0.0, b.kontokorrent_inanspruchnahme - repay
        )

    return Finding(
        rule_id="R05",
        title="Hohe Debitorenlaufzeit - Factoring statt Kreditlinie",
        category=FixCategory.PRODUCT_FIT,
        severity="wesentlich",
        observation=(
            f"Die Debitorenlaufzeit betraegt {de(dso)} Tage bei einem "
            f"Forderungsbestand von {de(bs.forderungen_ll)} EUR. Das Unternehmen "
            "finanziert seine Kunden ueber die eigene Kreditlinie vor."
        ),
        remediation=(
            f"Factoring pruefen: rund {de(released)} EUR koennten kurzfristig "
            "liquidisiert und zur Rueckfuehrung der kurzfristigen Bankverbindlichkeiten "
            "eingesetzt werden. Reduziert den Kreditbedarf, statt ihn zu finanzieren."
        ),
        affected_factors=("liquiditaet_2_grades", "dynamischer_verschuldungsgrad"),
        effort=Effort.MEDIUM,
        weeks_to_effect=6,
        caveat=(
            "Factoring kostet real 1-3% des Umsatzes und setzt B2B-Forderungen mit "
            "guter Debitorenbonitaet voraus. Bei Abhaengigkeit von wenigen Grosskunden "
            "oder bei Abtretungsverboten haeufig nicht darstellbar."
        ),
        simulate=sim,
    )


def _rule_fristenkongruenz(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    adg = r.anlagendeckungsgrad_ii
    if adg is None or adg >= 1.0:
        return None
    bs = case.balance_sheet
    gap = bs.anlagevermoegen - bs.langfristiges_kapital
    if gap <= 0:
        return None

    def sim(c: ClientCase) -> None:
        b = c.balance_sheet
        shift = min(b.anlagevermoegen - b.langfristiges_kapital, b.verb_kreditinstitute_kurz)
        if shift > 0:
            b.verb_kreditinstitute_kurz -= shift
            b.verb_kreditinstitute_lang += shift

    return Finding(
        rule_id="R06",
        title="Verletzung der Fristenkongruenz (goldene Bilanzregel)",
        category=FixCategory.PRODUCT_FIT,
        severity="wesentlich",
        observation=(
            f"Der Anlagendeckungsgrad II liegt bei {de(adg*100)}%. Rund "
            f"{de(gap)} EUR des Anlagevermoegens sind kurzfristig finanziert. "
            "Das erzeugt strukturellen Refinanzierungsdruck, den die Bank sieht."
        ),
        remediation=(
            "Kurzfristige Bankverbindlichkeiten in laufzeitkongruente Darlehen "
            "umschulden, abgestimmt auf die Nutzungsdauer der finanzierten "
            "Wirtschaftsgueter. Ggf. mit KfW-Investitionskredit kombinieren."
        ),
        affected_factors=("liquiditaet_2_grades", "kontokorrent_auslastung"),
        effort=Effort.MEDIUM,
        weeks_to_effect=8,
        simulate=sim,
    )


def _rule_collateral_gap(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    req = case.request
    if not req:
        return None
    dscr = r.kapitaldienstfaehigkeit_inkl_neu
    if dscr is None or dscr < 1.10:
        return None  # not a collateral problem, a capacity problem
    coverage = req.collateral_available / req.amount if req.amount else 0.0
    if coverage >= 0.60:
        return None

    return Finding(
        rule_id="R07",
        title="Besicherungsluecke bei tragfaehigem Kapitaldienst",
        category=FixCategory.COLLATERAL,
        severity="wesentlich",
        observation=(
            f"Die Kapitaldienstfaehigkeit liegt mit {de(dscr, 2)}x im tragfaehigen "
            f"Bereich, die verfuegbaren Sicherheiten decken aber nur "
            f"{de(coverage*100)}% des Finanzierungsvolumens von "
            f"{de(req.amount)} EUR. Eine Ablehnung waere hier eine "
            "Besicherungs-, keine Bonitaetsentscheidung."
        ),
        remediation=(
            "Foerderweg statt Standardkredit: KfW-Programm mit Haftungsfreistellung "
            "(typisch 50-80% Risikoentlastung fuer die Hausbank) oder Buergschaft "
            "der regionalen Buergschaftsbank. Antrag laeuft ueber die Hausbank -- "
            "der Weg muss aktiv eingefordert werden, er wird selten angeboten."
        ),
        affected_factors=(),
        effort=Effort.MEDIUM,
        weeks_to_effect=10,
        caveat=(
            "Programmkonditionen und Haftungsfreistellungssaetze aendern sich; vor "
            "jeder Empfehlung gegen das aktuelle KfW-Merkblatt pruefen. Kein "
            "Ratio-Effekt -- wirkt ueber die Strukturierung."
        ),
    )


def _rule_genuine_weakness(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    """The honest-decline rule. Deliberately blunt."""
    reasons: list[str] = []
    if r.ebitda <= 0:
        reasons.append(f"EBITDA negativ ({de(r.ebitda)} EUR)")
    if (r.eigenkapitalquote or 0) < 0:
        reasons.append(
            f"bilanzielle Ueberschuldung (wirtschaftliches EK "
            f"{de(r.wirtschaftliches_eigenkapital)} EUR)"
        )
    if r.umsatzwachstum is not None and r.umsatzwachstum < -0.15 and (r.ebit_marge or 0) < 0:
        reasons.append(
            f"Umsatzrueckgang {de(r.umsatzwachstum*100)}% bei negativer EBIT-Marge"
        )
    dv = r.dynamischer_verschuldungsgrad
    if dv is not None and dv > 8.0:
        reasons.append(f"dynamischer Verschuldungsgrad {de(dv, 1)}x")

    if not reasons:
        return None

    return Finding(
        rule_id="R08",
        title="Substanzielle Bonitaetsschwaeche - nicht durch Aufbereitung loesbar",
        category=FixCategory.GENUINE_RISK,
        severity="kritisch",
        observation=(
            "Folgende Befunde sind keine Darstellungsprobleme: "
            + "; ".join(reasons)
            + "."
        ),
        remediation=(
            "Keine Aufbereitungsmassnahme adressiert diese Befunde. Ehrliche "
            "Optionen: operative Restrukturierung vor jeder Antragstellung, "
            "Gesellschaftereinlage, oder die bewusste Entscheidung, aktuell nicht "
            "zu beantragen. Eine Antragstellung in diesem Zustand erzeugt eine "
            "dokumentierte Ablehnung, die spaetere Antraege zusaetzlich belastet."
        ),
        affected_factors=(),
        effort=Effort.HIGH,
        weeks_to_effect=52,
        caveat=(
            "Dieser Befund sollte zur Ablehnung des Mandats fuehren, wenn der "
            "Kunde eine kurzfristige Zusage erwartet. Das ist der Fall, in dem "
            "Nein-sagen das Produkt ist."
        ),
    )


def _rule_tax_arrears(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    if not case.behavior.tax_arrears:
        return None

    def sim(c: ClientCase) -> None:
        c.behavior.tax_arrears = False

    return Finding(
        rule_id="R09",
        title="Steuerrueckstaende",
        category=FixCategory.GENUINE_RISK,
        severity="kritisch",
        observation=(
            "Es bestehen Steuerrueckstaende. Bei nahezu allen Kreditgebern ist das "
            "ein K.-o.-Kriterium, unabhaengig von allen uebrigen Kennzahlen."
        ),
        remediation=(
            "Vor jeder Antragstellung zwingend klaeren: Rueckstaende ausgleichen "
            "oder eine belastbare, schriftliche Stundungsvereinbarung mit dem "
            "Finanzamt vorlegen. Erst danach Antrag stellen."
        ),
        affected_factors=("zahlungsverhalten",),
        effort=Effort.HIGH,
        weeks_to_effect=12,
        caveat=(
            "Als GENUINE_RISK eingestuft, weil ungeloest kein Kreditgeber zeichnet -- "
            "nach nachgewiesener Klaerung faellt der Befund weg."
        ),
        simulate=sim,
    )


def _rule_inventory(case: ClientCase, r: RatioSet, s: ScorecardResult) -> Optional[Finding]:
    reach = r.vorratsreichweite_tage
    if reach is None or reach < 90:
        return None
    bs = case.balance_sheet
    if bs.vorraete < 50_000:
        return None

    release = bs.vorraete * 0.20

    def sim(c: ClientCase) -> None:
        b = c.balance_sheet
        freed = b.vorraete * 0.20
        b.vorraete -= freed
        repay = min(freed, b.verb_kreditinstitute_kurz)
        b.verb_kreditinstitute_kurz -= repay
        b.liquide_mittel += freed - repay

    return Finding(
        rule_id="R10",
        title="Hohe Vorratsreichweite bindet Working Capital",
        category=FixCategory.PRODUCT_FIT,
        severity="gering",
        observation=(
            f"Die Vorratsreichweite betraegt {de(reach)} Tage "
            f"({de(bs.vorraete)} EUR). Ein Teil des Kreditbedarfs entsteht im "
            "Lager, nicht im Geschaeftsmodell."
        ),
        remediation=(
            f"Bestandsabbau von rund {de(release)} EUR (Langsamdreher, "
            "Mindestbestellmengen, Konsignationslager) reduziert den "
            "Finanzierungsbedarf unmittelbar."
        ),
        affected_factors=("liquiditaet_2_grades", "dynamischer_verschuldungsgrad"),
        effort=Effort.MEDIUM,
        weeks_to_effect=16,
        caveat="Bei Lieferkettenrisiken kann ein hoher Bestand bewusst gewollt sein.",
        simulate=sim,
    )


RULES: tuple[Callable[[ClientCase, RatioSet, ScorecardResult], Optional[Finding]], ...] = (
    _rule_genuine_weakness,
    _rule_tax_arrears,
    _rule_rangruecktritt,
    _rule_kontokorrent_dauerinanspruchnahme,
    _rule_factoring,
    _rule_fristenkongruenz,
    _rule_collateral_gap,
    _rule_stale_bwa,
    _rule_missing_forecast,
    _rule_inventory,
)


def diagnose(case: ClientCase, ratios: RatioSet, scorecard: ScorecardResult) -> list[Finding]:
    findings = [f for rule in RULES if (f := rule(case, ratios, scorecard)) is not None]
    order = {"kritisch": 0, "wesentlich": 1, "gering": 2}
    return sorted(findings, key=lambda f: (order.get(f.severity, 3), f.rule_id))


# ---------------------------------------------------------------------------
# Verdict + simulation
# ---------------------------------------------------------------------------


class Verdict(str, Enum):
    ALREADY_BANKABLE = "bereits finanzierbar"
    FIXABLE_PRESENTATION = "behebbar - Darstellung und Unterlagen"
    FIXABLE_STRUCTURE = "behebbar - Struktur, Produkt oder Besicherung"
    GENUINE_RISK = "nicht behebbar - substanzielles Kreditrisiko"


@dataclass
class SimulationResult:
    before_score: float
    after_score: float
    before_band: str
    after_band: str
    before_ratios: RatioSet
    after_ratios: RatioSet
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def delta(self) -> float:
        return round(self.after_score - self.before_score, 1)

    @property
    def band_improved(self) -> bool:
        return self.before_band != self.after_band


def classify(findings: list[Finding], scorecard: ScorecardResult) -> Verdict:
    """Decide which bucket the engagement falls into.

    Genuine risk dominates: one substantive finding outranks any number of
    cosmetic ones, because fixing presentation on a distressed borrower just
    produces a better-looking rejection.
    """
    if any(f.category is FixCategory.GENUINE_RISK for f in findings):
        return Verdict.GENUINE_RISK
    if scorecard.band.value in ("A", "B") and not findings:
        return Verdict.ALREADY_BANKABLE

    structural = {FixCategory.PRODUCT_FIT, FixCategory.COLLATERAL}
    if any(f.category in structural for f in findings):
        return Verdict.FIXABLE_STRUCTURE
    if findings:
        return Verdict.FIXABLE_PRESENTATION
    return Verdict.ALREADY_BANKABLE


def simulate(case: ClientCase, findings: list[Finding]) -> SimulationResult:
    """Apply every simulatable remediation to a copy and re-score.

    The copy is total: nothing here may mutate the client's actual case object,
    because the before/after comparison is the deliverable.
    """
    before_ratios = compute_ratios(case)
    before_card = evaluate(case, before_ratios)

    working = copy.deepcopy(case)
    applied: list[str] = []
    skipped: list[str] = []

    for f in findings:
        if f.simulate is None:
            skipped.append(f"{f.rule_id} {f.title} (keine Kennzahlenwirkung)")
            continue
        if f.category is FixCategory.GENUINE_RISK and f.rule_id != "R09":
            skipped.append(f"{f.rule_id} {f.title} (nicht durch Aufbereitung loesbar)")
            continue
        f.simulate(working)
        applied.append(f"{f.rule_id} {f.title}")

    after_ratios = compute_ratios(working)
    after_card = evaluate(working, after_ratios)

    return SimulationResult(
        before_score=before_card.total_score,
        after_score=after_card.total_score,
        before_band=before_card.band.value,
        after_band=after_card.band.value,
        before_ratios=before_ratios,
        after_ratios=after_ratios,
        applied=applied,
        skipped=skipped,
    )
