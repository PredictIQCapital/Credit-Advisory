"""Reading figures out of annual financial statements -- and never trusting it blindly.

Pipeline:

    PDF --(rules or AI provider)--> ExtractionResult (proposals + source + confidence)
        --> the COMPANY reviews and confirms every figure in the portal
        --> ConfirmedFigures --> the same deterministic engine as a DATEV export

The extraction layer only ever *proposes*. A proposal becomes an input only
after a human confirmed it, and the confirmation is stored with who and when.
The consistency checks below run on every proposal and every confirmation, so
an extraction slip (a prior-year column, a missed sign, a dropped line) shows
up as "Aktiva und Passiva weichen ab" before it can reach a ratio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..formatting import de
from ..models import BalanceSheet, IncomeStatement


@dataclass(frozen=True)
class FieldSpec:
    key: str
    statement: str          # "aktiva" | "passiva" | "guv"
    label_de: str
    label_en: str
    patterns: tuple[str, ...]   # regexes on a normalised line, most specific first
    negative_if: tuple[str, ...] = ()   # label words that flip the sign (losses)


# Order matters for the rules extractor: specific labels before generic ones
# ("Rueckstellungen fuer Pensionen" before "Rueckstellungen").
FIELDS: tuple[FieldSpec, ...] = (
    # ---------------------------------------------------------------- Aktiva
    FieldSpec("immaterielle_vermoegensgegenstaende", "aktiva", "Immaterielle Vermögensgegenstände", "Intangible assets", (r"immaterielle vermoegensgegenstaende",)),
    FieldSpec("sachanlagen", "aktiva", "Sachanlagen", "Property, plant and equipment", (r"^sachanlagen",)),
    FieldSpec("finanzanlagen", "aktiva", "Finanzanlagen", "Financial assets", (r"^finanzanlagen",)),
    FieldSpec("vorraete", "aktiva", "Vorräte", "Inventories", (r"^vorraete",)),
    FieldSpec("forderungen_ll", "aktiva", "Forderungen aus Lieferungen und Leistungen", "Trade receivables", (r"forderungen aus lieferungen und leistungen",)),
    FieldSpec("sonstige_vermoegensgegenstaende", "aktiva", "Sonstige Vermögensgegenstände", "Other assets", (r"sonstige vermoegensgegenstaende",)),
    FieldSpec("wertpapiere", "aktiva", "Wertpapiere", "Securities", (r"^wertpapiere",)),
    FieldSpec("liquide_mittel", "aktiva", "Kassenbestand, Guthaben bei Kreditinstituten", "Cash and bank balances", (r"kassenbestand", r"guthaben bei kreditinstituten", r"liquide mittel")),
    FieldSpec("aktive_rap", "aktiva", "Aktive Rechnungsabgrenzung", "Prepaid expenses", (r"rechnungsabgrenzungsposten",)),
    # --------------------------------------------------------------- Passiva
    FieldSpec("gezeichnetes_kapital", "passiva", "Gezeichnetes Kapital", "Subscribed capital", (r"gezeichnetes kapital",)),
    FieldSpec("kapitalruecklage", "passiva", "Kapitalrücklage", "Capital reserve", (r"kapitalruecklage",)),
    FieldSpec("gewinnruecklagen", "passiva", "Gewinnrücklagen", "Revenue reserves", (r"gewinnruecklagen",)),
    FieldSpec("gewinnvortrag", "passiva", "Gewinn-/Verlustvortrag", "Profit/loss carried forward", (r"gewinnvortrag", r"verlustvortrag"), negative_if=("verlustvortrag",)),
    FieldSpec("jahresueberschuss", "passiva", "Jahresüberschuss/-fehlbetrag", "Net income/loss for the year", (r"jahresueberschuss", r"jahresfehlbetrag"), negative_if=("jahresfehlbetrag",)),
    FieldSpec("pensionsrueckstellungen", "passiva", "Rückstellungen für Pensionen", "Pension provisions", (r"rueckstellungen fuer pensionen",)),
    FieldSpec("rueckstellungen", "passiva", "Sonstige Rückstellungen", "Other provisions", (r"sonstige rueckstellungen", r"^rueckstellungen")),
    FieldSpec("verb_kreditinstitute_kurz", "passiva", "Verbindlichkeiten gegenüber Kreditinstituten (bis 1 Jahr)", "Bank debt (up to 1 year)", ()),
    FieldSpec("verb_kreditinstitute_lang", "passiva", "Verbindlichkeiten gegenüber Kreditinstituten (über 1 Jahr)", "Bank debt (over 1 year)", ()),
    FieldSpec("verb_ll", "passiva", "Verbindlichkeiten aus Lieferungen und Leistungen", "Trade payables", (r"verbindlichkeiten aus lieferungen und leistungen",)),
    FieldSpec("gesellschafterdarlehen", "passiva", "Verbindlichkeiten gegenüber Gesellschaftern", "Shareholder loans", (r"verbindlichkeiten gegenueber gesellschaftern", r"gesellschafterdarlehen")),
    FieldSpec("sonstige_verbindlichkeiten_kurz", "passiva", "Sonstige Verbindlichkeiten (bis 1 Jahr)", "Other liabilities (up to 1 year)", ()),
    FieldSpec("sonstige_verbindlichkeiten_lang", "passiva", "Sonstige Verbindlichkeiten (über 1 Jahr)", "Other liabilities (over 1 year)", ()),
    FieldSpec("passive_rap", "passiva", "Passive Rechnungsabgrenzung", "Deferred income", (r"rechnungsabgrenzungsposten",)),
    # ------------------------------------------------------------------- GuV
    FieldSpec("umsatzerloese", "guv", "Umsatzerlöse", "Revenue", (r"^umsatzerloese",)),
    FieldSpec("bestandsveraenderungen", "guv", "Bestandsveränderungen", "Change in inventories", (r"erhoehung oder verminderung des bestands", r"bestandsveraenderung")),
    FieldSpec("sonstige_betriebliche_ertraege", "guv", "Sonstige betriebliche Erträge", "Other operating income", (r"sonstige betriebliche ertraege",)),
    FieldSpec("materialaufwand", "guv", "Materialaufwand", "Cost of materials", (r"^materialaufwand",)),
    FieldSpec("personalaufwand", "guv", "Personalaufwand", "Personnel expenses", (r"^personalaufwand",)),
    FieldSpec("abschreibungen", "guv", "Abschreibungen", "Depreciation and amortisation", (r"^abschreibungen",)),
    FieldSpec("sonstige_betriebliche_aufwendungen", "guv", "Sonstige betriebliche Aufwendungen", "Other operating expenses", (r"sonstige betriebliche aufwendungen",)),
    FieldSpec("zinsertraege", "guv", "Zinsen und ähnliche Erträge", "Interest income", (r"zinsen und aehnliche ertraege", r"sonstige zinsen")),
    FieldSpec("zinsaufwand", "guv", "Zinsen und ähnliche Aufwendungen", "Interest expense", (r"zinsen und aehnliche aufwendungen",)),
    FieldSpec("steuern", "guv", "Steuern (Einkommen, Ertrag und sonstige)", "Taxes", (r"steuern vom einkommen und vom ertrag", r"sonstige steuern")),
)
FIELDS_BY_KEY = {f.key: f for f in FIELDS}
SUMMED_FIELDS = {"steuern", "liquide_mittel"}     # several lines add up to one field


def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = s.strip()
    return re.sub(r"^(?:[a-h]|[ivx]+|\d+)[.)]\s+", "", s).strip()   # "A. ", "II. ", "1. ", "a) "


_NUM = re.compile(r"(?<![\w.,])(-?\s?\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|-?\s?\d+(?:,\d{1,2})?)(?:\s*(?:eur|€|teur|t€))?(?![\w])", re.I)


def _first_amount(line: str) -> Optional[float]:
    """The first amount on a line = the current-year column in German statements."""
    for m in _NUM.finditer(line):
        raw = m.group(1).replace(" ", "")
        digits = re.sub(r"\D", "", raw)
        if len(digits) <= 2 and "," not in raw:
            continue                       # "1." item numbers, "12" months, not amounts
        neg = raw.startswith("-")
        raw = raw.lstrip("-").replace(".", "").replace(",", ".")
        try:
            v = float(raw)
        except ValueError:
            continue
        return -v if neg else v
    return None


@dataclass
class FieldProposal:
    value: Optional[float]
    source: str = ""             # the line / label it was read from
    confidence: str = "mittel"   # hoch | mittel | niedrig
    note: str = ""

    def as_dict(self) -> dict:
        return {"value": self.value, "source": self.source, "confidence": self.confidence, "note": self.note}


@dataclass
class ExtractionResult:
    method: str                               # "regeln" | "claude-opus-5" | ...
    provider_label: str
    fields: dict[str, FieldProposal] = field(default_factory=dict)
    period_end: Optional[str] = None
    period_months: int = 12
    company_name: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    text_found: bool = True

    def as_dict(self) -> dict:
        figures = {k: (p.value if p.value is not None else 0.0) for k, p in self.fields.items()}
        return {
            "method": self.method,
            "provider_label": self.provider_label,
            "fields": {k: p.as_dict() for k, p in self.fields.items()},
            "period_end": self.period_end,
            "period_months": self.period_months,
            "company_name": self.company_name,
            "warnings": self.warnings,
            "text_found": self.text_found,
            "checks": check_figures(figures, self.period_months),
        }


def extract_with_rules(text: str) -> ExtractionResult:
    """Label matching on the text layer. Transparent, local, no data leaves the machine."""
    res = ExtractionResult(method="regeln", provider_label="Regelbasierte Auslesung (lokal)")
    if not text.strip():
        res.text_found = False
        res.warnings.append(
            "Das PDF enthaelt keinen lesbaren Text (vermutlich ein Scan). Bitte Zahlen "
            "manuell eintragen oder die KI-Auslesung verwenden.")
        return res

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    norm = [_norm(ln) for ln in lines]
    # Section boundaries: everything after "passiva" is liabilities; after
    # "gewinn- und verlustrechnung" is the P&L. Unknown layout -> whole text.
    def idx(pattern: str) -> Optional[int]:
        return next((i for i, n in enumerate(norm) if re.search(pattern, n)), None)

    i_pass = idx(r"^passiva") or idx(r"^passivseite")
    i_guv = idx(r"gewinn- und verlustrechnung")
    ranges = {
        "aktiva": (0, i_pass if i_pass is not None else len(lines)),
        "passiva": (i_pass or 0, i_guv if i_guv is not None and (i_pass or 0) < i_guv else len(lines)),
        "guv": (i_guv or 0, len(lines)),
    }
    for m in re.finditer(r"(\d{2})\.(\d{2})\.(\d{4})", text):
        d, mth, y = m.groups()
        if (d, mth) in (("31", "12"), ("30", "06"), ("30", "09"), ("31", "03")):
            res.period_end = f"{y}-{mth}-{d}"
            break

    used: set[int] = set()
    for spec in FIELDS:
        if not spec.patterns:
            continue
        lo, hi = ranges[spec.statement]
        total, sources = None, []
        summed = spec.key in SUMMED_FIELDS
        # Most specific pattern first; a generic label ("Rueckstellungen") is only
        # used when no specific one ("sonstige Rueckstellungen") exists.
        for pattern in spec.patterns:
            for i in range(lo, hi):
                if i in used or not re.search(pattern, norm[i]):
                    continue
                amount = _first_amount(lines[i])
                if amount is None:
                    continue
                if any(w in norm[i] for w in spec.negative_if):
                    amount = -abs(amount)
                used.add(i)
                total = amount if total is None else total + amount
                sources.append(lines[i])
                if not summed:
                    break
            if total is not None and not summed:
                break
        if total is not None:
            res.fields[spec.key] = FieldProposal(total, " | ".join(sources)[:160], "mittel")

    # Liabilities split by remaining term: the balance sheet shows one line; the
    # split is a "davon" line or in the notes. Without it we propose everything
    # as short-term -- the CONSERVATIVE reading -- and ask the company to confirm.
    splits = (
        (r"verbindlichkeiten gegenueber kreditinstituten", "verb_kreditinstitute_kurz", "verb_kreditinstitute_lang"),
        (r"^sonstige verbindlichkeiten", "sonstige_verbindlichkeiten_kurz", "sonstige_verbindlichkeiten_lang"),
    )
    lo, hi = ranges["passiva"]
    for pattern, short_key, long_key in splits:
        for i in range(lo, hi):
            if i in used or not re.search(pattern, norm[i]):
                continue
            total = _first_amount(lines[i])
            if total is None:
                continue
            used.add(i)
            short = long_ = None
            for j in range(i + 1, min(i + 3, hi)):
                if re.search(r"davon .*(bis zu einem jahr|restlaufzeit bis)", norm[j]):
                    short = _first_amount(lines[j])
                elif re.search(r"davon .*(mehr als (einem|1) jahr|ueber einem jahr)", norm[j]):
                    long_ = _first_amount(lines[j])
            if short is None and long_ is not None:
                short = total - long_
            if short is not None:
                res.fields[short_key] = FieldProposal(short, lines[i][:160], "mittel", "Anteil bis 1 Jahr laut davon-Vermerk")
                res.fields[long_key] = FieldProposal(total - short, lines[i][:160], "mittel", "Gesamtbetrag abzueglich kurzfristiger Anteil")
            else:
                res.fields[short_key] = FieldProposal(total, lines[i][:160], "niedrig",
                    "Aufteilung nach Restlaufzeit nicht gefunden - vorsichtig als kurzfristig erfasst. Bitte pruefen.")
                res.fields[long_key] = FieldProposal(0.0, "", "niedrig", "siehe kurzfristiger Anteil")
            break

    missing = [s.label_de for s in FIELDS if s.key in ("umsatzerloese", "gezeichnetes_kapital") and s.key not in res.fields]
    if missing:
        res.warnings.append("Nicht gefunden: " + ", ".join(missing) + ". Ist das ein Jahresabschluss (Bilanz und GuV)?")
    return res


# ---------------------------------------------------------------------------
# Consistency checks -- run on proposals AND on confirmed figures
# ---------------------------------------------------------------------------

AKTIVA = [f.key for f in FIELDS if f.statement == "aktiva"]
PASSIVA = [f.key for f in FIELDS if f.statement == "passiva"]


def to_statements(figures: dict[str, Any], period_end: date, period_months: int = 12
                  ) -> tuple[BalanceSheet, IncomeStatement]:
    bs = BalanceSheet(period_end=period_end)
    gu = IncomeStatement(period_end=period_end, period_months=period_months)
    for f in FIELDS:
        v = float(figures.get(f.key) or 0.0)
        setattr(bs if f.statement != "guv" else gu, f.key, v)
    return bs, gu


def check_figures(figures: dict[str, Any], period_months: int = 12) -> list[dict]:
    """Plausibility checks, phrased for the person confirming the figures."""
    fig = {k: float(figures.get(k) or 0.0) for k in FIELDS_BY_KEY}
    checks: list[dict] = []
    aktiva = sum(fig[k] for k in AKTIVA)
    passiva = sum(fig[k] for k in PASSIVA)
    diff = aktiva - passiva
    tol = max(1.0, abs(aktiva) * 0.005)
    checks.append({
        "code": "BILANZSUMME", "ok": abs(diff) <= tol,
        "de": f"Aktiva {de(aktiva)} EUR, Passiva {de(passiva)} EUR" + ("" if abs(diff) <= tol else f" - Differenz {de(diff)} EUR"),
        "en": f"Assets {aktiva:,.0f} EUR, equity and liabilities {passiva:,.0f} EUR" + ("" if abs(diff) <= tol else f" - difference {diff:,.0f} EUR"),
    })
    if period_months == 12:
        _, gu = to_statements(fig, date.today(), 12)
        gap = gu.jahresueberschuss - fig["jahresueberschuss"]
        ok = abs(gap) <= max(1.0, abs(aktiva) * 0.002)
        checks.append({
            "code": "ERGEBNIS", "ok": ok,
            "de": f"Ergebnis laut GuV {de(gu.jahresueberschuss)} EUR, laut Bilanz {de(fig['jahresueberschuss'])} EUR" + ("" if ok else " - bitte GuV-Positionen pruefen (fehlt ein Posten?)"),
            "en": f"Result per P&L {gu.jahresueberschuss:,.0f} EUR, per balance sheet {fig['jahresueberschuss']:,.0f} EUR" + ("" if ok else " - please check the P&L lines (is an item missing?)"),
        })
    checks.append({
        "code": "UMSATZ", "ok": fig["umsatzerloese"] > 0,
        "de": "Umsatzerloese vorhanden" if fig["umsatzerloese"] > 0 else "Keine Umsatzerloese erfasst",
        "en": "Revenue present" if fig["umsatzerloese"] > 0 else "No revenue entered",
    })
    return checks


def parse_confirmed(payload: dict) -> tuple[dict[str, float], date, int]:
    """Validate figures submitted from the confirmation screen."""
    raw = payload.get("figures")
    if not isinstance(raw, dict):
        raise ValueError("Zahlen fehlen")
    figures: dict[str, float] = {}
    for key in FIELDS_BY_KEY:
        v = raw.get(key)
        if v in (None, ""):
            figures[key] = 0.0
            continue
        if isinstance(v, str):
            s = v.strip().replace(" ", "").replace("EUR", "").replace("€", "")
            if "," in s:
                s = s.replace(".", "").replace(",", ".")
            elif re.match(r"^-?\d{1,3}(\.\d{3})+$", s):
                s = s.replace(".", "")
            try:
                v = float(s)
            except ValueError:
                raise ValueError(f"'{FIELDS_BY_KEY[key].label_de}': '{raw.get(key)}' ist keine Zahl") from None
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"'{FIELDS_BY_KEY[key].label_de}': Zahl erwartet")
        figures[key] = float(v)
    try:
        period_end = date.fromisoformat(str(payload.get("period_end")))
    except ValueError:
        raise ValueError("Bilanzstichtag fehlt oder ist ungueltig (JJJJ-MM-TT)") from None
    months = int(payload.get("period_months") or 12)
    if not 1 <= months <= 12:
        raise ValueError("Zeitraum muss 1-12 Monate sein")
    return figures, period_end, months
