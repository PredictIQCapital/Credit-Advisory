"""The two language versions of the methodology document must stay in step.

A translation that silently loses a section, or a placeholder, produces a
document that looks complete and is not -- and this is a document people are
asked to rely on. These tests are cheap insurance against that.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from methodology_sections import SECTIONS                               # noqa: E402
from methodology_text import (                                          # noqa: E402
    BAND_INTERPRETATION, CALIBRATED, COVER_LEDE, EBA_ANHANG3,
    EBA_METRIC_NAMES, FACTOR_LABELS, HERKUNFT, KNOCKOUTS, LABELS, SCENARIOS,
)

from credit_readiness import rejection_risk, sensitivity                # noqa: E402
from credit_readiness.scorecard import Band, FACTORS                    # noqa: E402

LANGS = ("de", "en")


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


@pytest.mark.parametrize("mapping,name", [
    (SECTIONS, "SECTIONS"), (LABELS, "LABELS"),
    (CALIBRATED, "CALIBRATED"), (HERKUNFT, "HERKUNFT"),
])
def test_both_languages_carry_the_same_keys(mapping, name):
    de_keys, en_keys = set(mapping["de"]), set(mapping["en"])
    assert de_keys == en_keys, (
        f"{name}: only in de {sorted(de_keys - en_keys)}, "
        f"only in en {sorted(en_keys - de_keys)}"
    )


def test_the_cover_lede_exists_in_both_languages():
    """A flat string per language, not a nested map -- checked on its own."""
    for lang in LANGS:
        assert COVER_LEDE[lang].strip(), lang
        assert len(COVER_LEDE[lang]) > 100, f"{lang}: suspiciously short"


def test_placeholders_match_between_languages():
    """A placeholder dropped in translation renders a literal brace to a client."""
    for key, german in SECTIONS["de"].items():
        assert _placeholders(german) == _placeholders(SECTIONS["en"][key]), key


def test_no_string_is_left_empty_in_either_language():
    for lang in LANGS:
        for key, value in SECTIONS[lang].items():
            assert value.strip(), f"{lang}/{key} is empty"
        for key, value in LABELS[lang].items():
            assert value.strip(), f"{lang}/{key} is empty"


def test_every_factor_has_a_label_and_an_origin_in_both_languages():
    for factor in FACTORS:
        assert factor.key in FACTOR_LABELS["en"], factor.key
        for lang in LANGS:
            assert HERKUNFT[lang].get(factor.key, "").strip(), f"{lang}/{factor.key}"


def test_every_knockout_and_scenario_and_band_is_translated():
    for code, *_ in rejection_risk.CHECK_CATALOGUE:
        assert code in KNOCKOUTS["en"], code
        assert all(part.strip() for part in KNOCKOUTS["en"][code]), code
    for key, *_ in sensitivity.SCENARIOS:
        assert key in SCENARIOS["en"], key
    for band in Band:
        assert band.value in BAND_INTERPRETATION["en"], band.value


def test_the_eba_annex_table_is_complete_and_aligned():
    """Twenty metrics, numbered 6-25, same verdicts in both languages."""
    assert len(EBA_METRIC_NAMES) == 20
    for lang in LANGS:
        assert len(EBA_ANHANG3[lang]) == 20, lang
        assert [row[0] for row in EBA_ANHANG3[lang]] == [str(n) for n in range(6, 26)], lang
    de_status = {"ja": "yes", "teilweise": "partly", "nein": "no"}
    for (nr, status_de, _), (_, status_en, _) in zip(EBA_ANHANG3["de"], EBA_ANHANG3["en"]):
        assert de_status[status_de] == status_en, f"metric {nr} disagrees across languages"


def test_the_document_builds_in_both_languages():
    """The whole point: neither version may raise on a missing key."""
    import build_methodology_pdf as builder

    for lang in LANGS:
        html = builder.build_html(lang)
        assert f'<html lang="{lang}">' in html
        assert "{" not in html.split("<style>")[0], "unfilled placeholder in the head"
        for n in range(1, 13):
            assert f'<span class="n">{n:02d}</span>' in html, f"{lang}: section {n} missing"


def test_neither_version_leaks_an_unfilled_placeholder():
    import build_methodology_pdf as builder

    for lang in LANGS:
        body = builder.build_body(lang)
        # Strip the CSS-free body; any remaining {word} is a formatting miss.
        leftovers = re.findall(r"\{[a-z_]+\}", body)
        assert not leftovers, f"{lang}: {leftovers}"
