"""Intake questionnaires: what we ask the SME, and what we ask its Steuerberater.

Why two questionnaires, not one
===============================
A trial balance (SuSa) cannot tell us the things that most often decide
fixability: whether a shareholder loan carries a Rangruecktritt, how large the
overdraft limit is, how often it sits at the limit, whether there are tax
arrears. Those facts come from people -- and from two different people with
different reliability:

  * the Unternehmen knows its plans, its lenders and its collateral;
  * the Steuerberater can CONFIRM the accounting facts (Rangruecktritt, tax
    account, BWA cadence) with professional responsibility behind the answer.

Where both answer the same fact, the Steuerberater wins. See
`intake/assemble.py` for the precedence rules and the provenance record.

Every question states `why` it is asked. That text is shown to the client: an
SME owner who understands why a question matters answers it more carefully,
and it is part of the transparency the whole product is built on.

The definitions here are the single source of truth. The web form, the
printable Markdown templates (docs/intake/) and the case builder all read them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..models import LegalForm, Sector

AUDIENCE_UNTERNEHMEN = "unternehmen"
AUDIENCE_STEUERBERATER = "steuerberater"
AUDIENCES = (AUDIENCE_UNTERNEHMEN, AUDIENCE_STEUERBERATER)

QUESTION_TYPES = (
    "text", "textarea", "int", "money", "percent", "date", "month", "bool", "select", "list",
)

PURPOSES = ("Betriebsmittel", "Investition", "Wachstum", "Umschuldung")
FACILITY_TYPES = (
    "Tilgungsdarlehen", "Kontokorrent", "Foerderkredit", "Leasing", "Sonstiges",
)
BWA_FREQUENCIES = ("monatlich", "quartalsweise", "jaehrlich")
KONTENRAHMEN = ("SKR04", "SKR03", "anderer")


@dataclass(frozen=True)
class Question:
    id: str
    label: str
    type: str
    required: bool = False
    help: str = ""
    why: str = ""
    options: tuple[str, ...] = ()
    fields: tuple["Question", ...] = ()          # sub-questions of a "list"
    show_if: Optional[tuple[str, Any]] = None    # (question_id, value)
    unit: str = ""

    def __post_init__(self) -> None:
        if self.type not in QUESTION_TYPES:
            raise ValueError(f"{self.id}: unbekannter Fragetyp {self.type}")
        if self.type == "select" and not self.options:
            raise ValueError(f"{self.id}: Auswahlfrage ohne Optionen")
        if self.type == "list" and not self.fields:
            raise ValueError(f"{self.id}: Listenfrage ohne Felder")

    def as_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "help": self.help,
            "why": self.why,
            "unit": self.unit,
        }
        if self.options:
            d["options"] = list(self.options)
        if self.fields:
            d["fields"] = [f.as_dict() for f in self.fields]
        if self.show_if:
            d["show_if"] = {"question": self.show_if[0], "equals": self.show_if[1]}
        return d


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    intro: str
    questions: tuple[Question, ...]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "intro": self.intro,
            "questions": [q.as_dict() for q in self.questions],
        }


@dataclass(frozen=True)
class Questionnaire:
    audience: str
    title: str
    intro: str
    sections: tuple[Section, ...]

    def questions(self) -> list[Question]:
        return [q for s in self.sections for q in s.questions]

    def question(self, qid: str) -> Question:
        for q in self.questions():
            if q.id == qid:
                return q
        raise KeyError(qid)

    def as_dict(self) -> dict:
        return {
            "audience": self.audience,
            "title": self.title,
            "intro": self.intro,
            "sections": [s.as_dict() for s in self.sections],
        }


# ---------------------------------------------------------------------------
# Fragebogen Unternehmen
# ---------------------------------------------------------------------------

_FACILITY_FIELDS = (
    Question("kreditgeber", "Kreditgeber", "text", required=True,
             help="z. B. Sparkasse Ostalb"),
    Question("art", "Art der Finanzierung", "select", required=True,
             options=FACILITY_TYPES),
    Question("urspruenglicher_betrag", "Urspruenglicher Betrag", "money", unit="EUR"),
    Question("restschuld", "Aktuelle Restschuld bzw. Inanspruchnahme", "money",
             required=True, unit="EUR"),
    Question("zinssatz", "Zinssatz", "percent", required=True, unit="% p.a.",
             help="Bei variablem Zins den aktuellen Satz angeben."),
    Question("tilgung_pro_jahr", "Tilgung pro Jahr", "money", unit="EUR",
             help="Bei Kontokorrent 0."),
    Question("laufzeit_bis", "Laufzeit bis (Jahr)", "int"),
    Question("besichert", "Besichert?", "bool"),
)

FRAGEBOGEN_UNTERNEHMEN = Questionnaire(
    audience=AUDIENCE_UNTERNEHMEN,
    title="Fragebogen fuer das Unternehmen",
    intro=(
        "Diese Angaben ergaenzen Ihre Buchhaltungsdaten um das, was in keiner "
        "Summen- und Saldenliste steht. Bei jeder Frage steht, warum wir sie "
        "stellen. Wenn Sie etwas nicht wissen, lassen Sie das Feld leer -- eine "
        "Luecke ist besser als eine Schaetzung."
    ),
    sections=(
        Section(
            "unternehmen", "1. Unternehmen",
            "Stammdaten fuer die Einordnung nach Branche und Groessenklasse.",
            (
                Question("firmenname", "Firmenname", "text", required=True),
                Question("rechtsform", "Rechtsform", "select", required=True,
                         options=tuple(lf.value for lf in LegalForm)),
                Question("branche", "Branche", "select", required=True,
                         options=tuple(s.value for s in Sector),
                         why="Kennzahlen werden mit dem Branchenmedian verglichen -- "
                             "eine niedrige EK-Quote ist im Gastgewerbe etwas anderes "
                             "als in der IT."),
                Question("mitarbeiter", "Anzahl Mitarbeiter (Vollzeitaequivalente)",
                         "int", required=True),
                Question("gruendungsjahr", "Gruendungsjahr", "int", required=True),
                Question("sitz", "Sitz (Stadt)", "text"),
                Question("land", "Land", "select", options=("DE", "AT")),
                Question("hrb_nummer", "Handelsregisternummer", "text",
                         help="z. B. HRB 12345, Amtsgericht Ulm"),
            ),
        ),
        Section(
            "vorhaben", "2. Finanzierungsvorhaben",
            "Was Sie finanzieren moechten. Das bestimmt, welcher Kreditgebertyp "
            "ueberhaupt passt -- oft staerker als die Kennzahlen.",
            (
                Question("betrag", "Gewuenschter Finanzierungsbetrag", "money",
                         required=True, unit="EUR"),
                Question("zweck", "Verwendungszweck", "select", required=True,
                         options=PURPOSES),
                Question("zweck_beschreibung", "Kurze Beschreibung des Vorhabens",
                         "textarea"),
                Question("laufzeit_jahre", "Gewuenschte Laufzeit", "int", unit="Jahre",
                         why="Die Laufzeit bestimmt die jaehrliche Rate und damit die "
                             "Kapitaldienstfaehigkeit."),
                Question("sicherheiten_wert", "Wert verfuegbarer Sicherheiten", "money",
                         unit="EUR",
                         why="Eine Ablehnung trotz tragfaehiger Zahlen ist oft eine "
                             "Besicherungsfrage -- die ueber Foerderprogramme loesbar ist."),
                Question("sicherheiten_beschreibung", "Welche Sicherheiten?", "textarea",
                         help="Grundschulden, Maschinen, Forderungsabtretung, Buergschaften"),
                Question("benoetigt_in_wochen", "Bis wann wird das Geld benoetigt?",
                         "int", unit="Wochen ab heute"),
                Question("bereits_abgelehnt", "Wurde das Vorhaben bereits abgelehnt?",
                         "bool"),
                Question("ablehnung_details", "Von wem und mit welcher Begruendung?",
                         "textarea", show_if=("bereits_abgelehnt", True),
                         why="Eine dokumentierte Ablehnung beeinflusst die naechste "
                             "Anfrage. Wir muessen sie kennen."),
                Question("hausbank", "Hausbank", "text"),
            ),
        ),
        Section(
            "finanzierungen", "3. Bestehende Finanzierungen",
            "Alle laufenden Kredite, Kontokorrentlinien und Leasingvertraege. "
            "Eine unvollstaendige Liste laesst Ihre Kapitaldienstfaehigkeit besser "
            "aussehen, als die Bank sie sehen wird.",
            (
                Question("darlehen", "Laufende Finanzierungen", "list",
                         fields=_FACILITY_FIELDS,
                         why="Zins und Tilgung aller Darlehen ergeben den Kapitaldienst -- "
                             "die wichtigste einzelne Kennzahl im Bankrating."),
                Question("kontokorrent_limit", "Kontokorrentlimit (Summe aller Linien)",
                         "money", unit="EUR"),
                Question("kontokorrent_inanspruchnahme",
                         "Aktuelle Inanspruchnahme des Kontokorrents", "money", unit="EUR"),
                Question("tage_am_limit", "An wie vielen Tagen der letzten 12 Monate war "
                         "das Kontokorrent (nahezu) ausgeschoepft?", "int", unit="Tage",
                         help="Schaetzung genuegt. Wird durch Kontoumsaetze ersetzt, "
                              "sobald diese vorliegen.",
                         why="Dauerhafte Ausschoepfung ist eines der staerksten "
                             "Warnsignale fuer Banken -- und oft mit einem passenden "
                             "Darlehen leicht behebbar."),
                Question("leasing_verpflichtungen", "Summe laufender Leasingverpflichtungen",
                         "money", unit="EUR"),
            ),
        ),
        Section(
            "gesellschafter", "4. Gesellschafter",
            "Gesellschafterdarlehen werden von Banken je nach Vertragsgestaltung als "
            "Eigen- oder als Fremdkapital gewertet.",
            (
                Question("hat_gesellschafterdarlehen",
                         "Bestehen Darlehen von Gesellschaftern an das Unternehmen?",
                         "bool", required=True),
                Question("gesellschafterdarlehen_betrag", "Hoehe der Gesellschafterdarlehen",
                         "money", unit="EUR", show_if=("hat_gesellschafterdarlehen", True)),
                Question("rangruecktritt", "Ist fuer diese Darlehen ein Rangruecktritt "
                         "vereinbart?", "bool", show_if=("hat_gesellschafterdarlehen", True),
                         help="Eine schriftliche Erklaerung, dass das Darlehen im "
                              "Insolvenzfall hinter allen anderen Glaeubigern steht.",
                         why="Mit Rangruecktritt zaehlt das Darlehen fuer fast alle Banken "
                             "als wirtschaftliches Eigenkapital. Das ist die haeufigste "
                             "einzelne Stellschraube."),
                Question("bereitschaft_einlage", "Waeren Gesellschafter bereit, zusaetzliches "
                         "Kapital einzubringen?", "bool"),
            ),
        ),
        Section(
            "verhalten", "5. Reporting und Zahlungsverhalten",
            "Weiche Faktoren. Sie zaehlen im Bankrating mehr, als die meisten "
            "Unternehmer erwarten -- und sie sind am billigsten zu verbessern.",
            (
                Question("bwa_frequenz", "Wie oft wird eine BWA erstellt?", "select",
                         required=True, options=BWA_FREQUENCIES),
                Question("bwa_stand", "Monat der juengsten BWA", "month", required=True,
                         why="Eine veraltete BWA wird als schwaches internes Reporting "
                             "gelesen."),
                Question("planrechnung_vorhanden", "Gibt es eine aktuelle Planrechnung "
                         "(Plan-GuV / Liquiditaetsplan)?", "bool"),
                Question("zahlungsverzug_tage", "Wie viele Tage zahlen Sie Lieferanten im "
                         "Schnitt nach Faelligkeit?", "int", unit="Tage",
                         help="0, wenn Sie puenktlich zahlen."),
                Question("ruecklastschriften_12m", "Anzahl Ruecklastschriften in den letzten "
                         "12 Monaten", "int"),
                Question("steuerrueckstaende", "Bestehen derzeit Steuerrueckstaende?", "bool",
                         required=True,
                         why="Fuer nahezu jede Bank ein K.-o.-Kriterium. Wir muessen es "
                             "vor der Bank wissen."),
                Question("creditreform_index", "Creditreform-Bonitaetsindex (falls bekannt)",
                         "int", help="Zwischen 100 (sehr gut) und 600 (Zahlungsausfall)."),
            ),
        ),
        Section(
            "einwilligung", "6. Einwilligungen und Kontakt",
            "Ohne diese Angaben koennen wir nicht arbeiten.",
            (
                Question("datenschutz_einwilligung", "Ich willige in die Verarbeitung der "
                         "uebermittelten Daten zum Zweck der Kreditfaehigkeitsanalyse ein.",
                         "bool", required=True),
                Question("steuerberater_kontakt_erlaubt", "Wir duerfen Ihren Steuerberater "
                         "direkt kontaktieren.", "bool",
                         why="Jede Umgliederung braucht die Freigabe Ihres Steuerberaters."),
                Question("steuerberater_kanzlei", "Kanzlei Ihres Steuerberaters", "text"),
                Question("steuerberater_email", "E-Mail Ihres Steuerberaters", "text"),
                Question("ansprechpartner", "Ihr Name", "text", required=True),
                Question("ansprechpartner_email", "Ihre E-Mail", "text", required=True),
                Question("ansprechpartner_telefon", "Ihre Telefonnummer", "text"),
            ),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Fragebogen Steuerberater
# ---------------------------------------------------------------------------

FRAGEBOGEN_STEUERBERATER = Questionnaire(
    audience=AUDIENCE_STEUERBERATER,
    title="Fragebogen fuer die Steuerberatung",
    intro=(
        "Ihr Mandant laesst seine Kreditfaehigkeit analysieren. Wir nehmen keine "
        "Umgliederung oder Neubewertung ohne Ihre Freigabe vor. Die folgenden "
        "Bestaetigungen ersetzen Angaben des Mandanten, wo beide vorliegen."
    ),
    sections=(
        Section(
            "kanzlei", "1. Kanzlei",
            "",
            (
                Question("kanzlei", "Kanzlei", "text", required=True),
                Question("ansprechpartner", "Ansprechpartner", "text", required=True),
                Question("email", "E-Mail", "text", required=True),
                Question("telefon", "Telefon", "text"),
            ),
        ),
        Section(
            "buchhaltung", "2. Buchhaltung und Abschluss",
            "Grundlage fuer das Einlesen der Summen- und Saldenliste.",
            (
                Question("kontenrahmen", "Verwendeter Kontenrahmen", "select", required=True,
                         options=KONTENRAHMEN,
                         why="Die Kontenzuordnung haengt vollstaendig davon ab. Derzeit "
                             "wird nur SKR04 automatisch eingelesen."),
                Question("individuelle_konten", "Gibt es individuelle Kontenanpassungen "
                         "gegenueber dem Standardkontenrahmen?", "bool"),
                Question("individuelle_konten_details", "Welche?", "textarea",
                         show_if=("individuelle_konten", True)),
                Question("jahresabschluss_festgestellt", "Ist der letzte Jahresabschluss "
                         "festgestellt?", "bool", required=True),
                Question("jahresabschluss_stichtag", "Stichtag des letzten Jahresabschlusses",
                         "date"),
                Question("bwa_frequenz", "BWA-Frequenz", "select", options=BWA_FREQUENCIES),
                Question("bwa_stand", "Monat der juengsten verfuegbaren BWA", "month"),
            ),
        ),
        Section(
            "bestaetigungen", "3. Bestaetigungen",
            "Diese Punkte entscheiden haeufig ueber die Einordnung als behebbar oder "
            "nicht behebbar.",
            (
                Question("rangruecktritt_bestaetigt", "Liegt fuer Gesellschafterdarlehen ein "
                         "qualifizierter Rangruecktritt vor?", "select",
                         options=("ja", "nein", "keine Gesellschafterdarlehen")),
                Question("steuerrueckstaende", "Bestehen Steuerrueckstaende?", "bool",
                         required=True),
                Question("stundungsvereinbarung", "Liegt eine Stundungs- oder "
                         "Ratenzahlungsvereinbarung mit dem Finanzamt vor?", "bool",
                         show_if=("steuerrueckstaende", True)),
                Question("planrechnung_vorhanden", "Liegt eine integrierte Planrechnung vor "
                         "oder kann sie erstellt werden?", "bool"),
            ),
        ),
        Section(
            "sondereffekte", "4. Sondereffekte und Einschaetzung",
            "Wir bereinigen nichts automatisch. Diese Angaben fliessen als Hinweis in "
            "die Beratung ein, nicht in die Kennzahlen.",
            (
                Question("einmaleffekte_betrag", "Einmalige, nicht wiederkehrende Aufwendungen "
                         "im letzten Geschaeftsjahr", "money", unit="EUR"),
                Question("einmaleffekte_beschreibung", "Welche?", "textarea"),
                Question("bilanzierungswahlrechte", "Wurden Bilanzierungswahlrechte ausgeuebt, "
                         "die das Eigenkapital wesentlich beeinflussen?", "textarea"),
                Question("besondere_risiken", "Sind Ihnen Risiken bekannt, die aus den Zahlen "
                         "nicht hervorgehen?", "textarea",
                         why="Ein Befund, den die Bank spaeter selbst findet, kostet mehr "
                             "Vertrauen als einer, den wir vorher adressieren."),
                Question("freigabe_umgliederung", "Sie sind bereit, vorgeschlagene "
                         "Umgliederungen (z. B. Rangruecktritt) fachlich zu pruefen.",
                         "bool"),
            ),
        ),
    ),
)

QUESTIONNAIRES: dict[str, Questionnaire] = {
    AUDIENCE_UNTERNEHMEN: FRAGEBOGEN_UNTERNEHMEN,
    AUDIENCE_STEUERBERATER: FRAGEBOGEN_STEUERBERATER,
}


def get_questionnaire(audience: str) -> Questionnaire:
    try:
        return QUESTIONNAIRES[audience]
    except KeyError:
        raise ValueError(
            f"Unbekannte Zielgruppe '{audience}'. Erlaubt: {', '.join(AUDIENCES)}"
        ) from None


# ---------------------------------------------------------------------------
# Answer coercion and validation
# ---------------------------------------------------------------------------


class AnswerError(ValueError):
    pass


def _is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and not raw.strip()) or raw == []


_THOUSANDS_DOT = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def _parse_number(raw: Any, thousands_dot: bool = True) -> float:
    """Parse a number the way a German user types it.

    "750.000" is seven hundred and fifty thousand, not 750.0. A dot followed by
    groups of exactly three digits (and no comma) is a thousands separator.
    Percent fields pass thousands_dot=False, because "4.875" there means 4,875 %.
    """
    if isinstance(raw, bool):
        raise AnswerError("Zahl erwartet")
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(" ", "").replace(" ", "")
    s = s.replace("EUR", "").replace("€", "").replace("%", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif thousands_dot and _THOUSANDS_DOT.match(s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        raise AnswerError(f"'{raw}' ist keine Zahl") from None


def coerce(question: Question, raw: Any) -> Any:
    """Turn a raw answer (form string or JSON value) into a typed value.

    Returns None for blank answers. Percent answers are entered as the number
    people say out loud ("4,8") and returned as a decimal (0.048).
    """
    if _is_blank(raw):
        return None
    t = question.type
    if t in ("text", "textarea"):
        return str(raw).strip()
    if t == "int":
        v = _parse_number(raw)
        if v != int(v):
            raise AnswerError(f"'{raw}' ist keine ganze Zahl")
        if v < 0:
            raise AnswerError("Wert darf nicht negativ sein")
        return int(v)
    if t == "money":
        v = _parse_number(raw)
        if v < 0:
            raise AnswerError("Betrag darf nicht negativ sein")
        return v
    if t == "percent":
        v = _parse_number(raw, thousands_dot=False)
        if not 0 <= v <= 100:
            raise AnswerError("Prozentwert zwischen 0 und 100 erwartet")
        return v / 100.0
    if t == "bool":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("ja", "true", "1", "yes", "j", "on"):
            return True
        if s in ("nein", "false", "0", "no", "n", "off"):
            return False
        raise AnswerError(f"'{raw}' ist weder ja noch nein")
    if t == "select":
        s = str(raw).strip()
        if s not in question.options:
            raise AnswerError(f"'{s}' ist keine zulaessige Auswahl")
        return s
    if t == "date":
        try:
            return date.fromisoformat(str(raw).strip()[:10])
        except ValueError:
            raise AnswerError(f"'{raw}' ist kein Datum (JJJJ-MM-TT)") from None
    if t == "month":
        s = str(raw).strip()
        try:
            if len(s) == 7:          # YYYY-MM
                return date.fromisoformat(s + "-01")
            return date.fromisoformat(s[:10]).replace(day=1)
        except ValueError:
            raise AnswerError(f"'{raw}' ist kein Monat (JJJJ-MM)") from None
    if t == "list":
        if not isinstance(raw, list):
            raise AnswerError("Liste erwartet")
        rows = []
        for i, row in enumerate(raw, start=1):
            if not isinstance(row, dict):
                raise AnswerError(f"Eintrag {i}: Objekt erwartet")
            if all(_is_blank(row.get(f.id)) for f in question.fields):
                continue  # an empty row added in the form and never filled
            parsed = {}
            for f in question.fields:
                try:
                    parsed[f.id] = coerce(f, row.get(f.id))
                except AnswerError as exc:
                    raise AnswerError(f"Eintrag {i}, {f.label}: {exc}") from None
                if f.required and parsed[f.id] is None:
                    raise AnswerError(f"Eintrag {i}: '{f.label}' fehlt")
            rows.append(parsed)
        return rows
    raise AnswerError(f"Fragetyp {t} nicht unterstuetzt")


def _visible(question: Question, raw_answers: dict) -> bool:
    if not question.show_if:
        return True
    qid, expected = question.show_if
    actual = raw_answers.get(qid)
    if isinstance(expected, bool):
        try:
            return coerce(Question(qid, qid, "bool"), actual) is expected
        except AnswerError:
            return False
    return actual == expected


@dataclass
class AnswerCheck:
    values: dict[str, Any] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)       # labels of required, unanswered
    errors: dict[str, str] = field(default_factory=dict)   # question id -> message

    @property
    def complete(self) -> bool:
        return not self.missing and not self.errors

    def as_dict(self) -> dict:
        return {"missing": self.missing, "errors": self.errors, "complete": self.complete}


def check_answers(questionnaire: Questionnaire, raw_answers: dict) -> AnswerCheck:
    """Coerce every answer and report missing required ones.

    Hidden questions (show_if not met) are neither required nor coerced, so a
    stale answer to a question that no longer applies cannot leak into a case.
    """
    result = AnswerCheck()
    for q in questionnaire.questions():
        if not _visible(q, raw_answers):
            continue
        try:
            value = coerce(q, raw_answers.get(q.id))
        except AnswerError as exc:
            result.errors[q.id] = str(exc)
            continue
        if value is None:
            if q.required:
                result.missing.append(q.label)
            continue
        result.values[q.id] = value
    return result
