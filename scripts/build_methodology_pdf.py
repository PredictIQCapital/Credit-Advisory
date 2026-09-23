"""Generate the scoring methodology document and render it to PDF.

Why this is generated and not hand-written: a methodology paper that drifts
from the code it documents is worse than none, because it is used to defend
numbers that the engine no longer produces. Every factor, weight, breakpoint,
band and scenario in the output is read out of the live modules, and the
worked example is a real diagnostic run. Change the scorecard, re-run this,
and the document is correct again.

    pip install playwright && playwright install chromium
    python scripts/build_methodology_pdf.py
"""

from __future__ import annotations

import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from credit_readiness import benchmarks, rejection_risk, sensitivity    # noqa: E402
from credit_readiness.engine import run_diagnostic                      # noqa: E402
from credit_readiness.formatting import de                              # noqa: E402
from credit_readiness.ingest.json_intake import load_case_file          # noqa: E402
from credit_readiness.scorecard import (                                # noqa: E402
    BAND_THRESHOLDS, FACTORS,
)

OUT_DIR = ROOT / "docs" / "methodik"
SOURCE = OUT_DIR / "scoring-methodik.html"
TARGET = OUT_DIR / "Scoring-Methodik.pdf"
EXAMPLE = ROOT / "data" / "samples" / "case_01_mueller_praezisionstechnik.json"

STAND = date.today().strftime("%d.%m.%Y")

FOOTER = f"""
<div style="width:100%;font-size:7pt;color:#8a99a8;
            font-family:'Segoe UI',Arial,sans-serif;padding:0 14mm;
            display:flex;justify-content:space-between;">
  <span>Scoring-Methodik &middot; Credit Readiness Advisory &middot; Stand {STAND}</span>
  <span>Seite <span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>
"""

# Which factors are anchored to published quartiles, and to which series.
CALIBRATED = {
    "eigenkapitalquote": "Eigenmittel / Bilanzsumme",
    "ebit_marge": "Ergebnis vor Steuern / Umsatz",
    "liquiditaet_2_grades": "Liquiditaet 2. Grades",
    "gesamtkapitalrentabilitaet_bbk": "(Jahresergebnis + Zins) / Bilanzsumme",
    "anlagendeckungsgrad_ii": "Langfr. Kapital / Anlagevermoegen",
    "kreditorenlaufzeit_tage": "Verb. aus LuL / Materialaufwand",
}

# Regulatory provenance per factor, shown next to the weight.
HERKUNFT = {
    "eigenkapitalquote": "EBA Anh. 3 Nr. 6; Bundesbank-Modellkennzahl",
    "kapitaldienstfaehigkeit_inkl_neu": "EBA Anh. 3 Nr. 14, 19; MaRisk BTO 1.2.1 Tz. 1",
    "dynamischer_verschuldungsgrad": "EBA Anh. 3 Nr. 10; Bundesbank-Zusatzkennzahl",
    "ebit_marge": "EBA Anh. 3 Nr. 24; Bundesbank-Modellkennzahl",
    "liquiditaet_2_grades": "EBA Anh. 3 Nr. 16; Bundesbank-Modellkennzahl",
    "zinsdeckungsgrad": "EBA Anh. 3 Nr. 21",
    "gesamtkapitalrentabilitaet_bbk": "EBA Anh. 3 Nr. 18",
    "anlagendeckungsgrad_ii": "Goldene Bilanzregel; Bundesbank-Verhaeltniszahl",
    "kreditorenlaufzeit_tage": "Bundesbank-Zusatzkennzahl (Kreditorenziel)",
    "kontokorrent_auslastung": "EBA Tz. 121 d (Inanspruchnahme zugesagter Linien)",
    "bwa_age_months": "EBA Anh. 2 B Nr. 3 (Aktualitaet der Rechnungslegung)",
    "creditreform_bonitaetsindex": "EBA Anh. 2 B Nr. 8, 9 (externe Auskunft/Rating)",
    "zahlungsverhalten": "EBA Tz. 121 d (Zahlungsverhalten, Steuer-/Sozialabgaben)",
}

# EBA/GL/2020/06 Annex 3 B, verbatim, with what we do about each.
EBA_ANHANG3 = [
    ("6", "Equity ratio", "ja", "Eigenkapitalquote (wirtschaftlich), Gewicht 0,16"),
    ("7", "(Long-term) debt-to-equity ratio", "teilweise",
     "Ueber Eigenkapitalquote und dyn. Verschuldungsgrad abgedeckt; "
     "nicht zusaetzlich gewichtet, um Verschuldung nicht dreifach zu zaehlen."),
    ("8", "EBITDA", "ja", "Eingangsgroesse fuer DSCR, Verschuldungsgrad und Marge"),
    ("9", "Debt yield", "nein", "Objektkennzahl der Immobilienfinanzierung"),
    ("10", "Interest bearing debt / EBITDA", "ja", "Dyn. Verschuldungsgrad, Gewicht 0,11"),
    ("11", "Enterprise value", "nein", "Setzt Marktwerte voraus; im Mittelstand nicht verfuegbar"),
    ("12", "Capitalisation rate", "nein", "Objektkennzahl der Immobilienfinanzierung"),
    ("13", "Asset quality", "teilweise", "Ueber Debitoren- und Kreditorenlaufzeit sowie "
     "Anlagendeckung; keine eigene Kennzahl"),
    ("14", "Total debt service coverage ratio", "ja", "Kapitaldienstfaehigkeit, Gewicht 0,20"),
    ("15", "Cash debt coverage ratio", "nein",
     "Setzt eine Kapitalflussrechnung voraus; kleine Gesellschaften erstellen keine"),
    ("16", "Coverage ratio (current assets / short-term debt)", "ja",
     "Liquiditaet 2. Grades, Gewicht 0,07 (strenger als Liquiditaet 3. Grades)"),
    ("17", "Future cash flow analysis", "teilweise",
     "Ueber die Szenariorechnung, nicht ueber eine Planungsrechnung"),
    ("18", "Return on assets", "ja", "Gesamtkapitalrentabilitaet, Gewicht 0,05"),
    ("19", "Debt service", "ja", "Nenner der Kapitaldienstfaehigkeit"),
    ("20", "Loan to cost", "nein", "Projektfinanzierungskennzahl"),
    ("21", "Interest coverage ratio", "ja", "Zinsdeckungsgrad, Gewicht 0,05"),
    ("22", "Return on equity ratio", "nein",
     "Bei duennem oder negativem Buchkapital instabil bis irrefuehrend - "
     "und genau das ist im inhabergefuehrten Mittelstand haeufig"),
    ("23", "Return on capital employed", "teilweise", "Ueber die Gesamtkapitalrentabilitaet"),
    ("24", "Net profit margin", "ja", "EBIT-Marge, Gewicht 0,09"),
    ("25", "Turnover evolution", "teilweise",
     "Wird berechnet und im Bericht ausgewiesen, aber nicht gewichtet: "
     "ein Jahresvergleich traegt keine Gewichtung"),
]

CSS = """
:root{
  --navy:#0d2440; --green:#0b8f73; --green-l:#39b894; --ink:#1a2430;
  --muted:#5b6b7c; --line:#d8e0e8; --bg-soft:#f4f7fa; --amber:#b57500; --red:#a8323a;
}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact; print-color-adjust:exact}
body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;
     color:var(--ink); font-size:9.7pt; line-height:1.5; margin:0}
h1,h2,h3{margin:0; line-height:1.25; color:var(--navy)}
p{margin:0 0 8px}
small{font-size:8.3pt}
.muted{color:var(--muted)}
.cover{background:var(--navy); color:#fff; padding:30mm 16mm 16mm; margin:-14mm -14mm 10mm}
.cover h1{color:#fff; font-size:26pt; letter-spacing:-.4pt; margin-bottom:10px}
.cover .sub{color:#a9c2dc; font-size:12pt; margin-bottom:16px}
.cover .lede{color:#dce7f2; font-size:10.4pt; max-width:150mm}
.logo{display:flex; align-items:center; gap:9px; margin-bottom:24mm}
.logo .bars{display:flex; align-items:flex-end; gap:3px; height:22px}
.logo .bars i{display:block; width:6px; border-radius:2px}
.logo .bars i:nth-child(1){height:9px;  background:#6fd3b7}
.logo .bars i:nth-child(2){height:15px; background:#39b894}
.logo .bars i:nth-child(3){height:22px; background:#0b8f73}
.logo span{color:#fff; font-weight:600; font-size:12pt}
.factbar{display:flex; border-top:1px solid rgba(255,255,255,.22);
         padding-top:12px; margin-top:22px}
.factbar div{flex:1; padding-right:10px}
.factbar b{display:block; color:#6fd3b7; font-size:13pt; line-height:1.2}
.factbar small{color:#a9c2dc}
.eyebrow{display:inline-block; font-size:7.6pt; font-weight:700; letter-spacing:1.1pt;
         text-transform:uppercase; color:var(--green); margin-bottom:5px}
h2{font-size:15pt; margin-bottom:4px; padding-bottom:5px; border-bottom:2px solid var(--green)}
h2 .n{color:var(--green-l); font-weight:700; margin-right:7px}
h3{font-size:10.6pt; margin:13px 0 5px}
section{margin-bottom:13px}
.lead{font-size:10.2pt; color:var(--muted); margin:8px 0 12px}
table{width:100%; border-collapse:collapse; margin:8px 0 10px; font-size:8.5pt}
th{text-align:left; background:var(--navy); color:#fff; font-weight:600;
   padding:5px 7px; font-size:8pt}
td{padding:5px 7px; border-bottom:1px solid var(--line); vertical-align:top}
tr:nth-child(even) td{background:var(--bg-soft)}
tr{page-break-inside:avoid}
thead{display:table-header-group}
table.thresholds td{padding:4px 7px}
td.num,th.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
code{font-family:"Cascadia Mono",Consolas,monospace; font-size:8.2pt;
     background:var(--bg-soft); padding:1px 3px; border-radius:2px}
th code{background:rgba(255,255,255,.16); color:#fff}
.note{background:var(--bg-soft); border-left:3px solid var(--green);
      padding:8px 11px; margin:10px 0; page-break-inside:avoid}
.note.warn{border-left-color:var(--amber)}
.note.stop{border-left-color:var(--red)}
.note b{color:var(--navy)}
.tag{display:inline-block; font-size:7.4pt; font-weight:700; padding:1px 5px;
     border-radius:3px; letter-spacing:.3pt}
.tag.cal{background:#d9f0e9; color:#0b6b57}
.tag.con{background:#f2e6cc; color:#8a5a00}
.tag.yes{background:#d9f0e9; color:#0b6b57}
.tag.part{background:#f2e6cc; color:#8a5a00}
.tag.no{background:#eceff2; color:#5b6b7c}
.band{display:inline-block; width:17px; height:17px; line-height:17px; text-align:center;
      border-radius:3px; color:#fff; font-weight:700; font-size:8.4pt}
.band.A{background:#0b8f73} .band.B{background:#39b894} .band.C{background:#b57500}
.band.D{background:#c2564e} .band.E{background:#a8323a}
.pagebreak{page-break-before:always}
ul{margin:4px 0 8px; padding-left:17px}
li{margin-bottom:3px}
.kv{display:flex; gap:14px; flex-wrap:wrap; margin:8px 0}
.kv div{flex:1; min-width:52mm; background:var(--bg-soft); padding:8px 10px;
        border-top:2px solid var(--green-l)}
.kv b{display:block; font-size:12.5pt; color:var(--navy)}
"""


def _fmt_x(unit: str, value: float) -> str:
    if unit == "percent":
        return f"{de(value * 100, 1)}%"
    if unit == "x":
        return f"{de(value, 2)}x"
    if unit in ("days", "months"):
        return de(value, 1)
    return de(value, 0)


def breakpoint_rows(factor) -> str:
    pts = " &nbsp;&rarr;&nbsp; ".join(
        f"<code>{_fmt_x(factor.unit, x)}</code> = {de(y, 0)}" for x, y in factor.breakpoints
    )
    return pts


def factor_table() -> str:
    rows = []
    for f in FACTORS:
        tag = ('<span class="tag cal">kalibriert</span>' if f.key in CALIBRATED
               else '<span class="tag con">Konvention</span>')
        rows.append(
            f"<tr><td><b>{escape(f.label)}</b><br><small class='muted'>"
            f"<code>{f.key}</code></small></td>"
            f"<td class='num'>{de(f.weight * 100, 0)}%</td>"
            f"<td>{tag}</td>"
            f"<td><small>{escape(HERKUNFT.get(f.key, ''))}</small></td></tr>"
        )
    return (
        "<table><thead><tr><th>Faktor</th><th class='num'>Gewicht</th>"
        "<th>Art</th><th>Regulatorische Herkunft</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table>"
    )


def threshold_table() -> str:
    rows = []
    for f in FACTORS:
        src = CALIBRATED.get(f.key)
        prov = (f"<small class='muted'>Bundesbank: {escape(src)}</small>" if src
                else "<small class='muted'>Konvention</small>")
        rows.append(
            f"<tr><td><b>{escape(f.label)}</b><br>{prov}</td>"
            f"<td>{breakpoint_rows(f)}</td></tr>"
        )
    return ("<table class='thresholds'><thead><tr><th style='width:48mm'>Faktor</th>"
            "<th>Stuetzstellen (Kennzahlenwert = Punkte, linear interpoliert)</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def band_table() -> str:
    rows = []
    ordered = sorted(BAND_THRESHOLDS, key=lambda t: -t[0])
    for i, (threshold, band) in enumerate(ordered):
        upper = "100,0" if i == 0 else de(ordered[i - 1][0], 1)
        rows.append(
            f"<tr><td><span class='band {band.value}'>{band.value}</span></td>"
            f"<td class='num'>{de(threshold, 1)} &ndash; {upper}</td>"
            f"<td>{escape(band.interpretation)}</td></tr>"
        )
    return ("<table><thead><tr><th style='width:14mm'>Stufe</th>"
            "<th class='num' style='width:26mm'>Punkte</th><th>Bedeutung</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def eba_table() -> str:
    tags = {"ja": "yes", "teilweise": "part", "nein": "no"}
    rows = []
    for nr, name, status, comment in EBA_ANHANG3:
        rows.append(
            f"<tr><td class='num'>{nr}</td><td>{escape(name)}</td>"
            f"<td><span class='tag {tags[status]}'>{status}</span></td>"
            f"<td><small>{escape(comment)}</small></td></tr>"
        )
    return ("<table><thead><tr><th class='num' style='width:9mm'>Nr.</th>"
            "<th style='width:46mm'>Kennzahl laut EBA Anhang 3 B</th>"
            "<th style='width:17mm'>Abgedeckt</th><th>Umsetzung</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def knockout_table() -> str:
    rows = []
    for code, title, condition, source in rejection_risk.CHECK_CATALOGUE:
        rows.append(f"<tr><td class='num'>{code}</td><td><b>{escape(title)}</b></td>"
                    f"<td><small>{escape(condition)}</small></td>"
                    f"<td><small>{escape(source)}</small></td></tr>")
    return ("<table><thead><tr><th class='num' style='width:13mm'>Code</th>"
            "<th style='width:44mm'>Kriterium</th><th style='width:48mm'>Bedingung</th>"
            "<th>Grundlage</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def scenario_table() -> str:
    rows = []
    for key, label, assumption, _ in sensitivity.SCENARIOS:
        rows.append(f"<tr><td><b>{escape(label)}</b></td>"
                    f"<td><small>{escape(assumption)}</small></td></tr>")
    return ("<table><thead><tr><th style='width:52mm'>Szenario</th>"
            "<th>Annahme und Fundstelle</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def worked_example() -> tuple[str, str]:
    """A real diagnostic run, printed factor by factor."""
    result = run_diagnostic(load_case_file(EXAMPLE))
    card = result.scorecard

    rows = []
    for f in card.factors:
        if f.score is None:
            rows.append(f"<tr><td>{escape(f.label)}</td><td class='num'>n/a</td>"
                        f"<td class='num'>&ndash;</td><td class='num'>&ndash;</td>"
                        f"<td class='num'>0,00</td>"
                        f"<td><small>{escape(f.missing_reason)}</small></td></tr>")
            continue
        rows.append(
            f"<tr><td>{escape(f.label)}</td>"
            f"<td class='num'>{escape(f.format_value())}</td>"
            f"<td class='num'>{de(f.score, 1)}</td>"
            f"<td class='num'>{de(f.weight * 100, 0)}%</td>"
            f"<td class='num'><b>{de(f.contribution, 2)}</b></td><td></td></tr>"
        )
    rows.append(
        f"<tr><td colspan='4'><b>Gesamtergebnis</b></td>"
        f"<td class='num'><b>{de(card.total_score, 1)}</b></td>"
        f"<td><span class='band {card.band.value}'>{card.band.value}</span></td></tr>"
    )
    table = ("<table><thead><tr><th>Faktor</th><th class='num'>Wert</th>"
             "<th class='num'>Punkte</th><th class='num'>Gewicht</th>"
             "<th class='num'>Beitrag</th><th></th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>")

    sens = result.sensitivity
    srows = [f"<tr><td>Ausgangslage</td><td class='num'>{de(sens.base_score, 1)}</td>"
             f"<td><span class='band {sens.base_band.value}'>{sens.base_band.value}</span></td>"
             f"<td class='num'>&ndash;</td></tr>"]
    for sc in sens.scenarios:
        srows.append(f"<tr><td>{escape(sc.label)}</td><td class='num'>{de(sc.score, 1)}</td>"
                     f"<td><span class='band {sc.band.value}'>{sc.band.value}</span></td>"
                     f"<td class='num'>{de(sc.delta, 1)}</td></tr>")
    stable = ("<table><thead><tr><th>Szenario</th><th class='num'>Punkte</th>"
              "<th>Stufe</th><th class='num'>Delta</th></tr></thead><tbody>"
              + "".join(srows) + "</tbody></table>")
    return table, stable


def build_html() -> str:
    example, example_sens = worked_example()
    n_cal = len(CALIBRATED)
    cal_weight = sum(f.weight for f in FACTORS if f.key in CALIBRATED)

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Scoring-Methodik &mdash; Credit Readiness Advisory</title>
<style>{CSS}</style>
</head>
<body>

<div class="cover">
  <div class="logo"><div class="bars"><i></i><i></i><i></i></div>
    <span>Credit Readiness Advisory</span></div>
  <h1>Scoring-Methodik</h1>
  <div class="sub">Kennzahlen, Gewichte, Schwellenwerte und Szenariorechnung</div>
  <div class="lede">Dieses Dokument beschreibt vollstaendig, wie die
    Bereitschaftsstufe eines Unternehmens zustande kommt: welche Kennzahlen
    eingehen, woher jeder einzelne Schwellenwert stammt und was bewusst nicht
    modelliert wird. Es ist so geschrieben, dass ein Steuerberater oder ein
    Kreditanalyst jeden Wert nachrechnen und jeder Annahme widersprechen kann.</div>
  <div class="factbar">
    <div><b>{len(FACTORS)}</b><small>gewichtete Faktoren</small></div>
    <div><b>{n_cal}</b><small>davon empirisch kalibriert</small></div>
    <div><b>{de(cal_weight * 100, 0)}%</b><small>kalibriertes Gewicht</small></div>
    <div><b>3</b><small>Stressszenarien</small></div>
    <div><b>{len(rejection_risk.CHECK_CATALOGUE)}</b><small>Ausschlusskriterien</small></div>
  </div>
</div>

<section>
  <span class="eyebrow">Abschnitt 1</span>
  <h2><span class="n">01</span>Zweck und Abgrenzung</h2>
  <p>Das Verfahren erzeugt eine <b>indikative Bereitschaftsstufe</b> (A bis E).
  Sie beschreibt, wie ein Kreditantrag mit dieser Datenlage bei einem typischen
  Kreditgeber voraussichtlich gelesen wird &ndash; und was daran veraenderbar ist.</p>
  <div class="note stop">
    <b>Was dies ausdruecklich nicht ist.</b> Kein Rating im Sinne der
    EU-Ratingverordnung (EG) Nr. 1060/2009, keine Ausfallwahrscheinlichkeit,
    keine Kreditentscheidung und keine Zusage. Es wird keine PD geschaetzt und
    keine ausgegeben. Jede Kreditentscheidung trifft ausschliesslich der
    jeweilige Kreditgeber nach eigenen Massstaeben.
  </div>
  <p>Drei Konstruktionsregeln folgen daraus und sind im Code durchgesetzt, nicht
  nur hier behauptet:</p>
  <ul>
    <li><b>Nachvollziehbarkeit.</b> Jeder Faktor gibt seinen Rohwert, seine
    Stuetzstellen, sein Gewicht und seinen Punktbeitrag aus. Es gibt keine
    Groesse, die nicht zeilenweise erklaerbar ist.</li>
    <li><b>Kein maschinelles Lernen.</b> Ausschliesslich stueckweise lineare
    Interpolation ueber offengelegte Schwellenwerte.</li>
    <li><b>Keine Ratingsprache.</b> Die Begriffe sind &bdquo;Stufe&ldquo; und
    &bdquo;indikativ&ldquo;.</li>
  </ul>
</section>

<section>
  <span class="eyebrow">Abschnitt 2</span>
  <h2><span class="n">02</span>Regulatorische Grundlage</h2>
  <p>Die Auswahl der Kennzahlen stammt nicht aus dem Lehrbuch, sondern aus drei
  Quellen, die beschreiben, was Kreditgeber im Euroraum tatsaechlich pruefen
  muessen beziehungsweise pruefen:</p>
  <table>
    <thead><tr><th style="width:52mm">Quelle</th><th>Was daraus uebernommen ist</th></tr></thead>
    <tbody>
      <tr><td><b>EBA/GL/2020/06</b><br><small class="muted">Leitlinien fuer die
        Kreditvergabe und Ueberwachung, gueltig seit 30.06.2021</small></td>
        <td>Anhang 3 Abschnitt B nennt die Kennzahlen, die ein Institut bei
        Unternehmenskrediten beruecksichtigen soll (Abschnitt 3). Tz. 121 und
        128 regeln, was in die Analyse der Finanzlage gehoert; Tz. 120 stellt
        klar, dass Sicherheiten <i>kein</i> vorrangiges Kriterium sein duerfen;
        Tz. 131 und 156&ndash;158 verlangen die Szenariorechnung.</td></tr>
      <tr><td><b>MaRisk (BaFin)</b><br><small class="muted">Rundschreiben 10/2021,
        Anlage 1, BTO 1.2</small></td>
        <td>BTO 1.2.1 Tz. 1 verlangt die Analyse der Risikofaktoren
        &bdquo;unter besonderer Beruecksichtigung der Kapitaldienstfaehigkeit&ldquo;
        &ndash; daher traegt die Kapitaldienstfaehigkeit hier das groesste
        Einzelgewicht. BTO 1.4 Tz. 3 verlangt qualitative neben quantitativen
        Kriterien.</td></tr>
      <tr><td><b>Bundesbank-Bonitaetsanalyse (ICAS)</b><br>
        <small class="muted">Beschreibung des Verfahrens, Stand Dezember 2023</small></td>
        <td>Die Kennzahlen, mit denen eine Zentralbank aus HGB-Abschluessen die
        Bonitaet deutscher Unternehmen einschaetzt: EBITDA, Gesamtverschuldung
        (bereinigt), Liquiditaet, Umsatzrendite, Entschuldungsfaehigkeit,
        bereinigte Eigenmittelquote und Kreditorenziel. Ausserdem die
        empirischen Verteilungen (Abschnitt 6) und die Methodik der
        Szenariorechnung (Abschnitt 8).</td></tr>
    </tbody>
  </table>
  <div class="note warn">
    <b>Der wichtigste Befund aus der Auswertung dieser Quellen:
    Schwellenwerte gibt keine von ihnen vor.</b>
    EBA Anhang 1 verlangt vom Institut, &bdquo;acceptable ... ratio limits&ldquo;
    <i>festzulegen</i>, nennt aber keine Zahlen. MaRisk regelt den Prozess, nicht
    die Kennzahlenhoehe. Die Aufsicht bestimmt also <i>welche</i> Kennzahlen und
    <i>dass</i> Grenzen existieren muessen &ndash; die Hoehe ist eine eigene,
    begruendungspflichtige Entscheidung. Genau deshalb sind in diesem Dokument
    Kennzahlenauswahl (Abschnitt 3) und Schwellenwerte (Abschnitte 5 und 6)
    getrennt dargestellt und getrennt belegt.
  </div>
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 3</span>
  <h2><span class="n">03</span>Abgleich mit EBA Anhang 3</h2>
  <p>Anhang 3 Abschnitt B der EBA-Leitlinien listet zwanzig Kennzahlen fuer
  Kredite an Unternehmen. Die Leitlinie verlangt, sie zu beruecksichtigen
  &bdquo;to an extent that is applicable and appropriate to the specific credit
  proposal&ldquo; (Tz. 128 e). Die folgende Tabelle sagt fuer jede einzelne, was
  damit geschieht &ndash; einschliesslich der Faelle, in denen bewusst nichts
  geschieht.</p>
  {eba_table()}
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 4</span>
  <h2><span class="n">04</span>Faktoren und Gewichte</h2>
  <p>Die Gewichte summieren sich auf 100%. Faellt ein Faktor mangels Daten aus,
  werden die verbleibenden Gewichte proportional hochgerechnet; der Bericht
  weist die erreichte Abdeckung aus. Eine duenne Akte wird dadurch nicht
  bestraft &ndash; sie wird als duenn gekennzeichnet.</p>
  {factor_table()}
  <div class="note">
    <b>Eine Ausnahme von der Umverteilung.</b> Ist das EBITDA null oder negativ,
    ist der dynamische Verschuldungsgrad rechnerisch nicht definiert. Der Faktor
    wird dann nicht weggelassen, sondern mit null Punkten bewertet: ein
    Unternehmen ohne operativen Ueberschuss kann seine Schulden nicht aus dem
    Geschaeft zurueckfuehren, und ein Weglassen wuerde genau den Fall
    schoenrechnen, auf den es ankommt.
  </div>
  <div class="note">
    <b>Warum Sicherheiten nicht bewertet werden.</b> EBA Tz. 120: Sicherheiten
    sind der zweite Ausweg, nicht die primaere Rueckzahlungsquelle, und duerfen
    eine Kreditvergabe nicht fuer sich rechtfertigen. Eine Besicherungsluecke
    erscheint deshalb als Befund und Massnahme im Bericht, aber nicht als
    punktewirksamer Faktor.
  </div>
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 5</span>
  <h2><span class="n">05</span>Schwellenwerte im Einzelnen</h2>
  <p>Zwischen zwei Stuetzstellen wird linear interpoliert, ausserhalb wird
  gekappt. Damit ist jeder Punktwert von Hand nachrechenbar &ndash; das ist der
  Grund fuer diese Konstruktion und nicht ein Nebeneffekt.</p>
  {threshold_table()}
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 6</span>
  <h2><span class="n">06</span>Woher die Schwellenwerte stammen</h2>
  <h3>Kalibrierte Faktoren</h3>
  <p>Sechs der {len(FACTORS)} Faktoren &ndash; zusammen
  {de(cal_weight * 100, 0)}% des Gewichts &ndash; sind an die
  <b>Quartilswerte der Jahresabschlussstatistik der Deutschen Bundesbank</b>
  (Verhaeltniszahlen) gebunden: alle Branchen, die Umsatzgroessenklassen
  2&ndash;10 Mio. und 10&ndash;50 Mio. EUR im Mittel, juengstes Berichtsjahr.
  Datenstand: {escape(benchmarks.VINTAGE)}.</p>
  <p>Die Verankerung lautet:</p>
  <div class="kv">
    <div><b>25. Perzentil</b><small>= 58 Punkte (Untergrenze Stufe C)</small></div>
    <div><b>Median</b><small>= 70 Punkte (Mitte Stufe B)</small></div>
    <div><b>75. Perzentil</b><small>= 82 Punkte (Stufe A)</small></div>
  </div>
  <p>Die Begruendung ist einen Schritt lang: die EZB-Unternehmensbefragung SAFE
  weist rund 14% der Antragsteller als in erheblichen Finanzierungsschwierigkeiten
  aus. Ein Unternehmen im Median seiner Groessenklasse gehoert also nicht zu den
  Problemfaellen, sondern ist finanzierbar &ndash; Stufe B. Eine reine
  Perzentilabbildung wuerde den Medianbetrieb auf 50 Punkte setzen und damit
  behaupten, die Haelfte des deutschen Mittelstands sei ein Grenzfall. Das waere
  empirisch falsch.</p>
  <div class="note">
    <b>Bei &bdquo;je niedriger, desto besser&ldquo; drehen sich die Anker um.</b>
    Fuer die Kreditorenlaufzeit ist das 25. Perzentil das gute Ende; die
    Zuordnung lautet dort 25. Perzentil = 82, Median = 70, 75. Perzentil = 58.
    Diese Kurve ist ausserdem die einzige, die bei 82 Punkten gedeckelt ist:
    schnelles Bezahlen ist kein Bonitaetsbeleg, sondern nur das Fehlen eines
    Warnsignals.
  </div>
  <p><b>Enden jenseits der Quartile.</b> Die Statistik liefert drei Punkte, keine
  Verteilung. Die Kurvenenden sind daher nicht extrapoliert, sondern auf
  wirtschaftlich bedeutsame Grenzen gezogen &ndash; Eigenkapital null, Marge
  negativ, Anlagendeckung unter 100%.</p>

  <h3>Nicht kalibrierte Faktoren</h3>
  <p>Fuer die uebrigen Faktoren enthaelt die Publikation keine vergleichbare
  Reihe. Ihre Kurven sind begruendete Konvention und als solche gekennzeichnet:
  Kapitaldienstfaehigkeit, dynamischer Verschuldungsgrad, Zinsdeckungsgrad,
  Kontokorrent-Auslastung, Aktualitaet der BWA, Creditreform-Index und
  Zahlungsverhalten.</p>
  <div class="note warn">
    <b>Eine Uebersetzung, die bewusst unterbleibt.</b> Die Bundesbank
    veroeffentlicht &bdquo;Cashflow in % der Nettofremdmittel&ldquo;. Das ist
    <i>nicht</i> unser dynamischer Verschuldungsgrad: anderer Zaehler (Cashflow
    nach Zins und Steuern statt EBITDA) und ein weit breiterer Nenner
    (saemtliche Verbindlichkeiten statt nur der Finanzschulden). Eine Umrechnung
    waere eine als Kalibrierung verkleidete Schaetzung. Der Faktor bleibt daher
    Konvention &ndash; und ist der erste Kandidat fuer eine Revision, sobald das
    Ergebnisprotokoll genug echte Platzierungen enthaelt.
  </div>
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 7</span>
  <h2><span class="n">07</span>Von Punkten zu Stufen</h2>
  {band_table()}
  <div class="note warn">
    <b>Die Stufengrenzen selbst sind nicht empirisch hergeleitet.</b> Sie sind
    so gesetzt, dass der Medianbetrieb in Stufe B und das untere Quartil in
    Stufe C liegt &ndash; also aus derselben SAFE-Ueberlegung wie die
    Faktorenanker, nicht aus beobachteten Ablehnungsquoten. Wer diese Zuordnung
    angreift, greift zu Recht die schwaechste Stelle des Verfahrens an. Sie
    aendert sich, sobald genug dokumentierte Kreditentscheidungen vorliegen.
  </div>
</section>

<section>
  <span class="eyebrow">Abschnitt 8</span>
  <h2><span class="n">08</span>Szenariorechnung</h2>
  <p>Eine Stichtagskennzahl aus dem Vorjahresabschluss beantwortet die falsche
  Frage. Der Kreditgeber will nicht wissen, wie das Unternehmen am 31. Dezember
  aussah, sondern ob es den Kapitaldienst auch dann noch traegt, wenn es
  schlechter laeuft. Beide Aufsichtsquellen verlangen das ausdruecklich
  (EBA Tz. 131 und 156&ndash;158, MaRisk BTO 1.2.1 Tz. 1).</p>
  {scenario_table()}
  <h3>Wie der Schock durch den Abschluss gerechnet wird</h3>
  <p>Der Mechanismus folgt dem veroeffentlichten Vorgehen der Deutschen
  Bundesbank zur Stressrechnung im eigenen Bonitaetsanalysesystem
  (Technical Paper 02/2023, Abschnitt 5.2). Dort wird eine Kostenposition
  gestresst; die Verrechnung ist unabhaengig davon, welcher Schock es ist:</p>
  <ul>
    <li>Mehrkosten beziehungsweise Deckungsbeitragsverlust ermitteln;</li>
    <li>Finanzierung zuerst aus liquiden Mitteln, danach ueber eine kurzfristige
      Bankverbindlichkeit;</li>
    <li>Zinsaufwand auf die neue Inanspruchnahme zum bisherigen Durchschnittssatz
      erhoehen, weil die Zinslast selbst bonitaetsrelevant ist;</li>
    <li>Steueraufwand mit dem unternehmenseigenen effektiven Satz mindern
      (nie unter null);</li>
    <li>vermindertes Ergebnis ins Eigenkapital durchbuchen;</li>
    <li>saemtliche Kennzahlen auf dem gestressten Abschluss neu rechnen.</li>
  </ul>
  <div class="note">
    <b>Der Zinsschock trifft die Kreditvertraege, nicht nur die GuV.</b>
    Tz. 158 k spricht von einer Erhoehung &bdquo;on all credit facilities of the
    borrower&ldquo;. Verteuert wuerde nur die Zinszeile, bliebe der Kapitaldienst
    &ndash; und damit die Kapitaldienstfaehigkeit, die entscheidende Kennzahl
    &ndash; unveraendert. Deshalb wird der Zinssatz jedes einzelnen Darlehens
    erhoeht.
  </div>
  <div class="note warn">
    <b>Was die Szenariorechnung nicht ist.</b> Keine Prognose und keine
    Wahrscheinlichkeitsaussage. Sie sagt: unter diesen benannten Annahmen
    verschiebt sich die Stufe von X nach Y. Die Annahmen stehen im Bericht neben
    dem Ergebnis, damit der Unternehmer ihnen widersprechen kann &ndash; er kennt
    seinen variablen Kostenanteil besser als wir.
  </div>
</section>

<section>
  <span class="eyebrow">Abschnitt 9</span>
  <h2><span class="n">09</span>Ausschlusskriterien</h2>
  <p>Eine gewichtete Punktzahl beantwortet die Frage, wie sich eine Akte
  insgesamt liest. Sie kann nicht beantworten, ob darin etwas steht, das das
  Gespraech unabhaengig vom Gesamtergebnis beendet &ndash; ein gewichteter
  Mittelwert laesst einen starken Faktor einen fatalen ausgleichen. Das sind
  zwei verschiedene Fragen und sie brauchen zwei verschiedene Verfahren.</p>
  <p>Diese {len(rejection_risk.CHECK_CATALOGUE)} Kriterien werden deshalb getrennt geprueft und getrennt
  berichtet, vor den Kennzahlen. Keiner der Schwellenwerte stammt von uns:</p>
  {knockout_table()}
  <div class="note stop">
    <b>Diese Pruefung ist keine rechtliche Beurteilung.</b> Ob sich aus einem
    Befund Pflichten ergeben &ndash; etwa nach 49 Abs. 3 GmbHG oder 15a InsO
    &ndash; haengt an einer Fortfuehrungsprognose, die dieses Verfahren nicht
    leisten kann und nicht zu leisten vorgibt. Der Bericht benennt den Zustand
    und verweist die Bewertung an den Steuerberater oder einen Rechtsanwalt.
  </div>
  <div class="note">
    <b>Warum ein sauberes Ergebnis eine eigene Aussage ist.</b> &bdquo;Keines
    dieser Kriterien liegt vor&ldquo; ist nicht dasselbe wie eine gute
    Bewertung. Es bedeutet, dass ueber Konditionen ueberhaupt gesprochen werden
    kann &ndash; und genau das ist die Information, die ein Unternehmer vor der
    Antragstellung braucht.
  </div>
</section>

<section class="pagebreak">
  <span class="eyebrow">Abschnitt 10</span>
  <h2><span class="n">10</span>Rechenweg an einem Beispiel</h2>
  <p>Vollstaendiger Durchlauf am fiktiven Musterfall Mueller Praezisionstechnik
  GmbH. Alle Werte sind aus dem laufenden System erzeugt, nicht abgeschrieben.</p>
  {example}
  <p>Die Szenariorechnung zum selben Fall:</p>
  {example_sens}
  <p>Die Lesart: der Betrieb ist zum Stichtag finanzierbar (Stufe B), haelt aber
  einen Umsatzrueckgang von 10% nicht aus, weil die Kapitaldienstfaehigkeit dann
  unter 1,0 faellt. Das ist die Information, die im Kreditgespraech ohnehin
  auftaucht &ndash; nur eben ohne Vorbereitung.</p>
</section>

<section>
  <span class="eyebrow">Abschnitt 11</span>
  <h2><span class="n">11</span>Grenzen des Verfahrens</h2>
  <p>Vollstaendige Aufzaehlung dessen, was dieses Verfahren nicht kann. Sie
  gehoert in dieses Dokument, weil eine Methodenbeschreibung ohne
  Schwaechenliste als Verkaufsunterlage taugt und sonst zu nichts.</p>
  <ul>
    <li><b>Keine Ausfallvalidierung.</b> Die Gewichte und Stufengrenzen sind an
    Verteilungen und an Fachurteil verankert, nicht an beobachteten Ausfaellen.
    Es gibt bislang keine Ergebnisdaten, gegen die sich das Verfahren
    zurueckrechnen liesse.</li>
    <li><b>Datenstand der Vergleichswerte.</b> {escape(benchmarks.VINTAGE)}.
    {escape(benchmarks.CAVEAT)}</li>
    <li><b>Qualitative Faktoren fehlen weitgehend.</b> MaRisk BTO 1.4 Tz. 3
    verlangt qualitative Kriterien. Abgedeckt sind nur Aktualitaet der
    Rechnungslegung, externe Auskunft und Zahlungsverhalten. Managementqualitaet,
    Marktstellung, Kunden- und Lieferantenabhaengigkeit (EBA Tz. 132&ndash;136)
    gehen nicht in die Punktzahl ein; sie erscheinen als Befund.</li>
    <li><b>Keine ESG-Bewertung.</b> EBA Tz. 126&ndash;127 verlangt die Beurteilung
    von ESG-Risiken. Das Verfahren leistet das derzeit nicht.</li>
    <li><b>Keine Planungsrechnung.</b> EBA Tz. 129 erwartet Finanzprojektionen.
    Bewertet wird der letzte Abschluss zuzueglich Szenarien; eine fehlende
    integrierte Planung wird als Befund ausgewiesen, nicht ersetzt.</li>
    <li><b>Branchenunterscheidung nur im Vergleich.</b> Die Schwellenwerte gelten
    branchenuebergreifend; nur der Branchenvergleich im Bericht ist
    branchenspezifisch. Die Bundesbank waehlt ihre Modellkennzahlen dagegen je
    Branche neu aus.</li>
    <li><b>Ein Faktor kann ausfallen.</b> Dienstleister ohne Materialaufwand
    haben keine Kreditorenlaufzeit; das Gewicht wird dann umverteilt und die
    Abdeckung sinkt entsprechend.</li>
  </ul>
</section>

<section>
  <span class="eyebrow">Abschnitt 12</span>
  <h2><span class="n">12</span>Aenderungen dieser Fassung</h2>
  <p>Ergebnis der Auswertung der EBA-Leitlinien, der MaRisk-Erlaeuterungen und
  der Bundesbank-Veroeffentlichungen:</p>
  <ul>
    <li><b>Drei Faktoren neu aufgenommen</b>, alle drei empirisch kalibriert:
    Gesamtkapitalrentabilitaet (EBA Anhang 3 Nr. 18), Anlagendeckungsgrad II und
    Kreditorenlaufzeit (beide Bundesbank-Verhaeltniszahlen). Der kalibrierte
    Gewichtsanteil steigt damit von 40% auf {de(cal_weight * 100, 0)}%.</li>
    <li><b>Gewichte neu austariert</b>, damit die Summe 100% bleibt. Die
    Kapitaldienstfaehigkeit bleibt unveraendert bei 20% und damit das groesste
    Einzelgewicht &ndash; MaRisk BTO 1.2.1 Tz. 1.</li>
    <li><b>Szenariorechnung neu eingefuehrt</b> (Abschnitt 8). Das war die
    groesste Luecke gegenueber den Leitlinien: gefordert in Tz. 131 und
    156&ndash;158, bisher gar nicht abgebildet.</li>
    <li><b>Gesamtkapitalrentabilitaet in der Bundesbank-Definition</b>
    (Jahresergebnis zuzueglich Zinsaufwand) statt auf EBIT-Basis, damit die
    veroeffentlichten Quartile ohne Umrechnung gelten. Beide Varianten werden
    berechnet; bewertet wird die uebernommene.</li>
    <li><b>Zwei bisher ungenutzte Bundesbank-Reihen</b> in den Datensatz
    aufgenommen, den die Anwendung zur Laufzeit laedt.</li>
    <li><b>Ausschlusskriterien neu eingefuehrt</b> (Abschnitt 9). Auswertung der
    EBA-Benchmarking-Berichte, des Rating-Leitfadens der Banque de France und
    der Ausfalldefinition nach Artikel 178 CRR. Die Punktzahl allein kann
    K.-o.-Befunde nicht abbilden, weil ein gewichteter Mittelwert sie
    ausgleicht.</li>
    <li><b>Kontokorrent-Ueberziehung heraufgestuft.</b> Bisher eine blosse
    Warnung in der Plausibilitaetspruefung. Nach Artikel 178 CRR gilt ein
    Kontokorrent als ueberfaellig, sobald die eingeraeumte Linie ueberschritten
    ist &ndash; das ist ein Ausfallmerkmal, keine Auffaelligkeit.</li>
    <li><b>Szenariogroessen an der Aufsicht verankert.</b> Der Umsatzrueckgang
    von 10% war bisher gesetzt; er steht jetzt neben dem adversen Szenario des
    EU-weiten Stresstests 2025, das fuer Deutschland ein kumuliert 7,5%
    niedrigeres BIP unterstellt. Umgekehrt zeigt derselbe Vergleich, dass
    unser Zinsschock von 200 Basispunkten fast doppelt so hart ist wie die
    dort unterstellten rund 110 Basispunkte.</li>
  </ul>
  <div class="note">
    <b>Dieses Dokument wird erzeugt, nicht gepflegt.</b> Saemtliche Faktoren,
    Gewichte, Stuetzstellen, Stufengrenzen, Szenarien und das Rechenbeispiel
    werden bei jedem Lauf aus den produktiven Modulen gelesen
    (<code>scripts/build_methodology_pdf.py</code>). Eine Abweichung zwischen
    diesem Papier und der Anwendung kann es nicht geben.
  </div>
</section>

</body>
</html>
"""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE.write_text(build_html(), encoding="utf-8")
    print(f"{SOURCE.relative_to(ROOT)}  ({SOURCE.stat().st_size // 1024} KB)")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && playwright install chromium")
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(SOURCE.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(TARGET),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=FOOTER,
            margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()

    print(f"{TARGET.relative_to(ROOT)}  ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
