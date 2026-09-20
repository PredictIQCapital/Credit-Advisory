"""Generate the Excel cross-check workbook for the scorecard.

The point of this file: the engine must be checkable by hand. An advisor, a
sceptical Steuerberater or a lender should be able to re-derive any band from
the raw balance-sheet lines without reading Python. So the workbook contains
*live formulas* -- not exported results -- that reimplement ratios.py and
scorecard.py in Excel, and a reconciliation sheet that compares those formulas
against what the engine actually produced for the sample cases.

If the two ever disagree, one of them is wrong and the difference shows up per
factor, per case, on the Abgleich sheet.

    pip install openpyxl
    python scripts/build_scorecard_workbook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName

from test_catalogue import TESTS

from credit_readiness.engine import run_diagnostic
from credit_readiness.ingest.json_intake import load_case_file
from credit_readiness.ratios import compute_ratios
from credit_readiness.scorecard import (
    BAND_THRESHOLDS,
    FACTORS,
    evaluate,
)

TARGET = ROOT / "docs" / "testing" / "Scorecard-Pruefblatt.xlsx"
SAMPLES = ROOT / "data" / "samples"

NAVY = "0D2440"
GREEN = "0B8F73"
SOFT = "F4F7FA"
AMBER = "FDF1DC"

H1 = Font(bold=True, color="FFFFFF", size=11)
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
SUB_FILL = PatternFill("solid", fgColor=SOFT)
GREEN_FILL = PatternFill("solid", fgColor="E2F4EE")
AMBER_FILL = PatternFill("solid", fgColor=AMBER)
BOLD = Font(bold=True)
GREY = Font(color="5B6B7C", size=9)
TITLE = Font(bold=True, size=14, color=NAVY)
THIN = Side(style="thin", color="D8E0E8")
BOX = Border(bottom=THIN)

MONEY = "#,##0"
PCT = "0.0%"
XFMT = "0.00"
NUM1 = "0.0"


# ---------------------------------------------------------------------------
# Input definition: label (DE), hint (EN), how to read it off a ClientCase
# ---------------------------------------------------------------------------

def _bs(name):
    return lambda c: getattr(c.balance_sheet, name)


def _gu(name):
    return lambda c: getattr(c.income_statement, name)


def _bh(name):
    return lambda c: getattr(c.behavior, name)


def _flag(fn):
    return lambda c: 1 if fn(c) else 0


def _req(name, default=0.0):
    return lambda c: getattr(c.request, name) if c.request else default


def _prior(name, default=0.0):
    return lambda c: getattr(c.prior_year_income, name) if c.prior_year_income else default


def _interest(c):
    return sum(f.annual_interest for f in c.facilities)


def _principal(c):
    return sum(f.annual_principal_repayment for f in c.facilities)


# (key, label DE, hint EN, getter, number format)  -- None key = section heading
INPUTS = [
    (None, "AKTIVA (Bilanz, HGB §266)", "Assets", None, None),
    ("immat", "Immaterielle Vermoegensgegenstaende", "Intangibles incl. goodwill", _bs("immaterielle_vermoegensgegenstaende"), MONEY),
    ("sachanlagen", "Sachanlagen", "Tangible fixed assets", _bs("sachanlagen"), MONEY),
    ("finanzanlagen", "Finanzanlagen", "Financial assets", _bs("finanzanlagen"), MONEY),
    ("vorraete", "Vorraete", "Inventory", _bs("vorraete"), MONEY),
    ("forderungen", "Forderungen aus L+L", "Trade receivables", _bs("forderungen_ll"), MONEY),
    ("sonst_vg", "Sonstige Vermoegensgegenstaende", "Other assets", _bs("sonstige_vermoegensgegenstaende"), MONEY),
    ("wertpapiere", "Wertpapiere", "Securities", _bs("wertpapiere"), MONEY),
    ("liquide", "Liquide Mittel", "Cash and bank", _bs("liquide_mittel"), MONEY),
    ("arap", "Aktive Rechnungsabgrenzung", "Prepaid expenses", _bs("aktive_rap"), MONEY),

    (None, "PASSIVA (Bilanz)", "Liabilities and equity", None, None),
    ("gez_kapital", "Gezeichnetes Kapital", "Subscribed capital", _bs("gezeichnetes_kapital"), MONEY),
    ("kapitalruecklage", "Kapitalruecklage", "Capital reserve", _bs("kapitalruecklage"), MONEY),
    ("gewinnruecklagen", "Gewinnruecklagen", "Retained earnings reserve", _bs("gewinnruecklagen"), MONEY),
    ("gewinnvortrag", "Gewinnvortrag / Verlustvortrag", "Profit carried forward (may be negative)", _bs("gewinnvortrag"), MONEY),
    ("js_bilanz", "Jahresueberschuss laut Bilanz", "Net result as shown in equity", _bs("jahresueberschuss"), MONEY),
    ("ausstehende", "Ausstehende Einlagen", "Unpaid contributions (deducted)", _bs("ausstehende_einlagen"), MONEY),
    ("rueckstellungen", "Rueckstellungen", "Provisions", _bs("rueckstellungen"), MONEY),
    ("pensionen", "Pensionsrueckstellungen", "Pension provisions", _bs("pensionsrueckstellungen"), MONEY),
    ("bank_kurz", "Verb. Kreditinstitute < 1 Jahr", "Bank debt, short term", _bs("verb_kreditinstitute_kurz"), MONEY),
    ("bank_lang", "Verb. Kreditinstitute > 1 Jahr", "Bank debt, long term", _bs("verb_kreditinstitute_lang"), MONEY),
    ("verb_ll", "Verbindlichkeiten aus L+L", "Trade payables", _bs("verb_ll"), MONEY),
    ("sonst_kurz", "Sonstige Verbindlichkeiten < 1 Jahr", "Other liabilities, short term", _bs("sonstige_verbindlichkeiten_kurz"), MONEY),
    ("sonst_lang", "Sonstige Verbindlichkeiten > 1 Jahr", "Other liabilities, long term", _bs("sonstige_verbindlichkeiten_lang"), MONEY),
    ("prap", "Passive Rechnungsabgrenzung", "Deferred income", _bs("passive_rap"), MONEY),

    (None, "SONDERPOSITIONEN", "The items that decide fixability", None, None),
    ("gesdarlehen", "Gesellschafterdarlehen", "Shareholder loan", _bs("gesellschafterdarlehen"), MONEY),
    ("rangruecktritt", "Rangruecktritt vorhanden (1 = ja)", "Subordination agreement in place", _flag(lambda c: c.balance_sheet.gesellschafterdarlehen_rangruecktritt), "0"),
    ("kk_limit", "Kontokorrentlinie (Limit)", "Overdraft facility limit", _bs("kontokorrent_limit"), MONEY),
    ("kk_inanspruch", "Kontokorrent-Inanspruchnahme", "Overdraft drawn", _bs("kontokorrent_inanspruchnahme"), MONEY),
    ("leasing", "Leasingverpflichtungen", "Off-balance-sheet leasing", _bs("leasing_verpflichtungen"), MONEY),

    (None, "GUV (HGB §275, Gesamtkostenverfahren)", "Income statement", None, None),
    ("monate", "Periodenlaenge in Monaten", "1-12; a mid-year BWA is annualised", _gu("period_months"), "0"),
    ("umsatz", "Umsatzerloese", "Revenue", _gu("umsatzerloese"), MONEY),
    ("bestand", "Bestandsveraenderungen", "Change in inventories", _gu("bestandsveraenderungen"), MONEY),
    ("sonst_ertrag", "Sonstige betriebliche Ertraege", "Other operating income", _gu("sonstige_betriebliche_ertraege"), MONEY),
    ("material", "Materialaufwand", "Cost of materials", _gu("materialaufwand"), MONEY),
    ("personal", "Personalaufwand", "Personnel expenses", _gu("personalaufwand"), MONEY),
    ("afa", "Abschreibungen", "Depreciation and amortisation", _gu("abschreibungen"), MONEY),
    ("sonst_aufwand", "Sonstige betriebliche Aufwendungen", "Other operating expenses", _gu("sonstige_betriebliche_aufwendungen"), MONEY),
    ("zinsertrag", "Zinsertraege", "Interest income", _gu("zinsertraege"), MONEY),
    ("zinsaufwand", "Zinsaufwand", "Interest expense", _gu("zinsaufwand"), MONEY),
    ("steuern", "Steuern", "Taxes", _gu("steuern"), MONEY),

    (None, "VORJAHR (nur fuer Trendaussagen)", "Prior year, for growth only", None, None),
    ("vj_umsatz", "Umsatzerloese Vorjahr", "Prior-year revenue (0 = none)", _prior("umsatzerloese"), MONEY),
    ("vj_monate", "Periodenlaenge Vorjahr", "Prior-year period months", lambda c: c.prior_year_income.period_months if c.prior_year_income else 12, "0"),

    (None, "DARLEHENSDIENST", "Debt service from the facility list", None, None),
    ("zins_darlehen", "Zinsen p.a. (Summe Darlehensliste)", "Sum of outstanding x rate", _interest, MONEY),
    ("tilgung_darlehen", "Tilgung p.a. (Summe Darlehensliste)", "Sum of annual principal repayments", _principal, MONEY),

    (None, "FINANZIERUNGSWUNSCH", "The requested new facility", None, None),
    ("wunsch_betrag", "Beantragter Betrag", "Requested amount (0 = none)", _req("amount"), MONEY),
    ("wunsch_laufzeit", "Laufzeit in Jahren", "Tenor in years", _req("tenor_years", 5), "0"),
    ("wunsch_sicherheiten", "Verfuegbare Sicherheiten", "Collateral available", _req("collateral_available"), MONEY),

    (None, "VERHALTENSDATEN", "Behavioural data", None, None),
    ("bwa_alter", "Alter der juengsten BWA (Monate)", "Age of latest management report", _bh("bwa_age_months"), NUM1),
    ("creditreform", "Creditreform Bonitaetsindex (100-600)", "Leave empty if no report held", lambda c: c.behavior.creditreform_bonitaetsindex, "0"),
    ("zahlungsverzug", "Durchschn. Zahlungsverzug (Tage)", "Average days beyond terms", _bh("days_beyond_terms"), NUM1),
    ("ruecklastschriften", "Ruecklastschriften (12 Monate)", "Returned direct debits", _bh("returned_direct_debits_12m"), "0"),
    ("kk_tage", "Tage am KK-Limit (12 Monate)", "Days at the overdraft limit", _bh("overdraft_days_at_limit_12m"), "0"),
    ("steuerrueckstand", "Steuerrueckstaende (1 = ja)", "Tax arrears", _flag(lambda c: c.behavior.tax_arrears), "0"),
    ("planrechnung", "Planrechnung liegt vor (1 = ja)", "Financial plan provided", _flag(lambda c: c.behavior.has_planning_forecast), "0"),
]


# ---------------------------------------------------------------------------
# Derived figures and ratios: label, hint, formula template, format
# `{c}` is replaced by the case's column letter.
# ---------------------------------------------------------------------------

def build_ratio_rows(ir: dict[str, int]) -> list:
    """Formula templates mirroring models.py and ratios.py line for line."""
    E = "Eingaben!"

    def i(key):                      # input cell on the Eingaben sheet
        return f"{E}{{c}}{ir[key]}"

    return [
        (None, "ZWISCHENGROESSEN (models.py)", "Derived figures", None, None),
        ("faktor", "Annualisierungsfaktor", "12 / Periodenmonate", f"=12/{i('monate')}", XFMT),
        ("av", "Anlagevermoegen", "immat + Sachanlagen + Finanzanlagen",
         f"={i('immat')}+{i('sachanlagen')}+{i('finanzanlagen')}", MONEY),
        ("uv", "Umlaufvermoegen", "Vorraete + Ford. + sonst. VG + WP + liquide Mittel",
         f"={i('vorraete')}+{i('forderungen')}+{i('sonst_vg')}+{i('wertpapiere')}+{i('liquide')}", MONEY),
        ("bilanzsumme", "Bilanzsumme (Aktiva)", "AV + UV + ARAP", "={c}%(av)s+{c}%(uv)s+" + i("arap"), MONEY),
        ("passiva", "Summe Passiva (Probe)", "EK + Rueckst. + Verb. + PRAP + Ges.darlehen",
         "={c}%(ek_bil)s+" + "+".join(i(k) for k in
           ("rueckstellungen", "pensionen", "bank_kurz", "bank_lang", "verb_ll",
            "sonst_kurz", "sonst_lang", "gesdarlehen", "prap")), MONEY),
        ("bilanzprobe", "Bilanzprobe: Aktiva - Passiva", "Muss ~0 sein, sonst blockiert die Engine",
         "={c}%(bilanzsumme)s-{c}%(passiva)s", MONEY),
        ("bilanz_ok", "Bilanz ausgeglichen?", "Toleranz: max(1 EUR; 0,5% der Bilanzsumme)",
         '=IF(ABS({c}%(bilanzprobe)s)<=MAX(1,0.005*{c}%(bilanzsumme)s),"OK","FEHLER - Engine bricht ab")', None),
        ("ek_bil", "Bilanzielles Eigenkapital", "gez. Kapital + Ruecklagen + Vortrag + JUE - ausst. Einlagen",
         f"={i('gez_kapital')}+{i('kapitalruecklage')}+{i('gewinnruecklagen')}+{i('gewinnvortrag')}+{i('js_bilanz')}-{i('ausstehende')}", MONEY),
        ("ek_wirt", "Wirtschaftliches Eigenkapital", "+ Gesellschafterdarlehen, wenn Rangruecktritt",
         "={c}%(ek_bil)s+IF(" + i("rangruecktritt") + "=1," + i("gesdarlehen") + ",0)", MONEY),
        ("finanzverb", "Finanzverbindlichkeiten", "Bankschulden + Ges.darlehen ohne Rangruecktritt",
         f"={i('bank_kurz')}+{i('bank_lang')}+IF({i('rangruecktritt')}=1,0,{i('gesdarlehen')})", MONEY),
        ("nettoverb", "Nettofinanzverbindlichkeiten", "abzgl. liquide Mittel und Wertpapiere, min. 0",
         "=MAX(0,{c}%(finanzverb)s-" + i("liquide") + "-" + i("wertpapiere") + ")", MONEY),
        ("kurzfrist", "Kurzfristige Verbindlichkeiten", "Bank kurz + L+L + sonstige kurz",
         f"={i('bank_kurz')}+{i('verb_ll')}+{i('sonst_kurz')}", MONEY),
        ("langkapital", "Langfristiges Kapital", "wirtsch. EK + Bank lang + sonst. lang + Pensionen",
         "={c}%(ek_wirt)s+" + i("bank_lang") + "+" + i("sonst_lang") + "+" + i("pensionen"), MONEY),

        (None, "ANNUALISIERTE GUV-GROESSEN (ratios.py)", "Flows, annualised", None, None),
        ("gesamtleistung", "Gesamtleistung", "Umsatz + Bestandsveraenderung + sonst. Ertraege",
         f"=({i('umsatz')}+{i('bestand')}+{i('sonst_ertrag')})*{{c}}%(faktor)s", MONEY),
        ("umsatz_a", "Umsatz (annualisiert)", "", f"={i('umsatz')}*{{c}}%(faktor)s", MONEY),
        ("ebitda", "EBITDA (annualisiert)", "Gesamtleistung - Material - Personal - sonst. Aufwand",
         "={c}%(gesamtleistung)s-(" + i("material") + "+" + i("personal") + "+" + i("sonst_aufwand") + ")*{c}%(faktor)s", MONEY),
        ("ebit", "EBIT (annualisiert)", "EBITDA - Abschreibungen",
         "={c}%(ebitda)s-" + i("afa") + "*{c}%(faktor)s", MONEY),
        ("zins_a", "Zinsaufwand (annualisiert)", "", f"={i('zinsaufwand')}*{{c}}%(faktor)s", MONEY),
        ("material_a", "Materialaufwand (annualisiert)", "", f"={i('material')}*{{c}}%(faktor)s", MONEY),
        ("jue_guv", "Jahresueberschuss laut GuV", "EBIT + Zinsertrag - Zinsaufwand - Steuern (nicht annualisiert)",
         "=({c}%(ebit)s/{c}%(faktor)s)+" + i("zinsertrag") + "-" + i("zinsaufwand") + "-" + i("steuern"), MONEY),
        ("ergebnis_ok", "Ergebnis GuV = Ergebnis Bilanz?", "Nur bei 12-Monats-Periode geprueft",
         '=IF(' + i("monate") + '<>12,"n/a (Rumpfperiode)",IF(ABS({c}%(jue_guv)s-' + i("js_bilanz")
         + ')<=MAX(1,0.002*{c}%(bilanzsumme)s),"OK","FEHLER - Engine bricht ab"))', None),

        (None, "KAPITALDIENST", "Debt service", None, None),
        ("kapitaldienst", "Kapitaldienst (bestehend)", "Zinsen + Tilgung aus der Darlehensliste",
         f"={i('zins_darlehen')}+{i('tilgung_darlehen')}", MONEY),
        ("annuitaet", "Annuitaet der neuen Finanzierung", "6,5% p.a., Laufzeit wie beantragt (konservativ)",
         "=IF(" + i("wunsch_betrag") + "<=0,0," + i("wunsch_betrag")
         + "*(0.065*(1+0.065)^MAX(1," + i("wunsch_laufzeit") + "))/((1+0.065)^MAX(1," + i("wunsch_laufzeit") + ")-1))", MONEY),
        ("kd_neu", "Kapitaldienst inkl. neuer Finanzierung", "",
         "={c}%(kapitaldienst)s+{c}%(annuitaet)s", MONEY),

        (None, "KENNZAHLEN (ratios.py)", "Ratios", None, None),
        ("ekq", "Eigenkapitalquote (wirtschaftlich)", "wirtsch. EK / Bilanzsumme  -- Faktor 1",
         '=IF({c}%(bilanzsumme)s=0,"",{c}%(ek_wirt)s/{c}%(bilanzsumme)s)', PCT),
        ("ekq_bil", "Eigenkapitalquote (bilanziell)", "nachrichtlich",
         '=IF({c}%(bilanzsumme)s=0,"",{c}%(ek_bil)s/{c}%(bilanzsumme)s)', PCT),
        ("adg2", "Anlagendeckungsgrad II", "langfr. Kapital / Anlagevermoegen -- Regel R06",
         '=IF({c}%(av)s=0,"",{c}%(langkapital)s/{c}%(av)s)', XFMT),
        ("dvg", "Dynamischer Verschuldungsgrad", "Nettoverschuldung / EBITDA -- Faktor 3",
         '=IF({c}%(ebitda)s<=0,"",{c}%(nettoverb)s/{c}%(ebitda)s)', XFMT),
        ("dscr", "Kapitaldienstfaehigkeit (bestehend)", "EBITDA / Kapitaldienst",
         '=IF({c}%(kapitaldienst)s<=0,"",{c}%(ebitda)s/{c}%(kapitaldienst)s)', XFMT),
        ("dscr_neu", "Kapitaldienstfaehigkeit inkl. neu", "EBITDA / Kapitaldienst inkl. neu -- Faktor 2",
         '=IF({c}%(kd_neu)s<=0,"",{c}%(ebitda)s/{c}%(kd_neu)s)', XFMT),
        ("zinsdeckung", "Zinsdeckungsgrad", "EBIT / Zinsaufwand -- Faktor 6",
         '=IF({c}%(zins_a)s=0,"",{c}%(ebit)s/{c}%(zins_a)s)', XFMT),
        ("ebitda_marge", "EBITDA-Marge", "nachrichtlich",
         '=IF({c}%(umsatz_a)s=0,"",{c}%(ebitda)s/{c}%(umsatz_a)s)', PCT),
        ("ebit_marge", "EBIT-Marge", "EBIT / Umsatz -- Faktor 4",
         '=IF({c}%(umsatz_a)s=0,"",{c}%(ebit)s/{c}%(umsatz_a)s)', PCT),
        ("gkr", "Gesamtkapitalrentabilitaet", "EBIT / Bilanzsumme",
         '=IF({c}%(bilanzsumme)s=0,"",{c}%(ebit)s/{c}%(bilanzsumme)s)', PCT),
        ("wachstum", "Umsatzwachstum", "gegen Vorjahr, annualisiert -- Regel R08",
         '=IF(' + i("vj_umsatz") + '<=0,"",({c}%(umsatz_a)s-' + i("vj_umsatz") + "*12/" + i("vj_monate")
         + ")/(" + i("vj_umsatz") + "*12/" + i("vj_monate") + "))", PCT),
        ("liq2", "Liquiditaet 2. Grades", "(Forderungen + liquide Mittel + WP) / kurzfr. Verb. -- Faktor 5",
         '=IF({c}%(kurzfrist)s=0,"",(' + i("forderungen") + "+" + i("liquide") + "+" + i("wertpapiere") + ")/{c}%(kurzfrist)s)", XFMT),
        ("liq3", "Liquiditaet 3. Grades", "Umlaufvermoegen / kurzfr. Verbindlichkeiten",
         '=IF({c}%(kurzfrist)s=0,"",{c}%(uv)s/{c}%(kurzfrist)s)', XFMT),
        ("wc", "Working Capital", "UV - kurzfristige Verbindlichkeiten",
         "={c}%(uv)s-{c}%(kurzfrist)s", MONEY),
        ("dso", "Debitorenlaufzeit (Tage)", "Forderungen / Umsatz x 365 -- Regel R05",
         '=IF({c}%(umsatz_a)s<=0,"",' + i("forderungen") + "/{c}%(umsatz_a)s*365)", NUM1),
        ("dpo", "Kreditorenlaufzeit (Tage)", "Verb. L+L / Materialaufwand x 365",
         '=IF({c}%(material_a)s<=0,"",' + i("verb_ll") + "/{c}%(material_a)s*365)", NUM1),
        ("dio", "Vorratsreichweite (Tage)", "Vorraete / Materialaufwand x 365 -- Regel R10",
         '=IF({c}%(material_a)s<=0,"",' + i("vorraete") + "/{c}%(material_a)s*365)", NUM1),
        ("ccc", "Cash Conversion Cycle (Tage)", "DSO + Vorratsreichweite - DPO",
         '=IF(OR(NOT(ISNUMBER({c}%(dso)s)),NOT(ISNUMBER({c}%(dpo)s))),"",{c}%(dso)s+{c}%(dio)s-{c}%(dpo)s)', NUM1),
        ("kk_quote", "Kontokorrent-Auslastung", "Inanspruchnahme / Limit -- Faktor 7",
         '=IF(' + i("kk_limit") + '<=0,"",' + i("kk_inanspruch") + "/" + i("kk_limit") + ")", PCT),
        ("zahlung", "Zahlungsverhalten-Index (0-100)", "100 - Verzug x2,5 (max 45) - Ruecklast. x12 (max 30) - Steuer 30 - KK-Tage",
         "=MAX(0,100-MIN(45," + i("zahlungsverzug") + "*2.5)-MIN(30," + i("ruecklastschriften") + "*12)-IF("
         + i("steuerrueckstand") + "=1,30,0)-IF(" + i("kk_tage") + ">60,15,IF(" + i("kk_tage") + ">20,7,0)))", NUM1),
    ]


# raw value of each scorecard factor -> key on the Kennzahlen sheet
FACTOR_SOURCE = {
    "eigenkapitalquote": "ekq",
    "kapitaldienstfaehigkeit_inkl_neu": "dscr_neu",
    "dynamischer_verschuldungsgrad": "dvg",
    "ebit_marge": "ebit_marge",
    "liquiditaet_2_grades": "liq2",
    "zinsdeckungsgrad": "zinsdeckung",
    "kontokorrent_auslastung": "kk_quote",
    "bwa_age_months": None,          # straight from Eingaben
    "creditreform_bonitaetsindex": None,
    "zahlungsverhalten": "zahlung",
}
FACTOR_INPUT = {
    "bwa_age_months": "bwa_alter",
    "creditreform_bonitaetsindex": "creditreform",
}


def interp(value_ref: str, key: str) -> str:
    """Piecewise-linear lookup with clamping -- mirrors scorecard.interpolate."""
    x, y = f"bpx_{key}", f"bpy_{key}"
    m = f"MATCH({value_ref},{x},1)"
    return (
        f'IF(NOT(ISNUMBER({value_ref})),"",'
        f"IF({value_ref}<=INDEX({x},1),INDEX({y},1),"
        f"IF({value_ref}>=INDEX({x},COUNT({x})),INDEX({y},COUNT({x})),"
        f"INDEX({y},{m})+({value_ref}-INDEX({x},{m}))"
        f"/(INDEX({x},{m}+1)-INDEX({x},{m}))"
        f"*(INDEX({y},{m}+1)-INDEX({y},{m})))))"
    )


def band_formula(total_ref: str) -> str:
    parts = "".join(f'IF({total_ref}>={t},"{b.value}",' for t, b in BAND_THRESHOLDS[:-1])
    return "=" + parts + '"E"' + ")" * (len(BAND_THRESHOLDS) - 1)


# ---------------------------------------------------------------------------


def style_header(ws, row: int, last_col: int) -> None:
    for col in range(1, last_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEAD_FILL
        cell.font = H1
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def section_row(ws, row: int, label: str, hint: str, last_col: int) -> None:
    ws.cell(row=row, column=1, value=label).font = Font(bold=True, color=NAVY)
    ws.cell(row=row, column=2, value=hint).font = GREY
    for col in range(1, last_col + 1):
        ws.cell(row=row, column=col).fill = SUB_FILL


def main() -> int:
    case_files = sorted(SAMPLES.glob("case_*.json"))
    cases = [load_case_file(p) for p in case_files]
    results = []
    diagnostics = []
    for case in cases:
        r = compute_ratios(case)
        results.append((case, r, evaluate(case, r)))
        diagnostics.append(run_diagnostic(case, strict=False))

    # column C = the user's own case, D.. = the samples
    columns = ["C"] + [get_column_letter(4 + i) for i in range(len(cases))]
    last_col = 3 + len(cases)

    wb = Workbook()

    # ---------------- Anleitung ----------------
    ws = wb.active
    ws.title = "Anleitung"
    ws["A1"] = "Scorecard-Pruefblatt"
    ws["A1"].font = TITLE
    lines = [
        "",
        "Wozu dieses Blatt / What this workbook is for",
        "Es rechnet die Bewertung der Engine mit Excel-Formeln nach. Jede Zahl ist nachvollziehbar,",
        "keine Zelle ist ein exportiertes Ergebnis. Wer die Engine pruefen will, prueft sie hier.",
        "",
        "It reimplements the engine's scoring in live Excel formulas. Nothing is a pasted result.",
        "",
        "So benutzen Sie es / How to use it",
        "1. Blatt 'Eingaben': Spalte C ist Ihr eigener Fall. Ueberschreiben Sie die Werte.",
        "   Spalten D bis I sind die Musterfaelle und sollten unveraendert bleiben.",
        "2. Blatt 'Kennzahlen': alle Zwischengroessen und Kennzahlen, Formel fuer Formel.",
        "3. Blatt 'Scorecard': die zehn Faktoren, ihre Punkte, Gewichte, der Gesamtscore und das Band.",
        "4. Blatt 'Abgleich': Excel gegen Engine, Faktor fuer Faktor, fuer jeden Musterfall.",
        "   Dort muss ueberall 'OK' stehen. Steht dort eine Abweichung, ist eine der beiden Seiten falsch.",
        "5. Blatt 'Stuetzstellen': die Schwellenwerte je Faktor und die Bandgrenzen.",
        "",
        "Was das Ergebnis NICHT ist / What the result is not",
        "Ein Readiness-Band ist eine richtungsweisende Einschaetzung, kein Rating und keine",
        "Ausfallwahrscheinlichkeit. Die Kreditentscheidung trifft allein der Kreditgeber.",
        "",
        "Pruefreihenfolge, wenn Sie einen Fall testen / Order to check a case",
        "a) Bilanzprobe und Ergebnisabgleich auf 'Kennzahlen' muessen 'OK' zeigen -- sonst",
        "   verweigert die Engine die Auswertung, und zwar absichtlich.",
        "b) Kennzahlen mit dem Bericht der Engine vergleichen.",
        "c) Punkte je Faktor vergleichen. Die groesste Abweichung zeigt, wo zu suchen ist.",
        "d) Gesamtscore und Band vergleichen.",
        "",
        f"Erzeugt aus dem Quellcode: scripts/build_scorecard_workbook.py",
        "Bei jeder Aenderung an scorecard.py oder ratios.py neu erzeugen.",
    ]
    for i, text in enumerate(lines, start=2):
        cell = ws.cell(row=i, column=1, value=text)
        if text and not text.startswith(" ") and text[0].isalpha() and text.endswith(("for", "it", "not", "case")):
            cell.font = Font(bold=True, color=GREEN)
    ws.column_dimensions["A"].width = 110

    # ---------------- Stuetzstellen ----------------
    bp = wb.create_sheet("Stuetzstellen")
    bp["A1"] = "Stuetzstellen der Faktoren / factor breakpoints"
    bp["A1"].font = TITLE
    bp["A2"] = "Zwischen den Punkten wird linear interpoliert, ausserhalb wird gekappt."
    bp["A2"].font = GREY
    row = 4
    for fd in FACTORS:
        bp.cell(row=row, column=1, value=fd.label).font = BOLD
        bp.cell(row=row, column=3, value=f"Gewicht {fd.weight:.0%}").font = GREY
        bp.cell(row=row, column=4, value=fd.note or "").font = GREY
        row += 1
        bp.cell(row=row, column=1, value="Wert").font = GREY
        bp.cell(row=row, column=2, value="Punkte").font = GREY
        row += 1
        first = row
        for x, y in fd.breakpoints:
            bp.cell(row=row, column=1, value=x).number_format = XFMT
            bp.cell(row=row, column=2, value=y).number_format = NUM1
            row += 1
        last = row - 1
        for axis, col in (("x", "A"), ("y", "B")):
            wb.defined_names.add(
                DefinedName(f"bp{axis}_{fd.key}", attr_text=f"Stuetzstellen!${col}${first}:${col}${last}")
            )
        row += 1

    bp.cell(row=row, column=1, value="Bandgrenzen / band thresholds").font = Font(bold=True, color=NAVY)
    row += 1
    for threshold, band in BAND_THRESHOLDS:
        bp.cell(row=row, column=1, value=f"Score >= {threshold:.0f}")
        bp.cell(row=row, column=2, value=band.value).font = BOLD
        bp.cell(row=row, column=3, value=band.interpretation).font = GREY
        row += 1
    bp.column_dimensions["A"].width = 46
    bp.column_dimensions["B"].width = 12
    bp.column_dimensions["C"].width = 16
    bp.column_dimensions["D"].width = 60

    # ---------------- Eingaben ----------------
    ein = wb.create_sheet("Eingaben")
    ein["A1"] = "Eingaben / inputs"
    ein["A1"].font = TITLE
    ein["A2"] = "Spalte C ueberschreiben. Musterfaelle nicht aendern -- der Abgleich haengt daran."
    ein["A2"].font = GREY

    header = 4
    ein.cell(row=header, column=1, value="Position")
    ein.cell(row=header, column=2, value="Hinweis / note")
    ein.cell(row=header, column=3, value="Ihr Fall")
    for k, (case, _, _) in enumerate(results):
        ein.cell(row=header, column=4 + k, value=case.profile.name)
    style_header(ein, header, last_col)

    input_row: dict[str, int] = {}
    r = header + 1
    for key, label, hint, getter, fmt in INPUTS:
        if key is None:
            section_row(ein, r, label, hint, last_col)
            r += 1
            continue
        ein.cell(row=r, column=1, value=label)
        ein.cell(row=r, column=2, value=hint).font = GREY
        for k, (case, _, _) in enumerate(results):
            value = getter(case)
            cell = ein.cell(row=r, column=4 + k, value=value)
            if fmt:
                cell.number_format = fmt
        # column C starts as a copy of the first sample so the sheet is alive
        own = ein.cell(row=r, column=3, value=getter(results[0][0]))
        own.fill = GREEN_FILL
        if fmt:
            own.number_format = fmt
        input_row[key] = r
        r += 1

    ein.freeze_panes = "C5"
    ein.column_dimensions["A"].width = 40
    ein.column_dimensions["B"].width = 42
    for col in columns:
        ein.column_dimensions[col].width = 16

    # ---------------- Kennzahlen ----------------
    ken = wb.create_sheet("Kennzahlen")
    ken["A1"] = "Zwischengroessen und Kennzahlen / derived figures and ratios"
    ken["A1"].font = TITLE
    ken["A2"] = "Alles Formeln. Diese Seite ist die eigentliche Nachrechnung von models.py und ratios.py."
    ken["A2"].font = GREY

    rows = build_ratio_rows(input_row)
    ken.cell(row=header, column=1, value="Groesse")
    ken.cell(row=header, column=2, value="Formel / formula")
    ken.cell(row=header, column=3, value="Ihr Fall")
    for k, (case, _, _) in enumerate(results):
        ken.cell(row=header, column=4 + k, value=case.profile.name)
    style_header(ken, header, last_col)

    ratio_row: dict[str, int] = {}
    r = header + 1
    for key, label, hint, template, fmt in rows:
        if key is None:
            section_row(ken, r, label, hint, last_col)
            r += 1
            continue
        ratio_row[key] = r
        r += 1

    r = header + 1
    for key, label, hint, template, fmt in rows:
        if key is None:
            r += 1
            continue
        ken.cell(row=r, column=1, value=label)
        ken.cell(row=r, column=2, value=hint).font = GREY
        for k, col in enumerate(columns):
            formula = (template % ratio_row) if "%(" in template else template
            cell = ken.cell(row=r, column=3 + k, value=formula.replace("{c}", col))
            if fmt:
                cell.number_format = fmt
        r += 1

    ken.freeze_panes = "C5"
    ken.column_dimensions["A"].width = 40
    ken.column_dimensions["B"].width = 58
    for col in columns:
        ken.column_dimensions[col].width = 16

    # ---------------- Scorecard ----------------
    sc = wb.create_sheet("Scorecard")
    sc["A1"] = "Scorecard / scoring"
    sc["A1"].font = TITLE
    sc["A2"] = "Je Fall zwei Spalten: der Rohwert und die daraus interpolierten Punkte (0-100)."
    sc["A2"].font = GREY

    sc.cell(row=header, column=1, value="Faktor")
    sc.cell(row=header, column=2, value="Gewicht")
    sc.cell(row=header, column=3, value="Einheit")
    names = ["Ihr Fall"] + [c.profile.name for c, _, _ in results]
    for k, name in enumerate(names):
        sc.cell(row=header, column=4 + 3 * k, value=name)
        sc.cell(row=header, column=5 + 3 * k, value="Punkte")
        sc.cell(row=header, column=6 + 3 * k, value="Beitrag")
    sc_last = 3 + 3 * len(names)
    style_header(sc, header, sc_last)

    first_factor = header + 1
    for fi, fd in enumerate(FACTORS):
        r = first_factor + fi
        sc.cell(row=r, column=1, value=fd.label)
        sc.cell(row=r, column=2, value=fd.weight).number_format = "0%"
        sc.cell(row=r, column=3, value=fd.unit).font = GREY
        source = FACTOR_SOURCE[fd.key]
        for k, col in enumerate(columns):
            vcol = get_column_letter(4 + 3 * k)
            pcol = get_column_letter(5 + 3 * k)
            ccol = get_column_letter(6 + 3 * k)
            if source is None:
                ref = f"Eingaben!{col}{input_row[FACTOR_INPUT[fd.key]]}"
                sc[f"{vcol}{r}"] = f'=IF({ref}="","",{ref})'
            else:
                ref = f"Kennzahlen!{col}{ratio_row[source]}"
                sc[f"{vcol}{r}"] = f'=IF({ref}="","",{ref})'
            sc[f"{vcol}{r}"].number_format = {
                "percent": PCT, "x": XFMT, "months": NUM1, "index": "0",
            }.get(fd.unit, XFMT)

            value_ref = f"{vcol}{r}"
            if fd.key == "dynamischer_verschuldungsgrad":
                # EBITDA <= 0 cannot service debt at all: scored 0, never dropped
                ebitda_ref = f"Kennzahlen!{col}{ratio_row['ebitda']}"
                sc[f"{pcol}{r}"] = f"=IF({ebitda_ref}<=0,0,{interp(value_ref, fd.key)})"
            else:
                sc[f"{pcol}{r}"] = "=" + interp(value_ref, fd.key)
            sc[f"{pcol}{r}"].number_format = NUM1
            # Row-wise, so the sum below never has to evaluate a text cell.
            sc[f"{ccol}{r}"] = f"=IF(ISNUMBER({pcol}{r}),$B{r}*{pcol}{r},0)"
            sc[f"{ccol}{r}"].number_format = NUM1
            sc[f"{ccol}{r}"].font = GREY

    last_factor = first_factor + len(FACTORS) - 1

    summary = [
        ("gewicht_bewertet", "Summe der Gewichte mit Punkten",
         "=SUMPRODUCT(($B${f}:$B${l})*ISNUMBER({p}{f}:{p}{l}))", "0%"),
        ("abdeckung", "Abdeckung (Coverage)", "={c}{gewicht_bewertet}", "0%"),
        ("gew_punkte", "Summe Gewicht x Punkte", "=SUM({b}{f}:{b}{l})", NUM1),
        ("score", "Gesamtscore (renormiert)",
         '=IF({c}{gewicht_bewertet}=0,0,{c}{gew_punkte}/{c}{gewicht_bewertet})', NUM1),
        ("band", "Readiness-Band", None, None),
        ("engine_score", "Engine-Score (Referenz)", None, NUM1),
        ("engine_band", "Engine-Band (Referenz)", None, None),
        ("diff", "Differenz Excel - Engine",
         '=IF(NOT(ISNUMBER({c}{engine_score})),"",ROUND({c}{score},1)-{c}{engine_score})', NUM1),
        ("status", "Status", '=IF({c}{diff}="","eigener Fall",IF(ABS({c}{diff})<=0.05,"OK","ABWEICHUNG"))', None),
    ]
    srow = {key: last_factor + 2 + i for i, (key, *_rest) in enumerate(summary)}

    for key, label, template, fmt in summary:
        r = srow[key]
        cell = sc.cell(row=r, column=1, value=label)
        cell.font = BOLD
        for k, col in enumerate(columns):
            pcol = get_column_letter(5 + 3 * k)
            bcol = get_column_letter(6 + 3 * k)
            target = sc.cell(row=r, column=4 + 3 * k)
            if key == "band":
                target.value = band_formula(f"{get_column_letter(4 + 3 * k)}{srow['score']}")
            elif key == "engine_score":
                target.value = None if k == 0 else results[k - 1][2].total_score
            elif key == "engine_band":
                target.value = None if k == 0 else results[k - 1][2].band.value
            elif template:
                target.value = template.format(
                    f=first_factor, l=last_factor, p=pcol, b=bcol,
                    c=get_column_letter(4 + 3 * k), **srow
                )
            if fmt:
                target.number_format = fmt
            target.font = BOLD
            if key in ("score", "band", "status"):
                target.fill = GREEN_FILL

    sc.freeze_panes = "D5"
    sc.column_dimensions["A"].width = 44
    sc.column_dimensions["B"].width = 9
    sc.column_dimensions["C"].width = 9
    for k in range(len(names)):
        sc.column_dimensions[get_column_letter(4 + 3 * k)].width = 15
        sc.column_dimensions[get_column_letter(5 + 3 * k)].width = 9
        sc.column_dimensions[get_column_letter(6 + 3 * k)].width = 9

    # ---------------- Abgleich ----------------
    ab = wb.create_sheet("Abgleich")
    ab["A1"] = "Abgleich Excel gegen Engine / reconciliation"
    ab["A1"].font = TITLE
    ab["A2"] = "Punkte je Faktor. Alles ausser 'OK' bedeutet: eine der beiden Seiten rechnet falsch."
    ab["A2"].font = GREY

    ab.cell(row=header, column=1, value="Faktor")
    for k, (case, _, _) in enumerate(results):
        ab.cell(row=header, column=2 + k, value=case.profile.name)
    style_header(ab, header, 1 + len(results))

    for fi, fd in enumerate(FACTORS):
        r = header + 1 + fi
        ab.cell(row=r, column=1, value=fd.label)
        for k, (_case, _ratios, card) in enumerate(results):
            fs = card.factor(fd.key)
            engine = fs.score if fs and fs.score is not None else None
            pcol = f"Scorecard!{get_column_letter(5 + 3 * (k + 1))}{first_factor + fi}"
            if engine is None:
                formula = f'=IF(NOT(ISNUMBER({pcol})),"OK (beide n/a)","ABWEICHUNG: Engine wertet nicht")'
            else:
                formula = (
                    f'=IF(NOT(ISNUMBER({pcol})),"ABWEICHUNG: Excel wertet nicht",'
                    f'IF(ABS({pcol}-{engine})<=0.05,"OK",'
                    f'"ABWEICHUNG "&TEXT({pcol}-{engine},"0.00")))'
                )
            cell = ab.cell(row=r, column=2 + k, value=formula)
            cell.alignment = Alignment(horizontal="center")
        ab.cell(row=r, column=1).border = BOX

    r = header + 1 + len(FACTORS) + 1
    ab.cell(row=r, column=1, value="Gesamtscore Excel").font = BOLD
    for k in range(len(results)):
        ab.cell(row=r, column=2 + k,
                value=f"=ROUND(Scorecard!{get_column_letter(4 + 3 * (k + 1))}{srow['score']},1)").number_format = NUM1
    ab.cell(row=r + 1, column=1, value="Gesamtscore Engine").font = BOLD
    for k, (_c, _r, card) in enumerate(results):
        ab.cell(row=r + 1, column=2 + k, value=card.total_score).number_format = NUM1
    ab.cell(row=r + 2, column=1, value="Band Excel / Engine").font = BOLD
    for k, (_c, _r, card) in enumerate(results):
        ab.cell(row=r + 2, column=2 + k,
                value=f'=Scorecard!{get_column_letter(4 + 3 * (k + 1))}{srow["band"]}&" / {card.band.value}"')
    ab.cell(row=r + 3, column=1, value="Gesamturteil").font = BOLD
    for k in range(len(results)):
        col = get_column_letter(2 + k)
        ab.cell(row=r + 3, column=2 + k,
                value=f'=IF(COUNTIF({col}{header+1}:{col}{header+len(FACTORS)},"OK*")={len(FACTORS)},'
                      f'IF(ABS({col}{r}-{col}{r+1})<=0.05,"ALLES OK","SCORE WEICHT AB"),"FAKTOR WEICHT AB")'
                ).font = BOLD
        ab.cell(row=r + 3, column=2 + k).fill = GREEN_FILL

    ab.cell(row=r + 5, column=1, value="Einordnung der Engine (nachrichtlich)").font = Font(bold=True, color=NAVY)
    for k, diag in enumerate(diagnostics):
        ab.cell(row=r + 5, column=2 + k, value=diag.verdict.value)
    ab.cell(row=r + 6, column=1, value="Befunde (Regel-IDs)").font = BOLD
    for k, diag in enumerate(diagnostics):
        ab.cell(row=r + 6, column=2 + k,
                value=", ".join(f.rule_id for f in diag.findings) or "keine")
    ab.cell(row=r + 7, column=1, value="Score nach Massnahmen -> Band").font = BOLD
    for k, diag in enumerate(diagnostics):
        sim = diag.simulation
        ab.cell(row=r + 7, column=2 + k,
                value=f"{sim.after_score:.1f} -> {sim.after_band}")
    ab.cell(row=r + 9, column=1,
            value="Diese drei Zeilen kommen aus der Engine und werden hier nicht nachgerechnet -- "
                  "die Simulation prueft man ueber den Bericht.").font = GREY
    ab.column_dimensions["A"].width = 44
    for k in range(len(results)):
        ab.column_dimensions[get_column_letter(2 + k)].width = 24

    # ---------------- Testprotokoll ----------------
    tp = wb.create_sheet("Testprotokoll")
    tp["A1"] = "Testprotokoll / test log"
    tp["A1"].font = TITLE
    tp["A2"] = ("Was jede Zeile genau verlangt, steht in docs/testing/test-plan.md. "
                "Hier nur eintragen: Datum, Ergebnis, offene Punkte.")
    tp["A2"].font = GREY

    heads = ["ID", "Was geprueft wird", "Erwartetes Ergebnis", "Datum",
             "Ergebnis (OK / Abweichung)", "Bemerkung"]
    for c, text in enumerate(heads, start=1):
        tp.cell(row=4, column=c, value=text)
    style_header(tp, 4, len(heads))

    r = 5
    for _area, title, items in TESTS:
        section_row(tp, r, title, "", len(heads))
        r += 1
        for tid, what, expected in items:
            tp.cell(row=r, column=1, value=tid).font = BOLD
            tp.cell(row=r, column=2, value=what)
            tp.cell(row=r, column=3, value=expected)
            for c in (4, 5, 6):
                tp.cell(row=r, column=c).fill = GREEN_FILL
            r += 1

    tp.freeze_panes = "A5"
    for col, width in zip("ABCDEF", (12, 48, 46, 12, 26, 36)):
        tp.column_dimensions[col].width = width

    wb.save(TARGET)
    print(f"{TARGET.relative_to(ROOT)}")
    for case, _r, card in results:
        print(f"  {case.profile.name:34s} {card.total_score:5.1f}  Band {card.band.value}"
              f"  Abdeckung {card.coverage:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
