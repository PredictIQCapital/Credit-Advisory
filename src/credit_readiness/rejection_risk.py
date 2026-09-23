"""Named reasons a lender would decline, checked explicitly rather than scored.

WHY THIS IS SEPARATE FROM THE SCORECARD
=======================================
A weighted score answers "how does this file read overall". It cannot answer
"is there something here that ends the conversation regardless of the total",
because a weighted average by construction lets a strong factor offset a fatal
one. Those are different questions and they need different machinery.

Every German lender runs a set of knock-out checks before, or alongside, the
rating. A file can score respectably and still be declined on one line. This
module makes those lines explicit, so the client hears them from us first --
which is the entire product promise.

WHERE THE CHECKS COME FROM
==========================
None of these thresholds are ours. Each check names its source, and the report
prints the source, because a client challenged on one of these will ask where
it comes from and "our model says so" is not an answer.

  * **CRR Article 178** -- the regulatory definition of default. Two limbs:
    unlikely to pay without recourse to realising security, and more than 90
    days past due on a material obligation. It also states that an overdraft
    counts as past due "once the customer has breached an advised limit".
  * **Banque de France rating reference guide, September 2026** -- a peer
    central bank's published criteria for its weak rating grades. Used here
    because it is the only source in the set that states distress criteria as
    concrete, checkable conditions rather than as principles.
  * **German statute** -- 49 Abs. 3 GmbHG (loss of half the share capital
    obliges the managing director to convene the shareholders) and 19 InsO
    (over-indebtedness, and the Rangruecktritt/going-concern defences).
  * **EBA/GL/2020/06 Tz. 121 d** -- obligations to tax authorities and social
    security funds belong in the assessment.

WHAT THIS DELIBERATELY DOES NOT DO
==================================
It does not conclude that a company is insolvent, and it must never be read as
doing so. Whether a filing obligation under 15a InsO exists is a legal question
with defences this engine cannot evaluate -- a going-concern prognosis above
all. The checks flag the *condition*; the text says what the condition means to
a lender and that the assessment belongs to the Steuerberater or a lawyer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .formatting import de
from .models import ClientCase
from .ratios import RatioSet

# CRR Art. 178: an overdraft is past due once an advised limit is breached.
# No tolerance band -- the regulation does not provide one.
KK_LIMIT_TOLERANCE = 1.0            # EUR, rounding only

# Banque de France rating 8: payment incidents over purchases above this share
# marks a company whose ability to meet commitments is "at risk or compromised".
ZAHLUNGSSTOERUNG_SCHWELLE = 0.02

# Banque de France rating X: accounts whose year-end is older than this are not
# usable for a rating at all.
ABSCHLUSS_UNBRAUCHBAR_MONATE = 23.0

# Banque de France rating 6 lists a very high share of EBITDA absorbed by
# financial charges, sustained, as a "serious financial imbalance".
ZINSLAST_KRITISCH = 0.50


class Schwere(str, Enum):
    """How a lender treats the finding, not how bad we think it is."""

    KO = "K.-o.-Kriterium"          # conversation ends until resolved
    SCHWER = "schwerwiegend"        # decline likely without a mitigant
    PRUEFEN = "klaerungsbeduerftig"  # will be asked about; have an answer ready


@dataclass(frozen=True)
class RejectionReason:
    code: str
    title: str
    severity: Schwere
    finding: str                    # what is true of this file
    consequence: str                # what a lender does with it
    source: str                     # where the criterion comes from
    action: str                     # what the client can do about it
    mitigated: bool = False         # condition present but already answered


@dataclass
class RejectionScreen:
    reasons: list[RejectionReason] = field(default_factory=list)
    checked: int = 0

    @property
    def knockouts(self) -> list[RejectionReason]:
        return [r for r in self.reasons if r.severity is Schwere.KO and not r.mitigated]

    @property
    def clean(self) -> bool:
        return not [r for r in self.reasons if not r.mitigated]

    @property
    def worst(self) -> Optional[Schwere]:
        for level in (Schwere.KO, Schwere.SCHWER, Schwere.PRUEFEN):
            if any(r.severity is level and not r.mitigated for r in self.reasons):
                return level
        return None


def _stammkapital_check(case: ClientCase) -> Optional[RejectionReason]:
    """49 Abs. 3 GmbHG: half the share capital lost.

    The Banque de France uses the same condition (its French statutory
    equivalent) as a criterion for rating 4- and, unmitigated, rating 6. It is
    a good check precisely because it is objective: no judgement, just two
    numbers off the balance sheet.
    """
    b = case.balance_sheet
    if b.gezeichnetes_kapital <= 0:
        return None
    if b.bilanzielles_eigenkapital >= b.gezeichnetes_kapital / 2.0:
        return None
    # Subordinated shareholder debt does not repair the statutory position --
    # 49 Abs. 3 looks at balance-sheet equity -- but it does change how a
    # lender reads the file, so it is reported as a mitigant, not a cure.
    mitigated = (
        case.balance_sheet.gesellschafterdarlehen_rangruecktritt
        and b.wirtschaftliches_eigenkapital >= b.gezeichnetes_kapital / 2.0
    )
    return RejectionReason(
        code="KO01",
        title="Verlust der Haelfte des Stammkapitals",
        severity=Schwere.SCHWER if mitigated else Schwere.KO,
        finding=(
            f"Das bilanzielle Eigenkapital betraegt {de(b.bilanzielles_eigenkapital)} EUR "
            f"bei einem gezeichneten Kapital von {de(b.gezeichnetes_kapital)} EUR. "
            "Damit ist mehr als die Haelfte des Stammkapitals aufgezehrt."
        ),
        consequence=(
            "Kreditgeber lesen diesen Zustand als Anzeichen einer Unternehmenskrise "
            "und verlangen regelmaessig eine Stellungnahme des Steuerberaters, bevor "
            "ueberhaupt ueber Konditionen gesprochen wird."
        ),
        source="49 Abs. 3 GmbHG; Banque de France, Rating-Leitfaden 09/2026, Note 4-/6",
        action=(
            "Der Geschaeftsfuehrer ist nach 49 Abs. 3 GmbHG verpflichtet, unverzueglich "
            "die Gesellschafterversammlung einzuberufen. Unabhaengig davon: "
            "Kapitalerhoehung, Einlage oder Rangruecktritt vorhandener "
            "Gesellschafterdarlehen mit dem Steuerberater besprechen."
        ),
        mitigated=mitigated,
    )


def _ueberschuldung_check(case: ClientCase) -> Optional[RejectionReason]:
    """Negative balance-sheet equity -- the entry point to 19 InsO."""
    b = case.balance_sheet
    if b.bilanzielles_eigenkapital >= 0:
        return None
    mitigated = b.gesellschafterdarlehen_rangruecktritt and b.wirtschaftliches_eigenkapital >= 0
    return RejectionReason(
        code="KO02",
        title="Bilanzielle Ueberschuldung",
        severity=Schwere.SCHWER if mitigated else Schwere.KO,
        finding=(
            f"Das bilanzielle Eigenkapital ist mit {de(b.bilanzielles_eigenkapital)} EUR "
            "negativ."
            + (f" Mit dem Rangruecktritt der Gesellschafterdarlehen ergibt sich ein "
               f"wirtschaftliches Eigenkapital von "
               f"{de(b.wirtschaftliches_eigenkapital)} EUR." if mitigated else "")
        ),
        consequence=(
            "Ohne belastbare Erklaerung wird nahezu jeder Kreditgeber ablehnen. "
            "Eine bilanzielle Ueberschuldung ist fuer sich genommen noch keine "
            "Ueberschuldung im Sinne des 19 InsO - dafuer kommt es auf die "
            "Fortfuehrungsprognose an -, aber die Unterscheidung muss belegt werden, "
            "und zwar bevor der Antrag gestellt wird."
        ),
        source="19 InsO; EBA/GL/2020/06 Tz. 128 a",
        action=(
            "Fortfuehrungsprognose und ggf. Rangruecktrittserklaerungen mit dem "
            "Steuerberater klaeren. Diese Frage gehoert nicht in ein Kreditgespraech, "
            "sondern davor."
        ),
        mitigated=mitigated,
    )


def _kontokorrent_check(case: ClientCase) -> Optional[RejectionReason]:
    """CRR Art. 178: a breached advised limit counts as past due."""
    b = case.balance_sheet
    if b.kontokorrent_limit <= 0:
        return None
    ueberziehung = b.kontokorrent_inanspruchnahme - b.kontokorrent_limit
    if ueberziehung <= KK_LIMIT_TOLERANCE:
        return None
    return RejectionReason(
        code="KO03",
        title="Kontokorrentlinie ueberzogen",
        severity=Schwere.KO,
        finding=(
            f"Die Inanspruchnahme liegt mit {de(b.kontokorrent_inanspruchnahme)} EUR um "
            f"{de(ueberziehung)} EUR ueber der eingeraeumten Linie von "
            f"{de(b.kontokorrent_limit)} EUR."
        ),
        consequence=(
            "Nach Artikel 178 CRR gilt ein Kontokorrent als ueberfaellig, sobald die "
            "eingeraeumte Linie ueberschritten ist. Die kontofuehrende Bank sieht das "
            "unmittelbar; jede andere Bank sieht es an den Kontoumsaetzen, die sie "
            "ohnehin anfordert. Eine geduldete Ueberziehung ist kein Verhandlungsspielraum, "
            "sondern ein Ausfallmerkmal."
        ),
        source="Artikel 178 CRR (Ausfalldefinition)",
        action=(
            "Vor Antragstellung zurueckfuehren oder die Linie foermlich erhoehen lassen. "
            "Beides ist besser als die Ueberziehung stehen zu lassen."
        ),
    )


def _steuer_check(case: ClientCase) -> Optional[RejectionReason]:
    if not case.behavior.tax_arrears:
        return None
    return RejectionReason(
        code="KO04",
        title="Steuerrueckstaende",
        severity=Schwere.KO,
        finding="Es bestehen Rueckstaende gegenueber dem Finanzamt.",
        consequence=(
            "Verbindlichkeiten gegenueber Steuer- und Sozialversicherungstraegern "
            "gehoeren nach den EBA-Leitlinien ausdruecklich in die Kreditwuerdigkeits"
            "pruefung. In der Praxis ist dies bei nahezu allen Kreditgebern ein "
            "K.-o.-Kriterium, unabhaengig von allen uebrigen Kennzahlen."
        ),
        source="EBA/GL/2020/06 Tz. 121 d",
        action=(
            "Ausgleichen oder eine schriftliche Stundungsvereinbarung vorlegen. "
            "Erst danach beantragen."
        ),
    )


def _zahlungsstoerung_check(case: ClientCase, r: RatioSet) -> Optional[RejectionReason]:
    """Returned direct debits relative to purchases, Banque de France style."""
    beh = case.behavior
    if beh.returned_direct_debits_12m <= 0:
        return None
    return RejectionReason(
        code="KO05",
        title="Ruecklastschriften im Zahlungsverkehr",
        severity=Schwere.SCHWER if beh.returned_direct_debits_12m >= 3 else Schwere.PRUEFEN,
        finding=(
            f"In den letzten zwoelf Monaten wurden {beh.returned_direct_debits_12m} "
            "Lastschriften zurueckgegeben."
        ),
        consequence=(
            "Ruecklastschriften sind fuer einen Kreditgeber das sichtbarste Zeichen "
            "angespannter Liquiditaet, weil sie aus den Kontoumsaetzen unmittelbar "
            "hervorgehen und sich nicht erklaeren lassen wie eine Kennzahl. Die Banque "
            "de France stuft Unternehmen allein aufgrund von Zahlungsstoerungen in ihre "
            "schwaechste Ratingklasse ein."
        ),
        source="Banque de France, Rating-Leitfaden 09/2026, Note 8",
        action=(
            "Ursache benennen und belegen, dass sie behoben ist. Ein einzelner "
            "erklaerbarer Vorfall ist verhandelbar, eine Serie nicht."
        ),
    )


def _verlustserie_check(case: ClientCase, r: RatioSet) -> Optional[RejectionReason]:
    """Sustained losses. The Banque de France uses three consecutive years."""
    g = case.income_statement
    if g.jahresueberschuss >= 0:
        return None
    vorjahr = case.prior_year_income
    if vorjahr is None:
        return RejectionReason(
            code="KO06",
            title="Jahresfehlbetrag ohne Vorjahresvergleich",
            severity=Schwere.PRUEFEN,
            finding=(
                f"Das Jahresergebnis ist mit {de(g.jahresueberschuss)} EUR negativ. "
                "Ohne Vorjahreszahlen laesst sich nicht erkennen, ob es sich um einen "
                "einmaligen Effekt oder um eine Serie handelt."
            ),
            consequence=(
                "Genau diese Unterscheidung entscheidet beim Kreditgeber ueber die "
                "Einordnung. Ohne Vorjahr wird im Zweifel die unguenstigere "
                "Annahme getroffen."
            ),
            source="Banque de France, Rating-Leitfaden 09/2026, Note 6",
            action="Vorjahresabschluss nachreichen - das ist hier die wirksamste Massnahme.",
        )
    if vorjahr.jahresueberschuss >= 0:
        return None
    return RejectionReason(
        code="KO06",
        title="Verluste in zwei aufeinanderfolgenden Jahren",
        severity=Schwere.SCHWER,
        finding=(
            f"Jahresergebnis {de(g.jahresueberschuss)} EUR nach "
            f"{de(vorjahr.jahresueberschuss)} EUR im Vorjahr."
        ),
        consequence=(
            "Zwei Verlustjahre in Folge gelten als Strukturproblem, nicht als Ausreisser. "
            "Die Banque de France zieht die Grenze bei drei Jahren; die dritte "
            "Beobachtung liegt hier noch nicht vor, die Richtung aber schon."
        ),
        source="Banque de France, Rating-Leitfaden 09/2026, Note 6",
        action=(
            "Ergebnisverbesserung belegen - Zwischenzahlen, Auftragsbestand, "
            "umgesetzte Massnahmen. Ohne einen Beleg fuer die Trendwende ist der "
            "Antrag verfrueht."
        ),
    )


def _zinslast_check(case: ClientCase, r: RatioSet) -> Optional[RejectionReason]:
    """Financial charges absorbing a very high share of EBITDA."""
    if r.ebitda <= 0:
        return None
    zins = case.income_statement.annualised(case.income_statement.zinsaufwand)
    if zins <= 0:
        return None
    anteil = zins / r.ebitda
    if anteil < ZINSLAST_KRITISCH:
        return None
    return RejectionReason(
        code="KO07",
        title="Zinslast bindet einen sehr hohen Anteil des EBITDA",
        severity=Schwere.SCHWER if anteil >= 1.0 else Schwere.PRUEFEN,
        finding=(
            f"Der Zinsaufwand von {de(zins)} EUR bindet {de(anteil * 100, 0)}% des "
            f"EBITDA von {de(r.ebitda)} EUR."
        ),
        consequence=(
            "Bleibt nach dem Zinsdienst zu wenig fuer die Tilgung, ist die "
            "Kapitaldienstfaehigkeit rechnerisch gegeben und praktisch nicht. "
            "Kreditgeber rechnen diese Groesse und sie faellt frueher auf als die "
            "Verschuldungskennzahlen."
        ),
        source="Banque de France, Rating-Leitfaden 09/2026, Note 6",
        action=(
            "Umschuldung teurer Linien pruefen - insbesondere Kontokorrent in "
            "Darlehen. Das senkt die Zinslast unmittelbar."
        ),
    )


def _aktualitaet_check(case: ClientCase) -> Optional[RejectionReason]:
    """Accounts too old to support a rating at all."""
    alter = case.behavior.jahresabschluss_age_months
    if alter < ABSCHLUSS_UNBRAUCHBAR_MONATE:
        return None
    return RejectionReason(
        code="KO08",
        title="Jahresabschluss zu alt fuer eine Beurteilung",
        severity=Schwere.KO,
        finding=f"Der juengste Jahresabschluss ist {de(alter, 0)} Monate alt.",
        consequence=(
            "Die Banque de France vergibt fuer Abschluesse, deren Stichtag laenger "
            "als 23 Monate zurueckliegt, ueberhaupt kein Rating mehr. Deutsche "
            "Kreditgeber verfahren im Ergebnis genauso: ohne aktuellen Abschluss "
            "gibt es keine Entscheidung, sondern eine Nachforderung."
        ),
        source="Banque de France, Rating-Leitfaden 09/2026, Note X",
        action=(
            "Aktuellen Jahresabschluss erstellen lassen. Bis dahin ist jede weitere "
            "Aufbereitung vergebliche Muehe."
        ),
    )


# Static description of each check, for the methodology document. Kept in step
# with CHECKS by test_rejection_risk.py rather than by construction, because
# the checks themselves only produce text when they fire.
CHECK_CATALOGUE = (
    ("KO01", "Verlust der Haelfte des Stammkapitals",
     "Bilanzielles Eigenkapital < 50% des gezeichneten Kapitals",
     "49 Abs. 3 GmbHG; Banque de France Note 4-/6"),
    ("KO02", "Bilanzielle Ueberschuldung",
     "Bilanzielles Eigenkapital negativ",
     "19 InsO; EBA/GL/2020/06 Tz. 128 a"),
    ("KO03", "Kontokorrentlinie ueberzogen",
     "Inanspruchnahme > eingeraeumte Linie",
     "Artikel 178 CRR (Ausfalldefinition)"),
    ("KO04", "Steuerrueckstaende",
     "Rueckstaende gegenueber dem Finanzamt",
     "EBA/GL/2020/06 Tz. 121 d"),
    ("KO05", "Ruecklastschriften",
     "Ruecklastschriften in den letzten 12 Monaten; ab 3 schwerwiegend",
     "Banque de France Note 8"),
    ("KO06", "Verlustserie",
     "Jahresfehlbetrag im laufenden und im Vorjahr",
     "Banque de France Note 6"),
    ("KO07", "Zinslast bindet das EBITDA",
     "Zinsaufwand >= 50% des EBITDA; ab 100% schwerwiegend",
     "Banque de France Note 6"),
    ("KO08", "Jahresabschluss zu alt",
     "Juengster Abschluss >= 23 Monate alt",
     "Banque de France Note X"),
)

CHECKS = (
    ("KO01", lambda c, r: _stammkapital_check(c)),
    ("KO02", lambda c, r: _ueberschuldung_check(c)),
    ("KO03", lambda c, r: _kontokorrent_check(c)),
    ("KO04", lambda c, r: _steuer_check(c)),
    ("KO05", _zahlungsstoerung_check),
    ("KO06", _verlustserie_check),
    ("KO07", _zinslast_check),
    ("KO08", lambda c, r: _aktualitaet_check(c)),
)

_ORDER = {Schwere.KO: 0, Schwere.SCHWER: 1, Schwere.PRUEFEN: 2}


def screen(case: ClientCase, ratios: RatioSet) -> RejectionScreen:
    """Run every knock-out check. Worst first."""
    found = []
    for _, check in CHECKS:
        reason = check(case, ratios)
        if reason is not None:
            found.append(reason)

    # Negative equity necessarily means more than half the share capital is
    # gone, so reporting both says the same thing twice and buries the more
    # serious one. Over-indebtedness subsumes it.
    codes = {r.code for r in found}
    if "KO02" in codes:
        found = [r for r in found if r.code != "KO01"]

    found.sort(key=lambda r: (r.mitigated, _ORDER[r.severity], r.code))
    return RejectionScreen(reasons=found, checked=len(CHECKS))
