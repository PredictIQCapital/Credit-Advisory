"""Case storage, assembly, the engagement workflow, letters and the portal API."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from credit_readiness import workflow as wf
from credit_readiness.casefile import CaseNotFound, CaseStoreError, LocalCaseStore, safe_filename
from credit_readiness.intake.assemble import assemble_case, months_between
from credit_readiness.reporting.forms import answers_template, documents_markdown, questionnaire_markdown
from credit_readiness.reporting.html import markdown_to_html
from credit_readiness.intake.questionnaire import AUDIENCES, get_questionnaire

INTAKE = Path(__file__).resolve().parents[1] / "data" / "samples" / "intake"
TODAY = date(2026, 9, 18)


def _answers(name: str) -> dict:
    return json.loads((INTAKE / name).read_text(encoding="utf-8"))


@pytest.fixture
def store(tmp_path) -> LocalCaseStore:
    return LocalCaseStore(tmp_path / "clients")


@pytest.fixture
def full_case(store) -> str:
    """The fictional Mueller engagement, fully uploaded."""
    cid = store.create_case("Mueller Praezisionstechnik GmbH")["case_id"]
    store.save_answers(cid, "unternehmen", _answers("antworten_unternehmen.json"))
    store.save_answers(cid, "steuerberater", _answers("antworten_steuerberater.json"))
    for doc_type, name, meta in [
        ("susa_aktuell", "susa_2025.csv", {"period_end": "2025-12-31", "period_months": 12}),
        ("susa_vorjahr", "susa_2024.csv", {"period_end": "2024-12-31", "period_months": 12}),
        ("kontoumsaetze", "kontoumsaetze_kontokorrent.csv", {"account_label": "KK"}),
    ]:
        store.add_document(cid, doc_type, name, (INTAKE / name).read_bytes(), meta)
    return cid


# ------------------------------------------------------------------ store


def test_case_ids_are_sequential_and_validated(store):
    a = store.create_case("A GmbH")["case_id"]
    b = store.create_case("B GmbH")["case_id"]
    assert int(b[-4:]) == int(a[-4:]) + 1
    for bad in ("../x", "CRA-2026-1", "CRA-2026-0001/../../etc"):
        with pytest.raises(CaseStoreError):
            store.get_meta(bad)
    with pytest.raises(CaseNotFound):
        store.get_meta("CRA-2026-9999")


@pytest.mark.parametrize("raw,expected", [
    ("../../evil.pdf", "evil.pdf"),
    ("C:\\Users\\x\\Bilanz 2025 (final).pdf", "Bilanz_2025_final_.pdf"),
    ("...", "datei"),
    ("süßes Dokument.pdf", "s_es_Dokument.pdf"),
])
def test_filenames_are_sanitised(raw, expected):
    assert safe_filename(raw) == expected


def test_upload_rules(store):
    cid = store.create_case("X GmbH")["case_id"]
    with pytest.raises(CaseStoreError, match="Format"):
        store.add_document(cid, "handelsregisterauszug", "hr.csv", b"x")
    with pytest.raises(CaseStoreError, match="Leere"):
        store.add_document(cid, "handelsregisterauszug", "hr.pdf", b"")
    with pytest.raises(ValueError):
        store.add_document(cid, "unbekannt", "x.pdf", b"x")


def test_single_slot_document_is_replaced_not_duplicated(store):
    cid = store.create_case("X GmbH")["case_id"]
    store.add_document(cid, "handelsregisterauszug", "alt.pdf", b"%PDF-1")
    store.add_document(cid, "handelsregisterauszug", "neu.pdf", b"%PDF-2")
    docs = store.list_documents(cid)
    assert [d["filename"] for d in docs] == ["neu.pdf"]
    files = list((store.root / cid / "documents").glob("*.pdf"))
    assert len(files) == 1, "the replaced file must be deleted from disk too"


def test_multi_slot_documents_accumulate_and_can_be_removed(store):
    cid = store.create_case("X GmbH")["case_id"]
    a = store.add_document(cid, "jahresabschluesse", "2025.pdf", b"%PDF-a")
    store.add_document(cid, "jahresabschluesse", "2024.pdf", b"%PDF-b")
    assert len(store.list_documents(cid)) == 2
    store.remove_document(cid, a["doc_id"])
    assert [d["filename"] for d in store.list_documents(cid)] == ["2024.pdf"]


def test_artifact_names_are_whitelisted(store):
    cid = store.create_case("X GmbH")["case_id"]
    for bad in ("../case_meta.json", "x.exe", "a/b.md", ""):
        with pytest.raises(CaseStoreError):
            store.write_artifact(cid, bad, "x")


def test_stage_changes_are_recorded(store):
    cid = store.create_case("X GmbH")["case_id"]
    store.set_stage(cid, "unterlagen_angefordert", "Brief raus")
    meta = store.get_meta(cid)
    assert meta["stage"] == "unterlagen_angefordert"
    assert [h["stage"] for h in meta["stage_history"]] == ["neu", "unterlagen_angefordert"]
    with pytest.raises(CaseStoreError):
        store.set_stage(cid, "erfunden")


# --------------------------------------------------------------- assembly


def test_empty_case_is_blocked_with_reasons(store):
    cid = store.create_case("X GmbH")["case_id"]
    asm = assemble_case(store, cid, today=TODAY)
    assert not asm.ready
    text = " ".join(asm.blocking)
    assert "Datenschutzeinwilligung" in text
    assert "Summen- und Saldenliste" in text


def test_missing_consent_blocks_even_with_complete_data(store, full_case):
    answers = _answers("antworten_unternehmen.json")
    answers["datenschutz_einwilligung"] = False
    store.save_answers(full_case, "unternehmen", answers)
    asm = assemble_case(store, full_case, today=TODAY)
    assert not asm.ready
    assert any("Datenschutz" in b for b in asm.blocking)


def test_skr03_is_refused_rather_than_guessed(store, full_case):
    stb = _answers("antworten_steuerberater.json")
    stb["kontenrahmen"] = "SKR03"
    store.save_answers(full_case, "steuerberater", stb)
    asm = assemble_case(store, full_case, today=TODAY)
    assert not asm.ready
    assert any("SKR03" in b for b in asm.blocking)


def test_susa_without_period_is_blocked(store):
    cid = store.create_case("X GmbH")["case_id"]
    store.save_answers(cid, "unternehmen", _answers("antworten_unternehmen.json"))
    store.add_document(cid, "susa_aktuell", "s.csv", (INTAKE / "susa_2025.csv").read_bytes())
    asm = assemble_case(store, cid, today=TODAY)
    assert any("Stichtag" in b for b in asm.blocking)


def test_upload_path_reproduces_the_hand_built_reference_case(store, full_case):
    """The strongest end-to-end check available: questionnaires + DATEV + bank
    CSV must land on exactly the result of the hand-built CASE-01 JSON."""
    res = wf.run_case_diagnostic(store, full_case, today=TODAY)
    assert res["ok"], res
    s = res["summary"]
    assert (s["band"], s["score"]) == ("B", 65.0)
    # Band B, not A, since the EBA/Bundesbank calibration round: the file still
    # carries a maturity mismatch that the Umschuldung only closes to exactly
    # 100% Anlagendeckung -- still below the sector's lower quartile of 122%.
    assert (s["band_after_remediation"], s["score_after_remediation"]) == ("B", 77.7)
    assert {"R01", "R04", "R05"} <= {f["rule"] for f in s["findings"]}


def test_precedence_bank_over_steuerberater_over_client(store, full_case):
    asm = assemble_case(store, full_case, today=TODAY)
    beh = asm.payload["behavior"]
    prov = asm.provenance
    # Client said 40 days at the limit; the statement shows more. Observed wins.
    assert prov["behavior.overdraft_days_at_limit_12m"] == "Kontoumsaetze"
    assert beh["overdraft_days_at_limit_12m"] > 40
    assert any("Selbstauskunft 40" in n for n in asm.notes)
    # Steuerberater confirmation beats the client's answer.
    assert prov["balance_sheet.gesellschafterdarlehen_rangruecktritt"] == "Steuerberater"
    assert prov["behavior.tax_arrears"] == "Steuerberater"


def test_steuerberater_overrides_client_on_tax_arrears(store, full_case):
    sme = _answers("antworten_unternehmen.json")
    sme["steuerrueckstaende"] = False
    stb = _answers("antworten_steuerberater.json")
    stb["steuerrueckstaende"] = True
    store.save_answers(full_case, "unternehmen", sme)
    store.save_answers(full_case, "steuerberater", stb)
    asm = assemble_case(store, full_case, today=TODAY)
    assert asm.payload["behavior"]["tax_arrears"] is True
    assert any("widerspruechliche" in n for n in asm.notes)


def test_client_only_answers_are_used_but_flagged(store, full_case):
    (store.root / full_case / "answers_steuerberater.json").unlink()
    asm = assemble_case(store, full_case, today=TODAY)
    assert asm.ready
    assert asm.provenance["behavior.tax_arrears"].startswith("Unternehmen")
    assert any("Selbstauskunft" in n for n in asm.notes)


def test_shareholder_loan_missing_from_susa_is_flagged_not_added(store, full_case):
    """Adding it would silently unbalance the balance sheet."""
    raw = (INTAKE / "susa_2025.csv").read_text(encoding="utf-8")
    raw = "\n".join(l for l in raw.splitlines() if not l.startswith("3600"))
    raw = raw.replace("3500;Sonstige Verbindlichkeiten langfristig;-400.000,00",
                      "3500;Sonstige Verbindlichkeiten langfristig;-1.000.000,00")
    store.add_document(full_case, "susa_aktuell", "s.csv", raw.encode(),
                       {"period_end": "2025-12-31", "period_months": 12})
    asm = assemble_case(store, full_case, today=TODAY)
    assert asm.payload["balance_sheet"]["gesellschafterdarlehen"] == 0
    assert any("NICHT ergaenzt" in n for n in asm.notes)


def test_months_between():
    assert months_between(date(2026, 4, 1), date(2026, 9, 18)) == 5
    assert months_between(date(2026, 10, 1), date(2026, 9, 18)) == 0


# --------------------------------------------------------------- workflow


def test_diagnostic_writes_all_artifacts_and_advances_stage(store, full_case):
    wf.run_case_diagnostic(store, full_case, today=TODAY)
    arts = set(store.list_artifacts(full_case))
    assert {"case.json", "assembly.json", "diagnostik.md", "diagnostik.html", "summary.json",
            "abstimmung_steuerberater.md"} <= arts
    assert store.get_meta(full_case)["stage"] == "diagnostik_erstellt"
    md = store.read_artifact(full_case, "diagnostik.md")
    assert "## 11. Datengrundlage" in md and "Kontoumsaetze" in md
    assert "750.000 EUR" in md, "client documents use German number format"


def test_invalid_input_is_refused_at_validation(store, full_case):
    raw = (INTAKE / "susa_2025.csv").read_text(encoding="utf-8").replace(
        "0400;Technische Anlagen und Maschinen;2.100.000,00",
        "0400;Technische Anlagen und Maschinen;2.500.000,00")
    store.add_document(full_case, "susa_aktuell", "s.csv", raw.encode(),
                       {"period_end": "2025-12-31", "period_months": 12})
    res = wf.run_case_diagnostic(store, full_case, today=TODAY)
    assert not res["ok"] and res["stage"] == "validation"
    assert any("BILANZ_UNAUSGEGLICHEN" in b for b in res["blocking"])
    assert store.read_artifact(full_case, "diagnostik.md") is None


def test_letters_list_only_what_is_still_missing(store, full_case):
    letters = wf.generate_letters(store, full_case, today=TODAY)
    assert "Aktueller Handelsregisterauszug" in letters["anforderung_unternehmen"]
    store.add_document(full_case, "handelsregisterauszug", "hr.pdf", b"%PDF-1")
    letters = wf.generate_letters(store, full_case, today=TODAY)
    assert "Aktueller Handelsregisterauszug" not in letters["anforderung_unternehmen"]
    assert "SKR04" in letters["anforderung_steuerberater"]


def test_signoff_letter_lists_findings_needing_professional_review(store, full_case):
    wf.run_case_diagnostic(store, full_case, today=TODAY)
    letter = store.read_artifact(full_case, "abstimmung_steuerberater.md")
    assert "R01" in letter and "rechtliche Pruefung" in letter


def test_outcome_requires_a_diagnostic_and_is_logged(store, full_case):
    with pytest.raises(CaseStoreError, match="Diagnostik"):
        wf.record_outcome(store, full_case, {"outcome": "APPROVED"})
    wf.run_case_diagnostic(store, full_case, today=TODAY)
    with pytest.raises(CaseStoreError):
        wf.record_outcome(store, full_case, {"outcome": "VIELLEICHT"})
    row = wf.record_outcome(store, full_case, {"outcome": "APPROVED_BETTER_TERMS",
                                               "facility_amount_eur": "750000"})
    assert row["band_before"] == "B" and row["findings"].startswith("R01")
    log = store.read_outcomes()
    assert len(log) == 1 and log[0]["outcome"] == "APPROVED_BETTER_TERMS"
    assert store.get_meta(full_case)["stage"] == "abgeschlossen"


# --------------------------------------------------------- forms and html


@pytest.mark.parametrize("audience", AUDIENCES)
def test_printable_questionnaire_contains_every_question(audience):
    q = get_questionnaire(audience)
    md = questionnaire_markdown(q)
    for question in q.questions():
        assert question.label in md
    tmpl = answers_template(q)
    assert {x.id for x in q.questions()} <= set(tmpl)


def test_documents_checklist_mentions_every_document():
    from credit_readiness.intake.documents import DOCUMENT_TYPES
    md = documents_markdown()
    for d in DOCUMENT_TYPES:
        assert d.title in md


def test_html_conversion_escapes_client_text():
    html = markdown_to_html("# Firma <script>alert(1)</script>\n\n| a | b |\n|---|---|\n| **x** | 1 |\n",
                            "T<i>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<table>" in html and "<strong>x</strong>" in html
    assert "<title>T&lt;i&gt;</title>" in html


def test_committed_intake_templates_match_the_definitions():
    """docs/intake/ is generated; a stale copy would send clients an outdated form."""
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / "scripts" / "export_intake_templates.py"),
                          "--check"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
