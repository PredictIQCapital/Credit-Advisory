"""Correspondence: document requests and the Steuerberater sign-off letter.

Three letters cover the whole information flow of an engagement:

  1. Unterlagenanforderung an das Unternehmen  -- what is still missing
  2. Anfrage an die Steuerberatung             -- documents + confirmations
  3. Abstimmung mit der Steuerberatung         -- after the diagnostic: every
     proposed change that needs the accountant's (and possibly a lawyer's)
     sign-off. The blueprint is explicit that nothing is reclassified
     unilaterally; this letter is how that rule is put into practice.

All letters are generated from the current case state, so re-generating after
an upload always yields an up-to-date list.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Optional

from ..intake.documents import (
    DOCUMENT_TYPES_BY_ID,
    SOURCE_BERATER,
    SOURCE_STEUERBERATER,
    SOURCE_UNTERNEHMEN,
)


def firm_name() -> str:
    return os.environ.get("CRA_FIRM_NAME", "Credit Readiness Advisory")


def _doc_lines(statuses: list[dict], source: str, only_outstanding: bool) -> list[str]:
    lines = []
    for s in statuses:
        if s["source"] != source:
            continue
        if only_outstanding and not s["outstanding"] and not (
            s["requirement"] in ("empfohlen",) and not s["satisfied"]
        ):
            continue
        d = DOCUMENT_TYPES_BY_ID[s["id"]]
        fmt = ", ".join(f.upper() for f in d.formats)
        need = "erforderlich" if s["required"] else "empfohlen" if s["requirement"] == "empfohlen" else "optional"
        count = f", mind. {s['min_count']} Dateien" if s["required"] and s["min_count"] > 1 else ""
        have = f" -- bereits {s['count']} erhalten" if s["count"] else ""
        lines.append(f"- [ ] **{d.title}** ({need}, {fmt}{count}){have}  ")
        lines.append(f"  {d.description}")
    return lines


def _header(recipient: str, subject: str, today: date) -> list[str]:
    return [
        f"# {subject}",
        "",
        f"**Von:** {firm_name()}  ",
        f"**An:** {recipient}  ",
        f"**Datum:** {today.strftime('%d.%m.%Y')}",
        "",
    ]


def letter_unternehmen(overview: dict, sme: dict, today: Optional[date] = None) -> str:
    today = today or date.today()
    meta = overview["meta"]
    name = sme.get("ansprechpartner") or "Damen und Herren"
    salutation = f"Guten Tag {name}," if sme.get("ansprechpartner") else "Sehr geehrte Damen und Herren,"
    out = _header(meta["company_name"], f"Unterlagen fuer Ihre Kreditfaehigkeitsanalyse ({meta['case_id']})", today)
    out += [salutation, "",
            "vielen Dank fuer Ihr Vertrauen. Damit wir Ihre Unterlagen so auswerten "
            "koennen, wie es ein Kreditgeber tut, fehlen uns noch die folgenden Angaben.", ""]

    missing = overview["missing_answers"]["unternehmen"]
    errors = overview["answer_errors"]["unternehmen"]
    out.append("## 1. Fragebogen")
    out.append("")
    if missing or errors:
        out.append("Bitte ergaenzen Sie im Fragebogen:")
        out.append("")
        out += [f"- {m}" for m in missing]
        out += [f"- {q}: {msg}" for q, msg in errors.items()]
    else:
        out.append("Ihr Fragebogen ist vollstaendig -- vielen Dank.")
    out.append("")

    own = _doc_lines(overview["documents"], SOURCE_UNTERNEHMEN, only_outstanding=True)
    out += ["## 2. Unterlagen von Ihnen", ""]
    out += own or ["Alle Unterlagen, die wir von Ihnen benoetigen, liegen vor."]
    out.append("")

    stb = _doc_lines(overview["documents"], SOURCE_STEUERBERATER, only_outstanding=True)
    out += ["## 3. Unterlagen von Ihrer Steuerberatung", ""]
    if stb:
        if sme.get("steuerberater_kontakt_erlaubt"):
            out.append("Sie haben uns erlaubt, Ihre Steuerberatung direkt anzusprechen. "
                       "Wir fordern dort an:")
        else:
            out.append("Bitte fordern Sie bei Ihrer Steuerberatung an -- oder erlauben Sie "
                       "uns im Fragebogen, sie direkt anzusprechen:")
        out.append("")
        out += stb
    else:
        out.append("Alle Unterlagen der Steuerberatung liegen vor.")
    out += ["",
            "## Wie Sie uns Unterlagen senden",
            "",
            "Bitte nutzen Sie ausschliesslich den sicheren Upload -- nicht E-Mail. "
            "Finanzunterlagen gehoeren nicht in ein ungeschuetztes Postfach.",
            "",
            "Mit freundlichen Gruessen  ",
            firm_name(),
            ""]
    return "\n".join(out)


def letter_steuerberater(overview: dict, sme: dict, today: Optional[date] = None) -> str:
    today = today or date.today()
    meta = overview["meta"]
    kanzlei = sme.get("steuerberater_kanzlei") or "Steuerberatung"
    out = _header(kanzlei, f"Mandant {meta['company_name']}: Unterlagen fuer eine Kreditfaehigkeitsanalyse", today)
    out += ["Sehr geehrte Damen und Herren,", "",
            f"Ihr Mandant **{meta['company_name']}** hat uns mit einer Analyse seiner "
            "Kreditfaehigkeit beauftragt. "
            + ("Er hat uns ausdruecklich erlaubt, Sie direkt anzusprechen. "
               if sme.get("steuerberater_kontakt_erlaubt") else "")
            + "Wir bitten um die folgenden Unterlagen und Bestaetigungen.", "",
            "**Wichtig vorab:** Wir nehmen keine Umgliederung und keine Neubewertung "
            "ohne Ihre fachliche Freigabe vor. Wo unsere Analyse eine Aenderung nahelegt "
            "(etwa einen Rangruecktritt), erhalten Sie von uns eine gesonderte "
            "Abstimmungsvorlage.", ""]

    docs = _doc_lines(overview["documents"], SOURCE_STEUERBERATER, only_outstanding=True)
    out += ["## 1. Unterlagen", ""]
    out += docs or ["Alle Unterlagen liegen bereits vor -- vielen Dank."]
    out += ["",
            "## 2. Hinweise zum DATEV-Export",
            "",
            "- Summen- und Saldenliste als **CSV**, Trennzeichen Semikolon.",
            "- Benoetigt werden mindestens die Spalten **Konto** und **Saldo** "
            "(ein vorzeichenbehafteter Saldo; Haben-Salden negativ).",
            "- Kontenrahmen **SKR04**. Bei SKR03 oder individuellen Kontenplaenen "
            "bitte kurz Bescheid geben -- wir lesen dann nicht automatisch ein.",
            "- Bitte den Stichtag und den Zeitraum (Monate) der SuSa mitteilen.",
            "",
            "## 3. Fragebogen fuer die Steuerberatung",
            ""]
    missing = overview["missing_answers"]["steuerberater"]
    if overview["answers"]["steuerberater"]["answered"] == 0:
        out.append("Bitte fuellen Sie den beiliegenden Fragebogen aus. Er umfasst "
                   "Kontenrahmen, Abschlussstatus, Rangruecktritt, Steuerrueckstaende "
                   "und bekannte Sondereffekte -- rund 10 Minuten.")
    elif missing:
        out.append("Im Fragebogen fehlen noch:")
        out.append("")
        out += [f"- {m}" for m in missing]
    else:
        out.append("Ihr Fragebogen liegt vollstaendig vor -- vielen Dank.")
    out += ["",
            "## Datenschutz",
            "",
            ("Die Einwilligung Ihres Mandanten in die Datenverarbeitung liegt uns vor."
             if sme.get("datenschutz_einwilligung") else
             "Die Datenschutzeinwilligung Ihres Mandanten liegt uns noch NICHT vor. "
             "Bitte senden Sie Unterlagen erst, wenn sie vorliegt."),
            "",
            "Mit freundlichen Gruessen  ",
            firm_name(),
            ""]
    return "\n".join(out)


def letter_abstimmung(result, sme: dict, today: Optional[date] = None) -> str:
    """After the diagnostic: every finding that needs professional sign-off."""
    today = today or date.today()
    case = result.case
    kanzlei = sme.get("steuerberater_kanzlei") or "Steuerberatung"
    out = _header(kanzlei, f"Abstimmung: vorgeschlagene Massnahmen fuer {case.profile.name}", today)
    needs = [f for f in result.findings if f.requires_steuerberater or f.requires_legal]
    out += ["Sehr geehrte Damen und Herren,", "",
            "unsere Analyse hat die unten aufgefuehrten Punkte ergeben. Bevor wir mit "
            "Ihrem Mandanten eine davon umsetzen, bitten wir um Ihre fachliche "
            "Einschaetzung. Nichts davon wird ohne Ihre Freigabe gegenueber einem "
            "Kreditgeber dargestellt.", ""]
    if not needs:
        out += ["Keiner der Befunde erfordert eine Umgliederung oder steuerliche "
                "Pruefung. Diese Nachricht dient Ihrer Information.", ""]
    for f in needs:
        who = []
        if f.requires_steuerberater:
            who.append("steuerliche Pruefung")
        if f.requires_legal:
            who.append("rechtliche Pruefung")
        out += [f"## {f.rule_id} -- {f.title}", "",
                f"**Befund.** {f.observation}", "",
                f"**Vorgeschlagene Massnahme.** {f.remediation}", ""]
        if f.caveat:
            out += [f"> {f.caveat}", ""]
        out += [f"Erforderlich: {', '.join(who)}.", "",
                "[ ] einverstanden   [ ] nicht einverstanden   [ ] Rueckfrage", "",
                "Anmerkung: ______________________________________________", ""]
    out += ["Die vollstaendige Diagnostik stellen wir Ihnen auf Wunsch zur Verfuegung.",
            "", "Mit freundlichen Gruessen  ", firm_name(), ""]
    return "\n".join(out)
