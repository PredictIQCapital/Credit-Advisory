"""The financial-statements grid: rows per statement, columns per fiscal year."""

from __future__ import annotations

from datetime import date

import pytest

from credit_readiness import workflow as wf
from credit_readiness.intake import docmatrix as dm

from tests.test_portal import TODAY, _register, env  # noqa: F401  (fixture)

LATEST = TODAY.year - 1
CFG = {"first_year": 2025, "years": 2, "fy_end_month": 12}


def _doc(doc_type, name, **meta):
    return {"doc_id": name, "doc_type": doc_type, "filename": name,
            "uploaded_at": "2026-01-01", "meta": meta}


def _cell(grid, row, year):
    r = next(x for x in grid["rows"] if x["id"] == row)
    return next(c for c in r["cells"] if c["year"] == year)


# ------------------------------------------------------------------ unit


@pytest.mark.parametrize("today, month, expected", [
    (date(2026, 9, 18), 12, 2025),
    (date(2026, 9, 18), 6, 2026),     # fiscal year ended 30 June 2026
    (date(2026, 6, 30), 6, 2025),     # ends today: not completed yet
])
def test_latest_completed_fiscal_year(today, month, expected):
    assert dm.last_completed_year(today, month) == expected


def test_combined_pdf_fills_balance_sheet_and_pl():
    grid = dm.build([_doc(dm.ANNUAL, "ja.pdf", fiscal_year=2025)], {}, CFG)
    assert _cell(grid, "bilanz", 2025)["state"] == "ok"
    assert _cell(grid, "guv", 2025)["state"] == "ok"


def test_balance_sheet_alone_offers_the_one_click_pl():
    grid = dm.build([_doc(dm.ANNUAL, "bs.pdf", fiscal_year=2025, part="bilanz")], {}, CFG)
    guv = _cell(grid, "guv", 2025)
    assert guv["state"] == "missing" and guv["combined_candidate"] == "bs.pdf"


def test_two_files_for_one_year_are_not_two_years():
    docs = [_doc(dm.ANNUAL, "bs.pdf", fiscal_year=2025, part="bilanz"),
            _doc(dm.ANNUAL, "pl.pdf", fiscal_year=2025, part="guv")]
    assert dm.completion(dm.build(docs, {}, CFG))[dm.ANNUAL] == {"count": 1, "satisfied": False}


def test_explained_cell_counts_as_done_for_the_company():
    docs = [_doc(dm.ANNUAL, "ja.pdf", fiscal_year=2025)]
    notes = {"bilanz:2024": "gegruendet 2025", "guv:2024": "gegruendet 2025"}
    grid = dm.build(docs, notes, CFG)
    assert _cell(grid, "bilanz", 2024)["state"] == "explained"
    assert dm.completion(grid)[dm.ANNUAL]["satisfied"]


def test_trial_balance_needs_only_two_columns():
    grid = dm.build([], {}, {**CFG, "years": 3})
    states = [c["state"] for c in next(r for r in grid["rows"] if r["id"] == "susa")["cells"]]
    assert states == ["missing", "open", "na"]


def test_trial_balance_cell_maps_to_current_and_prior():
    assert dm.upload_target("susa", 2025, CFG) == (
        dm.SUSA_CURRENT, {"fiscal_year": 2025, "period_end": "2025-12-31", "period_months": 12})
    assert dm.upload_target("susa", 2024, CFG)[0] == dm.SUSA_PRIOR
    with pytest.raises(ValueError):
        dm.upload_target("susa", 2023, CFG)
    june = {**CFG, "fy_end_month": 6}
    assert dm.upload_target("susa", 2025, june)[1]["period_end"] == "2025-06-30"


def test_files_outside_the_columns_are_shown_not_dropped():
    docs = [_doc(dm.ANNUAL, "old.pdf", fiscal_year=2021),
            _doc(dm.SUSA_CURRENT, "interim.csv", period_end="2026-06-30"),
            _doc(dm.ANNUAL, "abschluss.pdf")]
    grid = dm.build(docs, {}, CFG)
    assert 2021 in grid["columns"]
    assert {d["filename"] for d in grid["other"]} == {"interim.csv", "abschluss.pdf"}


@pytest.mark.parametrize("key, doc_type", [
    ("bilanz:2025", dm.ANNUAL), ("susa:2024", dm.SUSA_CURRENT),
    ("handelsregisterauszug", "handelsregisterauszug"),
    ("bilanz", None), ("bilanz:25", None), ("handelsregisterauszug:2025", None),
])
def test_note_keys(key, doc_type):
    assert dm.note_doc_type(key) == doc_type


# ------------------------------------------------------------------ over HTTP


def test_upload_into_a_cell_sets_type_year_and_part(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    status, up = c.upload(cid, None, "jahresabschluss_2025.pdf", cell={"row": "bilanz", "year": LATEST})
    assert status == 201, up
    assert up["document"]["doc_type"] == dm.ANNUAL
    assert up["document"]["meta"]["part"] == "bilanz"
    doc = up["document"]["doc_id"]
    assert _cell(up["overview"]["doc_matrix"], "guv", LATEST)["combined_candidate"] == doc

    # One click: the P&L is in the same PDF.
    status, ov = c.call("PUT", f"/api/cases/{cid}/documents/{doc}/meta", {"part": "bilanz_guv"})
    assert status == 200
    assert _cell(ov["doc_matrix"], "guv", LATEST)["state"] == "ok"


def test_uploading_a_cell_again_replaces_only_that_cell(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    c.upload(cid, None, "jahresabschluss_2025.pdf", cell={"row": "bilanz", "year": LATEST})
    c.upload(cid, None, "jahresabschluss_2025.pdf", cell={"row": "guv", "year": LATEST})
    _, up = c.upload(cid, None, "jahresabschluss_2024.pdf", cell={"row": "bilanz", "year": LATEST})
    grid = up["overview"]["doc_matrix"]
    assert [f["filename"] for f in _cell(grid, "bilanz", LATEST)["files"]] == ["jahresabschluss_2024.pdf"]
    assert _cell(grid, "guv", LATEST)["state"] == "ok"


def test_trial_balance_cell_is_read_like_a_datev_upload(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    status, up = c.upload(cid, None, "susa_2025.csv", cell={"row": "susa", "year": LATEST})
    assert status == 201
    assert up["document"]["doc_type"] == dm.SUSA_CURRENT
    assert up["document"]["meta"]["period_end"] == f"{LATEST}-12-31"
    assert c.upload(cid, None, "susa_2025.csv", cell={"row": "susa", "year": LATEST - 2})[0] == 400


def test_grid_settings_move_the_columns(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    status, ov = c.call("PUT", f"/api/cases/{cid}/doc-matrix", {"first_year": 2024, "years": 3})
    assert status == 200 and ov["doc_matrix"]["columns"] == [2024, 2023, 2022]
    assert c.call("PUT", f"/api/cases/{cid}/doc-matrix", {"years": 9})[0] == 400
    assert c.call("PUT", f"/api/cases/{cid}/doc-matrix", {"fy_end_month": 13})[0] == 400


def test_bwa_period_and_month_fill_the_answer(env):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    status, up = c.upload(cid, "bwa_aktuell", "bwa_2026_04.pdf", bwa_period="1-6", bwa_stand="2026-06")
    assert status == 201
    assert up["document"]["meta"]["bwa_period"] == "1-6"
    assert store.load_answers(cid, "unternehmen")["bwa_stand"] == "2026-06"
    assert c.upload(cid, "bwa_aktuell", "bwa_2026_04.pdf", bwa_period="1-5")[0] == 400


def test_cell_notes_explain_and_reach_the_letters(env):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    c.upload(cid, None, "jahresabschluss_2025.pdf", cell={"row": "bilanz", "year": LATEST})
    for row in ("bilanz", "guv"):
        status, ov = c.call("PUT", f"/api/cases/{cid}/document-notes",
                            {"key": f"{row}:{LATEST - 1}", "note": "Gegruendet 2025"})
        assert status == 200
    assert _cell(ov["doc_matrix"], "bilanz", LATEST - 1)["state"] == "explained"
    text = "\n".join(wf.generate_letters(store, cid, today=TODAY).values())
    assert f"Es fehlt: Gewinn- und Verlustrechnung {LATEST}" in text
    assert f"*Anmerkung:* Bilanz {LATEST - 1}: Gegruendet 2025" in text
    assert c.call("PUT", f"/api/cases/{cid}/document-notes",
                  {"key": "creditreform_auskunft", "note": "x"})[0] == 403


def test_history_lists_what_happened(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    _, up = c.upload(cid, "handelsregisterauszug", "handelsregisterauszug.pdf")
    kinds = [e["kind"] for e in up["overview"]["history"]]
    assert kinds[0] == "upload" and "created" in kinds
