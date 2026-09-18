"""Machine-readable result summary (JSON). Shared by CLI, web app and outcome log."""

from __future__ import annotations


def result_summary(result) -> dict:
    r = result.ratios
    return {
        "case_id": result.case.case_id,
        "company": result.case.profile.name,
        "sector": result.case.profile.sector.value,
        "generated_on": result.generated_on.isoformat(),
        "band": result.scorecard.band.value,
        "band_interpretation": result.scorecard.band.interpretation,
        "score": result.scorecard.total_score,
        "coverage": result.scorecard.coverage,
        "verdict": result.verdict.value,
        "engageable": result.is_engageable,
        "score_after_remediation": result.simulation.after_score,
        "band_after_remediation": result.simulation.after_band,
        "delta": result.simulation.delta,
        "key_ratios": {
            "eigenkapitalquote": r.eigenkapitalquote,
            "kapitaldienstfaehigkeit_inkl_neu": r.kapitaldienstfaehigkeit_inkl_neu,
            "dynamischer_verschuldungsgrad": r.dynamischer_verschuldungsgrad,
            "ebit_marge": r.ebit_marge,
            "liquiditaet_2_grades": r.liquiditaet_2_grades,
            "kontokorrent_auslastung": r.kontokorrent_auslastung,
            "umsatz": r.umsatz,
            "ebitda": r.ebitda,
        },
        "top_weaknesses": [
            {"factor": f.label, "value": f.format_value(), "points_lost": round(f.points_lost, 1)}
            for f in result.top_weaknesses
        ],
        "findings": [
            {
                "rule": f.rule_id,
                "title": f.title,
                "category": f.category.value,
                "severity": f.severity,
                "fixable": f.category.is_fixable,
                "requires_steuerberater": f.requires_steuerberater,
                "requires_legal": f.requires_legal,
                "weeks_to_effect": f.weeks_to_effect,
            }
            for f in result.findings
        ],
        "top_lender_now": next(
            (o.lender.name for o in result.routing_now if o.eligible), None
        ),
        "top_lender_after": next(
            (o.lender.name for o in result.routing_after if o.eligible), None
        ),
        "top_lender_key_after": next(
            (o.lender.key for o in result.routing_after if o.eligible), None
        ),
        "warnings": [str(i) for i in result.data_warnings],
        "disclaimer": result.disclaimer,
    }
