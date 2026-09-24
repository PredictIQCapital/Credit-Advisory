"""Agreements before data, messages, the company logo and the bank pack."""

from __future__ import annotations

import base64

import pytest

from credit_readiness import agreements as ag
from credit_readiness import workflow as wf
from credit_readiness.webapp import server

from tests.test_portal import Client, _register, env  # noqa: F401  (fixture)
from tests.test_workflow import TODAY, full_case, store  # noqa: F401  (fixtures)

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 40


# ------------------------------------------------------------------ agreements, unit


def test_signature_needs_first_and_last_name():
    with pytest.raises(ag.AgreementError):
        ag.sign([], ["datenschutz"], "Anna", "a@x.de")
    rec = ag.sign([], ["datenschutz"], "  Anna   Mueller ", "a@x.de", "10.0.0.1", "UA")[0]
    assert rec["signature"] == "Anna Mueller"
    assert rec["text_sha256"] == ag.AGREEMENTS_BY_ID["datenschutz"].sha256
    assert rec["version"] and rec["at"] and rec["ip"] == "10.0.0.1"


def test_required_agreements_and_version_changes():
    recs = ag.sign([], list(ag.REQUIRED_IDS), "Anna Mueller", "a@x.de")
    assert ag.missing_required(recs) == []
    # A new version of a text needs a new signature.
    recs[0] = {**recs[0], "version": "old"}
    assert ag.missing_required(recs) == [recs[0]["agreement"]]


def test_only_consents_can_be_withdrawn():
    recs = ag.sign([], ["ki", "datenschutz"], "Anna Mueller", "a@x.de")
    recs.append(ag.withdraw(recs, "ki", "a@x.de"))
    assert not ag.is_signed(recs, "ki")
    with pytest.raises(ag.AgreementError):
        ag.withdraw(recs, "datenschutz", "a@x.de")


# ------------------------------------------------------------------ agreements, HTTP


def test_nothing_is_entered_before_signing(env):  # noqa: F811
    store, _, base = env
    # A one-word name is not a signature: the account exists, the gate stays shut.
    c, cid = _register(base, name="Anna", release=False)
    assert store.list_records(cid, "agreements") == []
    status, _ = c.upload(cid, "handelsregisterauszug", "handelsregisterauszug.pdf")
    assert status == 403
    assert c.call("PUT", f"/api/cases/{cid}/answers/unternehmen", {"mitarbeiter": 5})[0] == 403
    # Reading and asking us a question stay open.
    assert c.call("GET", f"/api/cases/{cid}")[0] == 200
    assert c.call("POST", f"/api/cases/{cid}/messages", {"text": "Frage vorab"})[0] == 201

    status, ov = c.call("POST", f"/api/cases/{cid}/agreements",
                        {"ids": list(ag.REQUIRED_IDS), "name": "Anna Mueller"})
    assert status == 200 and ov["agreements_missing"] == []
    assert c.upload(cid, "handelsregisterauszug", "handelsregisterauszug.pdf")[0] == 201
    # The consent answer the engine reads follows the signature.
    assert store.load_answers(cid, "unternehmen")["datenschutz_einwilligung"] is True


def test_registration_with_full_name_signs(env):  # noqa: F811
    store, _, base = env
    _, cid = _register(base, release=False)
    recs = store.list_records(cid, "agreements")
    assert {r["agreement"] for r in recs} == set(ag.REQUIRED_IDS)
    assert all(r["signature"] == "Anna Mueller" and r["by"] == "anna@test.de" for r in recs)


def test_inviting_the_tax_advisor_needs_the_release(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base, release=False)
    body = {"role": "steuerberater", "email": "k@test.de", "name": "Kanzlei"}
    assert c.call("POST", f"/api/cases/{cid}/invite", body)[0] == 403
    c.call("POST", f"/api/cases/{cid}/agreements", {"ids": ["schweigepflicht"], "name": "Anna Mueller"})
    assert c.call("POST", f"/api/cases/{cid}/invite", body)[0] == 200


def test_ai_consent_withdrawal_is_recorded_and_synced(env):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    c.call("POST", f"/api/cases/{cid}/agreements", {"ids": ["ki"], "name": "Anna Mueller"})
    assert store.load_answers(cid, "unternehmen")["ki_einwilligung"] is True
    status, ov = c.call("POST", f"/api/cases/{cid}/agreements/ki/withdraw")
    assert status == 200
    assert store.load_answers(cid, "unternehmen")["ki_einwilligung"] is False
    assert [r["action"] for r in store.list_records(cid, "agreements") if r["agreement"] == "ki"] == \
        [ag.SIGNED, ag.WITHDRAWN]
    assert c.call("POST", f"/api/cases/{cid}/agreements/datenschutz/withdraw")[0] == 400


def test_proof_document_lists_every_record(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    status, html = c.call("GET", f"/api/cases/{cid}/agreements/record")
    assert status == 200
    text = html.decode("utf-8")
    assert "Anna Mueller" in text and ag.AGREEMENTS_BY_ID["datenschutz"].sha256 in text


# ------------------------------------------------------------------ messages


def test_messages_reach_the_advisor_with_unread_counts(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    status, ov = c.call("POST", f"/api/cases/{cid}/messages", {"text": "Wann ist der Bericht fertig?", "topic": "Termin"})
    assert status == 201 and ov["unread"] == 0 and ov["messages"][-1]["topic"] == "Termin"
    adv = Client(base)
    adv.login("berater@test.de", "berater-pass")
    assert next(x for x in adv.call("GET", "/api/cases")[1] if x["case_id"] == cid)["unread"] == 1
    adv.call("POST", f"/api/cases/{cid}/messages", {"text": "Bis Freitag."})
    assert adv.call("GET", f"/api/cases/{cid}")[1]["unread"] == 0
    assert c.call("GET", f"/api/cases/{cid}")[1]["unread"] == 1
    assert c.call("POST", f"/api/cases/{cid}/messages", {"text": "  "})[0] == 400
    assert c.call("POST", f"/api/cases/{cid}/messages", {"text": "x", "topic": "Werbung"})[0] == 400


def test_tax_advisor_does_not_see_the_thread(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    c.call("POST", f"/api/cases/{cid}/messages", {"text": "Vertraulich"})
    _, res = c.call("POST", f"/api/cases/{cid}/invite", {"role": "steuerberater", "email": "k@test.de"})
    stb = Client(base)
    stb.login("k@test.de", res["invite"]["temp_password"])
    assert stb.call("GET", f"/api/cases/{cid}")[1]["messages"] == []
    assert stb.call("POST", f"/api/cases/{cid}/messages", {"text": "x"})[0] == 403


# ------------------------------------------------------------------ logo


def test_logo_accepts_images_and_refuses_the_rest(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    put = lambda data: c.call("PUT", f"/api/cases/{cid}/logo",  # noqa: E731
                              {"content_base64": base64.b64encode(data).decode()})
    status, ov = put(PNG)
    assert status == 200 and ov["meta"]["has_logo"] is True
    assert c.call("GET", f"/api/cases/{cid}/logo") == (200, PNG)
    assert put(b"<svg onload='alert(1)'/>")[0] == 400
    assert put(PNG + b"\x00" * 1_000_001)[0] == 400
    assert c.call("DELETE", f"/api/cases/{cid}/logo")[1]["meta"]["has_logo"] is False
    assert c.call("GET", f"/api/cases/{cid}/logo")[0] == 404


# ------------------------------------------------------------------ bank pack


def test_bank_pack_holds_the_chosen_sections(store, full_case):  # noqa: F811
    res = wf.build_bank_pack(store, full_case, ["unternehmen", "kennzahlen", "band", "fortschreibung"],
                             actor="anna@test.de", today=TODAY)
    assert res["ok"]
    html = res["html"]
    assert "Mueller Praezisionstechnik" in html and "<svg" in html
    assert "Readiness-Band" in html and "kein Rating" in html
    assert "Massnahmenplan" not in html and "Unterlagenverzeichnis" not in html
    log = store.get_meta(full_case)["bankpack_downloads"]
    assert log[-1]["by"] == "anna@test.de" and log[-1]["sections"][0] == "unternehmen"


def test_bank_pack_defaults_leave_out_the_weaknesses(store, full_case):  # noqa: F811
    html = wf.build_bank_pack(store, full_case, [], today=TODAY)["html"]
    assert "Massnahmenplan" not in html and "Unterlagenverzeichnis" in html


def test_bank_pack_includes_the_logo(store, full_case):  # noqa: F811
    wf.set_logo(store, full_case, PNG)
    html = wf.build_bank_pack(store, full_case, ["unternehmen"], today=TODAY)["html"]
    assert "data:image/png;base64," in html


def test_bank_pack_over_http_is_a_pdf(env, monkeypatch):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    # Not enough data yet: a clear refusal, not an empty document.
    status, body = c.call("GET", f"/api/cases/{cid}/bankpack")
    assert status == 409 and "Noch nicht" in body["error"]
    monkeypatch.setattr(wf, "build_bank_pack", lambda *a, **k: {"ok": True, "html": "<p>x</p>", "company": "Firma"})
    monkeypatch.setattr(server, "html_to_pdf", lambda html, footer_title="": b"%PDF-1.7 test")
    status, body = c.call("GET", f"/api/cases/{cid}/bankpack?sections=band")
    assert status == 200 and body == b"%PDF-1.7 test"
    monkeypatch.setattr(server, "html_to_pdf", lambda html, footer_title="": None)
    assert c.call("GET", f"/api/cases/{cid}/bankpack")[1] == b"<p>x</p>"
