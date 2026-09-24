"""The bank pack: what a company hands its bank, as one PDF.

WHO READS IT
============
A credit officer at a Sparkasse or Volksbank, reading a first request. So it
is in German, it leads with the request and the company, and it shows figures
before judgements. The readiness band appears once, with its source (reviewed
report or automatic quick check) and the note that it is not a rating: the
company may show its own assessment to its bank, but nothing in the document
may read as a third-party credit rating (EU CRA Regulation, see
docs/regulatory-guardrails.md). The disclaimer is on every page.

The company chooses the sections. The improvement plan is off by default: it
lists weaknesses, and whether to show them is the company's call.

Everything is inline -- styles, charts (SVG), the logo (data URI) -- so the
same HTML prints identically in headless Chrome (reporting/pdf.py) and in any
browser as a fallback.
"""

from __future__ import annotations

import base64
from datetime import date
from html import escape
from typing import Optional

from ..engine import DISCLAIMER, DiagnosticResult
from ..formatting import de

SECTIONS: tuple[tuple[str, str, bool], ...] = (
    ("unternehmen", "Unternehmen", True),
    ("vorhaben", "Finanzierungsvorhaben", True),
    ("zahlen", "Finanzzahlen", True),
    ("kennzahlen", "Kennzahlen und Branchenvergleich", True),
    ("band", "Readiness-Band", True),
    ("fortschreibung", "Kapitaldienstfaehigkeit: Fortschreibung", True),
    ("massnahmen", "Massnahmenplan", False),
    ("unterlagen", "Unterlagenverzeichnis", True),
)
SECTION_IDS = tuple(s[0] for s in SECTIONS)
DEFAULT_SECTIONS = tuple(s[0] for s in SECTIONS if s[2])

GOOD, WARN, BAD, NAVY, MUTED, LINE, IQR = "#0b8f73", "#c98a00", "#b3261e", "#0d2440", "#5d6779", "#e2e6ec", "#d6efe7"
BAND_COLOR = {"A": GOOD, "B": GOOD, "C": WARN, "D": BAD, "E": BAD}

_e = escape


def _eur(v: Optional[float]) -> str:
    return "–" if v is None else f"{de(v)} EUR"


def _pct(v: Optional[float]) -> str:
    return "–" if v is None else f"{de(v * 100, 1)} %"


def _x(v: Optional[float]) -> str:
    return "–" if v is None else f"{de(v, 2)}x"


# ------------------------------------------------------------------ charts


def gauge_svg(band: str, score: float) -> str:
    import math
    r, c = 50, 2 * math.pi * 50
    frac = max(0.02, min(1.0, score / 100))
    col = BAND_COLOR.get(band, NAVY)
    return (f'<svg viewBox="0 0 120 120" width="120" height="120" role="img" aria-label="Band {band}, {de(score, 1)} von 100">'
            f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="#eef1f5" stroke-width="11"/>'
            f'<circle cx="60" cy="60" r="{r}" fill="none" stroke="{col}" stroke-width="11" stroke-linecap="round" '
            f'stroke-dasharray="{c * frac:.1f} {c:.1f}" transform="rotate(-90 60 60)"/>'
            f'<text x="60" y="62" text-anchor="middle" dominant-baseline="central" font-size="50" font-weight="800" fill="{NAVY}">{_e(band)}</text></svg>')


def range_svg(value: float, q25: float, median: float, q75: float, good: bool) -> str:
    """Company value against the sector's middle half and median."""
    span = max(q75 - q25, abs(median) * 0.2, 1e-6)
    lo, hi = min(value, q25) - span * 0.35, max(value, q75) + span * 0.35
    w = 300
    x = lambda v: max(0.0, min(w, (v - lo) / (hi - lo) * w))  # noqa: E731
    col = GOOD if good else WARN
    return (f'<svg viewBox="0 0 {w} 22" width="100%" height="22" preserveAspectRatio="none">'
            f'<rect x="0" y="7" width="{w}" height="8" rx="4" fill="#eef1f5"/>'
            f'<rect x="{x(q25):.1f}" y="7" width="{max(1.0, x(q75) - x(q25)):.1f}" height="8" rx="4" fill="{IQR}"/>'
            f'<rect x="{x(median) - 1:.1f}" y="3" width="2" height="16" fill="{NAVY}"/>'
            f'<circle cx="{x(value):.1f}" cy="11" r="6" fill="{col}" stroke="#fff" stroke-width="2"/></svg>')


def dscr_svg(years: list) -> str:
    """Debt service cover per projected year, with the 1.2x line banks use."""
    vals = [y.dscr for y in years if y.dscr is not None]
    if not vals:
        return ""
    top = max(2.0, max(vals) * 1.15)
    w, h, pad, bw = 520, 170, 34, 64
    gap = (w - pad - len(years) * bw) / (len(years) + 1)
    y = lambda v: h - 22 - (v / top) * (h - 40)  # noqa: E731
    parts = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Kapitaldienstfaehigkeit je Jahr">',
             f'<line x1="{pad}" x2="{w}" y1="{y(1.2):.1f}" y2="{y(1.2):.1f}" stroke="{MUTED}" stroke-dasharray="4 4"/>',
             f'<text x="{pad - 4}" y="{y(1.2) + 4:.1f}" text-anchor="end" font-size="10" fill="{MUTED}">1,2x</text>',
             f'<line x1="{pad}" x2="{w}" y1="{h - 22}" y2="{h - 22}" stroke="{LINE}"/>']
    for i, yr in enumerate(years):
        bx = pad + gap + i * (bw + gap)
        if yr.dscr is None:
            continue
        top_y = y(max(0.0, yr.dscr))
        col = GOOD if yr.dscr >= 1.2 else WARN
        parts.append(f'<rect x="{bx:.1f}" y="{top_y:.1f}" width="{bw}" height="{h - 22 - top_y:.1f}" rx="4" fill="{col}"/>')
        parts.append(f'<text x="{bx + bw / 2:.1f}" y="{top_y - 5:.1f}" text-anchor="middle" font-size="12" font-weight="700" fill="{NAVY}">{_x(yr.dscr)}</text>')
        parts.append(f'<text x="{bx + bw / 2:.1f}" y="{h - 6}" text-anchor="middle" font-size="11" fill="{MUTED}">{yr.year}</text>')
    parts.append("</svg>")
    return "".join(parts)


# ------------------------------------------------------------------ document

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #172033; font-size: 10.5pt; line-height: 1.45; margin: 0; }
h1 { font-size: 21pt; color: #0d2440; margin: 0; }
h2 { font-size: 13pt; color: #0d2440; margin: 18px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #0b8f73; break-after: avoid; }
section { break-inside: avoid; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding-bottom: 12px; border-bottom: 1px solid #e2e6ec; }
.head img { max-height: 54px; max-width: 180px; }
.sub { color: #5d6779; font-size: 9.5pt; }
.eyebrow { font-size: 8.5pt; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #0a7a62; }
table { width: 100%; border-collapse: collapse; margin: 4px 0; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid #e2e6ec; vertical-align: top; }
th { color: #5d6779; font-weight: 600; font-size: 9pt; }
td.n, th.n { text-align: right; white-space: nowrap; }
.kv td:first-child { color: #5d6779; width: 38%; }
.band { display: flex; gap: 18px; align-items: center; }
.band .score { font-size: 24pt; font-weight: 800; color: #0d2440; }
.note { background: #f5f7fa; border-left: 3px solid #0b8f73; padding: 8px 10px; font-size: 9pt; color: #5d6779; margin: 8px 0; }
.rb { display: grid; grid-template-columns: 38% 16% 1fr; gap: 10px; align-items: center; padding: 4px 0; border-bottom: 1px solid #f0f2f5; }
.rb .v { font-weight: 700; text-align: right; }
.legend { font-size: 8.5pt; color: #5d6779; }
.foot { margin-top: 22px; font-size: 8pt; color: #8a93a3; border-top: 1px solid #e2e6ec; padding-top: 8px; }
"""


def _kv(rows: list[tuple[str, Optional[str]]]) -> str:
    body = "".join(f"<tr><td>{_e(k)}</td><td>{_e(v)}</td></tr>" for k, v in rows if v not in (None, ""))
    return f'<table class="kv">{body}</table>'


def render(result: DiagnosticResult, answers: dict, *, sections: tuple[str, ...], reviewed: bool,
           documents: list[dict], logo: Optional[tuple[bytes, str]] = None,
           today: Optional[date] = None) -> str:
    today = today or date.today()
    c, r, sc = result.case, result.ratios, result.scorecard
    a = answers
    out: list[str] = []
    w = out.append

    logo_html = ""
    if logo:
        data, ctype = logo
        logo_html = f'<img src="data:{ctype};base64,{base64.b64encode(data).decode()}" alt="Logo">'
    w(f'<div class="head"><div><div class="eyebrow">Finanzierungsunterlage</div>'
      f'<h1>{_e(c.profile.name)}</h1><div class="sub">Stand {today.strftime("%d.%m.%Y")} · '
      f'erstellt mit Credit Readiness Advisory (unabhaengige Beratung, keine Provision von Kreditgebern)</div></div>{logo_html}</div>')

    if "unternehmen" in sections:
        w('<section><h2>Unternehmen</h2>' + _kv([
            ("Firma", c.profile.name), ("Rechtsform", c.profile.legal_form.value),
            ("Sitz", a.get("sitz")), ("Handelsregister", a.get("hrb_nummer")),
            ("Branche", c.profile.sector.value + (f" (WZ {c.profile.nace_code})" if c.profile.nace_code else "")),
            ("Gruendungsjahr", str(c.profile.founded_year)), ("Mitarbeiter", str(c.profile.employees)),
            ("Ansprechpartner", ", ".join(x for x in (a.get("ansprechpartner"), a.get("ansprechpartner_email"),
                                                     a.get("ansprechpartner_telefon")) if x)),
        ]) + "</section>")

    if "vorhaben" in sections and c.request:
        q = c.request
        w('<section><h2>Finanzierungsvorhaben</h2>' + _kv([
            ("Betrag", _eur(q.amount)), ("Zweck", q.purpose), ("Laufzeit", f"{q.tenor_years} Jahre"),
            ("Beschreibung", a.get("zweck_beschreibung")),
            ("Freie Sicherheiten", _eur(a.get("sicherheiten_wert")) if a.get("sicherheiten_wert") else None),
            ("Bereits belastete Sicherheiten", _eur(a.get("sicherheiten_belastet")) if a.get("sicherheiten_belastet") else None),
            ("Art der Sicherheiten", a.get("sicherheiten_beschreibung")),
        ]))
        if c.facilities:
            rows = "".join(
                f"<tr><td>{_e(f.lender)}</td><td>{_e(f.facility_type)}</td><td class='n'>{_eur(f.outstanding)}</td>"
                f"<td class='n'>{de(f.interest_rate * 100, 2)} %</td><td class='n'>{_eur(f.annual_debt_service)}</td>"
                f"<td class='n'>{f.maturity_year or '–'}</td></tr>" for f in c.facilities)
            w("<p class='sub' style='margin:10px 0 2px'>Bestehende Finanzierungen</p><table><tr><th>Kreditgeber</th><th>Art</th>"
              "<th class='n'>Restschuld</th><th class='n'>Zins</th><th class='n'>Kapitaldienst p. a.</th><th class='n'>Laufzeit bis</th></tr>"
              f"{rows}</table>")
        w("</section>")

    if "zahlen" in sections:
        gu, bs, py = c.income_statement, c.balance_sheet, c.prior_year_income
        cols = [(f"GJ {gu.period_end.year}" + ("" if gu.period_months == 12 else f" ({gu.period_months} Mon.)"), gu)]
        if py:
            cols.append((f"GJ {py.period_end.year}", py))
        head = "".join(f"<th class='n'>{_e(n)}</th>" for n, _ in cols)
        line = lambda label, f: "<tr><td>" + _e(label) + "</td>" + "".join(  # noqa: E731
            f"<td class='n'>{_eur(f(s))}</td>" for _, s in cols) + "</tr>"
        w(f"<section><h2>Finanzzahlen</h2><table><tr><th>GuV</th>{head}</tr>"
          + line("Umsatzerloese", lambda s: s.umsatzerloese)
          + line("EBITDA", lambda s: s.ebitda)
          + line("EBIT", lambda s: s.ebit)
          + line("Jahresueberschuss", lambda s: s.jahresueberschuss)
          + "</table>"
          + f"<table><tr><th>Bilanz zum {bs.period_end.strftime('%d.%m.%Y')}</th><th class='n'></th></tr>"
          + f"<tr><td>Bilanzsumme</td><td class='n'>{_eur(bs.bilanzsumme)}</td></tr>"
          + f"<tr><td>Wirtschaftliches Eigenkapital</td><td class='n'>{_eur(bs.wirtschaftliches_eigenkapital)}</td></tr>"
          + f"<tr><td>Nettofinanzverbindlichkeiten</td><td class='n'>{_eur(bs.nettofinanzverbindlichkeiten)}</td></tr>"
          + "</table><p class='sub'>Quelle: vom Unternehmen bereitgestellte und bestaetigte Abschlussdaten.</p></section>")

    if "kennzahlen" in sections:
        w("<section><h2>Kennzahlen und Branchenvergleich</h2><table>"
          f"<tr><td>Kapitaldienstfaehigkeit inkl. beantragter Finanzierung</td><td class='n'>{_x(r.kapitaldienstfaehigkeit_inkl_neu)}</td></tr>"
          f"<tr><td>Nettoverschuldung / EBITDA</td><td class='n'>{_x(r.dynamischer_verschuldungsgrad)}</td></tr>"
          f"<tr><td>Zinsdeckung (EBIT / Zinsaufwand)</td><td class='n'>{_x(r.zinsdeckungsgrad)}</td></tr>"
          f"<tr><td>Eigenkapitalquote (wirtschaftlich)</td><td class='n'>{_pct(r.eigenkapitalquote)}</td></tr>"
          f"<tr><td>EBIT-Marge</td><td class='n'>{_pct(r.ebit_marge)}</td></tr></table>")
        rows = []
        for b in result.benchmark:
            if b.company_value is None or not b.quartiles:
                continue
            days = b.metric == "Debitorenlaufzeit"
            fmt = (lambda v: f"{de(v)} Tage") if days else _pct
            good = b.verdict != "unter Branchenmedian"
            rows.append(f'<div class="rb"><div>{_e(b.metric)}<div class="legend">Branchenmedian {fmt(b.quartiles[1])}</div></div>'
                        f'<div class="v">{fmt(b.company_value)}</div>'
                        f'{range_svg(b.company_value, *b.quartiles, good=good)}</div>')
        if rows:
            basis = result.sector_trends[0].basis if result.sector_trends else c.profile.sector.value
            w(f"<p class='sub' style='margin:12px 0 2px'>Vergleich mit Unternehmen derselben Branche und Groesse ({_e(basis)}; "
              "Deutsche Bundesbank, Jahresabschlussstatistik). Band: mittlere Haelfte der Branche; Strich: Median.</p>"
              + "".join(rows))
        w("</section>")

    if "band" in sections:
        src = ("geprueft und freigegeben von einem Kreditanalysten" if reviewed
               else "automatischer Schnell-Check, nicht durch einen Analysten geprueft")
        g = result.scorecard_generic
        w(f'<section><h2>Readiness-Band</h2><div class="band">{gauge_svg(sc.band.value, sc.total_score)}<div>'
          f'<div class="score">Band {sc.band.value} · {de(sc.total_score, 1)} / 100</div>'
          f'<div>{_e(sc.band.interpretation)}</div>'
          f'<div class="sub">Quelle: {src}. Gemessen an der eigenen Branche'
          + (f"; ohne Branchenbezug {de(g.total_score, 1)} (Band {g.band.value})" if g else "")
          + '.</div></div></div>'
          '<div class="note">Das Readiness-Band ist eine richtungsweisende Einschaetzung auf Basis oeffentlich '
          'bekannter Analysepraxis. Es ist kein Rating, keine Ausfallwahrscheinlichkeit und keine Aussage '
          'ueber eine Kreditentscheidung.</div></section>')

    if "fortschreibung" in sections and result.projection and result.projection.years:
        p = result.projection
        rows = "".join(f"<tr><td>{y.year}</td><td class='n'>{_eur(y.umsatz)}</td><td class='n'>{_eur(y.ebitda)}</td>"
                       f"<td class='n'>{_eur(y.kapitaldienst)}</td><td class='n'>{_x(y.dscr)}</td></tr>" for y in p.years)
        w("<section><h2>Kapitaldienstfaehigkeit: Fortschreibung</h2>" + dscr_svg(p.years)
          + "<table><tr><th>Jahr</th><th class='n'>Umsatz</th><th class='n'>EBITDA</th><th class='n'>Kapitaldienst</th>"
          f"<th class='n'>Kapitaldienstfaehigkeit</th></tr>{rows}</table>"
          + "<p class='sub'>Mechanische Fortschreibung der eigenen Zahlen inkl. der beantragten Finanzierung, keine Prognose. "
          + _e(" ".join(p.assumptions)) + "</p></section>")

    if "massnahmen" in sections and result.improvements and result.improvements.items:
        rows = "".join(f"<tr><td>{_e(i.label)}</td><td class='n'>{_e(i.format(i.current))}</td>"
                       f"<td class='n'>{_e(i.format(i.target))}</td><td>{_e(i.lever)}</td></tr>"
                       for i in result.improvements.items[:6])
        w("<section><h2>Massnahmenplan</h2><table><tr><th>Kennzahl</th><th class='n'>Heute</th>"
          f"<th class='n'>Branchenueblich</th><th>Hebel</th></tr>{rows}</table></section>")

    if "unterlagen" in sections and documents:
        rows = "".join(f"<tr><td>{_e(d['title'])}</td><td>{_e(d['filename'])}</td><td class='n'>{_e(d['date'])}</td></tr>" for d in documents)
        w("<section><h2>Unterlagenverzeichnis</h2><p class='sub'>Liegen uns vor und koennen auf Anfrage bereitgestellt werden.</p>"
          f"<table><tr><th>Unterlage</th><th>Datei</th><th class='n'>Stand</th></tr>{rows}</table></section>")

    w(f'<div class="foot">{_e(DISCLAIMER)}</div>')
    title = _e(f"Finanzierungsunterlage {c.profile.name}")
    return (f'<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{CSS}</style></head><body>{''.join(out)}</body></html>")
