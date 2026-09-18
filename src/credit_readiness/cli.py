"""Command-line interface.

    python -m credit_readiness diagnose data/samples/case_01.json -o output/
    python -m credit_readiness batch data/samples
    python -m credit_readiness datev export.csv --period-end 2026-06-30
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .engine import run_diagnostic
from .remediation import Verdict
from .validation import Severity, ValidationError
from .ingest.datev import DatevMappingError, parse_datev_susa
from .ingest.json_intake import load_case_file
from .reporting.report import render_markdown


def _result_summary(result) -> dict:
    return {
        "case_id": result.case.case_id,
        "company": result.case.profile.name,
        "sector": result.case.profile.sector.value,
        "band": result.scorecard.band.value,
        "score": result.scorecard.total_score,
        "verdict": result.verdict.value,
        "engageable": result.is_engageable,
        "score_after_remediation": result.simulation.after_score,
        "band_after_remediation": result.simulation.after_band,
        "delta": result.simulation.delta,
        "findings": [
            {
                "rule": f.rule_id,
                "title": f.title,
                "category": f.category.value,
                "severity": f.severity,
                "fixable": f.category.is_fixable,
            }
            for f in result.findings
        ],
        "top_lender_now": next(
            (o.lender.name for o in result.routing_now if o.eligible), None
        ),
        "top_lender_after": next(
            (o.lender.name for o in result.routing_after if o.eligible), None
        ),
    }


def cmd_diagnose(args: argparse.Namespace) -> int:
    case = load_case_file(args.case)
    try:
        result = run_diagnostic(case, strict=not args.allow_invalid)
    except ValidationError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "\nAbbruch: Die Eingabedaten sind nicht plausibel. Mit --allow-invalid "
            "kann die Pruefung uebergangen werden (nur fuer Explorationszwecke).",
            file=sys.stderr,
        )
        return 2

    for issue in result.data_warnings:
        print(f"{issue}", file=sys.stderr)

    if args.json:
        print(json.dumps(_result_summary(result), indent=2, ensure_ascii=False))
        return 0

    report = render_markdown(result)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{case.case_id}_diagnostik.md"
        target.write_text(report, encoding="utf-8")
        print(f"Bericht geschrieben: {target}")
    else:
        print(report)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    files = sorted(folder.glob("*.json"))
    if not files:
        print(f"Keine Faelle in {folder}", file=sys.stderr)
        return 1

    summaries = []
    for f in files:
        try:
            result = run_diagnostic(load_case_file(f), strict=not args.allow_invalid)
        except Exception as exc:  # noqa: BLE001 - batch must not die on one case
            print(f"FEHLER in {f.name}: {exc}", file=sys.stderr)
            continue
        summaries.append(_result_summary(result))
        if args.out:
            out_dir = Path(args.out)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{result.case.case_id}_diagnostik.md").write_text(
                render_markdown(result), encoding="utf-8"
            )

    hdr = f"{'Fall':<10} {'Unternehmen':<28} {'Band':<5} {'Score':>6} {'->':^4} {'Score':>6} {'Band':<5} {'Einordnung'}"
    print(hdr)
    print("-" * len(hdr))
    for s in summaries:
        print(
            f"{s['case_id']:<10} {s['company'][:27]:<28} {s['band']:<5} "
            f"{s['score']:>6.1f} {'->':^4} {s['score_after_remediation']:>6.1f} "
            f"{s['band_after_remediation']:<5} {s['verdict']}"
        )

    # Three distinct buckets. Lumping 'already bankable' in with 'genuine risk'
    # would corrupt the very split this pipeline exists to measure.
    engageable = sum(1 for s in summaries if s["engageable"])
    genuine = sum(1 for s in summaries if s["verdict"] == Verdict.GENUINE_RISK.value)
    bankable = sum(1 for s in summaries if s["verdict"] == Verdict.ALREADY_BANKABLE.value)
    total = len(summaries)

    print()
    print(f"Faelle gesamt:                      {total}")
    print(f"  bearbeitbar (behebbar):           {engageable}")
    print(f"  bereits finanzierbar:             {bankable}")
    print(f"  substanzielles Kreditrisiko:      {genuine}")
    if total:
        print()
        print(
            f"Behebbar-Quote: {engageable/total*100:.0f}% "
            "(Planannahme des Blueprints: 33-50% der Problemfaelle)"
        )
    print(
        "\nHinweis: synthetische Testfaelle. Diese Quote validiert die "
        "Blueprint-Annahme NICHT -- dafuer braucht es echte Mandate."
    )

    if args.out:
        log = Path(args.out) / "batch_summary.json"
        log.write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Zusammenfassung: {log}")
    return 0


def cmd_datev(args: argparse.Namespace) -> int:
    try:
        balance, income, diag = parse_datev_susa(
            args.file,
            period_end=date.fromisoformat(args.period_end),
            period_months=args.period_months,
            kontenrahmen=args.kontenrahmen,
        )
    except DatevMappingError as exc:
        print(f"DATEV-Zuordnung fehlgeschlagen: {exc}", file=sys.stderr)
        return 2

    print(f"Zugeordnet: {diag['mapped_volume']:,.2f} EUR")
    print(
        f"Nicht zugeordnet: {diag['unmapped_volume']:,.2f} EUR "
        f"({diag['unmapped_share']*100:.2f}%)"
    )
    print()
    print(f"Bilanzsumme:            {balance.bilanzsumme:>15,.2f} EUR")
    print(f"Wirtschaftliches EK:    {balance.wirtschaftliches_eigenkapital:>15,.2f} EUR")
    print(f"Finanzverbindlichkeiten:{balance.finanzverbindlichkeiten:>15,.2f} EUR")
    print(f"Umsatzerloese:          {income.umsatzerloese:>15,.2f} EUR")
    print(f"EBITDA:                 {income.ebitda:>15,.2f} EUR")
    print(f"EBIT:                   {income.ebit:>15,.2f} EUR")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="credit_readiness",
        description="Kreditfaehigkeits-Diagnostik fuer deutsche/oesterreichische KMU",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_diag = sub.add_parser("diagnose", help="Einen Fall analysieren")
    p_diag.add_argument("case", help="Pfad zur Fall-JSON")
    p_diag.add_argument("-o", "--out", help="Ausgabeverzeichnis fuer den Bericht")
    p_diag.add_argument("--json", action="store_true", help="Kurzfassung als JSON")
    p_diag.add_argument(
        "--allow-invalid",
        action="store_true",
        help="Plausibilitaetspruefung uebergehen (nur Exploration)",
    )
    p_diag.set_defaults(func=cmd_diagnose)

    p_batch = sub.add_parser("batch", help="Alle Faelle eines Verzeichnisses")
    p_batch.add_argument("folder", help="Verzeichnis mit Fall-JSONs")
    p_batch.add_argument("-o", "--out", help="Ausgabeverzeichnis")
    p_batch.add_argument(
        "--allow-invalid", action="store_true", help="Plausibilitaetspruefung uebergehen"
    )
    p_batch.set_defaults(func=cmd_batch)

    p_datev = sub.add_parser("datev", help="DATEV-SuSa einlesen und pruefen")
    p_datev.add_argument("file", help="Pfad zur SuSa-CSV")
    p_datev.add_argument("--period-end", required=True, help="YYYY-MM-DD")
    p_datev.add_argument("--period-months", type=int, default=12)
    p_datev.add_argument("--kontenrahmen", default="SKR04")
    p_datev.set_defaults(func=cmd_datev)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
