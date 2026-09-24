"""Web portal: accounts, sessions, the permission matrix, demo data, translations.

The permission tests go through real HTTP with real cookies, because that is
where a mistake would leak one client's financials to another.
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import pytest

from credit_readiness import workflow as wf
from credit_readiness.auth import (
    ROLE_BERATER,
    AuthError,
    SessionManager,
    UserStore,
    hash_password,
    verify_password,
)
from credit_readiness.casefile import LocalCaseStore
from credit_readiness.demo import DEMO_PASSWORD, seed_demo
from credit_readiness.intake.documents import DOCUMENT_TYPES
from credit_readiness.intake.questionnaire import AUDIENCES, QUESTIONNAIRES
from credit_readiness.intake.translations_en import (
    document_with_english,
    questionnaire_with_english,
)
from credit_readiness.webapp.server import make_server

INTAKE = Path(__file__).resolve().parents[1] / "data" / "samples" / "intake"
TODAY = date(2026, 9, 18)


# ------------------------------------------------------------------ helpers


class Client:
    """A browser stand-in: keeps its own cookies, speaks JSON."""

    def __init__(self, base: str):
        self.base = base
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
        try:
            with self.opener.open(req) as r:
                raw = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            raw, status = e.read(), e.code
        try:
            return status, json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return status, raw

    def login(self, email, password):
        status, body = self.call("POST", "/api/auth/login", {"email": email, "password": password})
        assert status == 200, body
        return body

    def upload(self, cid, doc_type, name, **extra):
        return self.call("POST", f"/api/cases/{cid}/documents", {
            "doc_type": doc_type, "filename": name,
            "content_base64": base64.b64encode((INTAKE / name).read_bytes()).decode(), **extra})


@pytest.fixture
def env(tmp_path):
    store = LocalCaseStore(tmp_path / "clients")
    users = UserStore(store.root)
    users.create("berater@test.de", "Berater", ROLE_BERATER, "berater-pass")
    srv = make_server(store, port=0, today=TODAY, users=users)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    yield store, users, base
    srv.shutdown()
    srv.server_close()


def _answers(name):
    return json.loads((INTAKE / name).read_text(encoding="utf-8"))


def _register(base, company="Mueller Praezisionstechnik GmbH", email="anna@test.de"):
    c = Client(base)
    status, body = c.call("POST", "/api/auth/register", {
        "company_name": company, "name": "Anna", "email": email,
        "password": "anna-pass-1", "consent": True})
    assert status == 201, body
    return c, body["case_id"]


# ------------------------------------------------------------------ auth unit


def test_password_hashing():
    h = hash_password("geheim123")
    assert h.startswith("pbkdf2_sha256$") and "geheim123" not in h
    assert verify_password("geheim123", h)
    assert not verify_password("geheim124", h)
    assert hash_password("geheim123") != h, "salted: same password, different hash"


def test_user_store_rules(tmp_path):
    users = UserStore(tmp_path)
    users.create("A@Example.de", "A", ROLE_BERATER, "12345678")
    assert users.authenticate("a@example.de", "12345678").email == "a@example.de"
    assert users.authenticate("a@example.de", "falsch") is None
    assert users.authenticate("nobody@example.de", "12345678") is None
    with pytest.raises(AuthError):
        users.create("a@example.de", "dup", ROLE_BERATER, "12345678")
    with pytest.raises(AuthError):
        users.create("b@example.de", "short", ROLE_BERATER, "123")
    with pytest.raises(AuthError):
        users.create("not-an-email", "x", ROLE_BERATER, "12345678")
    with pytest.raises(AuthError):
        users.create("c@example.de", "x", "admin", "12345678")
    assert "password_hash" not in users.list()[0]


def test_sessions_expire_and_can_be_destroyed():
    from credit_readiness.auth import Principal
    sm = SessionManager(ttl=-1)
    tok = sm.create(Principal("a@b.de", "A", ROLE_BERATER))
    assert sm.get(tok) is None, "expired session must not authenticate"
    sm = SessionManager()
    tok = sm.create(Principal("a@b.de", "A", ROLE_BERATER))
    assert sm.get(tok).email == "a@b.de"
    sm.destroy(tok)
    assert sm.get(tok) is None


# ------------------------------------------------------------------ http: auth


def test_api_requires_login(env):
    _, _, base = env
    c = Client(base)
    assert c.call("GET", "/api/cases")[0] == 401
    assert c.call("GET", "/api/auth/me") == (200, {"user": None})
    for page in ("/", "/investors", "/app", "/site.css", "/app.js", "/api/meta"):
        assert c.call("GET", page)[0] == 200, page


def test_login_logout_and_wrong_password(env):
    _, _, base = env
    c = Client(base)
    assert c.call("POST", "/api/auth/login", {"email": "berater@test.de", "password": "x"})[0] == 401
    c.login("berater@test.de", "berater-pass")
    assert c.call("GET", "/api/auth/me")[1]["user"]["role"] == "berater"
    c.call("POST", "/api/auth/logout")
    assert c.call("GET", "/api/cases")[0] == 401


def test_repeated_failures_lock_the_account_temporarily(env):
    _, _, base = env
    c = Client(base)
    for _ in range(8):
        c.call("POST", "/api/auth/login", {"email": "berater@test.de", "password": "wrong"})
    status, _ = c.call("POST", "/api/auth/login", {"email": "berater@test.de", "password": "berater-pass"})
    assert status == 429


def test_session_cookie_is_httponly_and_samesite(env):
    _, _, base = env
    req = urllib.request.Request(base + "/api/auth/login", method="POST",
                                 data=json.dumps({"email": "berater@test.de", "password": "berater-pass"}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        cookie = r.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_registration_creates_account_and_case(env):
    store, users, base = env
    c, cid = _register(base)
    meta = store.get_meta(cid)
    assert meta["members"]["unternehmen"] == ["anna@test.de"]
    answers = store.load_answers(cid, "unternehmen")
    assert answers["firmenname"] == "Mueller Praezisionstechnik GmbH"
    assert answers["datenschutz_einwilligung"] is True
    assert [x["case_id"] for x in c.call("GET", "/api/cases")[1]] == [cid]


def test_registration_requires_consent(env):
    _, _, base = env
    status, body = Client(base).call("POST", "/api/auth/register", {
        "company_name": "X", "name": "Y", "email": "y@test.de", "password": "12345678"})
    assert status == 400


# ------------------------------------------------------------ http: permissions


def test_clients_cannot_see_each_others_cases(env):
    _, _, base = env
    a, cid_a = _register(base, "A GmbH", "a@test.de")
    b, cid_b = _register(base, "B GmbH", "b@test.de")
    assert a.call("GET", f"/api/cases/{cid_b}")[0] == 404
    assert a.call("PUT", f"/api/cases/{cid_b}/answers/unternehmen", {"x": 1})[0] == 404
    assert [x["case_id"] for x in b.call("GET", "/api/cases")[1]] == [cid_b]


def test_client_cannot_perform_advisor_actions(env):
    _, _, base = env
    c, cid = _register(base)
    for path in ("diagnose", "letters", "release", "stage", "outcome"):
        assert c.call("POST", f"/api/cases/{cid}/{path}", {})[0] == 403, path
    assert c.call("PUT", f"/api/cases/{cid}/answers/steuerberater", {})[0] == 403
    assert c.call("POST", "/api/cases", {"company_name": "X"})[0] == 403


def test_report_is_hidden_from_client_until_released(env):
    store, _, base = env
    c, cid = _register(base)
    c.call("PUT", f"/api/cases/{cid}/answers/unternehmen", {
        **_answers("antworten_unternehmen.json"), "ansprechpartner_email": "anna@test.de"})
    c.upload(cid, "susa_aktuell", "susa_2025.csv", period_end="2025-12-31", period_months=12)
    adv = Client(base)
    adv.login("berater@test.de", "berater-pass")
    status, res = adv.call("POST", f"/api/cases/{cid}/diagnose")
    assert status == 200 and res["ok"], res

    ov = c.call("GET", f"/api/cases/{cid}")[1]
    assert ov["latest_summary"] is None and ov["assembly_notes"] == []
    assert c.call("GET", f"/api/cases/{cid}/artifacts/diagnostik.html")[0] == 404
    assert c.call("GET", f"/api/cases/{cid}/artifacts/case.json")[0] == 404

    assert adv.call("POST", f"/api/cases/{cid}/release", {"released": True})[0] == 200
    ov = c.call("GET", f"/api/cases/{cid}")[1]
    assert ov["latest_summary"]["band"] == "B"
    assert c.call("GET", f"/api/cases/{cid}/artifacts/diagnostik.html")[0] == 200
    assert c.call("GET", f"/api/cases/{cid}/artifacts/case.json")[0] == 404, "internal files stay internal"
    assert store.get_meta(cid)["stage"] == "massnahmen_in_umsetzung"


def test_tax_advisor_flow_and_limits(env):
    _, _, base = env
    c, cid = _register(base)
    status, res = c.call("POST", f"/api/cases/{cid}/invite", {"role": "steuerberater", "email": "kanzlei@test.de", "name": "Kanzlei"})
    assert status == 200 and res["invite"]["created"]
    assert c.call("POST", f"/api/cases/{cid}/invite", {"role": "berater", "email": "x@test.de"})[0] == 403

    stb = Client(base)
    stb.login("kanzlei@test.de", res["invite"]["temp_password"])
    ov = stb.call("GET", f"/api/cases/{cid}")[1]
    assert "unternehmen" not in ov["raw_answers"], "tax advisor does not see the client's answers"
    assert stb.call("PUT", f"/api/cases/{cid}/answers/unternehmen", {})[0] == 403
    assert stb.call("PUT", f"/api/cases/{cid}/answers/steuerberater", _answers("antworten_steuerberater.json"))[0] == 200
    assert stb.upload(cid, "handelsregisterauszug", "handelsregisterauszug.pdf")[0] == 403
    assert stb.upload(cid, "susa_aktuell", "susa_2025.csv", period_end="2025-12-31")[0] == 201
    assert stb.call("POST", f"/api/cases/{cid}/submit")[0] == 403


def test_members_can_only_delete_their_own_uploads(env):
    _, _, base = env
    c, cid = _register(base)
    _, res = c.call("POST", f"/api/cases/{cid}/invite", {"role": "steuerberater", "email": "k@test.de"})
    stb = Client(base)
    stb.login("k@test.de", res["invite"]["temp_password"])
    _, up = stb.upload(cid, "bwa_aktuell", "bwa_2026_04.pdf")
    doc = up["document"]["doc_id"]
    assert c.call("DELETE", f"/api/cases/{cid}/documents/{doc}")[0] == 403
    assert stb.call("DELETE", f"/api/cases/{cid}/documents/{doc}")[0] == 200


def test_submit_requires_complete_questionnaire(env):
    store, _, base = env
    c, cid = _register(base)
    assert c.call("POST", f"/api/cases/{cid}/submit")[0] == 400
    c.call("PUT", f"/api/cases/{cid}/answers/unternehmen", _answers("antworten_unternehmen.json"))
    status, ov = c.call("POST", f"/api/cases/{cid}/submit")
    assert status == 200 and ov["submitted_at"]


def test_advisor_can_create_case_and_invite_client(env):
    _, _, base = env
    adv = Client(base)
    adv.login("berater@test.de", "berater-pass")
    status, res = adv.call("POST", "/api/cases", {"company_name": "Neu GmbH", "client_email": "neu@test.de", "client_name": "Neu"})
    assert status == 201 and res["invite"]["temp_password"]
    client = Client(base)
    client.login("neu@test.de", res["invite"]["temp_password"])
    assert [x["company_name"] for x in client.call("GET", "/api/cases")[1]] == ["Neu GmbH"]


def test_cross_site_writes_are_rejected(env):
    _, _, base = env
    status, _ = Client(base).call("POST", "/api/auth/login", {"email": "a", "password": "b"},
                                  {"Origin": "http://evil.example"})
    assert status == 403


def test_path_tricks_are_blocked(env):
    _, _, base = env
    c = Client(base)
    c.login("berater@test.de", "berater-pass")
    for path in ("/../pyproject.toml", "/..%2F..%2Fpyproject.toml", "/users.json",
                 "/api/cases/CRA-2026-0001/artifacts/..%2Fcase_meta.json"):
        assert c.call("GET", path)[0] == 404, path


def test_printable_forms_are_public(env):
    _, _, base = env
    for form in ("unternehmen", "steuerberater", "unterlagen"):
        assert Client(base).call("GET", f"/forms/{form}.html")[0] == 200


# ------------------------------------------------------------------ demo


def test_demo_seed_tells_the_intended_stories(tmp_path):
    store = LocalCaseStore(tmp_path / "demo")
    ids = seed_demo(store, today=TODAY)
    mueller = wf.case_overview(store, ids["mueller"], today=TODAY)
    gastro = wf.case_overview(store, ids["gastro"], today=TODAY)
    assert mueller["report_released"] and mueller["latest_summary"]["engageable"]
    assert (mueller["latest_summary"]["band"], mueller["latest_summary"]["score"]) == ("B", 65.6)
    assert gastro["latest_summary"]["verdict"].startswith("nicht behebbar")
    assert gastro["meta"]["stage"] == "abgeschlossen"
    assert store.read_outcomes()[0]["outcome"] == "ADVISED_NOT_TO_APPLY"
    assert wf.case_overview(store, ids["nordlicht"])["latest_summary"] is None
    assert UserStore(store.root).authenticate("anna.mueller@demo.de", DEMO_PASSWORD)
    with pytest.raises(RuntimeError):
        seed_demo(store)


def test_demo_meta_exposes_accounts_only_in_demo_mode(tmp_path):
    from credit_readiness.webapp.server import meta_payload
    assert "demo_accounts" not in meta_payload(False)
    assert len(meta_payload(True)["demo_accounts"]) == 6


# ------------------------------------------------------------ translations


@pytest.mark.parametrize("audience", AUDIENCES)
def test_every_question_has_an_english_text(audience):
    q = questionnaire_with_english(QUESTIONNAIRES[audience].as_dict())
    assert q["title_en"]
    for s in q["sections"]:
        assert s["title_en"]
        for question in s["questions"]:
            assert question["label_en"]
            if "options" in question:
                assert len(question["options_en"]) == len(question["options"])
            for f in question.get("fields", []):
                assert f["label_en"]


def test_every_document_has_an_english_text():
    for d in DOCUMENT_TYPES:
        en = document_with_english(d.as_dict())
        assert en["title_en"] and en["description_en"] and en["why_en"]


def test_section_progress_tracks_the_wizard(tmp_path):
    sections = {s["id"]: s for s in wf.section_progress("unternehmen", {})}
    assert not any(s["complete"] for s in sections.values())
    full = {s["id"]: s for s in wf.section_progress("unternehmen", _answers("antworten_unternehmen.json"))}
    assert all(s["complete"] for s in full.values())
