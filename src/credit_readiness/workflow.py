"""Engagement workflow: the operations the portal and the CLI both perform.

    create case -> collect answers + documents -> overview / letters
               -> run diagnostic -> Steuerberater sign-off letter
               -> record outcome (the proprietary dataset)

Keeping these here, rather than in the web handlers, means every operation is
testable without HTTP and behaves identically from the command line.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from .casefile import OUTCOMES, STAGE_IDS, STAGE_LABELS, STAGES, CaseStore, CaseStoreError
from .engine import run_diagnostic
from .ingest.json_intake import load_case
from .intake.assemble import assemble_case
from .intake.documents import (
    SOURCE_BERATER,
    SOURCE_STEUERBERATER,
    SOURCE_UNTERNEHMEN,
    document_status,
)
from .intake.questionnaire import (
    AUDIENCE_STEUERBERATER,
    AUDIENCE_UNTERNEHMEN,
    check_answers,
    get_questionnaire,
)
from .reporting.html import markdown_to_html
from .reporting.letters import letter_abstimmung, letter_steuerberater, letter_unternehmen
from .reporting.report import render_markdown
from .reporting.summary import result_summary
from .validation import ValidationError

LETTERS = {
    "anforderung_unternehmen": "Unterlagenanforderung an das Unternehmen",
    "anforderung_steuerberater": "Anfrage an die Steuerberatung",
    "abstimmung_steuerberater": "Abstimmung der Massnahmen mit der Steuerberatung",
}


def _checks(store: CaseStore, case_id: str):
    sme_raw = store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)
    stb_raw = store.load_answers(case_id, AUDIENCE_STEUERBERATER)
    sme = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN), sme_raw)
    stb = check_answers(get_questionnaire(AUDIENCE_STEUERBERATER), stb_raw)
    return sme_raw, stb_raw, sme, stb


def _answer_stats(questionnaire, check) -> dict:
    total = len(questionnaire.questions())
    return {
        "answered": len(check.values),
        "total": total,
        "missing_required": len(check.missing),
        "errors": len(check.errors),
        "complete": check.complete,
    }


def case_overview(store: CaseStore, case_id: str, today: Optional[date] = None) -> dict:
    """Everything the portal's case page shows, in one call."""
    meta = store.get_meta(case_id)
    sme_raw, stb_raw, sme, stb = _checks(store, case_id)
    docs = store.list_documents(case_id)
    statuses = [s.as_dict() for s in document_status(
        [d["doc_type"] for d in docs], sme.values, stb.values)]
    for s in statuses:
        s["files"] = [d for d in docs if d["doc_type"] == s["id"]]

    asm = assemble_case(store, case_id, today=today)
    summary_txt = store.read_artifact(case_id, "summary.json")

    outstanding = {
        src: [s["title"] for s in statuses if s["source"] == src and s["outstanding"]]
        for src in (SOURCE_UNTERNEHMEN, SOURCE_STEUERBERATER, SOURCE_BERATER)
    }
    return {
        "meta": meta,
        "stage_label": STAGE_LABELS.get(meta["stage"], meta["stage"]),
        "stages": [{"id": s, "label": label} for s, label in STAGES],
        "answers": {
            AUDIENCE_UNTERNEHMEN: _answer_stats(get_questionnaire(AUDIENCE_UNTERNEHMEN), sme),
            AUDIENCE_STEUERBERATER: _answer_stats(get_questionnaire(AUDIENCE_STEUERBERATER), stb),
        },
        "raw_answers": {AUDIENCE_UNTERNEHMEN: sme_raw, AUDIENCE_STEUERBERATER: stb_raw},
        "missing_answers": {AUDIENCE_UNTERNEHMEN: sme.missing, AUDIENCE_STEUERBERATER: stb.missing},
        "answer_errors": {AUDIENCE_UNTERNEHMEN: sme.errors, AUDIENCE_STEUERBERATER: stb.errors},
        "documents": statuses,
        "outstanding_documents": outstanding,
        "documents_complete": not any(outstanding.values()),
        "ready_for_diagnosis": asm.ready,
        "blocking": asm.blocking,
        "assembly_notes": asm.notes,
        "latest_summary": json.loads(summary_txt) if summary_txt else None,
        "artifacts": store.list_artifacts(case_id),
    }


def run_case_diagnostic(
    store: CaseStore, case_id: str, today: Optional[date] = None, strict: bool = True
) -> dict:
    """Assemble, validate, diagnose, and write every output artifact.

    Returns {"ok": bool, ...}. Failure is a normal return value with reasons,
    not an exception: "we cannot analyse this yet, because ..." is information
    the advisor needs to act on.
    """
    asm = assemble_case(store, case_id, today=today)
    if not asm.ready:
        return {"ok": False, "stage": "assembly", "blocking": asm.blocking, "notes": asm.notes}

    case = load_case(asm.payload)
    try:
        result = run_diagnostic(case, strict=strict)
    except ValidationError as exc:
        return {
            "ok": False,
            "stage": "validation",
            "blocking": [str(i) for i in exc.issues],
            "notes": asm.notes,
        }

    data_basis = asm.as_dict()
    md = render_markdown(result, data_basis=data_basis)
    summary = result_summary(result)
    title = f"Kreditfaehigkeits-Diagnostik {case.profile.name}"

    store.write_artifact(case_id, "case.json", json.dumps(asm.payload, indent=2, ensure_ascii=False))
    store.write_artifact(case_id, "assembly.json", json.dumps(data_basis, indent=2, ensure_ascii=False))
    store.write_artifact(case_id, "diagnostik.md", md)
    store.write_artifact(case_id, "diagnostik.html", markdown_to_html(md, title))
    store.write_artifact(case_id, "summary.json", json.dumps(summary, indent=2, ensure_ascii=False))

    sme = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN),
                        store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)).values
    abst = letter_abstimmung(result, sme, today=today)
    store.write_artifact(case_id, "abstimmung_steuerberater.md", abst)
    store.write_artifact(case_id, "abstimmung_steuerberater.html",
                         markdown_to_html(abst, LETTERS["abstimmung_steuerberater"]))

    meta = store.get_meta(case_id)
    if STAGE_IDS.index(meta["stage"]) < STAGE_IDS.index("diagnostik_erstellt"):
        store.set_stage(case_id, "diagnostik_erstellt",
                        f"Band {summary['band']}, {summary['verdict']}")
    return {"ok": True, "summary": summary, "notes": asm.notes,
            "warnings": summary["warnings"]}


def generate_letters(store: CaseStore, case_id: str, today: Optional[date] = None) -> dict:
    """(Re)generate the two request letters from the current case state."""
    overview = case_overview(store, case_id, today=today)
    sme = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN),
                        store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)).values
    letters = {
        "anforderung_unternehmen": letter_unternehmen(overview, sme, today=today),
        "anforderung_steuerberater": letter_steuerberater(overview, sme, today=today),
    }
    for name, md in letters.items():
        store.write_artifact(case_id, f"{name}.md", md)
        store.write_artifact(case_id, f"{name}.html", markdown_to_html(md, LETTERS[name]))
    return letters


def record_outcome(store: CaseStore, case_id: str, fields: dict[str, Any]) -> dict:
    """Append the engagement's outcome to the outcome log and close the case.

    The row is built from the stored diagnostic, so the log records what the
    engine said at the time -- not a later re-run with different rules.
    """
    outcome = fields.get("outcome")
    if outcome not in OUTCOMES:
        raise CaseStoreError(f"Ergebnis muss eines von {', '.join(OUTCOMES)} sein")
    summary_txt = store.read_artifact(case_id, "summary.json")
    if not summary_txt:
        raise CaseStoreError("Vor dem Ergebnis muss eine Diagnostik erstellt werden")
    s = json.loads(summary_txt)
    case_txt = store.read_artifact(case_id, "case.json")
    payload = json.loads(case_txt) if case_txt else {}
    row = {
        "case_id": case_id,
        "date_recorded": date.today().isoformat(),
        "sector": s["sector"],
        "employees": payload.get("profile", {}).get("employees", ""),
        "revenue_eur": round(s["key_ratios"]["umsatz"] or 0),
        "band_before": s["band"],
        "score_before": s["score"],
        "verdict": s["verdict"],
        "findings": ";".join(f["rule"] for f in s["findings"]),
        "remediation_applied": fields.get("remediation_applied", ""),
        "band_after": s["band_after_remediation"],
        "score_after": s["score_after_remediation"],
        "lender_type_routed": fields.get("lender_type_routed") or s.get("top_lender_key_after") or "",
        "outcome": outcome,
        "facility_amount_eur": fields.get("facility_amount_eur", ""),
        "rate_pct": fields.get("rate_pct", ""),
        "weeks_to_decision": fields.get("weeks_to_decision", ""),
        "notes": fields.get("notes", ""),
    }
    store.append_outcome(row)
    if outcome != "PENDING":
        store.set_stage(case_id, "abgeschlossen", f"Ergebnis: {outcome}")
    return row
