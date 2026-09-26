"""The score coach: measures with their own points, the simulator, the paywall."""

from __future__ import annotations

import json

import pytest

from credit_readiness import coach
from credit_readiness import workflow as wf
from credit_readiness.ingest.json_intake import load_case
from credit_readiness.scorecard import band_for

from tests.test_portal import INTAKE, Client, _register, env  # noqa: F401  (fixture)
from tests.test_workflow import TODAY, full_case, store  # noqa: F401  (fixtures)

SAMPLE = INTAKE.parent / "case_01_mueller_praezisionstechnik.json"


@pytest.fixture(scope="module")
def case():
    return load_case(json.loads(SAMPLE.read_text(encoding="utf-8")))


# ------------------------------------------------------------------ unit


def test_plan_ranks_measures_by_their_own_effect(case):
    p = coach.plan(case)
    assert p["band"] == band_for(p["score"])
    pts = [m["points"] for m in p["measures"] if m["points"] is not None]
    assert pts == sorted(pts, reverse=True) and pts[0] > 0
    for m in p["measures"]:
        assert m["remediation"] and m["weeks"] >= 1
        if m["points"]:
            assert m["score_after"] == pytest.approx(p["score"] + m["points"], abs=0.05)


def test_path_climbs_and_reaches_the_next_band(case):
    p = coach.plan(case)
    scores = [s["score"] for s in p["path"]]
    assert scores == sorted(scores) and scores[0] > p["score"]
    nb = p["next_band"]
    assert nb["band"] == "A" and nb["steps"] and p["path"][nb["steps"] - 1]["band"] == "A"
    assert all(s["band"] != "A" for s in p["path"][:nb["steps"] - 1])


METHOD = ("weight", "points_lost", "threshold", "points_needed", "basis", "contribution", "points_gain")


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def test_the_method_stays_ours(case):
    """The company sees ratings and effects, not weights, curves or band cut-offs."""
    p = coach.plan(case)
    assert not set(_keys(p)) & set(METHOD)
    assert not set(_keys(coach.simulate(case, {"equity": 300_000}))) & set(METHOD + ("points",))
    assert {f["rating"] for f in p["factors"]} <= {"strong", "average", "weak", None}
    assert set(p["factors"][0]) == {"key", "label", "value", "rating", "missing"}


def test_simulate_without_changes_is_the_base(case):
    r = coach.simulate(case, {})
    assert r["delta"] == 0 and r["score"] == r["base"]["score"] and r["changes"] == []


def test_simulate_equity_and_subordination_raise_the_score(case):
    r = coach.simulate(case, {"equity": 300_000})
    assert r["delta"] > 0 and r["changes"]
    both = coach.simulate(case, {"equity": 300_000, "rangruecktritt": 1})
    assert both["score"] > r["score"]
    # The subordination lever says the same as the matching measure.
    r05 = next(m for m in coach.plan(case)["measures"] if m["rule"] == "R05")
    assert coach.simulate(case, {"rangruecktritt": 1})["delta"] == pytest.approx(r05["points"], abs=0.5)


def test_simulate_ignores_unknown_levers_and_clamps(case):
    assert coach.simulate(case, {"nonsense": 5})["applied"] == {}
    lv = {l["id"]: l for l in coach.plan(case)["levers"]}
    r = coach.simulate(case, {"equity": 10 ** 12})
    assert r["applied"]["equity"] == lv["equity"]["max"]
    for bad in ("viel", None, float("nan"), float("inf")):
        assert coach.simulate(case, {"equity": bad})["applied"] == {}


@pytest.mark.parametrize("meta, role, ok", [
    ({}, "unternehmen", False),
    ({"orders": [{"product": "report"}]}, "unternehmen", True),
    ({"orders": [{"product": "advisor"}]}, "unternehmen", True),
    ({"report_released": True}, "unternehmen", True),
    ({}, "berater", True),
])
def test_entitlement(meta, role, ok):
    assert coach.entitled(meta, role) is ok


def test_action_status_is_validated(store, full_case):  # noqa: F811
    wf.set_action_status(store, full_case, "R05", "erledigt")
    assert store.get_meta(full_case)["action_status"] == {"R05": "erledigt"}
    for rule, state in [("R05", "fertig"), ("../x", "offen"), ("", "offen")]:
        with pytest.raises(wf.CaseStoreError):
            wf.set_action_status(store, full_case, rule, state)


# ------------------------------------------------------------------ HTTP


def _ready(store, cid):
    store.save_answers(cid, "unternehmen", json.loads((INTAKE / "antworten_unternehmen.json").read_text(encoding="utf-8")))
    store.save_answers(cid, "steuerberater", json.loads((INTAKE / "antworten_steuerberater.json").read_text(encoding="utf-8")))
    for doc_type, name, meta in [
        ("susa_aktuell", "susa_2025.csv", {"period_end": "2025-12-31", "period_months": 12}),
        ("susa_vorjahr", "susa_2024.csv", {"period_end": "2024-12-31", "period_months": 12}),
        ("kontoumsaetze", "kontoumsaetze_kontokorrent.csv", {"account_label": "KK"}),
    ]:
        store.add_document(cid, doc_type, name, (INTAKE / name).read_bytes(), meta)


def test_coach_needs_figures_first(env):  # noqa: F811
    _, _, base = env
    c, cid = _register(base)
    assert c.call("GET", f"/api/cases/{cid}/coach")[0] == 409


def test_free_users_see_a_preview_and_pay_for_the_rest(env):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    _ready(store, cid)
    status, view = c.call("GET", f"/api/cases/{cid}/coach")
    assert status == 200 and view["locked"] is True
    assert len(view["preview"]) <= 3 and "measures" not in view and "levers" not in view
    assert set(view["preview"][0]) == {"rule", "title", "points", "weeks"}
    assert c.call("POST", f"/api/cases/{cid}/coach/simulate", {"adjustments": {"equity": 1}})[0] == 402

    # The EUR 390 report opens everything.
    store.update_meta(cid, orders=[{"product": "report"}])
    status, view = c.call("GET", f"/api/cases/{cid}/coach")
    assert status == 200 and view["locked"] is False and view["measures"] and view["levers"]
    status, sim = c.call("POST", f"/api/cases/{cid}/coach/simulate", {"adjustments": {"rangruecktritt": 1}})
    assert status == 200 and sim["delta"] > 0

    assert c.call("PUT", f"/api/cases/{cid}/coach/status", {"rule": "R05", "status": "in_arbeit"})[0] == 200
    _, view = c.call("GET", f"/api/cases/{cid}/coach")
    assert next(m for m in view["measures"] if m["rule"] == "R05")["status"] == "in_arbeit"
    assert c.call("PUT", f"/api/cases/{cid}/coach/status", {"rule": "R05", "status": "egal"})[0] == 400


def test_other_companies_cannot_see_the_coach(env):  # noqa: F811
    store, _, base = env
    _, cid = _register(base)
    _ready(store, cid)
    other, _ = _register(base, company="Andere GmbH", email="bob@test.de", name="Bob Meier")
    assert other.call("GET", f"/api/cases/{cid}/coach")[0] == 404
    assert Client(base).call("GET", f"/api/cases/{cid}/coach")[0] == 401


# ------------------------------------------------------------------ languages


def test_english_plan_has_no_german(case):
    import re
    p = coach.plan(case, "en")
    blob = json.dumps({k: v for k, v in p.items() if k != "levers"}
                      | {"measures": [{k: v for k, v in m.items() if k != "title"} for m in p["measures"]]},
                      ensure_ascii=False)
    german = re.findall(r"\b(?:der|die|das|und|nicht|oder|Umsatz|Kennzahl|Branchen?|Gewerbe|Abbau|zusaetz\w*)\b", blob)
    assert german == [], german
    assert p["sector"] == "Manufacturing"
    assert all(re.fullmatch(r"[\d,]+(\.\d+)?(%|x| days)?", f["value"]) for f in p["factors"] if f["value"]), \
        [f["value"] for f in p["factors"]]
    r01 = next(m for m in p["measures"] if m["rule"] == "R01")
    assert "subordination" in r01["remediation"] and "lawyer" in r01["caveat"]


def test_german_plan_stays_german_and_figures_match(case):
    de_, en_ = coach.plan(case, "de"), coach.plan(case, "en")
    assert de_["score"] == en_["score"] and [m["points"] for m in de_["measures"]] == [m["points"] for m in en_["measures"]]
    assert de_["factors"][0]["value"] == "10,1%" and en_["factors"][0]["value"] == "10.1%"
    assert "Rangrücktritt" in json.dumps(de_["gaps"], ensure_ascii=False)
    sim = coach.simulate(case, {"rangruecktritt": 1}, "en")
    assert sim["changes"][0]["label"] in coach.FACTOR_EN.values()


def test_every_rule_speaks_english():
    from credit_readiness import remediation
    src = open(remediation.__file__, encoding="utf-8").read()
    for i in range(1, 11):
        assert f'rule_id="R{i:02d}",\n        en=dict(' in src, f"R{i:02d}"


def test_company_view_hides_the_method(env):  # noqa: F811
    store, _, base = env
    c, cid = _register(base)
    _ready(store, cid)
    wf.place_order(store, cid, "report", "anna@test.de")
    assert c.call("POST", f"/api/cases/{cid}/quickcheck")[0] == 200
    wf.run_case_diagnostic(store, cid, today=TODAY)
    wf.release_report(store, cid, True)
    _, ov = c.call("GET", f"/api/cases/{cid}")
    keys = set(_keys(ov))
    assert not keys & {"weight", "points_lost", "points_gain", "score_generic", "scoring_basis", "band_generic"}, keys
    assert "diagnostik_intern.html" not in ov["artifacts"] and "summary.json" not in ov["artifacts"]
    assert c.call("GET", f"/api/cases/{cid}/artifacts/diagnostik_intern.html")[0] == 404
    assert c.call("GET", f"/api/cases/{cid}/artifacts/summary.json")[0] == 404
    status, html = c.call("GET", f"/api/cases/{cid}/artifacts/diagnostik.html")
    assert status == 200
    text = html.decode("utf-8") if isinstance(html, bytes) else str(html)
    assert "Gewicht" not in text and "Punktverlust" not in text and "Bewertungsmassstab" not in text
    assert "70 Punkte" not in text and "Bis Band" not in text
    # The advisor keeps the full edition.
    full = store.read_artifact(cid, "diagnostik_intern.md")
    assert "Gewicht" in full and "Punktverlust" in full
