"""Validation, DATEV parsing, routing, reporting and end-to-end behaviour."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from credit_readiness.engine import run_diagnostic
from credit_readiness.ingest.datev import (
    DatevMappingError,
    _parse_german_number,
    parse_datev_susa,
)
from credit_readiness.ingest.json_intake import load_case_file
from credit_readiness.remediation import Verdict
from credit_readiness.reporting.report import render_markdown
from credit_readiness.routing import route
from credit_readiness.ratios import compute_ratios
from credit_readiness.scorecard import evaluate
from credit_readiness.validation import Severity, ValidationError, validate

# --------------------------------------------------------------------- validation


def test_all_sample_balance_sheets_balance(sample_dir):
    """Guards the fixtures themselves: unbalanced samples would mask real bugs."""
    for path in sorted(sample_dir.glob("*.json")):
        case = load_case_file(path)
        errors = [i for i in validate(case) if i.severity is Severity.ERROR]
        assert not errors, f"{path.name}: {[str(e) for e in errors]}"


def test_unbalanced_balance_sheet_is_an_error(minimal_case):
    minimal_case.balance_sheet.sachanlagen += 50_000
    issues = validate(minimal_case)
    codes = {i.code for i in issues if i.severity is Severity.ERROR}
    assert "BILANZ_UNAUSGEGLICHEN" in codes


def test_strict_mode_refuses_to_diagnose_broken_input(minimal_case):
    minimal_case.balance_sheet.sachanlagen += 50_000
    with pytest.raises(ValidationError):
        run_diagnostic(minimal_case, strict=True)


def test_non_strict_mode_proceeds_but_records_issues(minimal_case):
    minimal_case.balance_sheet.sachanlagen += 50_000
    result = run_diagnostic(minimal_case, strict=False)
    assert any(i.code == "BILANZ_UNAUSGEGLICHEN" for i in result.validation_issues)


def test_overdrawn_overdraft_raises_a_warning(minimal_case):
    minimal_case.balance_sheet.kontokorrent_limit = 100_000
    minimal_case.balance_sheet.kontokorrent_inanspruchnahme = 130_000
    codes = {i.code for i in validate(minimal_case)}
    assert "KK_UEBERZIEHUNG" in codes


def test_guv_result_must_match_the_balance_sheet_profit_line(minimal_case):
    """Bilanz and GuV from different runs is a first-minute analyst check."""
    minimal_case.balance_sheet.jahresueberschuss += 50_000
    codes = {i.code for i in validate(minimal_case) if i.severity is Severity.ERROR}
    assert "ERGEBNIS_ABWEICHUNG" in codes


def test_result_check_skipped_for_partial_year_bwa(minimal_case):
    """A mid-year BWA legitimately has no closed result to reconcile against."""
    minimal_case.income_statement.period_months = 6
    codes = {i.code for i in validate(minimal_case)}
    assert "ERGEBNIS_ABWEICHUNG" not in codes


def test_datev_carries_result_into_equity_so_the_sheet_balances():
    """Without this, every equity ratio is understated by the year's profit."""
    from credit_readiness.validation import Severity as _Sev

    csv_path = Path("data/samples/datev_susa_example.csv")
    balance, income, _ = parse_datev_susa(csv_path, period_end=date(2025, 12, 31))

    assert balance.jahresueberschuss == pytest.approx(income.jahresueberschuss)

    passiva = (
        balance.bilanzielles_eigenkapital
        + balance.rueckstellungen
        + balance.verb_kreditinstitute_kurz
        + balance.verb_kreditinstitute_lang
        + balance.verb_ll
        + balance.sonstige_verbindlichkeiten_kurz
        + balance.sonstige_verbindlichkeiten_lang
        + balance.gesellschafterdarlehen
    )
    assert balance.bilanzsumme == pytest.approx(passiva, abs=1.0)


def test_incomplete_facility_list_raises_a_warning(minimal_case):
    """An incomplete loan list overstates debt capacity -- the dangerous direction."""
    minimal_case.facilities = []
    codes = {i.code for i in validate(minimal_case)}
    assert "KEINE_DARLEHENSLISTE" in codes


# ------------------------------------------------------------------------- DATEV


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1.234.567,89", 1_234_567.89),
        ("-4.500,00", -4_500.0),
        ("4500.00", 4500.0),
        ("1500-", -1500.0),
        ("", 0.0),
        ("   ", 0.0),
        ("keine Zahl", 0.0),
    ],
)
def test_german_number_parsing(raw, expected):
    assert _parse_german_number(raw) == pytest.approx(expected)


def test_datev_susa_roundtrip(tmp_path: Path):
    csv = tmp_path / "susa.csv"
    csv.write_text(
        "Konto;Bezeichnung;Saldo\n"
        "0400;Maschinen;500.000,00\n"
        "1200;Forderungen LuL;150.000,00\n"
        "1800;Bank;50.000,00\n"
        "2000;Gezeichnetes Kapital;-100.000,00\n"
        "3200;Darlehen langfristig;-400.000,00\n"
        "3300;Verbindlichkeiten LuL;-200.000,00\n"
        "4000;Umsatzerloese;-1.000.000,00\n"
        "5000;Wareneinsatz;400.000,00\n"
        "6000;Loehne;300.000,00\n"
        "6200;Abschreibungen;50.000,00\n"
        "7100;Zinsaufwand;20.000,00\n",
        encoding="utf-8",
    )
    balance, income, diag = parse_datev_susa(csv, period_end=date(2025, 12, 31))

    assert balance.sachanlagen == 500_000
    assert balance.forderungen_ll == 150_000
    assert balance.gezeichnetes_kapital == 100_000        # credit sign flipped
    assert balance.verb_kreditinstitute_lang == 400_000
    assert balance.bilanzsumme == 700_000
    assert income.umsatzerloese == 1_000_000
    assert income.ebitda == 300_000                       # 1.000k - 400k - 300k
    assert income.ebit == 250_000
    assert diag["unmapped_share"] == 0.0


def test_datev_raises_when_too_much_is_unmapped(tmp_path: Path):
    """Silently dropping accounts produces a confident, wrong diagnostic."""
    csv = tmp_path / "susa.csv"
    csv.write_text(
        "Konto;Bezeichnung;Saldo\n"
        "0400;Maschinen;100.000,00\n"
        "9999;Unbekannt;900.000,00\n",
        encoding="utf-8",
    )
    with pytest.raises(DatevMappingError, match="nicht zugeordnet|zugeordnet"):
        parse_datev_susa(csv, period_end=date(2025, 12, 31))


def test_datev_rejects_unimplemented_chart_of_accounts(tmp_path: Path):
    csv = tmp_path / "susa.csv"
    csv.write_text("Konto;Saldo\n0400;1,00\n", encoding="utf-8")
    with pytest.raises(DatevMappingError, match="SKR03|nicht implementiert"):
        parse_datev_susa(csv, period_end=date(2025, 12, 31), kontenrahmen="SKR03")


def test_datev_rejects_unrecognisable_header(tmp_path: Path):
    csv = tmp_path / "susa.csv"
    csv.write_text("Spalte1;Spalte2\n1;2\n", encoding="utf-8")
    with pytest.raises(DatevMappingError):
        parse_datev_susa(csv, period_end=date(2025, 12, 31))


# ----------------------------------------------------------------------- routing


def test_collateral_gap_surfaces_guarantee_routes(case_04):
    ratios = compute_ratios(case_04)
    card = evaluate(case_04, ratios)
    options = route(case_04, ratios, card)
    eligible = {o.lender.key for o in options if o.eligible}
    assert {"kfw_haftungsfreistellung", "buergschaftsbank"} & eligible


def test_weak_case_is_excluded_from_standard_bank_lending(case_03):
    ratios = compute_ratios(case_03)
    card = evaluate(case_03, ratios)
    options = route(case_03, ratios, card)
    hausbank = next(o for o in options if o.lender.key == "hausbank")
    assert not hausbank.eligible
    assert hausbank.blockers


def test_slow_debtors_boost_factoring(case_02_path=None):
    from credit_readiness.ingest import load_case_file as _load

    case = _load(Path("data/samples/case_02_nordlicht_handel.json"))
    ratios = compute_ratios(case)
    card = evaluate(case, ratios)
    options = route(case, ratios, card)
    factoring = next(o for o in options if o.lender.key == "factoring")
    assert any("Debitorenlaufzeit" in r for r in factoring.reasons)


# --------------------------------------------------------------------- reporting


def test_report_renders_for_every_sample(sample_dir):
    for path in sorted(sample_dir.glob("*.json")):
        result = run_diagnostic(load_case_file(path))
        md = render_markdown(result)
        assert md.startswith("# Kreditfaehigkeits-Diagnostik")
        assert len(md) > 1500


def test_report_always_carries_the_disclaimer(case_01):
    md = render_markdown(run_diagnostic(case_01))
    assert md.count("KEIN Rating") >= 2
    assert "Ausfallwahrscheinlichkeit" in md


def test_report_never_claims_approval(sample_dir):
    """Wording discipline is a regulatory control, so it is tested like one.

    The bare word "Zusage" is legitimate in negated or descriptive use ("keine
    Zusage", "wenn der Kunde eine Zusage erwartet"). What must never appear is a
    phrase asserting that credit WILL be granted, or any rating/PD vocabulary.
    """
    forbidden_claims = (
        "garantiert",
        "wird genehmigt",
        "wird bewilligt",
        "sichere Zusage",
        "Zusage der Bank",
        "Ausfallwahrscheinlichkeit von",
        "Rating von",
        "Bonitaetsnote",
    )
    for path in sorted(sample_dir.glob("*.json")):
        md = render_markdown(run_diagnostic(load_case_file(path)))
        for phrase in forbidden_claims:
            assert phrase not in md, f"{path.name} contains a claim phrase: {phrase}"


def test_every_mention_of_zusage_is_negated_or_descriptive(sample_dir):
    """Belt and braces on the single riskiest word in the whole report."""
    allowed_contexts = (
        "keine Zusage",
        "Zusage erwartet",
    )
    for path in sorted(sample_dir.glob("*.json")):
        md = render_markdown(run_diagnostic(load_case_file(path)))
        idx = 0
        while (idx := md.find("Zusage", idx)) != -1:
            window = md[max(0, idx - 30) : idx + 30]
            assert any(ctx in window for ctx in allowed_contexts), (
                f"{path.name}: unguarded use of 'Zusage' near: ...{window}..."
            )
            idx += 1


def test_genuine_risk_report_leads_with_a_warning(case_03):
    md = render_markdown(run_diagnostic(case_03))
    assert "ACHTUNG" in md
    assert "Keine Antragstellung im aktuellen Zustand" in md


# --------------------------------------------------------------------- end to end


def test_end_to_end_produces_a_complete_result(case_01):
    result = run_diagnostic(case_01)
    assert result.ratios.eigenkapitalquote is not None
    assert result.scorecard.factors
    assert result.findings
    assert result.verdict in Verdict
    assert result.routing_now and result.routing_after
    assert result.benchmark
    assert result.simulation.applied


def test_remediation_can_unlock_new_lender_types(case_01):
    result = run_diagnostic(case_01)
    before = {o.lender.key for o in result.routing_now if o.eligible}
    after = {o.lender.key for o in result.routing_after if o.eligible}
    assert after >= before, "remediation must never remove an available route"
