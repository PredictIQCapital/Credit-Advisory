"""Write the printable intake templates to docs/intake/.

    python scripts/export_intake_templates.py          regenerate
    python scripts/export_intake_templates.py --check  fail if docs/intake is stale

The files are generated from the questionnaire and document definitions in
src/credit_readiness/intake/. Never edit them by hand -- edit the definitions
and re-run this script. The test suite runs --check, so a stale form cannot be
committed unnoticed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_readiness.intake.questionnaire import (          # noqa: E402
    FRAGEBOGEN_STEUERBERATER,
    FRAGEBOGEN_UNTERNEHMEN,
)
from credit_readiness.reporting.forms import (                # noqa: E402
    answers_template,
    documents_markdown,
    questionnaire_markdown,
)
from credit_readiness.reporting.html import markdown_to_html  # noqa: E402

OUT = ROOT / "docs" / "intake"


def render() -> dict[str, str]:
    files: dict[str, str] = {}
    for q, stem in ((FRAGEBOGEN_UNTERNEHMEN, "Fragebogen_Unternehmen"),
                    (FRAGEBOGEN_STEUERBERATER, "Fragebogen_Steuerberater")):
        md = questionnaire_markdown(q)
        files[f"{stem}.md"] = md
        files[f"{stem}.html"] = markdown_to_html(md, q.title)
        files[f"{stem}_Antwortvorlage.json"] = json.dumps(
            answers_template(q), indent=2, ensure_ascii=False) + "\n"
    md = documents_markdown()
    files["Unterlagenliste.md"] = md
    files["Unterlagenliste.html"] = markdown_to_html(md, "Unterlagenliste")
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    files = render()
    if args.check:
        stale = [n for n, text in files.items()
                 if not (OUT / n).is_file() or (OUT / n).read_text(encoding="utf-8") != text]
        if stale:
            print("Veraltet, bitte scripts/export_intake_templates.py ausfuehren:", ", ".join(stale))
            return 1
        print("docs/intake ist aktuell")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"geschrieben: docs/intake/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
