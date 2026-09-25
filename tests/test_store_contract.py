"""One set of checks for every storage backend: the folder store and Supabase.

The Supabase run touches the real project, so it only happens when asked:

    CRA_SUPABASE_TESTS=1 python -m pytest tests/test_store_contract.py

It numbers its cases in the year 1999 (never a real case year), and removes
those cases, their files, the counter and its test outcomes afterwards.
"""

from __future__ import annotations

import os
import secrets

import pytest

from credit_readiness.auth import AuthError, Principal
from credit_readiness.casefile import CaseNotFound, CaseStoreError, LocalCaseStore

TEST_YEAR = 1999
LIVE = os.environ.get("CRA_SUPABASE_TESTS") == "1"
PDF = b"%PDF-1.4 test"


def _supabase_store():
    from credit_readiness.casefile_supabase import SupabaseCaseStore
    from credit_readiness.config import supabase_client

    return SupabaseCaseStore(supabase_client(), case_year=TEST_YEAR)


def _cleanup(store) -> None:
    for meta in store.list_cases():
        store.delete_case(meta["case_id"])
    store.sb.delete("case_counters", f"year=eq.{TEST_YEAR}")
    store.sb.delete("outcomes", f"row->>case_id=like.CRA-{TEST_YEAR}-*")


@pytest.fixture(params=["local", pytest.param("supabase", marks=pytest.mark.skipif(
    not LIVE, reason="set CRA_SUPABASE_TESTS=1 to test against the Supabase project"))])
def store(request, tmp_path):
    if request.param == "local":
        yield LocalCaseStore(tmp_path / "clients")
        return
    s = _supabase_store()
    _cleanup(s)
    yield s
    _cleanup(s)


def test_cases_are_numbered_and_listed(store):
    a = store.create_case("Alpha GmbH")
    b = store.create_case("Beta GmbH")
    assert a["case_id"][:9] == b["case_id"][:9]
    assert int(b["case_id"][-4:]) == int(a["case_id"][-4:]) + 1
    assert {m["case_id"] for m in store.list_cases()} >= {a["case_id"], b["case_id"]}
    assert store.get_meta(a["case_id"])["company_name"] == "Alpha GmbH"
    with pytest.raises(CaseStoreError):
        store.create_case("  ")


def test_meta_updates_and_stages(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    store.update_meta(cid, doc_notes={"x": "y"})
    assert store.get_meta(cid)["doc_notes"] == {"x": "y"}
    with pytest.raises(CaseStoreError):
        store.update_meta(cid, stage="abgeschlossen")
    store.set_stage(cid, "unterlagen_angefordert", "Brief")
    meta = store.get_meta(cid)
    assert meta["stage"] == "unterlagen_angefordert"
    assert meta["stage_history"][-1]["note"] == "Brief"
    with pytest.raises(CaseStoreError):
        store.set_stage(cid, "erfunden")


def test_answers_round_trip(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    assert store.load_answers(cid, "unternehmen") == {}
    store.save_answers(cid, "unternehmen", {"mitarbeiter": 12, "branche": "Einzelhandel"})
    store.save_answers(cid, "unternehmen", {"mitarbeiter": 13})
    assert store.load_answers(cid, "unternehmen") == {"mitarbeiter": 13}
    with pytest.raises(CaseStoreError):
        store.save_answers(cid, "bank", {})


def test_documents(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    one = store.add_document(cid, "jahresabschluesse", "JA 2025.pdf", PDF, {"fiscal_year": 2025})
    two = store.add_document(cid, "jahresabschluesse", "ja_2024.pdf", PDF + b"2", {"fiscal_year": 2024})
    assert one["filename"] == "JA_2025.pdf"
    assert [d["doc_id"] for d in store.list_documents(cid)] == [one["doc_id"], two["doc_id"]]
    assert store.read_document(cid, two["doc_id"]) == PDF + b"2"
    # A single-slot document is replaced, not duplicated.
    store.add_document(cid, "handelsregisterauszug", "hr.pdf", PDF)
    store.add_document(cid, "handelsregisterauszug", "hr2.pdf", PDF)
    assert [d["filename"] for d in store.list_documents(cid) if d["doc_type"] == "handelsregisterauszug"] == ["hr2.pdf"]
    upd = store.update_document_meta(cid, one["doc_id"], part="bilanz")
    assert upd["meta"] == {"fiscal_year": 2025, "part": "bilanz"}
    store.remove_document(cid, one["doc_id"])
    assert one["doc_id"] not in {d["doc_id"] for d in store.list_documents(cid)}
    with pytest.raises(CaseNotFound):
        store.read_document(cid, one["doc_id"])
    with pytest.raises(CaseStoreError):
        store.add_document(cid, "jahresabschluesse", "virus.exe", b"x")
    with pytest.raises(CaseStoreError):
        store.add_document(cid, "jahresabschluesse", "leer.pdf", b"")


def test_records_are_ordered(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    for i in range(3):
        store.append_record(cid, "messages", {"n": i})
    assert [r["n"] for r in store.list_records(cid, "messages")] == [0, 1, 2]
    assert store.list_records(cid, "agreements") == []
    with pytest.raises(CaseStoreError):
        store.append_record(cid, "notizen", {})


def test_logo(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    assert store.get_logo(cid) is None
    store.set_logo(cid, b"\x89PNG-test", "png")
    assert store.get_logo(cid) == (b"\x89PNG-test", "image/png")
    assert store.get_meta(cid)["has_logo"] is True
    store.set_logo(cid, None)
    assert store.get_logo(cid) is None


def test_artifacts(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    store.write_artifact(cid, "summary.json", "{}")
    store.write_artifact(cid, "summary.json", '{"a": 1}')
    store.write_artifact(cid, "diagnostik.md", "# x")
    assert store.read_artifact(cid, "summary.json") == '{"a": 1}'
    assert store.list_artifacts(cid) == ["diagnostik.md", "summary.json"]
    assert store.read_artifact(cid, "fehlt.md") is None
    with pytest.raises(CaseStoreError):
        store.write_artifact(cid, "../etc.md", "x")


def test_delete_case_removes_everything(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    store.add_document(cid, "handelsregisterauszug", "hr.pdf", PDF)
    store.set_logo(cid, b"\x89PNG-test", "png")
    store.append_record(cid, "agreements", {"x": 1})
    store.delete_case(cid)
    with pytest.raises(CaseNotFound):
        store.get_meta(cid)


def test_outcomes(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    store.append_outcome({"case_id": cid, "outcome": "APPROVED", "facility_amount_eur": 500000})
    rows = [r for r in store.read_outcomes() if r["case_id"] == cid]
    assert rows and rows[0]["outcome"] == "APPROVED" and rows[0]["facility_amount_eur"] == "500000"
    with pytest.raises(CaseStoreError):
        store.append_outcome({"case_id": cid, "outcome": "VIELLEICHT"})


# ------------------------------------------------------------------ accounts


@pytest.mark.skipif(not LIVE, reason="set CRA_SUPABASE_TESTS=1 to test against the Supabase project")
def test_supabase_accounts_and_sessions():
    from credit_readiness.auth_supabase import DbSessionManager, SupabaseUserStore
    from credit_readiness.config import supabase_client

    sb = supabase_client()
    users, sessions = SupabaseUserStore(sb), DbSessionManager(sb)
    email = f"contract-test-{secrets.token_hex(4)}@example.com"
    try:
        p = users.create(email, "Test Konto", "unternehmen", "erstes-passwort")
        assert p == Principal(email, "Test Konto", "unternehmen")
        with pytest.raises(AuthError):
            users.create(email, "Doppelt", "unternehmen", "erstes-passwort")
        assert users.authenticate(email, "erstes-passwort") == p
        assert users.authenticate(email, "falsch-falsch") is None
        users.set_password(email, "zweites-passwort")
        assert users.authenticate(email, "zweites-passwort") == p

        token = sessions.create(p)
        assert sessions.get(token) == p
        assert sessions.get(token + "x") is None
        sessions.destroy(token)
        assert sessions.get(token) is None

        for _ in range(8):
            sessions.record_failure(email)
        assert sessions.locked_out(email)
        sessions.clear_failures(email)
        assert not sessions.locked_out(email)
    finally:
        users.delete(email)
    assert users.get(email) is None


def test_results_are_kept_in_order(store):
    cid = store.create_case("Alpha GmbH")["case_id"]
    base = {"kind": "quick", "model_version": "m-000000000000", "band": "B", "score": 66.0,
            "score_generic": 65.0, "band_generic": "B", "verdict": "behebbar", "sector": "Einzelhandel",
            "nace_code": None, "size_class": "2_bis_10m", "coverage": 1.0, "created_by": None,
            "summary": {"band": "B"}}
    factors = [{"factor_key": "eigenkapitalquote", "value": 0.2, "score": 63.0, "weight": 0.16,
                "points_lost": 5.9, "basis": "Einzelhandel"}]
    store.record_result(cid, {**base, "factors": factors})
    store.record_result(cid, {**base, "kind": "report", "score": 70.0, "factors": factors})
    rows = store.list_results(cid)
    assert [r["kind"] for r in rows] == ["quick", "report"]
    assert float(rows[1]["score"]) == 70.0
