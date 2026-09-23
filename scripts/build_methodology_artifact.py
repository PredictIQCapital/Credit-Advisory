"""Turn the generated methodology pages into one bilingual screen version.

The print versions are laid out for A4: the cover bleeds into the page margin
with negative margins, tables carry millimetre widths, and page breaks are
meaningful. None of that survives a browser at phone width, and none of it
should be hand-maintained as a second copy -- so this reads both generated
files and adapts them, rather than duplicating any content.

Both languages end up in one page behind a toggle, because the point is that a
reader can check a sentence against the other language without hunting for a
second file.

    python scripts/build_methodology_pdf.py      # source of truth, both langs
    python scripts/build_methodology_artifact.py # screen version
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "methodik"
SOURCES = {"de": OUT_DIR / "scoring-methodik.html",
           "en": OUT_DIR / "scoring-methodology-en.html"}
TARGET = OUT_DIR / "scoring-methodik-web.html"

SWITCH_LABEL = {"de": "English", "en": "Deutsch"}

# Screen overrides, appended after the generated CSS so they win without
# touching it -- the print layout stays the authority for the PDFs.
SCREEN_CSS = """
/* ---- screen adaptation (appended; the print CSS above is unchanged) ---- */
:root{ --page:#ffffff; --ground:#eef2f6; color-scheme: light; }
body{ background:var(--ground); margin:0; font-size:15px; line-height:1.55; }
.sheet-wrap{ max-width:900px; margin:0 auto; background:var(--page);
  padding:0 28px 48px; box-shadow:0 1px 3px rgba(13,36,64,.10); }
.cover{ margin:0 -28px 26px; padding:44px 28px 28px; position:relative; }
.cover h1{font-size:34px}
.cover .sub{font-size:17px}
.cover .lede{font-size:15px; max-width:none}
.logo{margin-bottom:34px}
h2{font-size:21px; margin-top:34px}
h3{font-size:15.5px}
section{margin-bottom:22px}
.pagebreak{page-break-before:auto}
.tablewrap{overflow-x:auto; -webkit-overflow-scrolling:touch; margin:10px 0 14px}
.tablewrap table{margin:0; min-width:560px; font-size:13px}
td,th{padding:7px 9px}
.note{padding:11px 14px; margin:14px 0}
.kv div{min-width:150px}
code{font-size:12.5px}

/* language toggle */
.langbar{position:sticky; top:0; z-index:10; display:flex; justify-content:flex-end;
  gap:8px; padding:9px 0; background:var(--ground);}
.langbtn{font:inherit; font-size:13px; font-weight:600; cursor:pointer;
  border:1px solid var(--line); background:var(--page); color:var(--ink);
  border-radius:999px; padding:6px 15px;}
.langbtn[aria-pressed="true"]{background:var(--navy); border-color:var(--navy); color:#fff;}

@media (max-width:640px){
  .sheet-wrap{padding:0 15px 34px}
  .cover{margin:0 -15px 20px; padding:30px 15px 20px}
  .cover h1{font-size:26px}
  .factbar{flex-wrap:wrap; gap:12px 0}
  .factbar div{flex:0 0 50%}
  .kv{flex-direction:column}
}

@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --page:#111a24; --ground:#0a1119; --ink:#dde5ec; --muted:#9bacbd;
    --line:#26333f; --bg-soft:#18222d; --navy:#c8dcf0; --green-l:#4fc6a3;
    color-scheme: dark;
  }
  :root:not([data-theme="light"]) td{color:var(--ink)}
  :root:not([data-theme="light"]) tr:nth-child(even) td{background:var(--bg-soft)}
  :root:not([data-theme="light"]) .sheet-wrap{box-shadow:none}
  :root:not([data-theme="light"]) .note b{color:var(--navy)}
  :root:not([data-theme="light"]) code{background:var(--bg-soft); color:var(--ink)}
  :root:not([data-theme="light"]) .langbtn[aria-pressed="true"]{color:#0a1119}
}
"""

SCRIPT = """
<script>
(function () {
  var buttons = document.querySelectorAll('.langbtn');
  var panes = document.querySelectorAll('[data-lang-pane]');
  function show(lang) {
    panes.forEach(function (p) { p.hidden = p.dataset.langPane !== lang; });
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.lang === lang));
    });
    document.documentElement.lang = lang;
    try { localStorage.setItem('methodik-lang', lang); } catch (e) { /* private mode */ }
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.lang); });
  });
  var saved = null;
  try { saved = localStorage.getItem('methodik-lang'); } catch (e) { /* ignore */ }
  show(saved === 'en' || saved === 'de' ? saved
       : (navigator.language || '').toLowerCase().startsWith('de') ? 'de' : 'en');
})();
</script>
"""


def extract(path: Path) -> tuple[str, str, str]:
    """Return (title, css, body) from a generated print page."""
    html = path.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    style = re.search(r"<style>(.*?)</style>", html, re.S)
    body = re.search(r"<body>(.*?)</body>", html, re.S)
    if not (title and style and body):
        raise SystemExit(f"could not parse {path.name}")
    return title.group(1), style.group(1), body.group(1).strip()


def main() -> int:
    for lang, path in SOURCES.items():
        if not path.exists():
            print(f"missing {path.name} -- run scripts/build_methodology_pdf.py first")
            return 1

    title, css, _ = extract(SOURCES["de"])
    panes = []
    for lang, path in SOURCES.items():
        body = extract(path)[2]
        # Each table gets its own horizontal scroll container, so a wide
        # breakpoint table never makes the whole page scroll sideways.
        body = re.sub(r"(<table\b.*?</table>)",
                      r'<div class="tablewrap">\1</div>', body, flags=re.S)
        panes.append(f'<div data-lang-pane="{lang}" hidden>\n{body}\n</div>')

    bar = ('<div class="langbar">'
           + "".join(f'<button type="button" class="langbtn" data-lang="{lang}" '
                     f'aria-pressed="false">{"Deutsch" if lang == "de" else "English"}'
                     f'</button>' for lang in SOURCES)
           + "</div>")

    page = (f"<title>{title}</title>\n<style>{css}{SCREEN_CSS}</style>\n"
            f'<div class="sheet-wrap">\n{bar}\n' + "\n".join(panes) + f"\n</div>\n{SCRIPT}")
    TARGET.write_text(page, encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)}  ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
