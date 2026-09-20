"""Render docs/overview/overview.html to a shareable PDF.

The overview is the one document handed to people outside the project -- a
developer sizing up the codebase, an investor sizing up the business. It is
written as HTML so it stays editable and diffable; this script prints it
through headless Chrome, which is the only renderer here that handles the
print CSS faithfully.

    pip install playwright && playwright install chromium
    python scripts/build_overview_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "overview" / "overview.html"
TARGET = ROOT / "docs" / "overview" / "Credit-Readiness-Advisory-Overview.pdf"

FOOTER = """
<div style="width:100%;font-size:7pt;color:#8a99a8;
            font-family:'Segoe UI',Arial,sans-serif;padding:0 14mm;
            display:flex;justify-content:space-between;">
  <span>Credit Readiness Advisory &middot; Product and technology overview &middot; 20 September 2026</span>
  <span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>
"""


def main() -> int:
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
            header_template="<div></div>",   # Chrome needs a template, not an empty string
            footer_template=FOOTER,
            margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()

    print(f"{TARGET.relative_to(ROOT)}  ({TARGET.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
