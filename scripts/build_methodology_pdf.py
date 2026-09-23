"""Generate the scoring methodology document, in German and English.

Why this is generated and not hand-written: a methodology paper that drifts
from the code it documents is worse than none, because it is used to defend
numbers that the engine no longer produces. Every factor, weight, breakpoint,
band, scenario and knock-out criterion in the output is read out of the live
modules, and the worked example is a real diagnostic run. Change the scorecard,
re-run this, and both language versions are correct again.

The prose lives in methodology_text.py and methodology_sections.py, so a second
language costs a translation rather than a second document to keep in step.

    pip install playwright && playwright install chromium
    python scripts/build_methodology_pdf.py          # both languages
    python scripts/build_methodology_pdf.py de       # one of them
"""

from __future__ import annotations

import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from credit_readiness import benchmarks, rejection_risk, sensitivity    # noqa: E402
from credit_readiness.engine import run_diagnostic                      # noqa: E402
from credit_readiness.formatting import de as de_num                    # noqa: E402
from credit_readiness.ingest.json_intake import load_case_file          # noqa: E402
from credit_readiness.scorecard import BAND_THRESHOLDS, FACTORS         # noqa: E402

from methodology_sections import SECTIONS                               # noqa: E402
from methodology_text import (                                          # noqa: E402
    BAND_INTERPRETATION, CALIBRATED, COVER_LEDE, EBA_ANHANG3,
    EBA_METRIC_NAMES, FACTOR_LABELS, HERKUNFT, KNOCKOUTS, LABELS,
    SCENARIOS, TAG_CLASS,
)

OUT_DIR = ROOT / "docs" / "methodik"
EXAMPLE = ROOT / "data" / "samples" / "case_01_mueller_praezisionstechnik.json"
LANGS = ("de", "en")

FILENAMES = {
    "de": ("scoring-methodik.html", "Scoring-Methodik.pdf"),
    "en": ("scoring-methodology-en.html", "Scoring-Methodology-EN.pdf"),
}


def stand(lang: str) -> str:
    today = date.today()
    return today.strftime("%d.%m.%Y") if lang == "de" else today.strftime("%d %B %Y")


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
table{width:100%; border-collapse:collapse; margin:8px 0 10px; font-size:8.5pt}
th{text-align:left; background:var(--navy); color:#fff; font-weight:600;
   padding:5px 7px; font-size:8pt}
td{padding:5px 7px; border-bottom:1px solid var(--line); vertical-align:top}
table.thresholds td{padding:4px 7px}
tr:nth-child(even) td{background:var(--bg-soft)}
tr{page-break-inside:avoid}
thead{display:table-header-group}
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


# ----------------------------------------------------------------- helpers


def factor_label(factor, lang: str) -> str:
    if lang == "de":
        return factor.label
    return FACTOR_LABELS["en"].get(factor.key, factor.label)


def _fmt_x(unit: str, value: float) -> str:
    if unit == "percent":
        return f"{de_num(value * 100, 1)}%"
    if unit == "x":
        return f"{de_num(value, 2)}x"
    if unit in ("days", "months"):
        return de_num(value, 1)
    return de_num(value, 0)


def breakpoint_rows(factor) -> str:
    return " &nbsp;&rarr;&nbsp; ".join(
        f"<code>{_fmt_x(factor.unit, x)}</code> = {de_num(y, 0)}"
        for x, y in factor.breakpoints
    )


# ------------------------------------------------------------------ tables


def factor_table(lang: str) -> str:
    L, cal = LABELS[lang], CALIBRATED[lang]
    rows = []
    for f in FACTORS:
        tag = (f'<span class="tag cal">{L["tag_calibrated"]}</span>' if f.key in cal
               else f'<span class="tag con">{L["tag_convention"]}</span>')
        rows.append(
            f"<tr><td><b>{escape(factor_label(f, lang))}</b><br><small class='muted'>"
            f"<code>{f.key}</code></small></td>"
            f"<td class='num'>{de_num(f.weight * 100, 0)}%</td>"
            f"<td>{tag}</td>"
            f"<td><small>{escape(HERKUNFT[lang].get(f.key, ''))}</small></td></tr>"
        )
    return (f"<table><thead><tr><th>{L['th_factor']}</th>"
            f"<th class='num'>{L['th_weight']}</th><th>{L['th_kind']}</th>"
            f"<th>{L['th_origin']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def threshold_table(lang: str) -> str:
    L, cal = LABELS[lang], CALIBRATED[lang]
    rows = []
    for f in FACTORS:
        src = cal.get(f.key)
        prov = (f"<small class='muted'>{L['bundesbank_prefix']}: {escape(src)}</small>"
                if src else f"<small class='muted'>{L['convention_plain']}</small>")
        rows.append(f"<tr><td><b>{escape(factor_label(f, lang))}</b><br>{prov}</td>"
                    f"<td>{breakpoint_rows(f)}</td></tr>")
    return (f"<table class='thresholds'><thead><tr>"
            f"<th style='width:48mm'>{L['th_factor']}</th>"
            f"<th>{L['th_breakpoints']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def band_table(lang: str) -> str:
    L = LABELS[lang]
    rows = []
    ordered = sorted(BAND_THRESHOLDS, key=lambda t: -t[0])
    for i, (threshold, band) in enumerate(ordered):
        upper = "100,0" if i == 0 else de_num(ordered[i - 1][0], 1)
        meaning = (band.interpretation if lang == "de"
                   else BAND_INTERPRETATION["en"][band.value])
        rows.append(f"<tr><td><span class='band {band.value}'>{band.value}</span></td>"
                    f"<td class='num'>{de_num(threshold, 1)} &ndash; {upper}</td>"
                    f"<td>{escape(meaning)}</td></tr>")
    return (f"<table><thead><tr><th style='width:14mm'>{L['th_level']}</th>"
            f"<th class='num' style='width:26mm'>{L['th_points']}</th>"
            f"<th>{L['th_meaning']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def eba_table(lang: str) -> str:
    L = LABELS[lang]
    rows = []
    for (nr, status, comment), name in zip(EBA_ANHANG3[lang], EBA_METRIC_NAMES):
        rows.append(f"<tr><td class='num'>{nr}</td><td>{escape(name)}</td>"
                    f"<td><span class='tag {TAG_CLASS[status]}'>{status}</span></td>"
                    f"<td><small>{escape(comment)}</small></td></tr>")
    return (f"<table><thead><tr><th class='num' style='width:9mm'>{L['th_no']}</th>"
            f"<th style='width:46mm'>{L['th_eba_metric']}</th>"
            f"<th style='width:17mm'>{L['th_covered']}</th>"
            f"<th>{L['th_implementation']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def knockout_table(lang: str) -> str:
    L = LABELS[lang]
    rows = []
    for code, title, condition, source in rejection_risk.CHECK_CATALOGUE:
        if lang == "en":
            title, condition, source = KNOCKOUTS["en"][code]
        rows.append(f"<tr><td class='num'>{code}</td><td><b>{escape(title)}</b></td>"
                    f"<td><small>{escape(condition)}</small></td>"
                    f"<td><small>{escape(source)}</small></td></tr>")
    return (f"<table><thead><tr><th class='num' style='width:13mm'>{L['th_code']}</th>"
            f"<th style='width:44mm'>{L['th_criterion']}</th>"
            f"<th style='width:48mm'>{L['th_condition']}</th>"
            f"<th>{L['th_basis']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def scenario_table(lang: str) -> str:
    L = LABELS[lang]
    rows = []
    for key, label, assumption, _ in sensitivity.SCENARIOS:
        if lang == "en":
            label, assumption = SCENARIOS["en"][key]
        rows.append(f"<tr><td><b>{escape(label)}</b></td>"
                    f"<td><small>{escape(assumption)}</small></td></tr>")
    return (f"<table><thead><tr><th style='width:52mm'>{L['th_scenario']}</th>"
            f"<th>{L['th_assumption']}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def worked_example(lang: str) -> tuple[str, str]:
    """A real diagnostic run, printed factor by factor."""
    L = LABELS[lang]
    result = run_diagnostic(load_case_file(EXAMPLE))
    card = result.scorecard
    by_key = {f.key: f for f in FACTORS}

    rows = []
    for f in card.factors:
        label = escape(factor_label(by_key[f.key], lang)) if f.key in by_key else escape(f.label)
        if f.score is None:
            rows.append(f"<tr><td>{label}</td><td class='num'>n/a</td>"
                        f"<td class='num'>&ndash;</td><td class='num'>&ndash;</td>"
                        f"<td class='num'>0,00</td>"
                        f"<td><small>{escape(f.missing_reason)}</small></td></tr>")
            continue
        rows.append(f"<tr><td>{label}</td>"
                    f"<td class='num'>{escape(f.format_value())}</td>"
                    f"<td class='num'>{de_num(f.score, 1)}</td>"
                    f"<td class='num'>{de_num(f.weight * 100, 0)}%</td>"
                    f"<td class='num'><b>{de_num(f.contribution, 2)}</b></td><td></td></tr>")
    rows.append(f"<tr><td colspan='4'><b>{L['total']}</b></td>"
                f"<td class='num'><b>{de_num(card.total_score, 1)}</b></td>"
                f"<td><span class='band {card.band.value}'>{card.band.value}</span></td></tr>")
    table = (f"<table><thead><tr><th>{L['th_factor']}</th>"
             f"<th class='num'>{L['th_value']}</th><th class='num'>{L['th_points']}</th>"
             f"<th class='num'>{L['th_weight']}</th>"
             f"<th class='num'>{L['th_contribution']}</th><th></th></tr></thead><tbody>"
             + "".join(rows) + "</tbody></table>")

    sens = result.sensitivity
    srows = [f"<tr><td>{L['baseline']}</td><td class='num'>{de_num(sens.base_score, 1)}</td>"
             f"<td><span class='band {sens.base_band.value}'>{sens.base_band.value}</span></td>"
             f"<td class='num'>&ndash;</td></tr>"]
    for sc in sens.scenarios:
        label = SCENARIOS["en"][sc.key][0] if lang == "en" else sc.label
        srows.append(f"<tr><td>{escape(label)}</td><td class='num'>{de_num(sc.score, 1)}</td>"
                     f"<td><span class='band {sc.band.value}'>{sc.band.value}</span></td>"
                     f"<td class='num'>{de_num(sc.delta, 1)}</td></tr>")
    stable = (f"<table><thead><tr><th>{L['th_scenario']}</th>"
              f"<th class='num'>{L['th_points']}</th><th>{L['th_level']}</th>"
              f"<th class='num'>{L['th_delta']}</th></tr></thead><tbody>"
              + "".join(srows) + "</tbody></table>")
    return table, stable


# ------------------------------------------------------------------- page


def build_body(lang: str) -> str:
    L, S = LABELS[lang], SECTIONS[lang]
    example, example_sens = worked_example(lang)
    cal_pct = de_num(sum(f.weight for f in FACTORS if f.key in CALIBRATED[lang]) * 100, 0)
    fill = {
        "n_factors": len(FACTORS),
        "cal_pct": cal_pct,
        "n_ko": len(rejection_risk.CHECK_CATALOGUE),
        "vintage": escape(benchmarks.VINTAGE),
        "caveat": escape(benchmarks.CAVEAT),
    }

    def sec(n: int, key: str, *blocks: str, brk: bool = False) -> str:
        cls = ' class="pagebreak"' if brk else ""
        return (f'<section{cls}>\n  <span class="eyebrow">{L["section"]} {n}</span>\n'
                f'  <h2><span class="n">{n:02d}</span>{S[key + "_h"]}</h2>\n'
                + "\n".join(blocks) + "\n</section>\n\n")

    def note(key: str, kind: str = "") -> str:
        return f'  <div class="note {kind}">{S[key].format(**fill)}</div>'

    def p(key: str) -> str:
        return "  " + S[key].format(**fill)

    src_table = (
        f'  <table><thead><tr><th style="width:52mm">{L["th_source"]}</th>'
        f'<th>{L["th_taken"]}</th></tr></thead><tbody>'
        f'<tr><td><b>{S["s02_src1_n"]}</b><br><small class="muted">{S["s02_src1_t"]}</small></td>'
        f'<td>{S["s02_src1"]}</td></tr>'
        f'<tr><td><b>{S["s02_src2_n"]}</b><br><small class="muted">{S["s02_src2_t"]}</small></td>'
        f'<td>{S["s02_src2"]}</td></tr>'
        f'<tr><td><b>{S["s02_src3_n"]}</b><br><small class="muted">{S["s02_src3_t"]}</small></td>'
        f'<td>{S["s02_src3"]}</td></tr>'
        "</tbody></table>")

    kv = ('  <div class="kv">'
          + "".join(f'<div><b>{S[f"s06_kv{i}"]}</b><small>{S[f"s06_kv{i}s"]}</small></div>'
                    for i in (1, 2, 3))
          + "</div>")

    return (
        f'<div class="cover">\n'
        f'  <div class="logo"><div class="bars"><i></i><i></i><i></i></div>'
        f'<span>Credit Readiness Advisory</span></div>\n'
        f'  <h1>{L["title"]}</h1>\n  <div class="sub">{L["subtitle"]}</div>\n'
        f'  <div class="lede">{COVER_LEDE[lang]}</div>\n'
        f'  <div class="factbar">\n'
        f'    <div><b>{len(FACTORS)}</b><small>{L["fact_factors"]}</small></div>\n'
        f'    <div><b>{len(CALIBRATED[lang])}</b><small>{L["fact_calibrated"]}</small></div>\n'
        f'    <div><b>{cal_pct}%</b><small>{L["fact_weight"]}</small></div>\n'
        f'    <div><b>{len(sensitivity.SCENARIOS)}</b><small>{L["fact_scenarios"]}</small></div>\n'
        f'    <div><b>{fill["n_ko"]}</b><small>{L["fact_knockouts"]}</small></div>\n'
        f'  </div>\n</div>\n\n'
        + sec(1, "s01", p("s01"))
        + sec(2, "s02", p("s02_intro"), src_table, note("s02_note", "warn"))
        + sec(3, "s03", p("s03"), "  " + eba_table(lang), brk=True)
        + sec(4, "s04", p("s04_intro"), "  " + factor_table(lang),
              note("s04_note1"), note("s04_note2"), brk=True)
        + sec(5, "s05", p("s05"), "  " + threshold_table(lang), brk=True)
        + sec(6, "s06", f'  <h3>{S["s06_h3a"]}</h3>', p("s06_p1"), kv, p("s06_p2"),
              note("s06_note1"), p("s06_p3"), f'  <h3>{S["s06_h3b"]}</h3>',
              p("s06_p4"), note("s06_note2"), brk=True)
        + sec(7, "s07", "  " + band_table(lang), note("s07_note", "warn"), brk=True)
        + sec(8, "s08", p("s08_p1"), "  " + scenario_table(lang),
              f'  <h3>{S["s08_h3"]}</h3>', p("s08_p2"),
              note("s08_note1"), note("s08_note2", "warn"))
        + sec(9, "s09", p("s09_p1"), p("s09_p2"), "  " + knockout_table(lang),
              note("s09_note1", "stop"), note("s09_note2"))
        + sec(10, "s10", p("s10_p1"), "  " + example, p("s10_p2"),
              "  " + example_sens, p("s10_p3"), brk=True)
        + sec(11, "s11", p("s11"))
        + sec(12, "s12", p("s12"), note("s12_note"))
    )


def build_html(lang: str) -> str:
    L = LABELS[lang]
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            f"<title>{L['doc_title']}</title>\n<style>{CSS}</style>\n</head>\n<body>\n\n"
            f"{build_body(lang)}</body>\n</html>\n")


def render_pdf(lang: str, source: Path, target: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && playwright install chromium")
        return False

    L = LABELS[lang]
    footer = (
        '<div style="width:100%;font-size:7pt;color:#8a99a8;'
        "font-family:'Segoe UI',Arial,sans-serif;padding:0 14mm;"
        'display:flex;justify-content:space-between;">'
        f'<span>{L["footer"].format(stand=stand(lang))}</span>'
        f'<span>{L["page"]} <span class="pageNumber"></span> / '
        '<span class="totalPages"></span></span></div>'
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(source.as_uri(), wait_until="networkidle")
        page.pdf(path=str(target), format="A4", print_background=True,
                 display_header_footer=True, header_template="<div></div>",
                 footer_template=footer,
                 margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        browser.close()
    return True


def main() -> int:
    langs = sys.argv[1:] or list(LANGS)
    for lang in langs:
        if lang not in LANGS:
            print(f"unknown language {lang!r}; expected one of {', '.join(LANGS)}")
            return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for lang in langs:
        html_name, pdf_name = FILENAMES[lang]
        source, target = OUT_DIR / html_name, OUT_DIR / pdf_name
        source.write_text(build_html(lang), encoding="utf-8")
        print(f"{source.relative_to(ROOT)}  ({source.stat().st_size // 1024} KB)")
        if render_pdf(lang, source, target):
            print(f"{target.relative_to(ROOT)}  ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
