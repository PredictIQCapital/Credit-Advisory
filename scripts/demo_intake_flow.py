"""End-to-end demonstration of a complete engagement, the way a real one runs.

    create case -> questionnaires -> uploads -> overview -> diagnostic
               -> letters -> outcome

Uses the fictional intake package from scripts/generate_intake_samples.py and
writes into a throw-away store unless --store is given, so it never touches
real client data.

Run:  python scripts/demo_intake_flow.py
      python scripts/demo_intake_flow.py --store data/clients   (keep the case)
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_readiness import workflow as wf                   # noqa: E402
from credit_readiness.casefile import LocalCaseStore          # noqa: E402

SAMPLES = ROOT / "data" / "samples" / "intake"

UPLOADS = [
    ("susa_aktuell", "susa_2025.csv", {"period_end": "2025-12-31", "period_months": 12}),
    ("susa_vorjahr", "susa_2024.csv", {"period_end": "2024-12-31", "period_months": 12}),
    ("kontoumsaetze", "kontoumsaetze_kontokorrent.csv", {"account_label": "Kontokorrent Sparkasse"}),
    ("bwa_aktuell", "bwa_2026_04.pdf", {}),
    ("jahresabschluesse", "jahresabschluss_2025.pdf", {}),
    ("jahresabschluesse", "jahresabschluss_2024.pdf", {}),
    ("handelsregisterauszug", "handelsregisterauszug.pdf", {}),
    ("darlehensvertraege", "kreditvertrag_tilgungsdarlehen.pdf", {}),
    ("darlehensvertraege", "kreditvertrag_kontokorrent.pdf", {}),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", help="Ablageverzeichnis (Standard: temporaer)")
    args = ap.parse_args()

    if not (SAMPLES / "antworten_unternehmen.json").exists():
        sys.exit("Beispieldaten fehlen: zuerst python scripts/generate_intake_samples.py")

    store = LocalCaseStore(args.store or tempfile.mkdtemp(prefix="cra_demo_"))
    today = date.today()

    meta = store.create_case("Mueller Praezisionstechnik GmbH")
    cid = meta["case_id"]
    print(f"1. Fall angelegt: {cid}  (Ablage: {store.root})")

    store.save_answers(cid, "unternehmen", json.loads(
        (SAMPLES / "antworten_unternehmen.json").read_text(encoding="utf-8")))
    ov = wf.case_overview(store, cid, today=today)
    print(f"2. Fragebogen Unternehmen: {ov['answers']['unternehmen']['answered']} Antworten, "
          f"fehlend: {ov['missing_answers']['unternehmen'] or 'nichts'}")
    wf.generate_letters(store, cid, today=today)
    store.set_stage(cid, "unterlagen_angefordert")
    print("3. Anforderungsschreiben an Unternehmen und Steuerberatung erzeugt")

    store.save_answers(cid, "steuerberater", json.loads(
        (SAMPLES / "antworten_steuerberater.json").read_text(encoding="utf-8")))
    for doc_type, name, meta_ in UPLOADS:
        store.add_document(cid, doc_type, name, (SAMPLES / name).read_bytes(), meta_)
    ov = wf.case_overview(store, cid, today=today)
    print(f"4. {len(UPLOADS)} Unterlagen hochgeladen; vollstaendig: {ov['documents_complete']}")
    for src, titles in ov["outstanding_documents"].items():
        for t in titles:
            print(f"     noch offen ({src}): {t}")
    if ov["documents_complete"]:
        store.set_stage(cid, "unterlagen_vollstaendig")

    res = wf.run_case_diagnostic(store, cid, today=today)
    if not res["ok"]:
        print("5. Diagnostik nicht moeglich:")
        for b in res["blocking"]:
            print(f"     - {b}")
        return
    s = res["summary"]
    print(f"5. Diagnostik: Band {s['band']} ({s['score']}) -> {s['band_after_remediation']} "
          f"({s['score_after_remediation']}) nach Massnahmen")
    print(f"   Einordnung: {s['verdict']}")
    print(f"   Befunde: {', '.join(f['rule'] + ' ' + f['title'] for f in s['findings'])}")
    print(f"   Kreditgebertyp nach Massnahmen: {s['top_lender_after']}")
    for n in res["notes"]:
        print(f"   Hinweis: {n}")

    row = wf.record_outcome(store, cid, {"outcome": "PENDING",
                                         "notes": "Demo - fiktiver Fall"})
    print(f"6. Ergebnis protokolliert: {row['outcome']} ({store.root / 'outcome_log.csv'})")
    print(f"\nArtefakte in {store.root / cid / 'artifacts'}:")
    for a in store.list_artifacts(cid):
        print(f"   {a}")


if __name__ == "__main__":
    main()
