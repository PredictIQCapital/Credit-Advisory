"""Markdown -> standalone, printable HTML.

Every client document (report, letters, questionnaires) is written once, as
Markdown, and converted here. One source of truth means the HTML a client
prints can never say something different from the Markdown in the case file.

Supports exactly the subset our own renderers emit: headings, paragraphs,
tables, block quotes, bullet and numbered lists, horizontal rules, fenced code,
**bold**, *italic*, `code`. No external dependency, and all text is escaped
before any markup is added, so client-supplied names cannot inject HTML.
"""

from __future__ import annotations

import html
import re

CSS = """
:root { --ink:#1d2330; --muted:#5b6475; --line:#d9dde5; --accent:#1f4e8c; --warn:#8a1c1c;
        --bg:#ffffff; --soft:#f4f6f9; }
* { box-sizing: border-box; }
body { font: 15px/1.55 "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
       color: var(--ink); background: var(--bg); margin: 0; padding: 32px 16px; }
main { max-width: 920px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0 0 12px; color: var(--accent); }
h2 { font-size: 19px; margin: 32px 0 10px; padding-bottom: 4px;
     border-bottom: 2px solid var(--line); }
h3 { font-size: 16px; margin: 22px 0 6px; }
p { margin: 8px 0; }
.table-wrap { overflow-x: auto; margin: 10px 0 14px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left;
         vertical-align: top; }
th { background: var(--soft); }
blockquote { margin: 12px 0; padding: 8px 14px; border-left: 4px solid var(--accent);
             background: var(--soft); color: var(--muted); }
code { background: var(--soft); padding: 1px 4px; border-radius: 3px; }
pre { background: var(--soft); padding: 10px; overflow-x: auto; }
hr { border: 0; border-top: 1px solid var(--line); margin: 24px 0; }
.box { display:inline-block; width:14px; height:14px; border:1.5px solid var(--ink);
       vertical-align:-2px; margin: 0 5px 0 18px; }
p > .box:first-child { margin-left: 0; }
@media print {
  body { padding: 0; font-size: 12px; }
  h2 { page-break-after: avoid; }
  table, blockquote { page-break-inside: avoid; }
}
"""


def _inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    s = s.replace("[ ]", '<span class="box"></span>')
    return s


def _cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def markdown_to_html(md: str, title: str = "") -> str:
    lines = md.splitlines()
    out: list[str] = []
    para: list[str] = []
    i = 0

    def flush_para() -> None:
        if para:
            out.append("<p>" + " ".join(_inline(p) for p in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        if stripped.startswith("```"):
            flush_para()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(html.escape(lines[i]))
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
            i += 1
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and _SEPARATOR.match(lines[i + 1].strip()):
            flush_para()
            head = _cells(stripped)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += [f"<th>{_inline(h)}</th>" for h in head]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue

        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote>" + " ".join(_inline(q) for q in quote) + "</blockquote>")
            continue

        if re.match(r"^([-*])\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            flush_para()
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            pattern = r"^\d+\.\s+" if ordered else r"^[-*]\s+"
            items = []
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append(re.sub(pattern, "", lines[i].strip(), count=1))
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue

        # Markdown hard line break: two trailing spaces.
        para.append(stripped + ("<br>" if line.endswith("  ") else ""))
        i += 1

    flush_para()
    body = "\n".join(out).replace("&lt;br&gt;", "<br>")
    safe_title = html.escape(title or "Dokument")
    return (
        "<!doctype html>\n<html lang=\"de\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{safe_title}</title><style>{CSS}</style></head>"
        f"<body><main>\n{body}\n</main></body></html>\n"
    )
