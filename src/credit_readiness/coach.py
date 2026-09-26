"""The score coach: what a company can do about its own score, in points.

Three answers, all computed with the same engine that produced the score:

  * **Measures** -- every diagnosed weakness with a remediation (remediation.py),
    each simulated on its own, so the company sees what *this one step* is
    worth: "subordination agreement: +4.2 points, about 2 weeks, with your tax
    advisor". Then the same measures applied one after another, best first,
    to show the path to the next band.
  * **Simulator** -- levers the company controls (fresh equity, overdraft into
    a term loan, collecting receivables, EBITDA, loan amount and term, a
    current BWA). Any combination is re-scored on the spot.
  * **Breakdown** -- every factor with its weight, the company's points, the
    points lost and the curve it was measured on (sector or all sectors).

Every figure is "all else equal" on the company's own statements. It says
what the scoring rules reward; it is not a forecast and not a promise that a
lender will decide the same way.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Callable, Optional

from . import improvement
from .models import ClientCase, LoanFacility
from .ratios import compute_ratios
from .remediation import FixCategory, diagnose
from .formatting import de_to_en
from .model_export import SECTOR_EN
from .scorecard import BAND_THRESHOLDS, GENERIC_BASIS, evaluate

# ---------------------------------------------------------------- levers


@dataclass(frozen=True)
class Lever:
    id: str
    kind: str                  # "eur" | "years" | "toggle"
    label_de: str
    label_en: str
    help_de: str
    help_en: str
    available: Callable[[ClientCase], bool]
    bounds: Callable[[ClientCase], tuple[float, float, float]]   # min, max, step
    current: Callable[[ClientCase], float]
    apply: Callable[[ClientCase, float], None]


def _eur_step(maximum: float) -> float:
    for step in (1_000, 5_000, 10_000, 25_000, 50_000):
        if maximum / step <= 200:
            return step
    return 100_000


def _rangruecktritt(c: ClientCase, on: float) -> None:
    c.balance_sheet.gesellschafterdarlehen_rangruecktritt = bool(on) or c.balance_sheet.gesellschafterdarlehen_rangruecktritt


def _equity(c: ClientCase, eur: float) -> None:
    c.balance_sheet.kapitalruecklage += eur
    c.balance_sheet.liquide_mittel += eur


def _overdraft_to_term(c: ClientCase, eur: float) -> None:
    b = c.balance_sheet
    moved = min(eur, b.kontokorrent_inanspruchnahme)
    if moved <= 0:
        return
    b.kontokorrent_inanspruchnahme -= moved
    b.verb_kreditinstitute_kurz = max(0.0, b.verb_kreditinstitute_kurz - moved)
    b.verb_kreditinstitute_lang += moved
    # The new term loan has to be repaid: five years, at the engine's cautious rate.
    c.facilities.append(LoanFacility(lender="Umschuldung (Simulation)", facility_type="Tilgungsdarlehen",
                                     original_amount=moved, outstanding=moved, interest_rate=0.065,
                                     annual_principal_repayment=moved / 5))


def _collect_receivables(c: ClientCase, eur: float) -> None:
    b = c.balance_sheet
    got = min(eur, b.forderungen_ll)
    b.forderungen_ll -= got
    repay = min(got, b.kontokorrent_inanspruchnahme, b.verb_kreditinstitute_kurz)
    b.kontokorrent_inanspruchnahme -= repay
    b.verb_kreditinstitute_kurz -= repay
    b.liquide_mittel += got - repay


def _ebitda(c: ClientCase, eur: float) -> None:
    # Lower operating costs by the annual amount, in the statement's own period.
    gu = c.income_statement
    gu.sonstige_betriebliche_aufwendungen -= eur / gu.annualisation_factor


def _loan_amount(c: ClientCase, eur: float) -> None:
    if c.request:
        c.request.amount = max(0.0, eur)


def _tenor(c: ClientCase, years: float) -> None:
    if c.request:
        c.request.tenor_years = max(1, int(round(years)))


def _bwa(c: ClientCase, on: float) -> None:
    if on:
        c.behavior.bwa_age_months = 1.0
        c.behavior.bwa_frequency = "monatlich"


LEVERS: tuple[Lever, ...] = (
    Lever("rangruecktritt", "toggle", "Rangrücktritt für das Gesellschafterdarlehen",
          "Subordination of the shareholder loan",
          "Das Darlehen zählt dann als wirtschaftliches Eigenkapital.",
          "The loan then counts as economic equity.",
          lambda c: c.balance_sheet.gesellschafterdarlehen > 0 and not c.balance_sheet.gesellschafterdarlehen_rangruecktritt,
          lambda c: (0, 1, 1), lambda c: 0, _rangruecktritt),
    Lever("equity", "eur", "Einlage der Gesellschafter", "Fresh equity from shareholders",
          "Neues Eigenkapital, das als Liquidität im Unternehmen bleibt.",
          "New equity that stays in the company as cash.",
          lambda c: True,
          lambda c: (0, max(50_000, round(c.balance_sheet.bilanzsumme * 0.3, -4)),
                     _eur_step(c.balance_sheet.bilanzsumme * 0.3)),
          lambda c: 0, _equity),
    Lever("overdraft", "eur", "Kontokorrent in ein Tilgungsdarlehen umschulden",
          "Move overdraft into a term loan",
          "Laufzeitgerecht finanzieren; die Linie wird wieder Reserve (5 Jahre Tilgung angenommen).",
          "Match terms to the assets; the line becomes a reserve again (5-year repayment assumed).",
          lambda c: c.balance_sheet.kontokorrent_inanspruchnahme > 0,
          lambda c: (0, c.balance_sheet.kontokorrent_inanspruchnahme,
                     _eur_step(c.balance_sheet.kontokorrent_inanspruchnahme)),
          lambda c: 0, _overdraft_to_term),
    Lever("receivables", "eur", "Forderungen einziehen (z. B. Factoring)", "Collect receivables (e.g. factoring)",
          "Eingezogene Forderungen tilgen zuerst den Kontokorrent.",
          "Collected receivables pay down the overdraft first.",
          lambda c: c.balance_sheet.forderungen_ll > 0,
          lambda c: (0, round(c.balance_sheet.forderungen_ll * 0.8, -3),
                     _eur_step(c.balance_sheet.forderungen_ll * 0.8)),
          lambda c: 0, _collect_receivables),
    Lever("ebitda", "eur", "Mehr EBITDA pro Jahr (Kosten senken, Preise)", "More EBITDA per year (costs, prices)",
          "Dauerhafte Ergebnisverbesserung, z. B. durch Preise oder geringere Kosten.",
          "A lasting improvement, e.g. through prices or lower costs.",
          lambda c: True,
          lambda c: (0, max(50_000, round(abs(c.income_statement.annualised(c.income_statement.umsatzerloese)) * 0.05, -3)),
                     _eur_step(max(50_000, c.income_statement.annualised(c.income_statement.umsatzerloese) * 0.05))),
          lambda c: 0, _ebitda),
    Lever("loan_amount", "eur", "Beantragter Kreditbetrag", "Requested loan amount",
          "Ein kleinerer Betrag senkt die neue Rate.", "A smaller amount lowers the new instalment.",
          lambda c: c.request is not None and c.request.amount > 0,
          lambda c: (0, max(100_000, round(c.request.amount * 2, -4)), _eur_step(c.request.amount * 2)),
          lambda c: c.request.amount, _loan_amount),
    Lever("tenor", "years", "Laufzeit des neuen Kredits", "Term of the new loan",
          "Eine längere Laufzeit senkt die jährliche Rate.", "A longer term lowers the annual instalment.",
          lambda c: c.request is not None and c.request.amount > 0,
          lambda c: (1, 15, 1), lambda c: c.request.tenor_years, _tenor),
    Lever("bwa", "toggle", "Monatliche, aktuelle BWA", "Monthly, current management accounts",
          "Banken lesen das Alter der BWA als Qualität des Reportings.",
          "Banks read the age of the BWA as the quality of reporting.",
          lambda c: c.behavior.bwa_age_months > 1.5,
          lambda c: (0, 1, 1), lambda c: 0, _bwa),
)
LEVERS_BY_ID = {lv.id: lv for lv in LEVERS}


# ---------------------------------------------------------------- scoring helpers


def _score(case: ClientCase) -> tuple[float, str, Any]:
    card = evaluate(case, compute_ratios(case))
    return card.total_score, card.band.value, card


def _next_band(score: float) -> Optional[tuple[str, float]]:
    better = [(t, b) for t, b in BAND_THRESHOLDS if t > score]
    if not better:
        return None
    t, b = min(better, key=lambda tb: tb[0])
    return b.value, t


# ---------------------------------------------------------------- English

FACTOR_EN = {
    "eigenkapitalquote": "Equity ratio (economic)",
    "kapitaldienstfaehigkeit_inkl_neu": "Debt service cover incl. new loan (DSCR)",
    "dynamischer_verschuldungsgrad": "Net debt / EBITDA",
    "ebit_marge": "EBIT margin",
    "liquiditaet_2_grades": "Quick ratio",
    "zinsdeckungsgrad": "Interest cover (EBIT / interest)",
    "gesamtkapitalrentabilitaet_bbk": "Return on total capital",
    "anlagendeckungsgrad_ii": "Fixed-asset cover II",
    "kreditorenlaufzeit_tage": "Days payable outstanding",
    "kontokorrent_auslastung": "Overdraft utilisation",
    "bwa_age_months": "Age of management accounts (months)",
    "creditreform_bonitaetsindex": "Creditreform credit index",
    "zahlungsverhalten": "Payment behaviour",
}
MISSING_EN = {
    "EBITDA <= 0, Kennzahl nicht aussagekraeftig": "EBITDA <= 0, ratio not meaningful",
    "Kein Kapitaldienst bekannt": "No debt service known",
    "Kein Zinsaufwand ausgewiesen": "No interest expense reported",
    "Kein Anlagevermoegen ausgewiesen": "No fixed assets reported",
    "Kein Materialaufwand ausgewiesen": "No material costs reported",
    "Bilanzsumme oder Jahresergebnis fehlt": "Total assets or net income missing",
    "Nicht berechenbar aus den vorliegenden Daten": "Cannot be calculated from the data provided",
}
GAP_LEVER_EN = {
    "zusaetzliches wirtschaftliches Eigenkapital (z. B. Rangruecktritt, Einlage)":
        "additional economic equity (e.g. subordination, capital contribution)",
    "zusaetzliches EBITDA p. a. -- oder entsprechend geringerer Kapitaldienst":
        "additional EBITDA per year -- or correspondingly lower debt service",
    "erst ein positives EBITDA macht die Verschuldung tragbar": "debt only becomes sustainable with a positive EBITDA",
    "Abbau der Nettofinanzverschuldung": "reduce net financial debt",
    "zusaetzliches EBIT p. a.": "additional EBIT per year",
    "mehr liquide Mittel/Forderungen -- oder weniger kurzfristige Verbindlichkeiten":
        "more cash/receivables -- or fewer short-term liabilities",
    "zusaetzliches Ergebnis vor Zinsen p. a.": "additional earnings before interest per year",
    "hoeheres EBIT oder geringerer Zinsaufwand": "higher EBIT or lower interest expense",
    "Umschichtung kurzfristiger in langfristige Finanzierung": "move short-term into long-term financing",
    "Abbau der Lieferantenverbindlichkeiten": "reduce supplier payables",
    "geringere Inanspruchnahme des Kontokorrents": "draw less on the overdraft",
    "aktuellere BWA vorlegen": "present more recent management accounts",
    "Auskunft pruefen und Fehler korrigieren lassen": "check the credit report and have errors corrected",
    "Zahlungsziele einhalten, Ruecklastschriften vermeiden": "pay on time, avoid returned direct debits",
}


def _lang(lang: str) -> str:
    return "en" if lang == "en" else "de"


def _factor_label(key: str, label: str, lang: str) -> str:
    return FACTOR_EN.get(key, label) if lang == "en" else _pretty_de(label)


def _figure(text: Optional[str], lang: str) -> Optional[str]:
    if text is None or lang != "en":
        return text
    return de_to_en(text).replace(" Tage", " days")


def _basis(text: str, lang: str) -> str:
    if lang != "en":
        return _pretty_de(text)
    if text == GENERIC_BASIS:
        return "All sectors (standard curve)"
    sector, _, size = text.partition(", ")
    size_en = {
        "Umsatz unter 2 Mio. EUR": "revenue under EUR 2m", "Umsatz 2-10 Mio. EUR": "revenue EUR 2-10m",
        "Umsatz 10-50 Mio. EUR": "revenue EUR 10-50m", "Umsatz ab 50 Mio. EUR": "revenue EUR 50m+",
        "alle Groessenklassen": "all sizes",
    }.get(size, size)
    return f"{SECTOR_EN.get(sector, sector)}, {size_en}" if size else SECTOR_EN.get(sector, sector)


# German text stored in ASCII (the engine's rule and ratio names) shown with umlauts.
_UMLAUT_WORDS = {
    "Kapitaldienstfaehigkeit": "Kapitaldienstfähigkeit", "Liquiditaet": "Liquidität",
    "Gesamtkapitalrentabilitaet": "Gesamtkapitalrentabilität", "Aktualitaet": "Aktualität",
    "Bonitaetsindex": "Bonitätsindex", "Groessenklassen": "Größenklassen",
    "zusaetzliches": "zusätzliches", "Rangruecktritt": "Rangrücktritt",
    "aussagekraeftig": "aussagekräftig", "Anlagevermoegen": "Anlagevermögen",
    "pruefen": "prüfen", "Ruecklastschriften": "Rücklastschriften", "hoeheres": "höheres",
}


def _pretty_de(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    for a, b in _UMLAUT_WORDS.items():
        text = text.replace(a, b)
    return text


def _factor_rows(card, lang: str = "de") -> list[dict]:
    return [{"key": f.key, "label": _factor_label(f.key, f.label, lang),
             "value": _figure(f.format_value(), lang) if f.value is not None else None,
             "score": None if f.score is None else round(f.score, 1),
             "weight": round(f.weight * 100, 1), "points_lost": round(f.points_lost, 2),
             "basis": _basis(f.basis, lang),
             "missing": (MISSING_EN.get(f.missing_reason, f.missing_reason) if lang == "en"
                         else _pretty_de(f.missing_reason)) or None} for f in card.factors]


# ---------------------------------------------------------------- the plan


def plan(case: ClientCase, lang: str = "de") -> dict:
    """Measures with their own effect, the path through them, levers, breakdown."""
    lang = _lang(lang)
    ratios = compute_ratios(case)
    card = evaluate(case, ratios)
    base = card.total_score
    findings = diagnose(case, ratios, card)

    measures = []
    for f in findings:
        workable = f.simulate is not None and (f.category.is_fixable or f.rule_id == "R09")
        delta = after = band_after = None
        if workable:
            trial = copy.deepcopy(case)
            f.simulate(trial)
            after, band_after, _ = _score(trial)
            delta = round(after - base, 1)
        measures.append({
            "rule": f.rule_id, "title": f.title, "category": f.category.value, "severity": f.severity,
            "fixable": f.category.is_fixable,
            "observation": f.en.get("observation", f.observation) if lang == "en" else f.observation,
            "remediation": f.en.get("remediation", f.remediation) if lang == "en" else f.remediation,
            "caveat": f.en.get("caveat", f.caveat) if lang == "en" else f.caveat,
            "weeks": f.weeks_to_effect, "requires_steuerberater": f.requires_steuerberater,
            "requires_legal": f.requires_legal,
            "points": delta, "score_after": after, "band_after": band_after, "_finding": f,
        })
    measures.sort(key=lambda m: (m["points"] is None, -(m["points"] or 0)))

    # The path: best measure first, each applied on top of the previous ones.
    working, path = copy.deepcopy(case), []
    for m in measures:
        if m["points"] is None or m["points"] <= 0:
            continue
        m["_finding"].simulate(working)
        s, b, _ = _score(working)
        path.append({"rule": m["rule"], "score": s, "band": b})
    for m in measures:
        del m["_finding"]

    levers = [{"id": lv.id, "kind": lv.kind, "label_de": lv.label_de, "label_en": lv.label_en,
               "help_de": lv.help_de, "help_en": lv.help_en,
               "min": lv.bounds(case)[0], "max": lv.bounds(case)[1], "step": lv.bounds(case)[2],
               "current": lv.current(case)} for lv in LEVERS if lv.available(case)]

    nb = _next_band(base)
    return {
        "score": base, "band": card.band.value,
        "sector": SECTOR_EN.get(case.profile.sector.value, case.profile.sector.value) if lang == "en"
        else case.profile.sector.value,
        "next_band": {"band": nb[0], "threshold": nb[1], "points_needed": round(nb[1] - base, 1)} if nb else None,
        "measures": measures, "path": path,
        "gaps": [{"factor": _factor_label(i.key, i.label, lang),
                  "current": _figure(i.format(i.current), lang), "target": _figure(i.format(i.target), lang),
                  "points": round(i.points_gain, 1), "euro_gap": round(i.euro_gap, -3) if i.euro_gap else None,
                  "lever": GAP_LEVER_EN.get(i.lever, i.lever) if lang == "en" else _pretty_de(i.lever)}
                 for i in improvement.plan(case, ratios, card).items],
        "factors": _factor_rows(card, lang),
        "levers": levers,
    }


def simulate(case: ClientCase, adjustments: dict, lang: str = "de") -> dict:
    """Re-score the company with the chosen levers applied."""
    lang = _lang(lang)
    base, base_band, base_card = _score(case)
    trial = copy.deepcopy(case)
    applied = {}
    for key, raw in (adjustments or {}).items():
        lv = LEVERS_BY_ID.get(key)
        if lv is None or not lv.available(case):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        lo, hi, _ = lv.bounds(case)
        value = max(lo, min(hi, value))
        if value == lv.current(case):
            continue
        lv.apply(trial, value)
        applied[key] = value
    score, band, card = _score(trial)
    before = {f.key: f for f in base_card.factors}
    changes = [{"key": f.key, "label": _factor_label(f.key, f.label, lang),
                "before": _figure(before[f.key].format_value(), lang) if before[f.key].value is not None else None,
                "after": _figure(f.format_value(), lang) if f.value is not None else None,
                "points": round((f.contribution - before[f.key].contribution), 2)}
               for f in card.factors
               if f.score is not None and before[f.key].score is not None
               and abs(f.contribution - before[f.key].contribution) >= 0.05]
    changes.sort(key=lambda c: -abs(c["points"]))
    nb = _next_band(score)
    return {"base": {"score": base, "band": base_band}, "score": score, "band": band,
            "delta": round(score - base, 1), "applied": applied, "changes": changes,
            "next_band": {"band": nb[0], "points_needed": round(nb[1] - score, 1)} if nb else None}


def entitled(meta: dict, role: str) -> bool:
    """The full coach comes with the report (EUR 390) or advisory plan; advisors always."""
    if role == "berater":
        return True
    return bool(meta.get("report_released")) or any(
        o.get("product") in ("report", "advisor") for o in meta.get("orders") or [])
