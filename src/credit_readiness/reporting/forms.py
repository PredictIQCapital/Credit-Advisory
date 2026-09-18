"""Printable questionnaires, document checklist and answer templates.

For clients who would rather fill in a form on paper or in an email than use
the portal. Generated from the same definitions as the web form, so the
printed version can never drift from what the engine expects.
"""

from __future__ import annotations

from typing import Any

from ..intake.documents import (
    CONDITIONAL,
    DOCUMENT_TYPES,
    REQUIRED,
    SOURCE_BERATER,
    SOURCE_LABELS,
    SOURCE_STEUERBERATER,
    SOURCE_UNTERNEHMEN,
)
from ..intake.questionnaire import Question, Questionnaire

_TYPE_HINT = {
    "text": "",
    "textarea": "",
    "int": "ganze Zahl",
    "money": "EUR",
    "percent": "% p.a.",
    "date": "TT.MM.JJJJ",
    "month": "MM/JJJJ",
    "bool": "",
    "select": "",
}


def _blank(q: Question) -> str:
    if q.type == "bool":
        return "[ ] ja   [ ] nein"
    if q.type == "select":
        return "   ".join(f"[ ] {o}" for o in q.options)
    hint = q.unit or _TYPE_HINT.get(q.type, "")
    line = "______________________________"
    return f"{line} {hint}".rstrip()


def questionnaire_markdown(q: Questionnaire) -> str:
    out = [f"# {q.title}", "", q.intro, "",
           "Pflichtangaben sind mit **(Pflicht)** markiert.", ""]
    for s in q.sections:
        out += [f"## {s.title}", ""]
        if s.intro:
            out += [s.intro, ""]
        for question in s.questions:
            star = " **(Pflicht)**" if question.required else ""
            cond = ""
            if question.show_if:
                ref = q.question(question.show_if[0]).label
                val = question.show_if[1]
                val_txt = "ja" if val is True else "nein" if val is False else str(val)
                cond = f" *(nur falls \"{ref}\" = {val_txt})*"
            out.append(f"**{question.label}**{star}{cond}")
            out.append("")
            if question.help:
                out.append(f"*{question.help}*")
                out.append("")
            if question.type == "list":
                cols = [f.label for f in question.fields]
                out.append("| " + " | ".join(cols) + " |")
                out.append("|" + "---|" * len(cols))
                for _ in range(4):
                    out.append("| " + " | ".join(" " for _ in cols) + " |")
            elif question.type == "textarea":
                out += ["______________________________________________________________",
                        "", "______________________________________________________________"]
            else:
                out.append(_blank(question))
            out.append("")
            if question.why:
                out.append(f"> Warum wir fragen: {question.why}")
                out.append("")
    out += ["---", "", "Datum, Unterschrift: ______________________________", ""]
    return "\n".join(out)


def _req_label(d) -> str:
    if d.requirement == REQUIRED:
        return f"Pflicht{f' (mind. {d.min_count})' if d.min_count > 1 else ''}"
    if d.requirement == CONDITIONAL:
        return f"bedingt: {d.condition_text}"
    return d.requirement


def documents_markdown() -> str:
    out = ["# Unterlagenliste", "",
           "Welche Unterlagen wir benoetigen, von wem, in welchem Format -- und warum.",
           "",
           "Nur zwei Dokumenttypen werden automatisch ausgewertet: die DATEV-Summen- und "
           "Saldenliste (CSV) und die Kontoumsaetze (CSV). Alle PDF-Unterlagen lesen wir "
           "selbst; aus einem PDF wird nie automatisch eine Zahl uebernommen.", ""]
    for source in (SOURCE_UNTERNEHMEN, SOURCE_STEUERBERATER, SOURCE_BERATER):
        docs = [d for d in DOCUMENT_TYPES if d.source == source]
        out += [f"## Von: {SOURCE_LABELS[source]}", "",
                "| | Unterlage | Erforderlich | Format | Warum |",
                "|---|---|---|---|---|"]
        for d in docs:
            fmt = ", ".join(f.upper() for f in d.formats)
            auto = " (wird automatisch ausgewertet)" if d.parser else ""
            out.append(f"| [ ] | **{d.title}**{auto} | {_req_label(d)} | {fmt} | {d.why} |")
        out.append("")
    return "\n".join(out)


def _template_value(q: Question) -> Any:
    if q.type == "list":
        return [{f.id: None for f in q.fields}]
    return None


def answers_template(q: Questionnaire) -> dict:
    """An empty answers file with every question id, for filling in by hand."""
    tmpl: dict[str, Any] = {
        "_hinweis": (
            f"{q.title}. Werte eintragen, unbekannte Felder auf null lassen. "
            "Prozente als Zahl (4,8 % -> 4.8), Monate als \"JJJJ-MM\", Daten als "
            "\"JJJJ-MM-TT\", ja/nein als true/false."
        ),
    }
    for question in q.questions():
        tmpl[question.id] = _template_value(question)
    return tmpl
