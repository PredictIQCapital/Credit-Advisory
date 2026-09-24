"""Case storage: one folder per engagement.

`CaseStore` is the interface; `LocalCaseStore` keeps everything on the local
disk. When a database and object storage are connected, implement `CaseStore`
against them and nothing else in the code base has to change -- the web app,
the CLI and the workflow only ever talk to this interface.

Local layout (default root: data/clients/, excluded from git):

    <root>/
      outcome_log.csv                    the proprietary dataset (see blueprint)
      CRA-2026-0001/
        case_meta.json                   name, stage, stage history
        answers_unternehmen.json         raw questionnaire answers
        answers_steuerberater.json
        documents/index.json             what was uploaded, by whom, when, sha256
        documents/<doc_id>__<name>       the files themselves
        artifacts/                       case.json, reports, letters

Security posture of the LOCAL store: files are written unencrypted to the local
disk. That is acceptable for the founder's own machine with disk encryption
(BitLocker) switched on, and for nothing else. A hosted deployment needs
encryption at rest and EU hosting -- see docs/regulatory-guardrails.md.
"""

from __future__ import annotations

import abc
import csv
import hashlib
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .intake.documents import get_document_type
from .intake.questionnaire import AUDIENCES

DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "clients"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

CASE_ID_RE = re.compile(r"^CRA-\d{4}-\d{4}$")
DOC_ID_RE = re.compile(r"^[a-f0-9]{12}$")
ARTIFACT_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,80}\.(md|html|json|csv)$")

STAGES: tuple[tuple[str, str], ...] = (
    ("neu", "Neu angelegt"),
    ("unterlagen_angefordert", "Unterlagen angefordert"),
    ("unterlagen_vollstaendig", "Unterlagen vollstaendig"),
    ("diagnostik_erstellt", "Diagnostik erstellt"),
    ("massnahmen_in_umsetzung", "Massnahmen in Umsetzung"),
    ("beim_kreditgeber", "Beim Kreditgeber"),
    ("abgeschlossen", "Abgeschlossen"),
)
STAGE_IDS = tuple(s for s, _ in STAGES)
STAGE_LABELS = dict(STAGES)

OUTCOMES = (
    "APPROVED", "APPROVED_BETTER_TERMS", "REJECTED", "WITHDRAWN",
    "ADVISED_NOT_TO_APPLY", "PENDING",
)
OUTCOME_COLUMNS = (
    "case_id", "date_recorded", "sector", "employees", "revenue_eur",
    "band_before", "score_before", "verdict", "findings", "remediation_applied",
    "band_after", "score_after", "lender_type_routed", "outcome",
    "facility_amount_eur", "rate_pct", "weeks_to_decision", "notes",
)


class CaseStoreError(ValueError):
    pass


class CaseNotFound(CaseStoreError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_filename(name: str) -> str:
    """Strip a client-supplied filename down to something harmless."""
    base = os.path.basename(name.replace("\\", "/")).strip() or "datei"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "datei"
    stem, dot, ext = base.rpartition(".")
    if dot and len(stem) > 70:
        base = stem[:70] + "." + ext[:10]
    return base[:90]


class CaseStore(abc.ABC):
    """Storage interface. Implement this to move cases into a database."""

    @abc.abstractmethod
    def create_case(self, company_name: str) -> dict: ...

    @abc.abstractmethod
    def list_cases(self) -> list[dict]: ...

    @abc.abstractmethod
    def get_meta(self, case_id: str) -> dict: ...

    @abc.abstractmethod
    def update_meta(self, case_id: str, **fields: Any) -> dict: ...

    @abc.abstractmethod
    def set_stage(self, case_id: str, stage: str, note: str = "") -> dict: ...

    @abc.abstractmethod
    def save_answers(self, case_id: str, audience: str, answers: dict) -> None: ...

    @abc.abstractmethod
    def load_answers(self, case_id: str, audience: str) -> dict: ...

    @abc.abstractmethod
    def add_document(
        self, case_id: str, doc_type: str, filename: str, content: bytes,
        meta: Optional[dict] = None,
    ) -> dict: ...

    @abc.abstractmethod
    def list_documents(self, case_id: str) -> list[dict]: ...

    @abc.abstractmethod
    def read_document(self, case_id: str, doc_id: str) -> bytes: ...

    @abc.abstractmethod
    def remove_document(self, case_id: str, doc_id: str) -> None: ...

    @abc.abstractmethod
    def update_document_meta(self, case_id: str, doc_id: str, **fields: Any) -> dict: ...

    # Append-only records: agreements signed or withdrawn, and messages.
    @abc.abstractmethod
    def append_record(self, case_id: str, kind: str, record: dict) -> dict: ...

    @abc.abstractmethod
    def list_records(self, case_id: str, kind: str) -> list[dict]: ...

    @abc.abstractmethod
    def set_logo(self, case_id: str, content: Optional[bytes], ext: str = "") -> None: ...

    @abc.abstractmethod
    def get_logo(self, case_id: str) -> Optional[tuple[bytes, str]]: ...

    @abc.abstractmethod
    def write_artifact(self, case_id: str, name: str, text: str) -> None: ...

    @abc.abstractmethod
    def read_artifact(self, case_id: str, name: str) -> Optional[str]: ...

    @abc.abstractmethod
    def list_artifacts(self, case_id: str) -> list[str]: ...

    @abc.abstractmethod
    def append_outcome(self, row: dict) -> None: ...

    @abc.abstractmethod
    def read_outcomes(self) -> list[dict]: ...


class LocalCaseStore(CaseStore):
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("CRA_DATA_DIR") or DEFAULT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------- helpers
    def _case_dir(self, case_id: str, must_exist: bool = True) -> Path:
        if not CASE_ID_RE.match(case_id or ""):
            raise CaseStoreError(f"Ungueltige Fall-ID '{case_id}'")
        d = self.root / case_id
        if must_exist and not (d / "case_meta.json").is_file():
            raise CaseNotFound(f"Fall {case_id} nicht gefunden")
        return d

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str),
                       encoding="utf-8")
        os.replace(tmp, path)     # atomic: a crash never leaves half a file

    def _next_case_id(self) -> str:
        year = datetime.now().year
        prefix = f"CRA-{year}-"
        numbers = [
            int(p.name[len(prefix):]) for p in self.root.iterdir()
            if p.is_dir() and p.name.startswith(prefix) and CASE_ID_RE.match(p.name)
        ]
        return f"{prefix}{(max(numbers) + 1) if numbers else 1:04d}"

    # --------------------------------------------------------------- cases
    def create_case(self, company_name: str) -> dict:
        name = (company_name or "").strip()
        if not name:
            raise CaseStoreError("Firmenname fehlt")
        with self._lock:
            case_id = self._next_case_id()
            d = self._case_dir(case_id, must_exist=False)
            d.mkdir(parents=True)
            (d / "documents").mkdir()
            (d / "artifacts").mkdir()
            now = _now()
            meta = {
                "case_id": case_id,
                "company_name": name,
                "created_at": now,
                "updated_at": now,
                "stage": "neu",
                "stage_history": [{"stage": "neu", "at": now, "note": ""}],
            }
            self._write_json(d / "case_meta.json", meta)
            self._write_json(d / "documents" / "index.json", [])
            return meta

    def list_cases(self) -> list[dict]:
        metas = []
        for p in sorted(self.root.iterdir()):
            if p.is_dir() and CASE_ID_RE.match(p.name) and (p / "case_meta.json").is_file():
                metas.append(self._read_json(p / "case_meta.json", {}))
        return sorted(metas, key=lambda m: m.get("created_at", ""), reverse=True)

    def get_meta(self, case_id: str) -> dict:
        return self._read_json(self._case_dir(case_id) / "case_meta.json", {})

    def update_meta(self, case_id: str, **fields: Any) -> dict:
        protected = {"case_id", "created_at", "stage", "stage_history"}
        with self._lock:
            meta = self.get_meta(case_id)
            for k, v in fields.items():
                if k in protected:
                    raise CaseStoreError(f"Feld '{k}' kann nicht direkt gesetzt werden")
                meta[k] = v
            meta["updated_at"] = _now()
            self._write_json(self._case_dir(case_id) / "case_meta.json", meta)
            return meta

    def set_stage(self, case_id: str, stage: str, note: str = "") -> dict:
        if stage not in STAGE_IDS:
            raise CaseStoreError(f"Unbekannte Phase '{stage}'")
        with self._lock:
            meta = self.get_meta(case_id)
            if meta["stage"] != stage:
                now = _now()
                meta["stage"] = stage
                meta["stage_history"].append({"stage": stage, "at": now, "note": note})
                meta["updated_at"] = now
                self._write_json(self._case_dir(case_id) / "case_meta.json", meta)
            return meta

    # ------------------------------------------------------------- answers
    def save_answers(self, case_id: str, audience: str, answers: dict) -> None:
        if audience not in AUDIENCES:
            raise CaseStoreError(f"Unbekannte Zielgruppe '{audience}'")
        if not isinstance(answers, dict):
            raise CaseStoreError("Antworten muessen ein Objekt sein")
        with self._lock:
            d = self._case_dir(case_id)
            self._write_json(d / f"answers_{audience}.json", answers)
            self.update_meta(case_id)

    def load_answers(self, case_id: str, audience: str) -> dict:
        if audience not in AUDIENCES:
            raise CaseStoreError(f"Unbekannte Zielgruppe '{audience}'")
        return self._read_json(self._case_dir(case_id) / f"answers_{audience}.json", {})

    # ----------------------------------------------------------- documents
    def add_document(
        self, case_id: str, doc_type: str, filename: str, content: bytes,
        meta: Optional[dict] = None,
    ) -> dict:
        dt = get_document_type(doc_type)
        if not content:
            raise CaseStoreError("Leere Datei")
        if len(content) > MAX_UPLOAD_BYTES:
            raise CaseStoreError(
                f"Datei zu gross ({len(content)/1e6:.1f} MB, max. "
                f"{MAX_UPLOAD_BYTES/1e6:.0f} MB)"
            )
        clean = safe_filename(filename)
        if not dt.accepts(clean):
            raise CaseStoreError(
                f"Format nicht zulaessig fuer '{dt.title}'. Erlaubt: "
                f"{', '.join('.' + f for f in dt.formats)}"
            )
        with self._lock:
            d = self._case_dir(case_id)
            index = self._read_json(d / "documents" / "index.json", [])
            if not dt.multiple:
                # A single-slot document is replaced, not duplicated -- a second
                # "current SuSa" would make the assembly ambiguous.
                for old in [e for e in index if e["doc_type"] == doc_type]:
                    (d / "documents" / old["stored_as"]).unlink(missing_ok=True)
                index = [e for e in index if e["doc_type"] != doc_type]
            doc_id = uuid.uuid4().hex[:12]
            stored_as = f"{doc_id}__{clean}"
            (d / "documents" / stored_as).write_bytes(content)
            entry = {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "filename": clean,
                "stored_as": stored_as,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "uploaded_at": _now(),
                "meta": dict(meta or {}),
            }
            index.append(entry)
            self._write_json(d / "documents" / "index.json", index)
            self.update_meta(case_id)
            return entry

    def list_documents(self, case_id: str) -> list[dict]:
        return self._read_json(self._case_dir(case_id) / "documents" / "index.json", [])

    def _entry(self, case_id: str, doc_id: str) -> dict:
        if not DOC_ID_RE.match(doc_id or ""):
            raise CaseStoreError("Ungueltige Dokument-ID")
        for e in self.list_documents(case_id):
            if e["doc_id"] == doc_id:
                return e
        raise CaseNotFound(f"Dokument {doc_id} nicht gefunden")

    def read_document(self, case_id: str, doc_id: str) -> bytes:
        e = self._entry(case_id, doc_id)
        return (self._case_dir(case_id) / "documents" / e["stored_as"]).read_bytes()

    def remove_document(self, case_id: str, doc_id: str) -> None:
        with self._lock:
            e = self._entry(case_id, doc_id)
            d = self._case_dir(case_id)
            (d / "documents" / e["stored_as"]).unlink(missing_ok=True)
            index = [x for x in self.list_documents(case_id) if x["doc_id"] != doc_id]
            self._write_json(d / "documents" / "index.json", index)
            self.update_meta(case_id)

    def update_document_meta(self, case_id: str, doc_id: str, **fields: Any) -> dict:
        with self._lock:
            self._entry(case_id, doc_id)
            d = self._case_dir(case_id)
            index = self.list_documents(case_id)
            for e in index:
                if e["doc_id"] == doc_id:
                    e["meta"] = {**(e.get("meta") or {}), **fields}
                    entry = e
            self._write_json(d / "documents" / "index.json", index)
            self.update_meta(case_id)
            return entry

    # ------------------------------------------------------------ records
    RECORD_KINDS = ("agreements", "messages")

    def append_record(self, case_id: str, kind: str, record: dict) -> dict:
        if kind not in self.RECORD_KINDS:
            raise CaseStoreError(f"Unbekannte Ablage '{kind}'")
        with self._lock:
            path = self._case_dir(case_id) / f"{kind}.json"
            rows = self._read_json(path, [])
            rows.append(record)
            self._write_json(path, rows)
            self.update_meta(case_id)
            return record

    def list_records(self, case_id: str, kind: str) -> list[dict]:
        if kind not in self.RECORD_KINDS:
            raise CaseStoreError(f"Unbekannte Ablage '{kind}'")
        return self._read_json(self._case_dir(case_id) / f"{kind}.json", [])

    # --------------------------------------------------------------- logo
    LOGO_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}

    def set_logo(self, case_id: str, content: Optional[bytes], ext: str = "") -> None:
        with self._lock:
            d = self._case_dir(case_id)
            for old in self.LOGO_TYPES:
                (d / f"logo.{old}").unlink(missing_ok=True)
            if content is not None:
                if ext not in self.LOGO_TYPES:
                    raise CaseStoreError("Logo: PNG, JPG oder WebP")
                (d / f"logo.{ext}").write_bytes(content)
            self.update_meta(case_id, has_logo=content is not None)

    def get_logo(self, case_id: str) -> Optional[tuple[bytes, str]]:
        d = self._case_dir(case_id)
        for ext, ctype in self.LOGO_TYPES.items():
            f = d / f"logo.{ext}"
            if f.is_file():
                return f.read_bytes(), ctype
        return None

    # ----------------------------------------------------------- artifacts
    def _artifact_path(self, case_id: str, name: str) -> Path:
        if not ARTIFACT_RE.match(name or ""):
            raise CaseStoreError(f"Ungueltiger Artefaktname '{name}'")
        return self._case_dir(case_id) / "artifacts" / name

    def write_artifact(self, case_id: str, name: str, text: str) -> None:
        path = self._artifact_path(case_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_artifact(self, case_id: str, name: str) -> Optional[str]:
        path = self._artifact_path(case_id, name)
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def list_artifacts(self, case_id: str) -> list[str]:
        d = self._case_dir(case_id) / "artifacts"
        return sorted(p.name for p in d.iterdir() if p.is_file()) if d.is_dir() else []

    # ------------------------------------------------------------- outcomes
    def append_outcome(self, row: dict) -> None:
        if row.get("outcome") not in OUTCOMES:
            raise CaseStoreError(f"Ergebnis muss eines von {', '.join(OUTCOMES)} sein")
        path = self.root / "outcome_log.csv"
        with self._lock:
            new = not path.is_file()
            with path.open("a", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=OUTCOME_COLUMNS, extrasaction="ignore")
                if new:
                    writer.writeheader()
                writer.writerow({k: row.get(k, "") for k in OUTCOME_COLUMNS})

    def read_outcomes(self) -> list[dict]:
        path = self.root / "outcome_log.csv"
        if not path.is_file():
            return []
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
