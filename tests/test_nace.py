"""WZ 2008 / NACE codes: parsing, sector mapping, and their effect on a case."""

from __future__ import annotations

import pytest

from credit_readiness import benchmarks, nace
from credit_readiness.intake.assemble import assemble_case
from credit_readiness.intake.questionnaire import check_answers, get_questionnaire
from credit_readiness.models import Sector
from credit_readiness.scorecard import FACTORS_BY_KEY, GENERIC_BASIS, curve_for

from tests.test_workflow import TODAY, _answers, full_case, store  # noqa: F401  (fixtures)


@pytest.mark.parametrize("raw, code, sector", [
    ("C25.62", "C25.62", Sector.MANUFACTURING),
    ("25.62", "C25.62", Sector.MANUFACTURING),
    (" c 25.62.0 ", "C25.62.0", Sector.MANUFACTURING),
    ("2562", "C25.62", Sector.MANUFACTURING),
    ("43.22", "F43.22", Sector.CONSTRUCTION),
    ("46.69", "G46.69", Sector.WHOLESALE),
    ("47.11", "G47.11", Sector.RETAIL),
    ("56.10", "I56.10", Sector.HOSPITALITY),
    ("62.01", "J62.01", Sector.IT_SERVICES),
    ("71.12", "M71.12", Sector.PROFESSIONAL_SERVICES),
    ("81.21", "N81.21", Sector.PROFESSIONAL_SERVICES),
    ("86.23", "Q86.23", Sector.HEALTHCARE),
    ("87.10", "Q87.10", Sector.OTHER_SERVICES),
    ("45.20", "G45.20", Sector.OTHER),        # motor-vehicle trade: no cell of its own
    ("68.20", "L68.20", Sector.OTHER),
    ("01.11", "A01.11", Sector.OTHER),
])
def test_codes_map_to_benchmark_sectors(raw, code, sector):
    parsed = nace.parse(raw)
    assert parsed.code == code
    assert parsed.sector is sector


@pytest.mark.parametrize("raw", ["", None, "F25.62", "04.11", "abc", "1", "100.1"])
def test_invalid_codes_are_rejected(raw):
    assert nace.parse(raw) is None


def test_every_benchmark_sector_is_reachable_from_some_code():
    reachable = {nace.sector_for_division(d) for d in range(1, 100)}
    assert reachable == set(Sector)


def test_unmapped_sector_is_scored_on_generic_curves():
    """The spec's fallback: no sector data -> the standard scoring approach."""
    fd = FACTORS_BY_KEY["eigenkapitalquote"]
    assert benchmarks.sector_cell("eigenmittel_pct_bilanzsumme", Sector.OTHER) is None
    assert curve_for(fd, Sector.OTHER, 5_000_000).basis == GENERIC_BASIS
    # The comparison table still has something to compare against.
    assert benchmarks.quartiles("eigenmittel_pct_bilanzsumme", Sector.OTHER) is not None


def test_questionnaire_normalises_and_rejects_codes():
    q = get_questionnaire("unternehmen")
    ok = check_answers(q, {"nace_code": "25.62"})
    assert ok.values["nace_code"] == "C25.62"
    bad = check_answers(q, {"nace_code": "F25.62"})
    assert "nace_code" in bad.errors


def test_code_overrides_the_dropdown_and_says_so(store, full_case):  # noqa: F811
    sme = _answers("antworten_unternehmen.json")
    sme["nace_code"] = "46.69"               # wholesale, while the dropdown says manufacturing
    store.save_answers(full_case, "unternehmen", sme)
    asm = assemble_case(store, full_case, today=TODAY)
    assert asm.payload["profile"]["sector"] == Sector.WHOLESALE.value
    assert asm.payload["profile"]["nace_code"] == "G46.69"
    assert asm.provenance["profile.sector"] == "WZ 2008 G46.69"
    assert any("WZ-Code" in n for n in asm.notes)
