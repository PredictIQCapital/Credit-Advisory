"""CaseStore on Supabase: tables in the private `app` schema, files in Storage.

Same interface and the same rules as LocalCaseStore -- file types, sizes,
names, stages, append-only records -- so the portal, the CLI and the workflow
do not know which one they talk to. tests/test_store_contract.py runs one set
of checks against both.

Files live in the private bucket under <case_id>/<doc_id>/<filename> and
<case_id>/logo.<ext>; the server streams them after its own permission check,
so no file ever has a public URL.
"""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import datetime
from typing import Any, Optional

from .casefile import (
    ARTIFACT_RE,
    AUDIENCES,
    CASE_ID_RE,
    DOC_ID_RE,
    MAX_UPLOAD_BYTES,
    OUTCOME_COLUMNS,
    OUTCOMES,
    STAGE_IDS,
    CaseNotFound,
    CaseStore,
    CaseStoreError,
    _now,
    safe_filename,
)
from .intake.documents import get_document_type
from .supa import Supabase, SupabaseError, q

RECORD_KINDS = ("agreements", "messages")
LOGO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
_PROTECTED = {"case_id", "created_at", "stage", "stage_history"}
_MIME = {"pdf": "application/pdf", "csv": "text/csv", "png": "image/png", "jpg": "image/jpeg",
         "jpeg": "image/jpeg", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


class SupabaseCaseStore(CaseStore):
    def __init__(self, client: Supabase, case_year: Optional[int] = None):
        self.sb = client
        # Tests number their cases in a year of their own and clean up after.
        self.case_year = case_year

    # ------------------------------------------------------------- helpers
    def _check_id(self, case_id: str) -> None:
        if not CASE_ID_RE.match(case_id or ""):
            raise CaseStoreError(f"Ungueltige Fall-ID '{case_id}'")

    def _row(self, case_id: str) -> dict:
        self._check_id(case_id)
        rows = self.sb.select("cases", f"case_id=eq.{q(case_id)}&select=meta")
        if not rows:
            raise CaseNotFound(f"Fall {case_id} nicht gefunden")
        return rows[0]["meta"]

    def _save_meta(self, meta: dict) -> dict:
        self.sb.update("cases", f"case_id=eq.{q(meta['case_id'])}", {
            "meta": meta, "company_name": meta["company_name"], "stage": meta["stage"],
            "updated_at": meta["updated_at"]})
        return meta

    def _touch(self, case_id: str) -> None:
        self.update_meta(case_id)

    # --------------------------------------------------------------- cases
    def create_case(self, company_name: str) -> dict:
        name = (company_name or "").strip()
        if not name:
            raise CaseStoreError("Firmenname fehlt")
        case_id = self.sb.rpc("next_case_id", {"p_year": self.case_year or datetime.now().year})
        now = _now()
        meta = {"case_id": case_id, "company_name": name, "created_at": now, "updated_at": now,
                "stage": "neu", "stage_history": [{"stage": "neu", "at": now, "note": ""}]}
        self.sb.insert("cases", {"case_id": case_id, "meta": meta, "company_name": name,
                                 "stage": "neu", "created_at": now, "updated_at": now}, returning=False)
        return meta

    def list_cases(self) -> list[dict]:
        rows = self.sb.select("cases", "select=meta&order=created_at.desc")
        if self.case_year:
            prefix = f"CRA-{self.case_year}-"
            rows = [r for r in rows if r["meta"]["case_id"].startswith(prefix)]
        return [r["meta"] for r in rows]

    def get_meta(self, case_id: str) -> dict:
        return self._row(case_id)

    def update_meta(self, case_id: str, **fields: Any) -> dict:
        meta = self._row(case_id)
        for k, v in fields.items():
            if k in _PROTECTED:
                raise CaseStoreError(f"Feld '{k}' kann nicht direkt gesetzt werden")
            meta[k] = v
        meta["updated_at"] = _now()
        return self._save_meta(meta)

    def set_stage(self, case_id: str, stage: str, note: str = "") -> dict:
        if stage not in STAGE_IDS:
            raise CaseStoreError(f"Unbekannte Phase '{stage}'")
        meta = self._row(case_id)
        if meta["stage"] != stage:
            now = _now()
            meta["stage"] = stage
            meta["stage_history"].append({"stage": stage, "at": now, "note": note})
            meta["updated_at"] = now
            self._save_meta(meta)
        return meta

    def delete_case(self, case_id: str) -> None:
        self._row(case_id)
        self.sb.remove(self.sb.list_folder(case_id))
        self.sb.delete("cases", f"case_id=eq.{q(case_id)}")

    # ------------------------------------------------------------- answers
    def save_answers(self, case_id: str, audience: str, answers: dict) -> None:
        if audience not in AUDIENCES:
            raise CaseStoreError(f"Unbekannte Zielgruppe '{audience}'")
        if not isinstance(answers, dict):
            raise CaseStoreError("Antworten muessen ein Objekt sein")
        self._row(case_id)
        self.sb.insert("answers", {"case_id": case_id, "audience": audience, "data": answers,
                                   "updated_at": _now()}, upsert=True, returning=False)
        self._touch(case_id)

    def load_answers(self, case_id: str, audience: str) -> dict:
        if audience not in AUDIENCES:
            raise CaseStoreError(f"Unbekannte Zielgruppe '{audience}'")
        self._check_id(case_id)
        rows = self.sb.select("answers", f"case_id=eq.{q(case_id)}&audience=eq.{q(audience)}&select=data")
        return rows[0]["data"] if rows else {}

    # ----------------------------------------------------------- documents
    @staticmethod
    def _entry(row: dict) -> dict:
        return {"doc_id": row["doc_id"], "doc_type": row["doc_type"], "filename": row["filename"],
                "stored_as": row["storage_path"], "size": row["size"], "sha256": row["sha256"],
                "uploaded_at": row["uploaded_at"], "meta": row.get("meta") or {}}

    def add_document(self, case_id: str, doc_type: str, filename: str, content: bytes,
                     meta: Optional[dict] = None) -> dict:
        dt = get_document_type(doc_type)
        if not content:
            raise CaseStoreError("Leere Datei")
        if len(content) > MAX_UPLOAD_BYTES:
            raise CaseStoreError(f"Datei zu gross ({len(content)/1e6:.1f} MB, max. "
                                 f"{MAX_UPLOAD_BYTES/1e6:.0f} MB)")
        clean = safe_filename(filename)
        if not dt.accepts(clean):
            raise CaseStoreError(f"Format nicht zulaessig fuer '{dt.title}'. Erlaubt: "
                                 f"{', '.join('.' + f for f in dt.formats)}")
        self._row(case_id)
        if not dt.multiple:
            # A single-slot document is replaced, not duplicated.
            for old in self.list_documents(case_id):
                if old["doc_type"] == doc_type:
                    self.remove_document(case_id, old["doc_id"])
        doc_id = uuid.uuid4().hex[:12]
        path = f"{case_id}/{doc_id}/{clean}"
        self.sb.upload(path, content, _MIME.get(clean.rsplit(".", 1)[-1].lower(), "application/octet-stream"))
        row = {"doc_id": doc_id, "case_id": case_id, "doc_type": doc_type, "filename": clean,
               "storage_path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
               "uploaded_at": _now(), "meta": dict(meta or {})}
        try:
            self.sb.insert("documents", row, returning=False)
        except SupabaseError:
            self.sb.remove([path])          # no orphan file without its record
            raise
        self._touch(case_id)
        return self._entry(row)

    def list_documents(self, case_id: str) -> list[dict]:
        self._check_id(case_id)
        rows = self.sb.select("documents", f"case_id=eq.{q(case_id)}&order=uploaded_at.asc,doc_id.asc")
        return [self._entry(r) for r in rows]

    def _doc(self, case_id: str, doc_id: str) -> dict:
        if not DOC_ID_RE.match(doc_id or ""):
            raise CaseStoreError("Ungueltige Dokument-ID")
        self._check_id(case_id)
        rows = self.sb.select("documents", f"case_id=eq.{q(case_id)}&doc_id=eq.{q(doc_id)}")
        if not rows:
            raise CaseNotFound(f"Dokument {doc_id} nicht gefunden")
        return rows[0]

    def read_document(self, case_id: str, doc_id: str) -> bytes:
        return self.sb.download(self._doc(case_id, doc_id)["storage_path"])

    def remove_document(self, case_id: str, doc_id: str) -> None:
        row = self._doc(case_id, doc_id)
        self.sb.delete("documents", f"doc_id=eq.{q(doc_id)}")
        self.sb.remove([row["storage_path"]])
        self._touch(case_id)

    def update_document_meta(self, case_id: str, doc_id: str, **fields: Any) -> dict:
        row = self._doc(case_id, doc_id)
        row["meta"] = {**(row.get("meta") or {}), **fields}
        self.sb.update("documents", f"doc_id=eq.{q(doc_id)}", {"meta": row["meta"]})
        self._touch(case_id)
        return self._entry(row)

    # ------------------------------------------------------------ records
    def append_record(self, case_id: str, kind: str, record: dict) -> dict:
        if kind not in RECORD_KINDS:
            raise CaseStoreError(f"Unbekannte Ablage '{kind}'")
        self._row(case_id)
        self.sb.insert("records", {"case_id": case_id, "kind": kind, "record": record}, returning=False)
        self._touch(case_id)
        return record

    def list_records(self, case_id: str, kind: str) -> list[dict]:
        if kind not in RECORD_KINDS:
            raise CaseStoreError(f"Unbekannte Ablage '{kind}'")
        self._check_id(case_id)
        rows = self.sb.select("records", f"case_id=eq.{q(case_id)}&kind=eq.{q(kind)}&select=record&order=id.asc")
        return [r["record"] for r in rows]

    # --------------------------------------------------------------- logo
    def set_logo(self, case_id: str, content: Optional[bytes], ext: str = "") -> None:
        self._row(case_id)
        self.sb.remove([f"{case_id}/logo.{e}" for e in LOGO_TYPES])
        if content is not None:
            if ext not in LOGO_TYPES:
                raise CaseStoreError("Logo: PNG, JPG oder WebP")
            self.sb.upload(f"{case_id}/logo.{ext}", content, LOGO_TYPES[ext])
        self.update_meta(case_id, has_logo=content is not None, logo_ext=ext if content is not None else None)

    def get_logo(self, case_id: str) -> Optional[tuple[bytes, str]]:
        ext = self._row(case_id).get("logo_ext")
        if not ext:
            return None
        try:
            return self.sb.download(f"{case_id}/logo.{ext}"), LOGO_TYPES[ext]
        except SupabaseError:
            return None

    # ----------------------------------------------------------- artifacts
    @staticmethod
    def _check_artifact(name: str) -> None:
        if not ARTIFACT_RE.match(name or ""):
            raise CaseStoreError(f"Ungueltiger Artefaktname '{name}'")

    def write_artifact(self, case_id: str, name: str, text: str) -> None:
        self._check_artifact(name)
        self._check_id(case_id)
        self.sb.insert("artifacts", {"case_id": case_id, "name": name, "content": text, "updated_at": _now()},
                       upsert=True, returning=False)

    def read_artifact(self, case_id: str, name: str) -> Optional[str]:
        self._check_artifact(name)
        self._check_id(case_id)
        rows = self.sb.select("artifacts", f"case_id=eq.{q(case_id)}&name=eq.{q(name)}&select=content")
        return rows[0]["content"] if rows else None

    def list_artifacts(self, case_id: str) -> list[str]:
        self._check_id(case_id)
        rows = self.sb.select("artifacts", f"case_id=eq.{q(case_id)}&select=name&order=name.asc")
        return [r["name"] for r in rows]

    # ------------------------------------------------------------- outcomes
    def append_outcome(self, row: dict) -> None:
        if row.get("outcome") not in OUTCOMES:
            raise CaseStoreError(f"Ergebnis muss eines von {', '.join(OUTCOMES)} sein")
        # Stored as the CSV would hold it -- strings -- so both stores read back alike.
        self.sb.insert("outcomes", {"row": {k: "" if row.get(k) is None else str(row.get(k))
                                            for k in OUTCOME_COLUMNS}}, returning=False)

    def read_outcomes(self) -> list[dict]:
        return [r["row"] for r in self.sb.select("outcomes", "select=row&order=id.asc")]

    def outcomes_csv(self) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=OUTCOME_COLUMNS)
        w.writeheader()
        w.writerows(self.read_outcomes())
        return buf.getvalue()
