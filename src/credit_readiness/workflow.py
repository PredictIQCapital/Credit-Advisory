"""Engagement workflow: the operations the portal and the CLI both perform.

    create case -> collect answers + documents -> overview / letters
               -> run diagnostic -> Steuerberater sign-off letter
               -> record outcome (the proprietary dataset)

Keeping these here, rather than in the web handlers, means every operation is
testable without HTTP and behaves identically from the command line.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Optional

from .casefile import OUTCOMES, STAGE_IDS, STAGE_LABELS, STAGES, CaseStore, CaseStoreError
from .engine import run_diagnostic
from .ingest.json_intake import load_case
from . import agreements
from .intake import docmatrix
from .intake.assemble import assemble_case
from .intake.documents import (
    SOURCE_BERATER,
    SOURCE_STEUERBERATER,
    SOURCE_UNTERNEHMEN,
    DOCUMENT_TYPES_BY_ID,
    document_status,
)
from .intake.questionnaire import (
    AUDIENCE_STEUERBERATER,
    AUDIENCE_UNTERNEHMEN,
    AnswerError,
    _visible,
    check_answers,
    coerce,
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


def section_progress(audience: str, raw_answers: dict) -> list[dict]:
    """Per-section completeness, for the step tracker of the guided flow."""
    q = get_questionnaire(audience)
    out = []
    for s in q.sections:
        required = answered_required = answered = total = 0
        for question in s.questions:
            if not _visible(question, raw_answers):
                continue
            total += 1
            try:
                value = coerce(question, raw_answers.get(question.id))
            except AnswerError:
                value = None
            if value not in (None, []):
                answered += 1
            if question.required:
                required += 1
                if value is not None:
                    answered_required += 1
        out.append({
            "id": s.id, "title": s.title, "required": required,
            "answered_required": answered_required, "answered": answered, "total": total,
            # A section with no required questions counts as done once anything
            # in it is answered -- an untouched section is never "complete".
            "complete": answered_required == required and answered > 0,
        })
    return out


# ------------------------------------------------------------ document notes
#
# Every document row -- and every cell of the financial-statements grid -- can
# carry a short note, also without a file ("founded 2024, no 2023 accounts").

MAX_DOC_NOTE = 500


def valid_doc_note_key(key: str) -> bool:
    return docmatrix.note_doc_type(key) in DOCUMENT_TYPES_BY_ID


def set_doc_note(store: CaseStore, case_id: str, key: str, note: str) -> dict:
    if not valid_doc_note_key(key):
        raise CaseStoreError(f"Unbekannte Unterlage '{key}'")
    notes = dict(store.get_meta(case_id).get("doc_notes") or {})
    note = (note or "").strip()[:MAX_DOC_NOTE]
    if note:
        notes[key] = note
    else:
        notes.pop(key, None)
    return store.update_meta(case_id, doc_notes=notes)


def set_doc_matrix(store: CaseStore, case_id: str, raw: dict, today: Optional[date] = None) -> dict:
    cfg = dict(store.get_meta(case_id).get("doc_matrix") or {})
    cfg.update(docmatrix.validate_settings(raw, today or date.today()))
    return store.update_meta(case_id, doc_matrix=cfg)


def history(meta: dict, docs: list[dict]) -> list[dict]:
    """What happened on the case, newest first -- for the company's timeline."""
    ev = [{"at": meta.get("created_at"), "kind": "created", "text": "Fall angelegt"}]
    for h in meta.get("stage_history") or []:
        if h["stage"] != "neu":
            ev.append({"at": h["at"], "kind": "stage", "stage": h["stage"], "text": h.get("note", "")})
    for d in docs:
        ev.append({"at": d["uploaded_at"], "kind": "upload", "text": d["filename"],
                   "doc_type": d["doc_type"]})
    for o in meta.get("orders") or []:
        ev.append({"at": o["at"], "kind": "order", "product": o["product"], "text": o.get("note", "")})
    for b in meta.get("bankpack_downloads") or []:
        ev.append({"at": b["at"], "kind": "bankpack", "text": ", ".join(b["sections"])})
    for key, kind in (("quick_check_at", "quick_check"), ("submitted_at", "submitted")):
        if meta.get(key):
            ev.append({"at": meta[key], "kind": kind, "text": ""})
    # Same-second events: the case was created before anything happened on it.
    return sorted((e for e in ev if e["at"]), key=lambda e: (e["at"], e["kind"] != "created"),
                  reverse=True)


# ------------------------------------------------------------ agreements
#
# Nothing is entered before the required agreements are signed (agreements.py
# holds the texts and the rules). Each signature syncs the questionnaire
# answers that express the same consent, so the rest of the engine keeps
# reading one source.

_AGREEMENT_ANSWERS = {
    "datenschutz": "datenschutz_einwilligung",
    "ki": "ki_einwilligung",
    "schweigepflicht": "steuerberater_kontakt_erlaubt",
}


def agreement_records(store: CaseStore, case_id: str) -> list[dict]:
    return store.list_records(case_id, "agreements")


def agreements_ok(store: CaseStore, case_id: str) -> bool:
    return not agreements.missing_required(agreement_records(store, case_id))


def _sync_answers(store: CaseStore, case_id: str, updates: dict) -> None:
    if not updates:
        return
    answers = store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)
    answers.update(updates)
    store.save_answers(case_id, AUDIENCE_UNTERNEHMEN, answers)


def sign_agreements(store: CaseStore, case_id: str, ids: list[str], name: str, email: str,
                    ip: str = "", user_agent: str = "") -> list[dict]:
    records = agreements.sign(agreement_records(store, case_id), ids, name, email, ip, user_agent)
    for r in records:
        store.append_record(case_id, "agreements", r)
    _sync_answers(store, case_id, {_AGREEMENT_ANSWERS[i]: True for i in ids if i in _AGREEMENT_ANSWERS})
    return records


def withdraw_agreement(store: CaseStore, case_id: str, agreement_id: str, email: str,
                       ip: str = "") -> dict:
    record = agreements.withdraw(agreement_records(store, case_id), agreement_id, email, ip)
    store.append_record(case_id, "agreements", record)
    if agreement_id in _AGREEMENT_ANSWERS:
        _sync_answers(store, case_id, {_AGREEMENT_ANSWERS[agreement_id]: False})
    return record


# ------------------------------------------------------------ messages
#
# "Contact us" inside the portal: one thread per case, so every question and
# answer sits next to the documents it is about -- not in someone's inbox.

MESSAGE_TOPICS = ("Frage zum Ergebnis", "Unterlagen", "Termin", "Rechnung und Tarif", "Sonstiges")
MAX_MESSAGE = 4000


def post_message(store: CaseStore, case_id: str, principal, text: str, topic: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise CaseStoreError("Nachricht ist leer")
    if topic and topic not in MESSAGE_TOPICS:
        raise CaseStoreError("Unbekanntes Thema")
    from datetime import datetime, timezone
    import uuid
    # Microseconds: a reply in the same second must still count as unread.
    msg = {"id": uuid.uuid4().hex[:12], "at": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
           "by": principal.email, "name": principal.name, "role": principal.role,
           "topic": topic, "text": text[:MAX_MESSAGE]}
    store.append_record(case_id, "messages", msg)
    mark_read(store, case_id, principal.email, msg["at"])
    return msg


def mark_read(store: CaseStore, case_id: str, email: str, at: Optional[str] = None) -> None:
    from datetime import datetime, timezone
    read = dict(store.get_meta(case_id).get("messages_read") or {})
    read[email] = at or datetime.now(timezone.utc).isoformat(timespec="microseconds")
    store.update_meta(case_id, messages_read=read)


def unread_count(meta: dict, messages: list[dict], email: str) -> int:
    last = (meta.get("messages_read") or {}).get(email, "")
    return sum(1 for m in messages if m["by"] != email and m["at"] > last)


# ------------------------------------------------------------ logo

MAX_LOGO_BYTES = 1_000_000
_LOGO_MAGIC = ((bytes.fromhex("89504e470d0a1a0a"), "png"), (bytes.fromhex("ffd8ff"), "jpg"))


def logo_type(content: bytes) -> Optional[str]:
    """Recognise the image by its bytes, never by the file name. No SVG: it can carry script."""
    for magic, ext in _LOGO_MAGIC:
        if content.startswith(magic):
            return ext
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def set_logo(store: CaseStore, case_id: str, content: Optional[bytes]) -> None:
    if content is None:
        return store.set_logo(case_id, None)
    if len(content) > MAX_LOGO_BYTES:
        raise CaseStoreError("Logo zu gross (max. 1 MB)")
    ext = logo_type(content)
    if ext is None:
        raise CaseStoreError("Logo: bitte PNG, JPG oder WebP")
    store.set_logo(case_id, content, ext)


# ------------------------------------------------------------ bank pack


def build_bank_pack(store: CaseStore, case_id: str, sections: list[str], actor: str = "",
                    today: Optional[date] = None) -> dict:
    """The document a company hands its bank. Logged, because it leaves our hands."""
    from datetime import datetime, timezone
    from .reporting import bankpack

    sections = [s for s in sections if s in bankpack.SECTION_IDS] or list(bankpack.DEFAULT_SECTIONS)
    asm = assemble_case(store, case_id, today=today)
    if not asm.ready:
        return {"ok": False, "blocking": asm.blocking}
    case = load_case(asm.payload)
    try:
        result = run_diagnostic(case, strict=True)
    except ValidationError as exc:
        return {"ok": False, "blocking": [str(i) for i in exc.issues]}
    meta = store.get_meta(case_id)
    titles = {d.id: d.title for d in DOCUMENT_TYPES_BY_ID.values()}
    order = {t: i for i, t in enumerate(DOCUMENT_TYPES_BY_ID)}
    docs = [{"title": titles.get(d["doc_type"], d["doc_type"]), "filename": d["filename"],
             "date": (f"GJ {docmatrix.fiscal_year_of(d)}" if d["doc_type"] in docmatrix.ROW_DOC_TYPES
                      and docmatrix.fiscal_year_of(d) else
                      date.fromisoformat(d["uploaded_at"][:10]).strftime("%d.%m.%Y"))}
            for d in sorted(store.list_documents(case_id), key=lambda d: (order.get(d["doc_type"], 99), d["filename"]))]
    sme = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN),
                        store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)).values
    html = bankpack.render(result, sme, sections=tuple(sections), reviewed=bool(meta.get("report_released")),
                           documents=docs, logo=store.get_logo(case_id), today=today)
    log = list(meta.get("bankpack_downloads") or [])
    log.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "by": actor,
                "sections": sections, "band": result.scorecard.band.value,
                "score": result.scorecard.total_score})
    store.update_meta(case_id, bankpack_downloads=log)
    return {"ok": True, "html": html, "company": case.profile.name}


# ------------------------------------------------------------ score coach

ACTION_STATES = ("offen", "in_arbeit", "erledigt")


def coach_case(store: CaseStore, case_id: str, today: Optional[date] = None):
    """The company's case as the coach scores it; CaseStoreError with the reasons if not ready."""
    asm = assemble_case(store, case_id, today=today)
    if not asm.ready:
        raise CaseStoreError("Noch nicht moeglich: " + " · ".join(asm.blocking))
    return load_case(asm.payload)


def coach_view(store: CaseStore, case_id: str, role: str, today: Optional[date] = None,
               lang: str = "de") -> dict:
    """The coach page: full for the report and advisory plans, a preview otherwise."""
    from . import coach

    meta = store.get_meta(case_id)
    p = coach.plan(coach_case(store, case_id, today), lang)
    status = meta.get("action_status") or {}
    for m in p["measures"]:
        m["status"] = status.get(m["rule"], "offen")
    if coach.entitled(meta, role):
        return {"locked": False, **p}
    preview = [{k: m[k] for k in ("rule", "title", "points", "weeks")} for m in p["measures"][:3]]
    return {"locked": True, "score": p["score"], "band": p["band"], "next_band": p["next_band"],
            "sector": p["sector"], "preview": preview, "more": max(0, len(p["measures"]) - 3)}


def set_action_status(store: CaseStore, case_id: str, rule: str, state: str) -> dict:
    if state not in ACTION_STATES or not re.fullmatch(r"R\d{2}", rule or ""):
        raise CaseStoreError("Unbekannter Status")
    status = dict(store.get_meta(case_id).get("action_status") or {})
    status[rule] = state
    return store.update_meta(case_id, action_status=status)


def case_overview(store: CaseStore, case_id: str, today: Optional[date] = None) -> dict:
    """Everything the portal's case page shows, in one call."""
    meta = store.get_meta(case_id)
    sme_raw, stb_raw, sme, stb = _checks(store, case_id)
    docs = store.list_documents(case_id)
    statuses = [s.as_dict() for s in document_status(
        [d["doc_type"] for d in docs], sme.values, stb.values)]
    notes = meta.get("doc_notes") or {}
    grid = docmatrix.build(docs, notes, docmatrix.settings(meta, today or date.today()))
    done = docmatrix.completion(grid)
    for s in statuses:
        s["files"] = [d for d in docs if d["doc_type"] == s["id"]]
        s["note"] = notes.get(s["id"], "")
        if s["id"] in done:
            # The grid knows years and parts; a plain file count does not.
            s.update(done[s["id"]])
            s["outstanding"] = s["required"] and not s["satisfied"]

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
        "doc_matrix": grid,
        "history": history(meta, docs),
        "agreements": agreements.status(agreement_records(store, case_id)),
        "agreements_missing": agreements.missing_required(agreement_records(store, case_id)),
        "messages": store.list_records(case_id, "messages"),
        "outstanding_documents": outstanding,
        "documents_complete": not any(outstanding.values()),
        "ready_for_diagnosis": asm.ready,
        "blocking": asm.blocking,
        "assembly_notes": asm.notes,
        "latest_summary": json.loads(summary_txt) if summary_txt else None,
        "artifacts": store.list_artifacts(case_id),
        "sections": {
            AUDIENCE_UNTERNEHMEN: section_progress(AUDIENCE_UNTERNEHMEN, sme_raw),
            AUDIENCE_STEUERBERATER: section_progress(AUDIENCE_STEUERBERATER, stb_raw),
        },
        "report_released": bool(meta.get("report_released")),
        "quick_check": json.loads(store.read_artifact(case_id, QUICK_CHECK) or "null"),
        "extraction": json.loads(store.read_artifact(case_id, EXTRACTION) or "null"),
        "figures_confirmed": json.loads(store.read_artifact(case_id, "figures_confirmed.json") or "null"),
        "orders": meta.get("orders") or [],
        "submitted_at": meta.get("submitted_at"),
        "members": meta.get("members") or {},
    }


# ---------------------------------------------------------------------------
# Multi-party operations (portal with accounts)
# ---------------------------------------------------------------------------


def register_client(store: CaseStore, users, company_name: str, name: str, email: str,
                    password: str, account=None) -> tuple[Any, dict]:
    """Self-registration of an SME: account + case + pre-filled contact answers.

    `account` is an already-created principal (Supabase sign-up, which sends
    the confirmation e-mail); without it the account is created here.
    """
    from .auth import ROLE_UNTERNEHMEN

    if not (company_name or "").strip():
        raise CaseStoreError("Firmenname fehlt")
    principal = account or users.create(email, name, ROLE_UNTERNEHMEN, password)
    meta = store.create_case(company_name)
    store.update_meta(meta["case_id"], members={ROLE_UNTERNEHMEN: [principal.email]})
    store.save_answers(meta["case_id"], AUDIENCE_UNTERNEHMEN, {
        "firmenname": company_name.strip(),
        "ansprechpartner": principal.name,
        "ansprechpartner_email": principal.email,
    })
    return principal, store.get_meta(meta["case_id"])


def add_member(store: CaseStore, case_id: str, role: str, email: str) -> dict:
    meta = store.get_meta(case_id)
    members = {k: list(v) for k, v in (meta.get("members") or {}).items()}
    lst = members.setdefault(role, [])
    if email not in lst:
        lst.append(email)
    return store.update_meta(case_id, members=members)


def invite_member(store: CaseStore, users, case_id: str, role: str, email: str,
                  name: str = "") -> dict:
    """Give a client or its tax advisor access to this one case.

    If the person has no account yet, one is created with a one-time password
    that the inviter passes on. A hosted version sends an invitation e-mail
    with a set-password link instead; the portal says so where it shows the
    password.
    """
    import secrets

    from .auth import ROLE_STEUERBERATER, ROLE_UNTERNEHMEN, AuthError, normalise_email

    if role not in (ROLE_UNTERNEHMEN, ROLE_STEUERBERATER):
        raise AuthError("Einladen koennen wir nur Unternehmen und Steuerberater")
    email = normalise_email(email)
    existing = users.get(email)
    temp_password = None
    if existing:
        if existing["role"] != role:
            raise AuthError("Diese E-Mail gehoert zu einem Konto mit anderer Rolle")
    else:
        temp_password = secrets.token_urlsafe(9)
        users.create(email, name or email, role, temp_password)
    add_member(store, case_id, role, email)
    answers = store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)
    if role == ROLE_STEUERBERATER:
        answers.setdefault("steuerberater_email", email)
        if name:
            answers.setdefault("steuerberater_kanzlei", name)
    else:
        answers.setdefault("ansprechpartner_email", email)
        if name:
            answers.setdefault("ansprechpartner", name)
    store.save_answers(case_id, AUDIENCE_UNTERNEHMEN, answers)
    if STAGE_IDS.index(store.get_meta(case_id)["stage"]) < STAGE_IDS.index("unterlagen_angefordert"):
        store.set_stage(case_id, "unterlagen_angefordert", f"Eingeladen: {email}")
    return {"email": email, "role": role, "created": temp_password is not None,
            "temp_password": temp_password}


def invite_steuerberater(store: CaseStore, users, case_id: str, email: str, name: str = "") -> dict:
    from .auth import ROLE_STEUERBERATER
    return invite_member(store, users, case_id, ROLE_STEUERBERATER, email, name)


def submit_case(store: CaseStore, case_id: str, today: Optional[date] = None) -> dict:
    """The client says 'done'. The advisor takes over from here."""
    from datetime import datetime, timezone

    ov = case_overview(store, case_id, today=today)
    if ov["missing_answers"][AUDIENCE_UNTERNEHMEN] or ov["answer_errors"][AUDIENCE_UNTERNEHMEN]:
        raise CaseStoreError("Bitte zuerst alle Pflichtangaben im Fragebogen ergaenzen")
    store.update_meta(case_id, submitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    target = "unterlagen_vollstaendig" if ov["documents_complete"] else "unterlagen_angefordert"
    if STAGE_IDS.index(store.get_meta(case_id)["stage"]) < STAGE_IDS.index(target):
        store.set_stage(case_id, target, "Vom Unternehmen eingereicht")
    return case_overview(store, case_id, today=today)


def release_report(store: CaseStore, case_id: str, released: bool = True) -> dict:
    """Make the report visible to the client -- only after the advisor has read it.

    The blueprint's model is a human advisor translating every flag; the client
    never sees raw engine output that no person has reviewed.
    """
    if released and not store.read_artifact(case_id, "summary.json"):
        raise CaseStoreError("Es gibt noch keine Analyse, die freigegeben werden koennte")
    meta = store.update_meta(case_id, report_released=bool(released))
    if released and STAGE_IDS.index(meta["stage"]) < STAGE_IDS.index("massnahmen_in_umsetzung"):
        store.set_stage(case_id, "massnahmen_in_umsetzung", "Bericht an das Unternehmen freigegeben")
    return store.get_meta(case_id)


def result_record(result, summary: dict, kind: str, actor: str = "") -> dict:
    """One row for app.results: the headline, the model version, every factor."""
    from . import benchmarks

    card = result.scorecard
    generic = result.scorecard_generic
    return {
        "kind": kind, "model_version": summary["model_version"],
        "band": card.band.value, "score": card.total_score,
        "score_generic": generic.total_score if generic else None,
        "band_generic": generic.band.value if generic else None,
        "verdict": result.verdict.value, "sector": result.case.profile.sector.value,
        "nace_code": result.case.profile.nace_code,
        "size_class": benchmarks.size_class(result.ratios.umsatz),
        "coverage": card.coverage, "created_by": actor or None, "summary": summary,
        "factors": [{"factor_key": f.key, "value": f.value, "score": f.score,
                     "weight": round(f.weight, 6), "points_lost": round(f.points_lost, 4),
                     "basis": f.basis} for f in card.factors],
    }


def _record(store: CaseStore, case_id: str, record: dict) -> None:
    """Store a result row. A failure is logged, never shown: the result itself stands."""
    import sys

    try:
        store.record_result(case_id, record)
    except Exception as e:  # noqa: BLE001 -- recording must not break the check
        print(f"[results] {case_id}: result not recorded: {e}", file=sys.stderr)


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
    _record(store, case_id, result_record(result, summary, "report"))

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


# ---------------------------------------------------------------------------
# Quick check (free tier): read annual accounts -> confirm -> instant result
# ---------------------------------------------------------------------------

EXTRACTION = "extraction.json"
QUICK_CHECK = "quickcheck.json"

PRODUCTS = {
    # key: (German label, English label, indicative price in EUR)
    "quick": ("Schnell-Check", "Quick check", 0),
    "report": ("Vollstaendiger Bericht", "Full report", 390),
    "advisor": ("Beratung mit Berater", "Advisor support", 1500),
}


def extract_figures(store: CaseStore, case_id: str, doc_id: Optional[str] = None,
                    provider=None, actor: str = "") -> dict:
    """Read the latest annual accounts and store the PROPOSED figures.

    Nothing here feeds the engine. The proposal waits for the company to
    confirm it (`confirm_figures`).
    """
    from .ai import AIError, get_provider, log_ai_use

    provider = provider or get_provider()
    docs = [d for d in store.list_documents(case_id) if d["doc_type"] == "jahresabschluesse"]
    if doc_id:
        docs = [d for d in docs if d["doc_id"] == doc_id]
    if not docs:
        raise CaseStoreError("Bitte zuerst einen Jahresabschluss hochladen")
    # The newest year's balance sheet; among equals, the latest upload.
    doc = sorted(docs, key=lambda d: (docmatrix.fiscal_year_of(d) or 0,
                                      docmatrix.covers(d, "bilanz"), d["uploaded_at"]))[-1]

    if provider.info.external:
        sme = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN),
                            store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)).values
        if sme.get("ki_einwilligung") is not True:
            raise CaseStoreError(
                "Fuer die KI-Auslesung fehlt die Einwilligung des Unternehmens. "
                "Bitte Einwilligung erteilen oder die Zahlen manuell eintragen.")

    data = store.read_document(case_id, doc["doc_id"])
    try:
        result = provider.extract(data, doc["filename"])
    except AIError as exc:
        log_ai_use(store, case_id, provider, "auslesung", False, str(exc), data, actor)
        raise CaseStoreError(str(exc)) from exc
    log_ai_use(store, case_id, provider, "auslesung", True,
               f"{len(result.fields)} Positionen", data, actor)

    out = result.as_dict()
    out["doc_id"] = doc["doc_id"]
    out["filename"] = doc["filename"]
    store.write_artifact(case_id, EXTRACTION, json.dumps(out, indent=2, ensure_ascii=False))
    return out


def confirm_figures(store: CaseStore, case_id: str, payload: dict, actor: str) -> dict:
    """The human step: the company confirms (and corrects) the figures."""
    from datetime import datetime, timezone

    from .ai import check_figures, parse_confirmed
    from .intake.assemble import CONFIRMED_FIGURES

    figures, period_end, months = parse_confirmed(payload)
    checks = check_figures(figures, months)
    extraction = json.loads(store.read_artifact(case_id, EXTRACTION) or "{}")
    proposed = {k: v.get("value") for k, v in (extraction.get("fields") or {}).items()}
    corrected = sorted(k for k, v in figures.items()
                       if proposed.get(k) is not None and abs(proposed[k] - v) > 0.5)
    record = {
        "figures": figures,
        "period_end": period_end.isoformat(),
        "period_months": months,
        "confirmed_by": actor,
        "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": extraction.get("method", "manuell"),
        "method_label": extraction.get("provider_label", "manuelle Eingabe"),
        "source_doc": extraction.get("filename"),
        "corrected_fields": corrected,
        "checks": checks,
    }
    store.write_artifact(case_id, CONFIRMED_FIGURES, json.dumps(record, indent=2, ensure_ascii=False))
    return record


def run_quick_check(store: CaseStore, case_id: str, today: Optional[date] = None) -> dict:
    """Instant, automated result: band + the three weightiest findings.

    Deliberately partial. No simulation, no lender routing, no full report:
    those are in the full report, which a person reviews before release.
    """
    from datetime import datetime, timezone

    asm = assemble_case(store, case_id, today=today)
    if not asm.ready:
        return {"ok": False, "stage": "assembly", "blocking": asm.blocking}
    case = load_case(asm.payload)
    try:
        result = run_diagnostic(case, strict=True)
    except ValidationError as exc:
        return {"ok": False, "stage": "validation", "blocking": [str(i) for i in exc.issues]}
    s = result_summary(result)
    order = {"kritisch": 0, "wesentlich": 1}
    ranked = sorted(s["findings"], key=lambda f: order.get(f["severity"], 2))
    quick = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "band": s["band"],
        "band_interpretation": s["band_interpretation"],
        "coverage": s["coverage"],
        "verdict": s["verdict"],
        "engageable": s["engageable"],
        "top_findings": ranked[:3],
        "more_findings": max(0, len(ranked) - 3),
        "score": s["score"],
        "scoring_basis": s["scoring_basis"],
        "score_generic": s["score_generic"],
        "band_generic": s["band_generic"],
        "key_ratios": s["key_ratios"],
        "benchmark": s["benchmark"],
        # The free check shows where the biggest levers are; the full list, the
        # simulation and the lender fit stay in the paid report.
        "improvements": s["improvements"][:3],
        "projection": s["projection"],
        "data_notes": asm.notes,
        "disclaimer": s["disclaimer"],
        "model_version": s["model_version"],
    }
    store.write_artifact(case_id, QUICK_CHECK, json.dumps(quick, indent=2, ensure_ascii=False))
    _record(store, case_id, result_record(result, s, "quick"))
    store.update_meta(case_id, quick_check_at=quick["generated_at"])
    return {"ok": True, "quick_check": quick}


def place_order(store: CaseStore, case_id: str, product: str, actor: str, note: str = "") -> dict:
    """Record an order for the next tier. Invoiced until a payment provider is connected.

    An order is a binding request the advisor confirms and invoices; Stripe,
    Mollie or similar plug in here later.
    """
    from datetime import datetime, timezone

    if product not in ("report", "advisor"):
        raise CaseStoreError("Unbekanntes Produkt")
    meta = store.get_meta(case_id)
    orders = list(meta.get("orders") or [])
    if any(o["product"] == product for o in orders):
        raise CaseStoreError("Bereits bestellt")
    orders.append({
        "product": product,
        "price_eur": PRODUCTS[product][2],
        "status": "bestellt",
        "payment": "Rechnung",
        "note": (note or "")[:500],
        "by": actor,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    store.update_meta(case_id, orders=orders)
    if STAGE_IDS.index(store.get_meta(case_id)["stage"]) < STAGE_IDS.index("unterlagen_angefordert"):
        store.set_stage(case_id, "unterlagen_angefordert", f"Bestellt: {PRODUCTS[product][0]}")
    return store.get_meta(case_id)


def explain_result(store: CaseStore, case_id: str, lang: str, question: Optional[str],
                   which: str, actor: str, provider=None) -> dict:
    """Plain-language explanation of a quick check or a released report."""
    from .ai import explain, get_provider, log_ai_use

    provider = provider or get_provider()
    name = QUICK_CHECK if which == "quick" else "summary.json"
    raw = store.read_artifact(case_id, name)
    if not raw:
        raise CaseStoreError("Noch kein Ergebnis vorhanden")
    summary = json.loads(raw)
    if which == "quick":
        summary = {**summary, "findings": summary.get("top_findings", [])}

    def log(purpose, ok, detail):
        log_ai_use(store, case_id, provider, purpose, ok, detail,
                   (question or "").encode("utf-8"), actor)

    return explain(provider, summary, "en" if lang == "en" else "de", question, log=log)


def delete_client_data(store: CaseStore, users, email: str) -> list[str]:
    """Art. 17 GDPR: erase the company's cases and its account.

    Cases the company is a member of are deleted completely, documents
    included. The outcome log keeps its pseudonymous row (case id, sector,
    figures -- no names or documents); docs/ai-and-data-protection.md explains
    why and how it is removed on explicit request.
    """
    from .auth import ROLE_UNTERNEHMEN

    deleted = []
    for meta in store.list_cases():
        if email in (meta.get("members") or {}).get(ROLE_UNTERNEHMEN, []):
            store.delete_case(meta["case_id"])
            deleted.append(meta["case_id"])
    users.delete(email)
    return deleted
