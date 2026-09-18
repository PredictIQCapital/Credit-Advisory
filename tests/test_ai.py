"""AI layer: document reading, confirmation, quick check, explanations, guardrails.

The Claude provider is tested against a stand-in client: the tests pin the
exact request we would send (model, document block, JSON schema, fallback) and
our handling of every response shape, without calling the paid API or sending
any data anywhere.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from credit_readiness import workflow as wf
from credit_readiness.ai import (
    AIError,
    AnthropicProvider,
    RulesProvider,
    check_figures,
    parse_confirmed,
    template_explanation,
    violates_guardrails,
)
from credit_readiness.ai.explain import explain
from credit_readiness.ai.extraction import FIELDS, extract_with_rules
from credit_readiness.ai.pdftext import _builtin, pdf_to_text
from credit_readiness.auth import ROLE_BERATER, UserStore
from credit_readiness.casefile import CaseStoreError, LocalCaseStore
from credit_readiness.demo import annual_accounts_pdf, placeholder_pdf

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"
TODAY = date(2026, 9, 18)


def _case(name: str) -> dict:
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


MUELLER = "case_01_mueller_praezisionstechnik"


# ------------------------------------------------------------------ reading


@pytest.mark.parametrize("name", [MUELLER, "case_02_nordlicht_handel",
                                  "case_03_gastro_rheinblick", "case_06_hoffmann_medizintechnik"])
def test_rules_reader_recovers_every_figure(name):
    payload = _case(name)
    res = RulesProvider().extract(annual_accounts_pdf(payload), "ja.pdf").as_dict()
    expected = {**payload["balance_sheet"], **payload["income_statement"]}
    for key, prop in res["fields"].items():
        assert prop["value"] == pytest.approx(float(expected.get(key) or 0), abs=0.5), key
    assert res["period_end"] == payload["balance_sheet"]["period_end"]
    assert all(c["ok"] for c in res["checks"])


def test_builtin_pdf_reader_works_without_optional_dependencies():
    text = _builtin(annual_accounts_pdf(_case(MUELLER)))
    assert "Umsatzerlöse" in text and "8.200.000,00" in text
    res = extract_with_rules(text)
    assert res.fields["umsatzerloese"].value == 8_200_000


def test_losses_are_read_with_a_negative_sign():
    res = extract_with_rules(_builtin(annual_accounts_pdf(_case("case_03_gastro_rheinblick"))))
    assert res.fields["jahresueberschuss"].value < 0
    assert res.fields["gewinnvortrag"].value < 0


def test_missing_term_split_is_flagged_conservatively():
    text = "PASSIVA\n1. Verbindlichkeiten gegenüber Kreditinstituten   500.000,00\n"
    res = extract_with_rules(text)
    assert res.fields["verb_kreditinstitute_kurz"].value == 500_000
    assert res.fields["verb_kreditinstitute_kurz"].confidence == "niedrig"


def test_scans_and_images_are_not_guessed():
    res = RulesProvider().extract(b"\x89PNG....", "scan.png")
    assert not res.text_found and res.warnings
    text, _ = pdf_to_text(b"not a pdf")
    assert text == ""


def test_prior_year_column_is_ignored():
    text = "GEWINN- UND VERLUSTRECHNUNG\n1. Umsatzerlöse   8.200.000,00   7.650.000,00\n"
    assert extract_with_rules(text).fields["umsatzerloese"].value == 8_200_000


# ------------------------------------------------------------ confirmation


def test_consistency_checks_catch_extraction_slips():
    payload = _case(MUELLER)
    figures = {**payload["balance_sheet"], **payload["income_statement"]}
    assert all(c["ok"] for c in check_figures(figures))
    figures["sachanlagen"] += 100_000                 # a misread line
    checks = {c["code"]: c["ok"] for c in check_figures(figures)}
    assert not checks["BILANZSUMME"]
    figures["sachanlagen"] -= 100_000
    figures["personalaufwand"] = 0                     # a dropped P&L line
    assert not {c["code"]: c["ok"] for c in check_figures(figures)}["ERGEBNIS"]


def test_confirmed_figures_accept_german_input_and_reject_garbage():
    figures, end, months = parse_confirmed({"figures": {"umsatzerloese": "8.200.000,00", "sachanlagen": "2.100.000"},
                                            "period_end": "2025-12-31", "period_months": 12})
    assert figures["umsatzerloese"] == 8_200_000 and figures["sachanlagen"] == 2_100_000
    assert set(figures) == {f.key for f in FIELDS}
    with pytest.raises(ValueError):
        parse_confirmed({"figures": {"umsatzerloese": "viel"}, "period_end": "2025-12-31"})
    with pytest.raises(ValueError):
        parse_confirmed({"figures": {}, "period_end": "gestern"})


# ------------------------------------------------------------------ Claude


class FakeClaude:
    """Records the request, returns a canned response."""

    def __init__(self, response_text="", stop_reason="end_turn", error=None):
        self.calls = []
        self._text, self._stop, self._error = response_text, stop_reason, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(stop_reason=self._stop,
                               content=[SimpleNamespace(type="text", text=self._text)])


def _claude_answer(**overrides) -> str:
    fields = {f.key: {"value": None, "source": "", "confidence": "hoch", "note": ""} for f in FIELDS}
    fields["umsatzerloese"] = {"value": 8200000, "source": "1. Umsatzerlöse", "confidence": "hoch", "note": ""}
    fields["sachanlagen"] = {"value": 2100000, "source": "II. Sachanlagen", "confidence": "mittel", "note": ""}
    data = {"company_name": "Mueller GmbH", "period_end": "2025-12-31", "period_months": 12,
            "fields": fields, "warnings": []}
    data.update(overrides)
    return json.dumps(data)


def test_claude_request_shape():
    fake = FakeClaude(_claude_answer())
    res = AnthropicProvider(client=fake).extract(b"%PDF-1.4 test", "ja.pdf")
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["extra_body"] == {"fallbacks": "default"}
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["format"]["type"] == "json_schema"
    schema = call["output_config"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]["fields"]["required"]) == {f.key for f in FIELDS}
    doc = call["messages"][0]["content"][0]
    assert doc["type"] == "document" and doc["source"]["media_type"] == "application/pdf"
    assert "\n" not in doc["source"]["data"]
    assert "not instructions" in call["system"], "prompt-injection guard in the system prompt"
    # Parsing: nulls are dropped, values kept with their source
    assert res.fields["umsatzerloese"].value == 8_200_000
    assert res.fields["sachanlagen"].source == "II. Sachanlagen"
    assert "vorraete" not in res.fields
    assert res.period_end == "2025-12-31"


def test_claude_reads_images_as_image_blocks():
    fake = FakeClaude(_claude_answer())
    AnthropicProvider(client=fake).extract(b"\xff\xd8jpeg", "scan.jpg")
    block = fake.calls[0]["messages"][0]["content"][0]
    assert block["type"] == "image" and block["source"]["media_type"] == "image/jpeg"


@pytest.mark.parametrize("fake", [
    FakeClaude(stop_reason="refusal"),
    FakeClaude(stop_reason="max_tokens"),
    FakeClaude(response_text="kein json"),
    FakeClaude(error=RuntimeError("network")),
])
def test_claude_failures_become_one_clear_error(fake):
    with pytest.raises(AIError):
        AnthropicProvider(client=fake).extract(b"%PDF-1.4", "ja.pdf")


def test_inference_region_is_passed_when_configured(monkeypatch):
    monkeypatch.setenv("CRA_AI_INFERENCE_GEO", "eu")
    fake = FakeClaude(_claude_answer())
    AnthropicProvider(client=fake).extract(b"%PDF-1.4", "ja.pdf")
    assert fake.calls[0]["inference_geo"] == "eu"


def test_explanation_request_sends_only_the_result_summary():
    fake = FakeClaude("Ihr Band ist C.")
    summary = {"band": "C", "findings": [], "company": "Geheim GmbH", "key_ratios": {}}
    AnthropicProvider(client=fake).explain(summary, "de")
    sent = fake.calls[0]["messages"][0]["content"]
    assert "Geheim GmbH" not in sent, "data minimisation: no company name to the AI"
    assert fake.calls[0]["output_config"] == {"effort": "low"}


# ------------------------------------------------------------- guardrails


@pytest.mark.parametrize("text", [
    "Ihr Kredit wird genehmigt.", "Die Bank wird sicher bewilligt", "You have a 80% chance of approval",
    "Das ist garantiert.", "Ihre Ausfallwahrscheinlichkeit von 2 %", "Your loan will be approved.",
])
def test_guardrails_catch_promises_and_ratings(text):
    assert violates_guardrails(text)


def test_guardrails_let_normal_explanations_through():
    assert violates_guardrails("Ihr Readiness-Band ist C. Ein Rangrücktritt würde die Eigenkapitalquote verbessern.") is None


def test_ai_text_that_breaks_the_rules_is_replaced_by_the_template():
    fake = FakeClaude("Gute Nachricht: Ihr Kredit wird genehmigt!")
    res = explain(AnthropicProvider(client=fake), {"band": "C", "band_after_remediation": "A",
                                                   "verdict": "behebbar", "findings": []}, "de")
    assert res["source"] == "vorlage" and res["blocked"]
    assert "genehmigt" not in res["text"]


def test_template_explanation_names_the_findings_and_the_disclaimer():
    text = template_explanation({"band": "C", "band_after_remediation": "A", "verdict": "behebbar",
                                 "findings": [{"rule": "R01"}]}, "en")
    assert "subordination" in text and "not a credit rating" in text


# ------------------------------------------------------------- quick check


@pytest.fixture
def store(tmp_path):
    return LocalCaseStore(tmp_path / "clients")


QUICK_ANSWERS = {
    "firmenname": "Mueller Praezisionstechnik GmbH", "rechtsform": "GmbH",
    "branche": "Verarbeitendes Gewerbe", "mitarbeiter": 45, "gruendungsjahr": 2009,
    "betrag": "750.000", "zweck": "Investition", "laufzeit_jahre": 7,
    "hat_gesellschafterdarlehen": True, "rangruecktritt": False, "tilgung_gesamt_jahr": 180000,
    "kontokorrent_limit": 500000, "kontokorrent_inanspruchnahme": 420000,
    "steuerrueckstaende": False, "bwa_frequenz": "quartalsweise", "bwa_stand": "2026-04",
    "datenschutz_einwilligung": True,
}


def _quick_case(store, answers=QUICK_ANSWERS):
    cid = store.create_case("Mueller Praezisionstechnik GmbH")["case_id"]
    store.save_answers(cid, "unternehmen", answers)
    store.add_document(cid, "jahresabschluesse", "ja_2025.pdf", annual_accounts_pdf(_case(MUELLER)))
    ext = wf.extract_figures(store, cid, actor="anna@test.de")
    wf.confirm_figures(store, cid, {"figures": {k: v["value"] for k, v in ext["fields"].items()},
                                    "period_end": ext["period_end"], "period_months": 12}, "anna@test.de")
    return cid


def test_quick_check_from_a_pdf_end_to_end(store):
    cid = _quick_case(store)
    res = wf.run_quick_check(store, cid, today=TODAY)
    assert res["ok"], res
    q = res["quick_check"]
    assert q["band"] in "ABCDE" and len(q["top_findings"]) == 3
    assert {"R01", "R04"} & {f["rule"] for f in q["top_findings"]}
    assert any("bestaetigt" in n for n in q["data_notes"])
    assert any("Kapitaldienst geschaetzt" in n for n in q["data_notes"])
    assert "simulation" not in q and "top_lender_after" not in q, "the free tier stays partial"


def test_nothing_is_calculated_before_confirmation(store):
    cid = store.create_case("X GmbH")["case_id"]
    store.save_answers(cid, "unternehmen", QUICK_ANSWERS)
    store.add_document(cid, "jahresabschluesse", "ja.pdf", annual_accounts_pdf(_case(MUELLER)))
    wf.extract_figures(store, cid)
    res = wf.run_quick_check(store, cid, today=TODAY)
    assert not res["ok"] and any("bestaetigter Jahresabschluss" in b for b in res["blocking"])


def test_confirmed_figures_that_do_not_balance_are_refused(store):
    cid = _quick_case(store)
    raw = json.loads(store.read_artifact(cid, "figures_confirmed.json"))
    raw["figures"]["sachanlagen"] += 250_000
    wf.confirm_figures(store, cid, {"figures": raw["figures"], "period_end": "2025-12-31"}, "anna@test.de")
    res = wf.run_quick_check(store, cid, today=TODAY)
    assert not res["ok"] and res["stage"] == "validation"


def test_corrections_are_recorded(store):
    cid = _quick_case(store)
    raw = json.loads(store.read_artifact(cid, "figures_confirmed.json"))
    figures = dict(raw["figures"])
    figures["verb_kreditinstitute_kurz"], figures["verb_kreditinstitute_lang"] = 100_000, 1_570_000
    rec = wf.confirm_figures(store, cid, {"figures": figures, "period_end": "2025-12-31"}, "anna@test.de")
    assert rec["corrected_fields"] == ["verb_kreditinstitute_kurz", "verb_kreditinstitute_lang"]


def test_datev_export_takes_precedence_over_read_figures(store):
    cid = _quick_case(store)
    store.add_document(cid, "susa_aktuell", "susa.csv", (SAMPLES / "datev_susa_example.csv").read_bytes(),
                       {"period_end": "2025-12-31", "period_months": 12})
    from credit_readiness.intake.assemble import assemble_case
    asm = assemble_case(store, cid, today=TODAY)
    assert asm.provenance["balance_sheet"] == "DATEV-SuSa"


def test_external_ai_requires_the_companys_consent(store):
    cid = store.create_case("X GmbH")["case_id"]
    store.save_answers(cid, "unternehmen", {**QUICK_ANSWERS, "ki_einwilligung": False})
    store.add_document(cid, "jahresabschluesse", "ja.pdf", annual_accounts_pdf(_case(MUELLER)))
    fake = FakeClaude(_claude_answer())
    with pytest.raises(CaseStoreError, match="Einwilligung"):
        wf.extract_figures(store, cid, provider=AnthropicProvider(client=fake))
    assert fake.calls == [], "nothing may be sent without consent"
    store.save_answers(cid, "unternehmen", {**QUICK_ANSWERS, "ki_einwilligung": True})
    wf.extract_figures(store, cid, provider=AnthropicProvider(client=fake), actor="a@b.de")
    assert len(fake.calls) == 1


def test_every_ai_call_is_logged_without_content(store):
    cid = _quick_case(store)
    log = json.loads(store.read_artifact(cid, "ai_log.json"))
    entry = log[0]
    assert entry["purpose"] == "auslesung" and entry["provider"] == "regeln" and not entry["external"]
    assert len(entry["input_sha256"]) == 64 and entry["actor"] == "anna@test.de"
    assert "Umsatz" not in json.dumps(log), "the log must not become a copy of the data"


def test_explain_quick_result_uses_template_with_local_provider(store):
    cid = _quick_case(store)
    wf.run_quick_check(store, cid, today=TODAY)
    res = wf.explain_result(store, cid, "de", None, "quick", "anna@test.de")
    assert res["source"] == "vorlage" and "Readiness-Band" in res["text"]


def test_orders(store):
    cid = _quick_case(store)
    meta = wf.place_order(store, cid, "report", "anna@test.de")
    assert meta["orders"][0]["price_eur"] == 390 and meta["orders"][0]["payment"] == "Rechnung"
    with pytest.raises(CaseStoreError):
        wf.place_order(store, cid, "report", "anna@test.de")
    with pytest.raises(CaseStoreError):
        wf.place_order(store, cid, "gold", "anna@test.de")


def test_client_can_erase_everything(store):
    users = UserStore(store.root)
    p, meta = wf.register_client(store, users, "Weg GmbH", "W", "weg@test.de", "12345678")
    store.add_document(meta["case_id"], "handelsregisterauszug", "hr.pdf", placeholder_pdf("x"))
    deleted = wf.delete_client_data(store, users, "weg@test.de")
    assert deleted == [meta["case_id"]]
    assert not (store.root / meta["case_id"]).exists()
    assert users.get("weg@test.de") is None


# ------------------------------------------------------------------- http


def test_quick_check_over_http(tmp_path):
    from tests.test_portal import Client, _register  # noqa: F401  (reuse helpers)
    from credit_readiness.webapp.server import make_server
    store = LocalCaseStore(tmp_path / "c")
    users = UserStore(store.root)
    users.create("berater@test.de", "B", ROLE_BERATER, "berater-pass")
    srv = make_server(store, port=0, today=TODAY, users=users)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        c, cid = _register(base)
        import base64
        pdf = base64.b64encode(annual_accounts_pdf(_case(MUELLER))).decode()
        assert c.call("POST", f"/api/cases/{cid}/documents", {"doc_type": "jahresabschluesse",
                      "filename": "ja.pdf", "content_base64": pdf})[0] == 201
        status, res = c.call("POST", f"/api/cases/{cid}/extract", {})
        assert status == 200 and res["extraction"]["fields"]["umsatzerloese"]["value"] == 8_200_000
        figures = {k: v["value"] for k, v in res["extraction"]["fields"].items()}
        assert c.call("PUT", f"/api/cases/{cid}/figures", {"figures": figures, "period_end": "2025-12-31"})[0] == 200
        c.call("PUT", f"/api/cases/{cid}/answers/unternehmen", QUICK_ANSWERS)
        status, res = c.call("POST", f"/api/cases/{cid}/quickcheck")
        assert status == 200 and res["ok"] and res["overview"]["quick_check"]["band"]
        status, res = c.call("POST", f"/api/cases/{cid}/explain", {"which": "quick", "lang": "en"})
        assert status == 200 and res["text"]
        # The full report is not visible, so it cannot be explained either
        assert c.call("POST", f"/api/cases/{cid}/explain", {"which": "report"})[0] == 404
        assert c.call("POST", f"/api/cases/{cid}/order", {"product": "report"})[0] == 200
        # Erasure needs the typed confirmation, then logs out
        assert c.call("DELETE", "/api/account", {"confirm": "ja"})[0] == 400
        assert c.call("DELETE", "/api/account", {"confirm": "LOESCHEN"})[0] == 200
        assert c.call("GET", "/api/cases")[0] == 401
        assert not (store.root / cid).exists()
    finally:
        srv.shutdown()
        srv.server_close()


def test_meta_tells_the_page_which_ai_is_active(monkeypatch):
    from credit_readiness.webapp.server import meta_payload
    assert meta_payload()["ai"] == {"key": "regeln", "label": "Regelbasierte Auslesung (lokal)",
                                    "external": False, "model": None}
    monkeypatch.setenv("CRA_AI_PROVIDER", "anthropic")
    ai = meta_payload()["ai"]
    assert ai["external"] and ai["model"] == "claude-opus-5"
    assert len(meta_payload()["figure_fields"]) == len(FIELDS)


def test_quick_check_explanation_never_mentions_a_missing_band():
    """The quick check has no after-remediation band; the text must not say 'None'."""
    text = template_explanation({"band": "B", "verdict": "behebbar", "findings": [{"rule": "R04"}]}, "en")
    assert "None" not in text and "band today is B" in text
