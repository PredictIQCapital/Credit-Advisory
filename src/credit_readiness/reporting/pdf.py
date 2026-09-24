"""HTML to PDF without a runtime dependency.

Two ways, tried in order: Playwright's Chromium when it is installed (as it is
for the build scripts), else a Chrome or Edge already on the machine, driven
with --headless --print-to-pdf. When neither exists, callers get None and serve
the HTML instead -- a browser prints it to the same result.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

FOOTER = ('<div style="width:100%;font-size:7pt;color:#8a93a3;font-family:Segoe UI,Arial,sans-serif;'
          'padding:0 14mm;display:flex;justify-content:space-between;"><span>{title} · Richtungsweisende Einschaetzung, kein Rating, keine Kreditzusage</span>'
          '<span>Seite <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')

_BROWSERS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def _browser() -> Optional[str]:
    env = os.environ.get("CRA_CHROME")
    if env and Path(env).is_file():
        return env
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return next((b for b in _BROWSERS if Path(b).is_file()), None)


def html_to_pdf(html: str, footer_title: str = "") -> Optional[bytes]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sync_playwright = None
    if sync_playwright is not None:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                data = page.pdf(format="A4", print_background=True, display_header_footer=True,
                                header_template="<div></div>",
                                footer_template=FOOTER.format(title=footer_title.replace("<", "")),
                                margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
                browser.close()
                return data
        except Exception:        # no browser downloaded for Playwright: try the system one
            pass
    exe = _browser()
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "in.html", Path(tmp) / "out.pdf"
        src.write_text(html, encoding="utf-8")
        try:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={Path(tmp) / 'profile'}",
                            f"--print-to-pdf={out}", src.as_uri()],
                           check=False, timeout=60, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return out.read_bytes() if out.is_file() and out.stat().st_size > 0 else None
