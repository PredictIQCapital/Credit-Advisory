"""Questionnaires, answer coercion, document catalogue."""

from __future__ import annotations

from datetime import date

import pytest

from credit_readiness.formatting import de
from credit_readiness.intake.documents import DOCUMENT_TYPES, document_status
from credit_readiness.intake.questionnaire import (
    AUDIENCES,
    AnswerError,
    FRAGEBOGEN_UNTERNEHMEN,
    Question,
    check_answers,
    coerce,
    get_questionnaire,
)
from credit_readiness.models import LegalForm, Sector

# ------------------------------------------------------------ definitions


@pytest.mark.parametrize("audience", AUDIENCES)
def test_question_ids_are_unique(audience):
    ids = [q.id for q in get_questionnaire(audience).questions()]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("audience", AUDIENCES)
def test_show_if_refers_to_an_existing_earlier_question(audience):
    q = get_questionnaire(audience)
    seen = set()
    for question in q.questions():
        if question.show_if:
            assert question.show_if[0] in seen, f"{question.id} depends on a later/unknown question"
        seen.add(question.id)


def test_select_options_match_the_domain_enums():
    """A drift here would make every questionnaire answer fail to load."""
    assert set(FRAGEBOGEN_UNTERNEHMEN.question("rechtsform").options) == {lf.value for lf in LegalForm}
    assert set(FRAGEBOGEN_UNTERNEHMEN.question("branche").options) == {s.value for s in Sector}


def test_unknown_audience_is_rejected():
    with pytest.raises(ValueError):
        get_questionnaire("bank")


# ---------------------------------------------------------------- coercion

MONEY = Question("x", "x", "money")
PCT = Question("p", "p", "percent")


@pytest.mark.parametrize("raw,expected", [
    ("750.000", 750_000.0),          # German thousands dot -- the bug this guards
    ("1.250.000", 1_250_000.0),
    ("750.000,50", 750_000.5),
    ("750000", 750_000.0),
    (750000, 750_000.0),
    ("12,5", 12.5),
    ("1 250 000 EUR", 1_250_000.0),
    ("400.000 €", 400_000.0),
])
def test_money_parses_the_way_germans_type_it(raw, expected):
    assert coerce(MONEY, raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw,expected", [("4,8", 0.048), ("4.8", 0.048), ("4.875", 0.04875), (9.5, 0.095)])
def test_percent_is_returned_as_decimal_and_never_as_thousands(raw, expected):
    assert coerce(PCT, raw) == pytest.approx(expected)


def test_invalid_values_raise():
    with pytest.raises(AnswerError):
        coerce(MONEY, "viel")
    with pytest.raises(AnswerError):
        coerce(MONEY, "-5")
    with pytest.raises(AnswerError):
        coerce(PCT, "150")
    with pytest.raises(AnswerError):
        coerce(Question("i", "i", "int"), "2,5")
    with pytest.raises(AnswerError):
        coerce(Question("s", "s", "select", options=("a", "b")), "c")


@pytest.mark.parametrize("raw,expected", [
    (True, True), ("ja", True), ("true", True), ("nein", False), (False, False),
])
def test_bool_accepts_german_and_json(raw, expected):
    assert coerce(Question("b", "b", "bool"), raw) is expected


def test_month_and_date():
    assert coerce(Question("m", "m", "month"), "2026-04") == date(2026, 4, 1)
    assert coerce(Question("d", "d", "date"), "2025-12-31") == date(2025, 12, 31)
    with pytest.raises(AnswerError):
        coerce(Question("m", "m", "month"), "April")


def test_blank_answers_become_none():
    for raw in (None, "", "   ", []):
        assert coerce(MONEY, raw) is None


def test_list_drops_empty_rows_and_enforces_required_fields():
    q = FRAGEBOGEN_UNTERNEHMEN.question("darlehen")
    rows = coerce(q, [
        {"kreditgeber": "Bank", "art": "Tilgungsdarlehen", "restschuld": "100.000", "zinssatz": "5"},
        {"kreditgeber": None, "art": None, "restschuld": None, "zinssatz": None},
    ])
    assert len(rows) == 1
    assert rows[0]["restschuld"] == 100_000
    assert rows[0]["zinssatz"] == pytest.approx(0.05)
    with pytest.raises(AnswerError, match="Restschuld"):
        coerce(q, [{"kreditgeber": "Bank", "art": "Kontokorrent", "zinssatz": "9"}])


def test_hidden_questions_are_neither_required_nor_used():
    """A stale answer to a question that no longer applies must not leak in."""
    answers = {"hat_gesellschafterdarlehen": False, "rangruecktritt": True,
               "gesellschafterdarlehen_betrag": "100.000"}
    check = check_answers(FRAGEBOGEN_UNTERNEHMEN, answers)
    assert "rangruecktritt" not in check.values
    assert "gesellschafterdarlehen_betrag" not in check.values


def test_missing_required_answers_are_listed_by_label():
    check = check_answers(FRAGEBOGEN_UNTERNEHMEN, {})
    assert "Firmenname" in check.missing
    assert not check.complete


def test_errors_are_reported_per_question():
    check = check_answers(FRAGEBOGEN_UNTERNEHMEN, {"betrag": "viel Geld"})
    assert "betrag" in check.errors


# ---------------------------------------------------------- documents


def test_document_catalogue_ids_unique_and_formats_lowercase():
    ids = [d.id for d in DOCUMENT_TYPES]
    assert len(ids) == len(set(ids))
    for d in DOCUMENT_TYPES:
        assert all(f == f.lower() and not f.startswith(".") for f in d.formats)


def test_blueprint_data_requirements_are_all_covered():
    """Blueprint: BWA, 2-3 Abschluesse, SuSa, Kreditvertraege, HR-Auszug,
    Kontoumsaetze, Creditreform."""
    ids = {d.id for d in DOCUMENT_TYPES}
    for needed in ("bwa_aktuell", "jahresabschluesse", "susa_aktuell", "darlehensvertraege",
                   "handelsregisterauszug", "kontoumsaetze", "creditreform_auskunft"):
        assert needed in ids


def test_conditional_documents_follow_the_answers():
    def required(ids, sme, stb):
        return {s.doc_type.id for s in document_status(ids, sme, stb) if s.required}

    base = required([], {}, {})
    assert "susa_aktuell" in base and "planrechnung" not in base
    assert "planrechnung" in required([], {"betrag": 250_000}, {})
    assert "darlehensvertraege" in required([], {"darlehen": [{"x": 1}]}, {})
    assert "rangruecktrittserklaerung" in required([], {}, {"rangruecktritt_bestaetigt": "ja"})
    # Steuerberater's "no arrears" overrides the client's "yes".
    assert "stundungsvereinbarung" not in required(
        [], {"steuerrueckstaende": True}, {"steuerrueckstaende": False})


def test_multi_file_document_needs_its_minimum_count():
    status = {s.doc_type.id: s for s in document_status(["jahresabschluesse"], {}, {})}
    assert status["jahresabschluesse"].outstanding
    status = {s.doc_type.id: s for s in document_status(["jahresabschluesse"] * 2, {}, {})}
    assert status["jahresabschluesse"].satisfied


def test_german_number_formatting():
    assert de(1_234_567.891, 2) == "1.234.567,89"
    assert de(750_000) == "750.000"
    assert de(-0.5, 1) == "-0,5"
