"""The scoring model as data -- for the database, for audits, for analysts.

The rules live in Python (scorecard.py, benchmarks.py, nace.py,
rejection_risk.py) and are tested there. This module reads them and turns
them into table rows, so that the model that produced a score can be stored
next to the score, queried, and compared across versions.

The version is a fingerprint of the content: the same rules always give the
same version, and any change -- a weight, a breakpoint, a new Bundesbank
edition -- gives a new one. Every stored result carries the version it was
computed with (scripts/publish_scoring_model.py puts the model into the
`scoring` schema; results go to app.results).
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from . import benchmarks, nace
from .models import Sector
from .rejection_risk import CHECK_CATALOGUE
from .scorecard import (
    ANCHOR_SCORES,
    BAND_THRESHOLDS,
    CALIBRATION,
    FACTORS,
    GENERIC_BASIS,
    curve_for,
)

GENERIC = "*"
#: A revenue inside each Bundesbank size class, to ask curve_for for its curve.
SIZE_REVENUE = {"unter_2m": 1_000_000, "2_bis_10m": 5_000_000,
                "10_bis_50m": 20_000_000, "ab_50m": 100_000_000}
SECTOR_EN = {
    "Verarbeitendes Gewerbe": "Manufacturing", "Baugewerbe": "Construction", "Grosshandel": "Wholesale",
    "Einzelhandel": "Retail", "Verkehr und Lagerei": "Transport and storage", "Gastgewerbe": "Hospitality",
    "Information und Kommunikation": "Information and communication",
    "Freiberufliche und technische Dienstleistungen": "Professional and technical services",
    "Gesundheitswesen": "Health care", "Sonstige Dienstleistungen": "Other services",
    "Andere Branche": "Other sector",
}


def _num(x) -> float:
    return round(float(x), 6)


def build_model() -> dict[str, list[dict]]:
    """Every table of the model, as rows (without the version column)."""
    factors, curves = [], []
    for pos, fd in enumerate(FACTORS, start=1):
        cal = CALIBRATION.get(fd.key)
        factors.append({
            "key": fd.key, "position": pos, "label": fd.label, "weight": _num(fd.weight),
            "unit": fd.unit, "source": fd.source, "note": fd.note, "calibrated": cal is not None,
            "higher_is_better": None if cal is None else cal[2],
            "bundesbank_metric": None if cal is None else cal[0],
        })
        curves += [{"factor_key": fd.key, "sector": GENERIC, "size_class": GENERIC, "seq": i,
                    "x": _num(x), "score": _num(y), "basis": GENERIC_BASIS}
                   for i, (x, y) in enumerate(fd.breakpoints, start=1)]
        if cal is None:
            continue
        for sector in Sector:
            for size, revenue in SIZE_REVENUE.items():
                c = curve_for(fd, sector, revenue)
                if c.basis == GENERIC_BASIS:
                    continue                      # the generic curve applies
                curves += [{"factor_key": fd.key, "sector": sector.value, "size_class": size, "seq": i,
                            "x": _num(x), "score": _num(y), "basis": c.basis}
                           for i, (x, y) in enumerate(c.breakpoints, start=1)]

    bands = [{"band": b.value, "min_score": _num(t), "interpretation": b.interpretation}
             for t, b in BAND_THRESHOLDS]
    settings = [
        {"key": "anchor_scores", "value": list(ANCHOR_SCORES)},
        {"key": "ebt_to_ebit_adjustment", "value": benchmarks.EBT_TO_EBIT_ADJUSTMENT},
        {"key": "size_classes", "value": [[None if lim == float("inf") else lim, key]
                                          for lim, key in benchmarks._SIZE_CLASSES]},
        {"key": "default_size_class", "value": benchmarks._DEFAULT_SIZE},
        {"key": "benchmark_vintage", "value": benchmarks.vintage()},
        {"key": "benchmark_caveat", "value": benchmarks.CAVEAT},
    ]
    has_data = set(benchmarks._dataset()["sectors"])
    sectors = [{"sector": s.value, "label_en": SECTOR_EN.get(s.value, s.value),
                "has_benchmarks": s.value in has_data} for s in Sector]
    nace_ranges = [{"from_division": lo, "to_division": hi, "sector": s.value} for lo, hi, s in nace._RANGES]
    nace_sections = [{"from_division": lo, "to_division": hi, "section": sec} for lo, hi, sec in nace._SECTIONS]
    knockouts = [{"code": c, "title": t, "condition": cond, "source": src} for c, t, cond, src in CHECK_CATALOGUE]

    hist = benchmarks._dataset().get("history", {})
    rows = []
    for sector, sizes in hist.get("sectors", {}).items():
        for size, metrics in sizes.items():
            for metric, years in metrics.items():
                for year, cell in years.items():
                    rows.append({"sector": sector, "size_class": size, "metric": metric, "year": int(year),
                                 "q25": cell.get("q25"), "q50": cell.get("q50"), "q75": cell.get("q75"),
                                 "edition": hist.get("editions", {}).get(year)})
    rows.sort(key=lambda r: (r["sector"], r["size_class"], r["metric"], r["year"]))
    return {"factors": factors, "curves": curves, "bands": bands, "settings": settings, "sectors": sectors,
            "nace_ranges": nace_ranges, "nace_sections": nace_sections, "knockouts": knockouts,
            "benchmarks": rows}


def fingerprint(model: dict) -> str:
    canonical = json.dumps(model, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def model_version() -> str:
    """The version of the model this code computes with, e.g. 'm-3f9a1c0b7e21'."""
    return "m-" + fingerprint(build_model())[:12]
