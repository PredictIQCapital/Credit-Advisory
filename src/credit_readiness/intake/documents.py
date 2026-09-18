"""Document catalogue: every document an engagement needs, from whom, and why.

Follows the blueprint's data requirements: current BWA, 2-3 years of annual
statements, Summen- und Saldenliste, loan agreements, Handelsregisterauszug,
6-12 months of bank transactions, and a Creditreform report.

Two kinds of document, deliberately distinguished:

  * PARSED documents feed numbers into the engine (DATEV SuSa, bank CSV).
    Their format is strict because a misread number becomes a wrong diagnosis.
  * EVIDENCE documents (PDFs) are stored for the advisor to read and for the
    lender package. One exception, with a safeguard: the latest annual
    accounts can be READ (rules or AI, see credit_readiness.ai) to PROPOSE
    figures for the quick check -- but a proposal only becomes an input after
    the company has reviewed and confirmed every figure, and the consistency
    checks pass. An unconfirmed PDF never reaches a ratio.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

SOURCE_UNTERNEHMEN = "unternehmen"
SOURCE_STEUERBERATER = "steuerberater"
SOURCE_BERATER = "berater"          # obtained by us (e.g. Creditreform report)

PARSER_DATEV = "datev_susa"
PARSER_BANK = "bank_csv"

REQUIRED = "pflicht"
RECOMMENDED = "empfohlen"
CONDITIONAL = "bedingt"
OPTIONAL = "optional"


@dataclass(frozen=True)
class DocumentType:
    id: str
    title: str
    source: str
    requirement: str
    formats: tuple[str, ...]            # accepted file extensions, lower case
    description: str
    why: str
    parser: Optional[str] = None
    needs_period: bool = False          # upload must state Stichtag + Monate
    multiple: bool = False              # several files allowed (e.g. 3 Abschluesse)
    min_count: int = 1
    # For CONDITIONAL documents: when do they become required?
    condition_text: str = ""
    condition: Optional[Callable[[dict, dict], bool]] = None

    def is_required(self, sme: dict, stb: dict) -> bool:
        """`sme`/`stb` are the coerced answer values of the two questionnaires."""
        if self.requirement == REQUIRED:
            return True
        if self.requirement == CONDITIONAL and self.condition:
            return bool(self.condition(sme, stb))
        return False

    def accepts(self, filename: str) -> bool:
        return filename.lower().rsplit(".", 1)[-1] in self.formats

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "requirement": self.requirement,
            "formats": list(self.formats),
            "description": self.description,
            "why": self.why,
            "parser": self.parser,
            "needs_period": self.needs_period,
            "multiple": self.multiple,
            "min_count": self.min_count,
            "condition_text": self.condition_text,
        }


def _has_facilities(sme: dict, stb: dict) -> bool:
    return bool(sme.get("darlehen"))


def _has_rangruecktritt(sme: dict, stb: dict) -> bool:
    if stb.get("rangruecktritt_bestaetigt") == "ja":
        return True
    return bool(sme.get("rangruecktritt"))


def _large_request(sme: dict, stb: dict) -> bool:
    return (sme.get("betrag") or 0) >= 100_000


def _tax_arrears(sme: dict, stb: dict) -> bool:
    if "steuerrueckstaende" in stb:
        return bool(stb["steuerrueckstaende"])
    return bool(sme.get("steuerrueckstaende"))


DOCUMENT_TYPES: tuple[DocumentType, ...] = (
    # ------------------------------------------------ from the Steuerberater
    DocumentType(
        id="susa_aktuell",
        title="Summen- und Saldenliste, aktuelles Geschaeftsjahr (DATEV-Export)",
        source=SOURCE_STEUERBERATER,
        requirement=REQUIRED,
        formats=("csv",),
        parser=PARSER_DATEV,
        needs_period=True,
        description="DATEV-Export als CSV (Semikolon-getrennt) mit den Spalten Konto "
                    "und Saldo. Jahresabschluss-SuSa oder aktuelle unterjaehrige SuSa.",
        why="Die Hauptquelle fuer alle Bilanz- und GuV-Kennzahlen. Wird automatisch "
            "eingelesen und auf Plausibilitaet geprueft.",
    ),
    DocumentType(
        id="susa_vorjahr",
        title="Summen- und Saldenliste, Vorjahr (DATEV-Export)",
        source=SOURCE_STEUERBERATER,
        requirement=RECOMMENDED,
        formats=("csv",),
        parser=PARSER_DATEV,
        needs_period=True,
        description="Wie oben, fuer das abgeschlossene Vorjahr.",
        why="Ermoeglicht Trendaussagen (Umsatzentwicklung). Ein Umsatzrueckgang bei "
            "negativer Marge ist ein Befund, den nur der Vorjahresvergleich zeigt.",
    ),
    DocumentType(
        id="bwa_aktuell",
        title="Aktuelle BWA",
        source=SOURCE_STEUERBERATER,
        requirement=REQUIRED,
        formats=("pdf", "csv"),
        description="Betriebswirtschaftliche Auswertung, nicht aelter als 2-3 Monate.",
        why="Banken verlangen eine aktuelle BWA; ihr Alter wird als Qualitaet des "
            "internen Reportings gelesen.",
    ),
    DocumentType(
        id="jahresabschluesse",
        title="Jahresabschluesse der letzten 2-3 Jahre",
        source=SOURCE_STEUERBERATER,
        requirement=REQUIRED,
        formats=("pdf", "png", "jpg", "jpeg"),
        multiple=True,
        min_count=2,
        description="Bilanz, GuV und ggf. Anhang, je Geschaeftsjahr eine Datei. Der juengste "
                    "Abschluss wird fuer den Schnell-Check automatisch ausgelesen.",
        why="Grundlage jeder Kreditentscheidung; Pflichtbestandteil des Kreditantrags.",
    ),
    DocumentType(
        id="steuerkonto",
        title="Steuerkontoauszug oder Bescheinigung in Steuersachen",
        source=SOURCE_STEUERBERATER,
        requirement=RECOMMENDED,
        formats=("pdf",),
        description="Aktueller Auszug des Finanzamts-Steuerkontos.",
        why="Belegt, dass keine Steuerrueckstaende bestehen -- fuer Banken ein "
            "K.-o.-Kriterium.",
    ),
    DocumentType(
        id="stundungsvereinbarung",
        title="Stundungs- oder Ratenzahlungsvereinbarung mit dem Finanzamt",
        source=SOURCE_STEUERBERATER,
        requirement=CONDITIONAL,
        formats=("pdf",),
        description="Schriftliche Vereinbarung zu bestehenden Steuerrueckstaenden.",
        why="Ohne sie ist ein Kreditantrag bei bestehenden Rueckstaenden praktisch "
            "aussichtslos.",
        condition_text="erforderlich, wenn Steuerrueckstaende bestehen",
        condition=_tax_arrears,
    ),
    DocumentType(
        id="planrechnung",
        title="Planrechnung (Plan-GuV, Liquiditaetsplan, Planbilanz)",
        source=SOURCE_STEUERBERATER,
        requirement=CONDITIONAL,
        formats=("pdf", "xlsx", "csv"),
        description="Integrierte Planung fuer mindestens 24 Monate.",
        why="Ab rund 100.000 EUR erwarten Banken einen Blick nach vorn, nicht nur zurueck.",
        condition_text="erforderlich ab 100.000 EUR Finanzierungsvolumen",
        condition=_large_request,
    ),
    # ------------------------------------------------- from the Unternehmen
    DocumentType(
        id="kontoumsaetze",
        title="Kontoumsaetze der letzten 6-12 Monate (CSV-Export)",
        source=SOURCE_UNTERNEHMEN,
        requirement=RECOMMENDED,
        formats=("csv",),
        parser=PARSER_BANK,
        multiple=True,
        description="CSV-Export aus dem Online-Banking, je Geschaeftskonto eine Datei, "
                    "mit Buchungsdatum, Betrag und moeglichst Saldo.",
        why="Die wertvollste einzelne Quelle: Kontodaten sind live und lassen sich "
            "nicht schoenen. Zeigt Ausschoepfung der Linie und Ruecklastschriften.",
    ),
    DocumentType(
        id="darlehensvertraege",
        title="Kredit- und Leasingvertraege",
        source=SOURCE_UNTERNEHMEN,
        requirement=CONDITIONAL,
        formats=("pdf",),
        multiple=True,
        description="Alle laufenden Kredit-, Kontokorrent- und Leasingvertraege.",
        why="Konditionen, Laufzeiten, Sicherheiten und Covenants lassen sich nur aus "
            "den Vertraegen ablesen.",
        condition_text="erforderlich, wenn laufende Finanzierungen angegeben sind",
        condition=_has_facilities,
    ),
    DocumentType(
        id="handelsregisterauszug",
        title="Aktueller Handelsregisterauszug",
        source=SOURCE_UNTERNEHMEN,
        requirement=REQUIRED,
        formats=("pdf",),
        description="Nicht aelter als 3 Monate.",
        why="Standardbestandteil jedes Kreditantrags; belegt Vertretungsbefugnis.",
    ),
    DocumentType(
        id="rangruecktrittserklaerung",
        title="Rangruecktrittserklaerung",
        source=SOURCE_UNTERNEHMEN,
        requirement=CONDITIONAL,
        formats=("pdf",),
        description="Unterzeichnete Erklaerung zum Rangruecktritt der "
                    "Gesellschafterdarlehen.",
        why="Nur mit dem Dokument wertet die Bank das Darlehen als Eigenkapital.",
        condition_text="erforderlich, wenn ein Rangruecktritt angegeben ist",
        condition=_has_rangruecktritt,
    ),
    DocumentType(
        id="sicherheitenaufstellung",
        title="Aufstellung der Sicherheiten",
        source=SOURCE_UNTERNEHMEN,
        requirement=OPTIONAL,
        formats=("pdf", "xlsx", "csv"),
        description="Grundbuchauszuege, Gutachten, Maschinenlisten.",
        why="Bestimmt, ob eine Besicherungsluecke besteht und wie gross sie ist.",
    ),
    DocumentType(
        id="gesellschafterliste",
        title="Gesellschafterliste",
        source=SOURCE_UNTERNEHMEN,
        requirement=OPTIONAL,
        formats=("pdf",),
        description="Aktuelle Gesellschafterliste.",
        why="Eigentuemerstruktur; relevant fuer Buergschaften und Foerderprogramme.",
    ),
    # ---------------------------------------------------- obtained by us
    DocumentType(
        id="creditreform_auskunft",
        title="Creditreform-Auskunft",
        source=SOURCE_BERATER,
        requirement=RECOMMENDED,
        formats=("pdf",),
        description="Wirtschaftsauskunft mit Bonitaetsindex. Wird von uns eingeholt.",
        why="Zeigt, was der Kreditgeber bereits sieht, bevor er die Unterlagen oeffnet. "
            "Den Index bitte zusaetzlich im Fragebogen eintragen.",
    ),
)

DOCUMENT_TYPES_BY_ID = {d.id: d for d in DOCUMENT_TYPES}

SOURCE_LABELS = {
    SOURCE_UNTERNEHMEN: "Unternehmen",
    SOURCE_STEUERBERATER: "Steuerberatung",
    SOURCE_BERATER: "Berater (holen wir ein)",
}


def get_document_type(doc_type: str) -> DocumentType:
    try:
        return DOCUMENT_TYPES_BY_ID[doc_type]
    except KeyError:
        raise ValueError(f"Unbekannter Dokumenttyp '{doc_type}'") from None


@dataclass
class DocumentStatus:
    doc_type: DocumentType
    required: bool
    count: int

    @property
    def satisfied(self) -> bool:
        needed = self.doc_type.min_count if self.required else 1
        return self.count >= needed

    @property
    def outstanding(self) -> bool:
        return self.required and not self.satisfied

    def as_dict(self) -> dict:
        return {
            "id": self.doc_type.id,
            "title": self.doc_type.title,
            "source": self.doc_type.source,
            "requirement": self.doc_type.requirement,
            "required": self.required,
            "count": self.count,
            "min_count": self.doc_type.min_count if self.required else 1,
            "satisfied": self.satisfied,
            "outstanding": self.outstanding,
            "condition_text": self.doc_type.condition_text,
        }


def document_status(
    uploaded_types: list[str], sme_values: dict, stb_values: dict
) -> list[DocumentStatus]:
    """Checklist status for a case, given the doc types uploaded so far."""
    counts: dict[str, int] = {}
    for t in uploaded_types:
        counts[t] = counts.get(t, 0) + 1
    return [
        DocumentStatus(d, d.is_required(sme_values, stb_values), counts.get(d.id, 0))
        for d in DOCUMENT_TYPES
    ]
