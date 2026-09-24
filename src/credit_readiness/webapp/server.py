"""Local web application: public website, login, and the three-party portal.

    python -m credit_readiness serve           real data in data/clients/
    python -m credit_readiness serve --demo    fictional demo data in data/demo/

Pages
=====
    /            public website (what we do, for SMEs)
    /investors   investor one-pager
    /app         the portal: login / registration, then a role-specific view

Roles and permissions (enforced here, on every request -- the front end only
hides what a role cannot do; it never decides):

    action                         berater  unternehmen        steuerberater
    list / open cases              all      own case(s)        invited case(s)
    answer questionnaire           both     'unternehmen'      'steuerberater'
    upload documents               all      company + tax adv. tax-advisor docs
    delete a document              all      own uploads        own uploads
    invite                         both     tax advisor        -
    submit case                    yes      yes                -
    run analysis, letters, stage,
      outcome, release report      yes      -                  -
    read report                    yes      after release      after release

Scope
=====
Standard library only, bound to 127.0.0.1. Not yet for the open internet:
hosting needs TLS, encryption at rest, EU hosting, a database-backed CaseStore
and UserStore, e-mail invitations and audit logging. See
docs/regulatory-guardrails.md. All business logic lives in workflow.py, so a
production framework replaces this file only.
"""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import re
import threading
import traceback
from datetime import date
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from .. import workflow as wf
from ..auth import (
    ROLE_BERATER,
    ROLE_STEUERBERATER,
    ROLE_UNTERNEHMEN,
    AuthError,
    Principal,
    SessionManager,
    UserStore,
    can_access_case,
)
from ..casefile import (
    MAX_UPLOAD_BYTES,
    OUTCOMES,
    STAGES,
    CaseNotFound,
    CaseStore,
    CaseStoreError,
    LocalCaseStore,
)
from ..intake.documents import DOCUMENT_TYPES, DOCUMENT_TYPES_BY_ID, SOURCE_LABELS
from ..intake.questionnaire import AUDIENCES, QUESTIONNAIRES
from ..intake.translations_en import document_with_english, questionnaire_with_english
from ..reporting.forms import documents_markdown, questionnaire_markdown
from ..reporting.html import markdown_to_html
from ..routing import LENDERS

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = int(MAX_UPLOAD_BYTES * 1.4) + 64 * 1024     # base64 overhead
COOKIE = "cra_session"

PAGES = {"/": "index.html", "/investors": "investors.html", "/app": "app.html",
         "/sicherheit": "sicherheit.html", "/security": "sicherheit.html"}

# What each role may upload, by document source.
UPLOAD_SOURCES = {
    ROLE_UNTERNEHMEN: {"unternehmen", "steuerberater"},   # SMEs often forward their accountant's files
    ROLE_STEUERBERATER: {"steuerberater"},
}
REPORT_ARTIFACTS = {"diagnostik.html", "diagnostik.md", "summary.json"}
STB_ARTIFACTS = {"anforderung_steuerberater.html", "anforderung_steuerberater.md",
                 "abstimmung_steuerberater.html", "abstimmung_steuerberater.md"}

_CASE = r"(?P<cid>CRA-\d{4}-\d{4})"
_ROUTE_TABLE = [
    ("GET", r"/api/meta", "meta"),
    ("GET", r"/api/auth/me", "me"),
    ("POST", r"/api/auth/login", "login"),
    ("POST", r"/api/auth/logout", "logout"),
    ("POST", r"/api/auth/register", "register"),
    ("GET", r"/api/cases", "list_cases"),
    ("POST", r"/api/cases", "create_case"),
    ("GET", rf"/api/cases/{_CASE}", "get_case"),
    ("PUT", rf"/api/cases/{_CASE}/answers/(?P<aud>[a-z]+)", "save_answers"),
    ("POST", rf"/api/cases/{_CASE}/documents", "upload"),
    ("GET", rf"/api/cases/{_CASE}/documents/(?P<doc>[a-f0-9]{{12}})", "download"),
    ("DELETE", rf"/api/cases/{_CASE}/documents/(?P<doc>[a-f0-9]{{12}})", "delete_doc"),
    ("POST", rf"/api/cases/{_CASE}/invite", "invite"),
    ("POST", rf"/api/cases/{_CASE}/submit", "submit"),
    ("POST", rf"/api/cases/{_CASE}/stage", "stage"),
    ("POST", rf"/api/cases/{_CASE}/diagnose", "diagnose"),
    ("POST", rf"/api/cases/{_CASE}/letters", "letters"),
    ("POST", rf"/api/cases/{_CASE}/release", "release"),
    ("POST", rf"/api/cases/{_CASE}/outcome", "outcome"),
    ("POST", rf"/api/cases/{_CASE}/extract", "extract"),
    ("PUT", rf"/api/cases/{_CASE}/figures", "figures"),
    ("POST", rf"/api/cases/{_CASE}/quickcheck", "quickcheck"),
    ("POST", rf"/api/cases/{_CASE}/order", "order"),
    ("POST", rf"/api/cases/{_CASE}/explain", "explain"),
    ("DELETE", r"/api/account", "delete_account"),
    ("GET", rf"/api/cases/{_CASE}/artifacts/(?P<name>[a-z0-9_\-]+\.(?:md|html|json|csv))", "artifact"),
    ("GET", r"/forms/(?P<form>unternehmen|steuerberater|unterlagen)\.html", "form"),
]
ROUTES = [(m, re.compile("^" + p + "$"), h) for m, p, h in _ROUTE_TABLE]
PUBLIC_HANDLERS = {"meta", "me", "login", "logout", "register", "form"}


MAX_NOTE_CHARS = 500


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def meta_payload(demo: bool = False) -> dict:
    payload = {
        "questionnaires": {a: questionnaire_with_english(QUESTIONNAIRES[a].as_dict()) for a in AUDIENCES},
        "documents": [document_with_english(d.as_dict()) for d in DOCUMENT_TYPES],
        "source_labels": SOURCE_LABELS,
        "stages": [{"id": s, "label": label} for s, label in STAGES],
        "outcomes": list(OUTCOMES),
        "letters": wf.LETTERS,
        "lenders": [{"key": lp.key, "name": lp.name} for lp in LENDERS],
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "demo": demo,
        "ai": _ai_info(),
        "figure_fields": _figure_fields(),
        "products": {k: {"de": v[0], "en": v[1], "price_eur": v[2]} for k, v in wf.PRODUCTS.items()},
    }
    if demo:
        from ..demo import DEMO_HINTS, DEMO_PASSWORD, DEMO_USERS
        payload["demo_password"] = DEMO_PASSWORD
        payload["demo_accounts"] = [
            {"email": e, "name": n, "role": r, "hint_de": DEMO_HINTS[e][0], "hint_en": DEMO_HINTS[e][1]}
            for e, n, r, _ in DEMO_USERS
        ]
    return payload


def _ai_info() -> dict:
    from ..ai import get_provider
    info = get_provider().info
    return {"key": info.key, "label": info.label, "external": info.external, "model": info.model}


def _figure_fields() -> list[dict]:
    from ..ai.extraction import FIELDS
    return [{"key": f.key, "statement": f.statement, "label_de": f.label_de, "label_en": f.label_en}
            for f in FIELDS]


def view_for(principal: Principal, ov: dict) -> dict:
    """Strip what a role must not see from a case overview."""
    if principal.is_berater:
        return ov
    v = dict(ov)
    released = ov["report_released"]
    if not released:
        v["latest_summary"] = None
    v["assembly_notes"] = []
    v["blocking"] = []
    # A company may see who it invited; a tax advisor does not need the list.
    v["members"] = ov["members"] if principal.role == ROLE_UNTERNEHMEN else {}
    allowed = REPORT_ARTIFACTS if released else set()
    if principal.role == ROLE_STEUERBERATER:
        allowed = allowed | STB_ARTIFACTS
        v["raw_answers"] = {"steuerberater": ov["raw_answers"]["steuerberater"]}
        v["quick_check"] = v["extraction"] = v["figures_confirmed"] = None
        v["orders"] = []
    else:
        v["raw_answers"] = {"unternehmen": ov["raw_answers"]["unternehmen"]}
    v["artifacts"] = [a for a in ov["artifacts"] if a in allowed]
    return v


class Handler(BaseHTTPRequestHandler):
    server_version = "CreditReadiness/0.3"
    store: CaseStore
    users: UserStore
    sessions: SessionManager
    today: Optional[date] = None
    demo: bool = False
    lock = threading.Lock()

    # ---------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args: Any) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "frame-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'none'",
        )
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any, extra: dict | None = None) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra)

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Anfrage zu gross")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Ungueltiges JSON") from None
        return data

    def _obj(self) -> dict:
        body = self._body()
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Objekt erwartet")
        return body

    def _check_origin(self) -> None:
        """Reject cross-site writes (belt and braces next to SameSite=Strict)."""
        origin = self.headers.get("Origin")
        if origin is not None and urlparse(origin).netloc != self.headers.get("Host", ""):
            raise ApiError(HTTPStatus.FORBIDDEN, "Fremder Ursprung abgelehnt")

    def _token(self) -> Optional[str]:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        c = SimpleCookie()
        try:
            c.load(raw)
        except Exception:  # noqa: BLE001 - malformed cookie header
            return None
        return c[COOKIE].value if COOKIE in c else None

    def _principal(self) -> Optional[Principal]:
        return self.sessions.get(self._token())

    def _cookie_header(self, token: str, max_age: int) -> dict:
        return {"Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"}

    # --------------------------------------------------------- dispatch
    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        path = unquote(urlparse(self.path).path)
        try:
            if method != "GET":
                self._check_origin()
            for m, pattern, handler in ROUTES:
                match = pattern.match(path)
                if match and m == method:
                    principal = self._principal()
                    if handler not in PUBLIC_HANDLERS and principal is None:
                        raise ApiError(HTTPStatus.UNAUTHORIZED, "Bitte anmelden")
                    return getattr(self, "h_" + handler)(principal, **match.groupdict())
            if method == "GET":
                return self._static(path)
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        except ApiError as e:
            self._json(e.status, {"error": e.message})
        except CaseNotFound as e:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(e)})
        except (CaseStoreError, AuthError, ValueError) as e:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - never leak a stack trace to the page
            traceback.print_exc()
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Interner Fehler: {type(e).__name__}"})

    # ------------------------------------------------------ authorisation
    def _case(self, principal: Principal, cid: str) -> dict:
        meta = self.store.get_meta(cid)
        if not can_access_case(principal, meta):
            # 404, not 403: do not confirm that someone else's case exists.
            raise ApiError(HTTPStatus.NOT_FOUND, f"Fall {cid} nicht gefunden")
        return meta

    @staticmethod
    def _require(principal: Principal, *roles: str) -> None:
        if principal.role not in roles:
            raise ApiError(HTTPStatus.FORBIDDEN, "Dafuer fehlt die Berechtigung")

    def _overview(self, principal: Principal, cid: str) -> dict:
        return view_for(principal, wf.case_overview(self.store, cid, today=self.today))

    # ------------------------------------------------------------ public
    def h_meta(self, principal) -> None:
        self._json(200, meta_payload(self.demo))

    def h_me(self, principal) -> None:
        # 200 with user=null rather than 401: "not logged in" is a normal state.
        self._json(200, {"user": principal.public() if principal else None})

    def h_login(self, principal) -> None:
        body = self._obj()
        email = str(body.get("email", "")).strip().lower()
        if self.sessions.locked_out(email):
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS,
                           "Zu viele Fehlversuche. Bitte in einigen Minuten erneut versuchen.")
        p = self.users.authenticate(email, str(body.get("password", "")))
        if p is None:
            self.sessions.record_failure(email)
            raise ApiError(HTTPStatus.UNAUTHORIZED, "E-Mail oder Passwort ist falsch")
        self.sessions.clear_failures(email)
        token = self.sessions.create(p)
        self._json(200, p.public(), self._cookie_header(token, self.sessions.ttl))

    def h_logout(self, principal) -> None:
        self.sessions.destroy(self._token())
        self._json(200, {"ok": True}, self._cookie_header("", 0))

    def h_register(self, principal) -> None:
        body = self._obj()
        if body.get("consent") is not True:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Bitte der Datenverarbeitung zustimmen")
        with self.lock:
            p, meta = wf.register_client(
                self.store, self.users, str(body.get("company_name", "")),
                str(body.get("name", "")), str(body.get("email", "")),
                str(body.get("password", "")))
            answers = self.store.load_answers(meta["case_id"], "unternehmen")
            answers["datenschutz_einwilligung"] = True
            self.store.save_answers(meta["case_id"], "unternehmen", answers)
        token = self.sessions.create(p)
        self._json(201, {"user": p.public(), "case_id": meta["case_id"]},
                   self._cookie_header(token, self.sessions.ttl))

    def h_form(self, principal, form: str) -> None:
        if form == "unterlagen":
            md, title = documents_markdown(), "Unterlagenliste"
        else:
            q = QUESTIONNAIRES[form]
            md, title = questionnaire_markdown(q), q.title
        self._send(200, markdown_to_html(md, title).encode("utf-8"), "text/html; charset=utf-8")

    # ------------------------------------------------------------- cases
    def h_list_cases(self, principal) -> None:
        cases = [m for m in self.store.list_cases() if can_access_case(principal, m)]
        if principal.is_berater:
            for m in cases:
                s = self.store.read_artifact(m["case_id"], "summary.json")
                m["summary"] = json.loads(s) if s else None
        self._json(200, cases)

    def h_create_case(self, principal) -> None:
        self._require(principal, ROLE_BERATER)
        body = self._obj()
        with self.lock:
            meta = self.store.create_case(str(body.get("company_name", "")))
            invite = None
            if body.get("client_email"):
                invite = wf.invite_member(self.store, self.users, meta["case_id"], ROLE_UNTERNEHMEN,
                                          str(body["client_email"]), str(body.get("client_name", "")))
            answers = self.store.load_answers(meta["case_id"], "unternehmen")
            answers.setdefault("firmenname", meta["company_name"])
            self.store.save_answers(meta["case_id"], "unternehmen", answers)
        self._json(201, {"case": self.store.get_meta(meta["case_id"]), "invite": invite})

    def h_get_case(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._json(200, self._overview(principal, cid))

    def h_save_answers(self, principal, cid: str, aud: str) -> None:
        self._case(principal, cid)
        if aud not in AUDIENCES:
            raise ApiError(HTTPStatus.NOT_FOUND, f"Unbekannter Fragebogen '{aud}'")
        if not principal.is_berater and principal.role != aud:
            raise ApiError(HTTPStatus.FORBIDDEN, "Dieser Fragebogen ist fuer eine andere Partei")
        body = self._obj()
        with self.lock:
            self.store.save_answers(cid, aud, body)
        self._json(200, self._overview(principal, cid))

    def h_upload(self, principal, cid: str) -> None:
        self._case(principal, cid)
        body = self._obj()
        doc_type = str(body.get("doc_type", ""))
        dt = DOCUMENT_TYPES_BY_ID.get(doc_type)
        if dt is None:
            raise ApiError(HTTPStatus.BAD_REQUEST, f"Unbekannter Dokumenttyp '{doc_type}'")
        if not principal.is_berater and dt.source not in UPLOAD_SOURCES[principal.role]:
            raise ApiError(HTTPStatus.FORBIDDEN, "Diese Unterlage liefert eine andere Partei")
        try:
            content = base64.b64decode(str(body.get("content_base64", "")), validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Dateiinhalt nicht lesbar") from None
        meta = {k: body[k] for k in ("period_end", "period_months", "account_label")
                if body.get(k) not in (None, "")}
        note = str(body.get("note") or "").strip()
        if note:
            # Free text explaining the document ("Entwurf, Testat folgt"). Kept
            # short: it is a label for the reader, not a place for a second file.
            meta["note"] = note[:MAX_NOTE_CHARS]
        if "period_end" in meta:
            try:
                date.fromisoformat(str(meta["period_end"]))
            except ValueError:
                raise ApiError(HTTPStatus.BAD_REQUEST, "Stichtag ungueltig (JJJJ-MM-TT)") from None
        meta["uploaded_by"] = principal.email
        with self.lock:
            entry = self.store.add_document(cid, doc_type, str(body.get("filename", "")), content, meta)
        self._json(201, {"document": entry, "overview": self._overview(principal, cid)})

    def _doc_entry(self, cid: str, doc: str) -> dict:
        entry = next((d for d in self.store.list_documents(cid) if d["doc_id"] == doc), None)
        if entry is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Dokument nicht gefunden")
        return entry

    def h_download(self, principal, cid: str, doc: str) -> None:
        self._case(principal, cid)
        entry = self._doc_entry(cid, doc)
        ctype = mimetypes.guess_type(entry["filename"])[0] or "application/octet-stream"
        self._send(200, self.store.read_document(cid, doc), ctype, {
            "Content-Disposition": f'attachment; filename="{entry["filename"]}"'})

    def h_delete_doc(self, principal, cid: str, doc: str) -> None:
        self._case(principal, cid)
        entry = self._doc_entry(cid, doc)
        if not principal.is_berater and (entry.get("meta") or {}).get("uploaded_by") != principal.email:
            raise ApiError(HTTPStatus.FORBIDDEN, "Nur eigene Uploads koennen entfernt werden")
        with self.lock:
            self.store.remove_document(cid, doc)
        self._json(200, self._overview(principal, cid))

    def h_invite(self, principal, cid: str) -> None:
        self._case(principal, cid)
        body = self._obj()
        role = str(body.get("role", ROLE_STEUERBERATER))
        if principal.role == ROLE_STEUERBERATER or (
                principal.role == ROLE_UNTERNEHMEN and role != ROLE_STEUERBERATER):
            raise ApiError(HTTPStatus.FORBIDDEN, "Dafuer fehlt die Berechtigung")
        with self.lock:
            res = wf.invite_member(self.store, self.users, cid, role,
                                   str(body.get("email", "")), str(body.get("name", "")))
        self._json(200, {"invite": res, "overview": self._overview(principal, cid)})

    def h_submit(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER, ROLE_UNTERNEHMEN)
        with self.lock:
            wf.submit_case(self.store, cid, today=self.today)
        self._json(200, self._overview(principal, cid))

    # ------------------------------------------------------ advisor only
    def h_stage(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER)
        body = self._obj()
        with self.lock:
            self.store.set_stage(cid, str(body.get("stage", "")), str(body.get("note", "")))
        self._json(200, self._overview(principal, cid))

    def h_diagnose(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER)
        with self.lock:
            result = wf.run_case_diagnostic(self.store, cid, today=self.today)
        result["overview"] = self._overview(principal, cid)
        self._json(200, result)

    def h_letters(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER)
        with self.lock:
            wf.generate_letters(self.store, cid, today=self.today)
        self._json(200, self._overview(principal, cid))

    def h_release(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER)
        body = self._obj()
        with self.lock:
            wf.release_report(self.store, cid, bool(body.get("released", True)))
        self._json(200, self._overview(principal, cid))

    def h_outcome(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER)
        body = self._obj()
        with self.lock:
            row = wf.record_outcome(self.store, cid, body)
        self._json(200, {"row": row, "overview": self._overview(principal, cid)})

    # ------------------------------------------------------ quick check / AI
    def h_extract(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER, ROLE_UNTERNEHMEN)
        body = self._obj()
        with self.lock:
            res = wf.extract_figures(self.store, cid, body.get("doc_id"), actor=principal.email)
        self._json(200, {"extraction": res, "overview": self._overview(principal, cid)})

    def h_figures(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER, ROLE_UNTERNEHMEN)
        body = self._obj()
        with self.lock:
            rec = wf.confirm_figures(self.store, cid, body, principal.email)
        self._json(200, {"confirmed": rec, "overview": self._overview(principal, cid)})

    def h_quickcheck(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER, ROLE_UNTERNEHMEN)
        with self.lock:
            res = wf.run_quick_check(self.store, cid, today=self.today)
        res["overview"] = self._overview(principal, cid)
        self._json(200, res)

    def h_order(self, principal, cid: str) -> None:
        self._case(principal, cid)
        self._require(principal, ROLE_BERATER, ROLE_UNTERNEHMEN)
        body = self._obj()
        with self.lock:
            wf.place_order(self.store, cid, str(body.get("product", "")), principal.email,
                           str(body.get("note", "")))
        self._json(200, self._overview(principal, cid))

    def h_explain(self, principal, cid: str) -> None:
        self._case(principal, cid)
        body = self._obj()
        which = "report" if body.get("which") == "report" else "quick"
        if which == "quick" and principal.role == ROLE_STEUERBERATER:
            raise ApiError(HTTPStatus.FORBIDDEN, "Dafuer fehlt die Berechtigung")
        if which == "report" and not principal.is_berater:
            if not self.store.get_meta(cid).get("report_released"):
                raise ApiError(HTTPStatus.NOT_FOUND, "Noch nicht verfuegbar")
        question = body.get("question")
        res = wf.explain_result(self.store, cid, str(body.get("lang", "de")),
                                str(question)[:600] if question else None, which, principal.email)
        self._json(200, res)

    def h_delete_account(self, principal) -> None:
        self._require(principal, ROLE_UNTERNEHMEN)
        body = self._obj()
        if body.get("confirm") != "LOESCHEN":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Bitte zur Bestaetigung LOESCHEN eingeben")
        with self.lock:
            deleted = wf.delete_client_data(self.store, self.users, principal.email)
        self.sessions.destroy(self._token())
        self._json(200, {"deleted_cases": deleted}, self._cookie_header("", 0))

    def h_artifact(self, principal, cid: str, name: str) -> None:
        self._case(principal, cid)
        if not principal.is_berater:
            ov = view_for(principal, wf.case_overview(self.store, cid, today=self.today))
            if name not in ov["artifacts"]:
                raise ApiError(HTTPStatus.NOT_FOUND, "Noch nicht verfuegbar")
        text = self.store.read_artifact(cid, name)
        if text is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "Noch nicht erstellt")
        ext = name.rsplit(".", 1)[1]
        ctype = {"md": "text/markdown", "html": "text/html", "json": "application/json",
                 "csv": "text/csv"}[ext] + "; charset=utf-8"
        self._send(200, text.encode("utf-8"), ctype)

    # ------------------------------------------------------------ static
    def _static(self, path: str) -> None:
        name = PAGES.get(path.rstrip("/") or "/") or path.lstrip("/")
        if not re.match(r"^[a-z0-9_\-]+\.(html|js|css|svg)$", name):
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        f = STATIC / name
        if not f.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        ctype = mimetypes.guess_type(name)[0] or "text/plain"
        if name.endswith(".js"):
            ctype = "text/javascript"
        if ctype.startswith("text/") or ctype.endswith("xml"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)


def make_server(
    store: Optional[CaseStore] = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    today: Optional[date] = None,
    verbose: bool = False,
    users: Optional[UserStore] = None,
    demo: bool = False,
) -> ThreadingHTTPServer:
    store = store or LocalCaseStore()
    handler = type("BoundHandler", (Handler,), {
        "store": store,
        "users": users or UserStore(store.root),
        "sessions": SessionManager(),
        "today": today,
        "demo": demo,
        "lock": threading.Lock(),
    })
    server = ThreadingHTTPServer((host, port), handler)
    server.verbose = verbose
    return server


def serve(
    host: str = "127.0.0.1", port: int = 8765, data_dir: Optional[str] = None,
    open_browser: bool = False, demo: bool = False,
) -> None:
    if demo:
        from ..demo import DEMO_ROOT, DEMO_USERS, seed_demo
        data_dir = data_dir or str(DEMO_ROOT)
        store = LocalCaseStore(data_dir)
        if UserStore(store.root).count() == 0:
            print("Demo-Daten werden angelegt ...")
            seed_demo(store)
    else:
        store = LocalCaseStore(data_dir)
    users = UserStore(store.root)
    server = make_server(store, host, port, users=users, demo=demo)
    url = f"http://{host}:{server.server_port}/"
    print(f"Credit Readiness laeuft: {url}")
    print(f"Ablage: {store.root}")
    if demo:
        print("\nDemo-Zugaenge (Passwort jeweils: demo1234):")
        for email, _, role, _ in DEMO_USERS:
            print(f"  {role:<14} {email}")
    elif users.count() == 0:
        print("\nNoch kein Konto vorhanden. Beraterkonto anlegen mit:")
        print('  python -m credit_readiness user add ihre@mail.de "Ihr Name" --role berater --password ...')
    if host not in ("127.0.0.1", "localhost"):
        print("WARNUNG: nicht nur lokal erreichbar. Ohne TLS nicht fuer echte Mandantendaten verwenden.")
    print("Beenden mit Strg+C")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
