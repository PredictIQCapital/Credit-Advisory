"""Local client portal: a small JSON API plus a single-page front end.

    python -m credit_readiness serve              -> http://127.0.0.1:8765

Scope, stated plainly
=====================
This is the Phase-0 portal the blueprint describes: the founder runs it on
their own machine and works through real client files with it. It is
deliberately built on the standard library only and binds to 127.0.0.1.

It is NOT ready to be exposed to the internet. Before any hosted deployment
(e.g. Vercel + a database, as planned) it needs, at minimum:
  * authentication and per-client access control,
  * TLS, encryption at rest, EU (Frankfurt) hosting,
  * a `CaseStore` implementation backed by the database / object storage,
  * CSRF protection and rate limiting.
The HTTP layer is thin on purpose: all logic lives in `workflow.py` and
`casefile.py`, so a production framework can replace this file without
touching any business rule.

Uploads arrive as JSON with base64 content. That avoids multipart parsing
(the stdlib `cgi` module no longer exists) and is fine for local use.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from .. import workflow as wf
from ..casefile import (
    MAX_UPLOAD_BYTES,
    OUTCOMES,
    STAGES,
    CaseNotFound,
    CaseStore,
    CaseStoreError,
    LocalCaseStore,
)
from ..intake.documents import DOCUMENT_TYPES, SOURCE_LABELS
from ..intake.questionnaire import AUDIENCES, QUESTIONNAIRES
from ..reporting.forms import documents_markdown, questionnaire_markdown
from ..reporting.html import markdown_to_html
from ..routing import LENDERS

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = int(MAX_UPLOAD_BYTES * 1.4) + 64 * 1024     # base64 overhead

_CASE = r"(?P<cid>CRA-\d{4}-\d{4})"
ROUTES: list[tuple[str, re.Pattern]] = [
    (m, re.compile("^" + p + "$")) for m, p in [
        ("GET", r"/api/meta"),
        ("GET", r"/api/cases"),
        ("POST", r"/api/cases"),
        ("GET", rf"/api/cases/{_CASE}"),
        ("PUT", rf"/api/cases/{_CASE}/answers/(?P<aud>[a-z]+)"),
        ("POST", rf"/api/cases/{_CASE}/documents"),
        ("GET", rf"/api/cases/{_CASE}/documents/(?P<doc>[a-f0-9]{{12}})"),
        ("DELETE", rf"/api/cases/{_CASE}/documents/(?P<doc>[a-f0-9]{{12}})"),
        ("POST", rf"/api/cases/{_CASE}/stage"),
        ("POST", rf"/api/cases/{_CASE}/diagnose"),
        ("POST", rf"/api/cases/{_CASE}/letters"),
        ("POST", rf"/api/cases/{_CASE}/outcome"),
        ("GET", rf"/api/cases/{_CASE}/artifacts/(?P<name>[a-z0-9_\-]+\.(?:md|html|json|csv))"),
        ("GET", r"/forms/(?P<form>unternehmen|steuerberater|unterlagen)\.html"),
    ]
]


class ApiError(Exception):
    def __init__(self, status: int, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def meta_payload() -> dict:
    return {
        "questionnaires": {a: QUESTIONNAIRES[a].as_dict() for a in AUDIENCES},
        "documents": [d.as_dict() for d in DOCUMENT_TYPES],
        "source_labels": SOURCE_LABELS,
        "stages": [{"id": s, "label": label} for s, label in STAGES],
        "outcomes": list(OUTCOMES),
        "letters": wf.LETTERS,
        "lenders": [{"key": lp.key, "name": lp.name} for lp in LENDERS],
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CreditReadiness/0.2"
    store: CaseStore        # set by make_server
    today: Optional[date] = None
    lock = threading.Lock()  # one diagnostic/write at a time; single-user tool

    # ---------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args: Any) -> None:   # quieter console
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
            "frame-src 'self'; frame-ancestors 'self'",
        )
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Anfrage zu gross")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Ungueltiges JSON") from None

    def _check_origin(self) -> None:
        """Reject cross-site writes: a page on another site must not be able to
        post into a portal running on the founder's machine."""
        origin = self.headers.get("Origin")
        if origin is None:
            return
        host = self.headers.get("Host", "")
        if urlparse(origin).netloc != host:
            raise ApiError(HTTPStatus.FORBIDDEN, "Fremder Ursprung abgelehnt")

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
            for m, pattern in ROUTES:
                match = pattern.match(path)
                if match and m == method:
                    return self._route(method, path, match.groupdict())
            if method == "GET":
                return self._static(path)
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        except ApiError as e:
            self._json(e.status, {"error": e.message, "details": e.details})
        except CaseNotFound as e:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(e)})
        except (CaseStoreError, ValueError) as e:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - never leak a stack trace to the page
            traceback.print_exc()
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                       {"error": f"Interner Fehler: {type(e).__name__}"})

    # ----------------------------------------------------------- routes
    def _route(self, method: str, path: str, p: dict) -> None:
        st = self.store
        cid = p.get("cid")

        if path == "/api/meta":
            return self._json(200, meta_payload())

        if path == "/api/cases":
            if method == "GET":
                return self._json(200, st.list_cases())
            body = self._body()
            with self.lock:
                meta = st.create_case(str(body.get("company_name", "")))
            return self._json(201, meta)

        if path.startswith("/forms/"):
            form = p["form"]
            if form == "unterlagen":
                md, title = documents_markdown(), "Unterlagenliste"
            else:
                q = QUESTIONNAIRES[form]
                md, title = questionnaire_markdown(q), q.title
            return self._send(200, markdown_to_html(md, title).encode("utf-8"),
                              "text/html; charset=utf-8")

        if "/answers/" in path:
            aud = p["aud"]
            if aud not in AUDIENCES:
                raise ApiError(HTTPStatus.NOT_FOUND, f"Unbekannte Zielgruppe '{aud}'")
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Antworten muessen ein Objekt sein")
            with self.lock:
                st.save_answers(cid, aud, body)
            return self._json(200, wf.case_overview(st, cid, today=self.today))

        if path.endswith("/documents") and method == "POST":
            body = self._body()
            try:
                content = base64.b64decode(str(body.get("content_base64", "")), validate=True)
            except (binascii.Error, ValueError):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Dateiinhalt nicht lesbar") from None
            meta = {k: body[k] for k in ("period_end", "period_months", "account_label")
                    if body.get(k) not in (None, "")}
            if "period_end" in meta:
                try:
                    date.fromisoformat(str(meta["period_end"]))
                except ValueError:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Stichtag ungueltig (JJJJ-MM-TT)") from None
            with self.lock:
                entry = st.add_document(cid, str(body.get("doc_type", "")),
                                        str(body.get("filename", "")), content, meta)
            return self._json(201, {"document": entry,
                                    "overview": wf.case_overview(st, cid, today=self.today)})

        if "/documents/" in path:
            doc = p["doc"]
            if method == "DELETE":
                with self.lock:
                    st.remove_document(cid, doc)
                return self._json(200, wf.case_overview(st, cid, today=self.today))
            entry = next((d for d in st.list_documents(cid) if d["doc_id"] == doc), None)
            if entry is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Dokument nicht gefunden")
            ctype = mimetypes.guess_type(entry["filename"])[0] or "application/octet-stream"
            return self._send(200, st.read_document(cid, doc), ctype, {
                "Content-Disposition": f'attachment; filename="{entry["filename"]}"'})

        if path.endswith("/stage"):
            body = self._body()
            with self.lock:
                st.set_stage(cid, str(body.get("stage", "")), str(body.get("note", "")))
            return self._json(200, wf.case_overview(st, cid, today=self.today))

        if path.endswith("/diagnose"):
            with self.lock:
                result = wf.run_case_diagnostic(st, cid, today=self.today)
            result["overview"] = wf.case_overview(st, cid, today=self.today)
            return self._json(200, result)

        if path.endswith("/letters"):
            with self.lock:
                wf.generate_letters(st, cid, today=self.today)
            return self._json(200, wf.case_overview(st, cid, today=self.today))

        if path.endswith("/outcome"):
            body = self._body()
            with self.lock:
                row = wf.record_outcome(st, cid, body)
            return self._json(200, {"row": row,
                                    "overview": wf.case_overview(st, cid, today=self.today)})

        if "/artifacts/" in path:
            text = st.read_artifact(cid, p["name"])
            if text is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "Noch nicht erstellt")
            ext = p["name"].rsplit(".", 1)[1]
            ctype = {"md": "text/markdown", "html": "text/html", "json": "application/json",
                     "csv": "text/csv"}[ext] + "; charset=utf-8"
            return self._send(200, text.encode("utf-8"), ctype)

        if re.match(rf"^/api/cases/{_CASE}$", path):
            st.get_meta(cid)      # 404 if missing
            return self._json(200, wf.case_overview(st, cid, today=self.today))

        raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")

    def _static(self, path: str) -> None:
        name = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        if not re.match(r"^[a-z0-9_\-]+\.(html|js|css)$", name):
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        f = STATIC / name
        if not f.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Nicht gefunden")
        ctype = mimetypes.guess_type(name)[0] or "text/plain"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)


def make_server(
    store: Optional[CaseStore] = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    today: Optional[date] = None,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {
        "store": store or LocalCaseStore(),
        "today": today,
        "lock": threading.Lock(),
    })
    server = ThreadingHTTPServer((host, port), handler)
    server.verbose = verbose
    return server


def serve(
    host: str = "127.0.0.1", port: int = 8765, data_dir: Optional[str] = None,
    open_browser: bool = False,
) -> None:
    store = LocalCaseStore(data_dir)
    server = make_server(store, host, port)
    url = f"http://{host}:{server.server_port}/"
    print(f"Credit Readiness Portal laeuft: {url}")
    print(f"Ablage: {store.root}")
    if host not in ("127.0.0.1", "localhost"):
        print("WARNUNG: nicht nur lokal erreichbar. Ohne Anmeldung und TLS nicht "
              "fuer echte Mandantendaten verwenden.")
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
