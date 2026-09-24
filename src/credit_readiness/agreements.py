"""Agreements a company signs before it gives us any data -- and the proof that it did.

WHY
===
GDPR Art. 7(1) and Art. 5(2): whoever relies on a consent or an
acknowledgement must be able to *demonstrate* it. A ticked box in a form that
can later be edited demonstrates nothing. So every signature is an
append-only record holding who signed, when, from where, which version of
which text, and a SHA-256 fingerprint of the exact text shown. A withdrawal is
a new record, never an edit.

The signature is a simple electronic signature in the sense of eIDAS
Art. 3(10): the signer types their full name and confirms. That is the
standard for terms of use, privacy acknowledgements and consents; none of
these texts needs a qualified signature. The release from the tax advisor's
duty of confidentiality is the one text a lawyer should look at for form
(StBerG §57, StGB §203) -- see docs/regulatory-guardrails.md.

LEGAL STATUS OF THE TEXTS
=========================
Drafts written to the structure the law requires (Art. 13 GDPR for the
privacy notice). They must be reviewed by a German lawyer before the first
real client; the version numbers exist so that a reviewed text can replace a
draft and everyone signs again.

  id                  required            basis
  nutzungsbedingungen always              contract
  datenschutz         always              Art. 13 GDPR notice (acknowledged)
  schweigepflicht     before inviting the Steuerberater
  ki                  optional            Art. 6(1)(a) GDPR consent, revocable
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

SIGNED = "unterzeichnet"
WITHDRAWN = "widerrufen"

PROVIDER = "Credit Readiness Advisory"


@dataclass(frozen=True)
class Agreement:
    id: str
    version: str
    title_de: str
    title_en: str
    summary_en: str
    text_de: str
    required: bool          # before any data is entered
    revocable: bool         # a consent the signer can withdraw
    confirm_de: str         # the sentence next to the checkbox

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text_de.encode("utf-8")).hexdigest()


AGREEMENTS: tuple[Agreement, ...] = (
    Agreement(
        id="nutzungsbedingungen", version="2026-09-v1",
        title_de="Nutzungs- und Auftragsbedingungen",
        title_en="Terms of use and engagement",
        summary_en=("What we do and do not do: an indicative readiness assessment, not a credit "
                    "rating, not a loan promise, no loan brokerage; your duty to supply accurate "
                    "data; fees only for plans you order."),
        text_de="""1. Leistung. Wir erstellen eine richtungsweisende Einschaetzung der Kreditfaehigkeit Ihres Unternehmens auf Grundlage der von Ihnen und Ihrer Steuerberatung bereitgestellten Unterlagen und Angaben. Das Ergebnis ist kein Rating im Sinne der Verordnung (EG) Nr. 1060/2009, keine Ausfallwahrscheinlichkeit und keine Zusage oder Prognose einer Kreditentscheidung. Jede Kreditentscheidung trifft ausschliesslich der jeweilige Kreditgeber.

2. Keine Kreditvermittlung. Wir vermitteln keine Kredite und erhalten keine Provision von Kreditgebern. Empfehlungen zu Kreditgebertypen sind allgemeiner Natur.

3. Ihre Mitwirkung. Sie stellen sicher, dass die uebermittelten Unterlagen und Angaben vollstaendig und richtig sind, und dass Sie berechtigt sind, sie uns zu uebermitteln. Ausgelesene Zahlen gelten erst nach Ihrer Bestaetigung.

4. Verguetung. Der Schnell-Check ist kostenlos. Kostenpflichtige Leistungen (vollstaendiger Bericht, Beratung) entstehen nur durch Ihre ausdrueckliche Bestellung im Portal zu dem dort genannten Preis zuzueglich Umsatzsteuer.

5. Weitergabe durch Sie. Geben Sie Berichte oder die Bankmappe an Dritte weiter, geschieht dies in Ihrer Verantwortung; der Hinweis zur Einordnung (kein Rating, keine Kreditzusage) ist Bestandteil jedes Dokuments und darf nicht entfernt werden.

6. Vertraulichkeit. Wir behandeln alle Unterlagen vertraulich und nutzen sie ausschliesslich fuer Ihren Auftrag.

7. Kuendigung und Loeschung. Sie koennen Ihr Konto jederzeit im Portal loeschen; damit werden Ihre Daten geloescht, soweit keine gesetzliche Aufbewahrungspflicht entgegensteht.

[Entwurf -- vor Einsatz anwaltlich zu pruefen.]""",
        required=True, revocable=False,
        confirm_de="Ich habe die Nutzungs- und Auftragsbedingungen gelesen und akzeptiere sie.",
    ),
    Agreement(
        id="datenschutz", version="2026-09-v1",
        title_de="Datenschutzhinweise (Art. 13 DSGVO)",
        title_en="Privacy notice (Art. 13 GDPR)",
        summary_en=("Who processes your data, why, on which legal basis, who receives it, how "
                    "long it is kept, and your rights (access, rectification, erasure, "
                    "restriction, portability, objection, complaint)."),
        text_de=f"""Verantwortlicher: {PROVIDER} (Anschrift und Kontakt des Datenschutzbeauftragten: vor Einsatz zu ergaenzen).

Zwecke: Analyse der Kreditfaehigkeit Ihres Unternehmens, Erstellung von Berichten und Unterlagen, Kommunikation mit Ihnen und -- nur nach Ihrer Einladung -- mit Ihrer Steuerberatung.

Rechtsgrundlagen: Vertragserfuellung (Art. 6 Abs. 1 lit. b DSGVO); gesetzliche Aufbewahrungspflichten (Art. 6 Abs. 1 lit. c DSGVO); fuer die Auslesung durch einen KI-Dienstleister ausschliesslich Ihre gesonderte Einwilligung (Art. 6 Abs. 1 lit. a DSGVO).

Empfaenger: unser Hosting-Dienstleister in der EU als Auftragsverarbeiter; Ihre Steuerberatung, soweit Sie sie einladen; ein KI-Dienstleister nur mit Ihrer Einwilligung. Keine Weitergabe an Kreditgeber durch uns.

Speicherdauer: fuer die Dauer des Auftrags; danach Loeschung, soweit keine gesetzlichen Aufbewahrungsfristen bestehen (z. B. Rechnungen: 10 Jahre nach § 147 AO).

Ihre Rechte: Auskunft (Art. 15), Berichtigung (Art. 16), Loeschung (Art. 17), Einschraenkung (Art. 18), Datenuebertragbarkeit (Art. 20), Widerspruch (Art. 21), Widerruf erteilter Einwilligungen mit Wirkung fuer die Zukunft (Art. 7 Abs. 3), Beschwerde bei einer Aufsichtsbehoerde (Art. 77).

Pflicht zur Bereitstellung: Ohne die Unterlagen und Angaben koennen wir die Analyse nicht erstellen. Eine automatisierte Entscheidung im Sinne von Art. 22 DSGVO findet nicht statt; das Ergebnis ist eine Einschaetzung, keine Entscheidung ueber einen Kredit.

[Entwurf -- vor Einsatz anwaltlich zu pruefen.]""",
        required=True, revocable=False,
        confirm_de="Ich habe die Datenschutzhinweise zur Kenntnis genommen.",
    ),
    Agreement(
        id="schweigepflicht", version="2026-09-v1",
        title_de="Entbindung der Steuerberatung von der Verschwiegenheitspflicht",
        title_en="Release of the tax advisor from confidentiality",
        summary_en=("Allows your tax advisor to share your accounting data with us and to "
                    "answer our questions about it, for this analysis only. Revocable at any time."),
        text_de="""Ich entbinde die von mir im Portal eingeladene Steuerberatung gegenueber Credit Readiness Advisory von ihrer Verschwiegenheitspflicht (§ 57 Abs. 1 StBerG, § 203 StGB), soweit dies fuer die Kreditfaehigkeitsanalyse meines Unternehmens erforderlich ist.

Umfang: Jahresabschluesse, Summen- und Saldenlisten, betriebswirtschaftliche Auswertungen, Steuerkontoauszuege und Auskuenfte zu diesen Unterlagen.

Zweck: ausschliesslich die Analyse und die damit verbundene Abstimmung. Eine Weitergabe an Dritte ist nicht umfasst.

Widerruf: jederzeit mit Wirkung fuer die Zukunft, im Portal oder in Textform.

Ich bin berechtigt, diese Erklaerung fuer das Unternehmen abzugeben.

[Entwurf -- Form vor Einsatz anwaltlich zu pruefen.]""",
        required=False, revocable=True,
        confirm_de="Ich entbinde meine Steuerberatung im beschriebenen Umfang von der Verschwiegenheitspflicht.",
    ),
    Agreement(
        id="ki", version="2026-09-v1",
        title_de="Einwilligung in die KI-gestuetzte Auslesung",
        title_en="Consent to AI-assisted reading",
        summary_en=("Optional. Allows us to send uploaded annual accounts to an AI provider to "
                    "read the figures. The AI only reads; the assessment uses transparent rules. "
                    "Revocable at any time."),
        text_de="""Ich willige ein, dass hochgeladene Jahresabschluesse zur automatischen Auslesung der Zahlen an einen KI-Dienstleister uebermittelt werden, mit dem ein Auftragsverarbeitungsvertrag besteht.

Die KI liest ausschliesslich Zahlen aus; die Bewertung erfolgt mit transparenten Regeln. Jede ausgelesene Zahl bestaetige ich selbst, bevor sie verwendet wird.

Die Einwilligung ist freiwillig. Ohne sie lesen wir lokal aus oder ich trage die Zahlen selbst ein. Ich kann sie jederzeit mit Wirkung fuer die Zukunft widerrufen (Art. 7 Abs. 3 DSGVO).""",
        required=False, revocable=True,
        confirm_de="Ich willige in die KI-gestuetzte Auslesung ein.",
    ),
)
AGREEMENTS_BY_ID = {a.id: a for a in AGREEMENTS}
REQUIRED_IDS = tuple(a.id for a in AGREEMENTS if a.required)


class AgreementError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def current(records: list[dict]) -> dict[str, dict]:
    """The latest record per agreement id (signed or withdrawn)."""
    out: dict[str, dict] = {}
    for r in records:
        out[r["agreement"]] = r
    return out


def is_signed(records: list[dict], agreement_id: str) -> bool:
    """Signed, not withdrawn, and signed on the version in force."""
    r = current(records).get(agreement_id)
    a = AGREEMENTS_BY_ID[agreement_id]
    return bool(r) and r["action"] == SIGNED and r["version"] == a.version


def missing_required(records: list[dict]) -> list[str]:
    return [i for i in REQUIRED_IDS if not is_signed(records, i)]


def sign(records: list[dict], ids: list[str], name: str, email: str,
         ip: str = "", user_agent: str = "") -> list[dict]:
    """New records for `ids`. `name` is the typed signature."""
    name = " ".join((name or "").split())
    if len(name) < 3 or " " not in name:
        raise AgreementError("Bitte Vor- und Nachnamen als Unterschrift eingeben")
    unknown = [i for i in ids if i not in AGREEMENTS_BY_ID]
    if unknown or not ids:
        raise AgreementError(f"Unbekannte Vereinbarung: {', '.join(unknown) or '-'}")
    at = _now()
    return [{
        "agreement": a.id, "version": a.version, "title": a.title_de, "action": SIGNED,
        "text_sha256": a.sha256, "signature": name, "by": email, "at": at,
        "ip": ip[:64], "user_agent": user_agent[:200],
    } for a in (AGREEMENTS_BY_ID[i] for i in ids)]


def withdraw(records: list[dict], agreement_id: str, email: str, ip: str = "") -> dict:
    a = AGREEMENTS_BY_ID.get(agreement_id)
    if a is None:
        raise AgreementError("Unbekannte Vereinbarung")
    if not a.revocable:
        raise AgreementError("Diese Erklaerung ist Vertragsgrundlage; statt Widerruf das Konto loeschen")
    if not is_signed(records, agreement_id):
        raise AgreementError("Nicht erteilt, daher nichts zu widerrufen")
    return {"agreement": a.id, "version": a.version, "title": a.title_de, "action": WITHDRAWN,
            "text_sha256": a.sha256, "signature": "", "by": email, "at": _now(),
            "ip": ip[:64], "user_agent": ""}


def status(records: list[dict]) -> list[dict]:
    """For the portal: every agreement, whether it is in force, and its latest record."""
    cur = current(records)
    return [{
        "id": a.id, "version": a.version, "title_de": a.title_de, "title_en": a.title_en,
        "summary_en": a.summary_en, "text_de": a.text_de, "confirm_de": a.confirm_de,
        "required": a.required, "revocable": a.revocable, "sha256": a.sha256,
        "signed": is_signed(records, a.id),
        "outdated": bool(cur.get(a.id)) and cur[a.id]["action"] == SIGNED
                    and cur[a.id]["version"] != a.version,
        "record": cur.get(a.id),
    } for a in AGREEMENTS]


def record_markdown(company: str, case_id: str, records: list[dict]) -> str:
    """The proof, as a document the company can keep."""
    lines = [f"# Nachweis der Erklaerungen -- {company}", "",
             f"**Fall:** {case_id}  ", f"**Erstellt:** {_now()}", "",
             "Jede Zeile ist ein unveraenderlicher Eintrag. Der Fingerabdruck (SHA-256) "
             "identifiziert den exakten Wortlaut, der bei der Unterzeichnung angezeigt wurde.", "",
             "| Zeitpunkt (UTC) | Erklaerung | Version | Aktion | Unterschrift | Konto | IP | SHA-256 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in records:
        lines.append(f"| {r['at']} | {r['title']} | {r['version']} | {r['action']} | "
                     f"{r['signature'] or '-'} | {r['by']} | {r['ip'] or '-'} | {r['text_sha256'][:16]}... |")
    lines += ["", "## Wortlaut der geltenden Fassungen", ""]
    for a in AGREEMENTS:
        lines += [f"### {a.title_de} ({a.version})", "", f"SHA-256: `{a.sha256}`", "", a.text_de, ""]
    return "\n".join(lines)


def latest_signature(records: list[dict]) -> Optional[str]:
    signed = [r for r in records if r["action"] == SIGNED]
    return signed[-1]["signature"] if signed else None
