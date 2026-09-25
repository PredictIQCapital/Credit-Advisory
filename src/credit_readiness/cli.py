"""Command-line interface.

    python -m credit_readiness diagnose data/samples/case_01.json -o output/
    python -m credit_readiness batch data/samples
    python -m credit_readiness datev export.csv --period-end 2026-06-30

Intake and engagement workflow:

    python -m credit_readiness serve --open                  website + portal
    python -m credit_readiness serve --demo --open           same, with fictional demo data
    python -m credit_readiness user add me@firma.de "Name" --password ...   advisor account
    python -m credit_readiness questionnaire unternehmen      printable questionnaire
    python -m credit_readiness documents                      document checklist
    python -m credit_readiness bank konto.csv --limit 500000  analyse bank export
    python -m credit_readiness case new "Firma GmbH"          engagement via CLI
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
from .reporting.summary import result_summary
from . import workflow as wf
from .auth import ROLE_BERATER, ROLES, AuthError, UserStore
from .casefile import OUTCOMES, CaseStoreError, LocalCaseStore
from .ingest.bank_csv import BankCsvError, analyse_bank_csv
from .intake.documents import DOCUMENT_TYPES
from .intake.questionnaire import AUDIENCES, get_questionnaire
from .reporting.forms import answers_template, documents_markdown, questionnaire_markdown
from .reporting.html import markdown_to_html


_result_summary = result_summary


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

    # ------------------------------------------------------------ intake
    p_serve = sub.add_parser("serve", help="Lokales Mandantenportal starten")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--data-dir", help="Ablage (Standard: data/clients)")
    p_serve.add_argument("--open", action="store_true", help="Browser oeffnen")
    p_serve.add_argument("--local", action="store_true",
                         help="Ordner statt Supabase verwenden, auch wenn .env gesetzt ist")
    p_serve.add_argument("--demo", action="store_true",
                         help="Demo mit fiktiven Unternehmen (Ablage data/demo)")
    p_serve.set_defaults(func=cmd_serve)

    p_user = sub.add_parser("user", help="Konten verwalten")
    p_user.add_argument("--data-dir", help="Ablage (Standard: data/clients)")
    p_user.add_argument("--local", action="store_true", help="Ordner statt Supabase")
    us = p_user.add_subparsers(dest="user_command", required=True)
    u = us.add_parser("add", help="Konto anlegen")
    u.add_argument("email")
    u.add_argument("name")
    u.add_argument("--role", choices=ROLES, default=ROLE_BERATER)
    u.add_argument("--password", required=True)
    u = us.add_parser("list", help="Konten auflisten")
    u = us.add_parser("passwd", help="Passwort setzen")
    u.add_argument("email")
    u.add_argument("--password", required=True)
    p_user.set_defaults(func=cmd_user)

    p_q = sub.add_parser("questionnaire", help="Fragebogen ausgeben")
    p_q.add_argument("audience", choices=AUDIENCES)
    p_q.add_argument("--format", choices=("md", "html", "json", "template"), default="md",
                     help="template = leere Antwortdatei zum Ausfuellen")
    p_q.add_argument("-o", "--out", help="Zieldatei")
    p_q.set_defaults(func=cmd_questionnaire)

    p_docs = sub.add_parser("documents", help="Unterlagenliste ausgeben")
    p_docs.add_argument("--format", choices=("md", "html", "json"), default="md")
    p_docs.add_argument("-o", "--out", help="Zieldatei")
    p_docs.set_defaults(func=cmd_documents)

    p_bank = sub.add_parser("bank", help="Kontoumsaetze (CSV) auswerten")
    p_bank.add_argument("file")
    p_bank.add_argument("--limit", type=float, help="Kontokorrentlimit in EUR")
    p_bank.set_defaults(func=cmd_bank)

    p_case = sub.add_parser("case", help="Faelle verwalten")
    p_case.add_argument("--data-dir", help="Ablage (Standard: data/clients)")
    cs = p_case.add_subparsers(dest="case_command", required=True)
    c = cs.add_parser("new", help="Fall anlegen")
    c.add_argument("company_name")
    c = cs.add_parser("list", help="Faelle auflisten")
    c = cs.add_parser("show", help="Stand eines Falls")
    c.add_argument("case_id")
    c = cs.add_parser("answers", help="Antworten (JSON) speichern")
    c.add_argument("case_id")
    c.add_argument("audience", choices=AUDIENCES)
    c.add_argument("file")
    c = cs.add_parser("upload", help="Unterlage hochladen")
    c.add_argument("case_id")
    c.add_argument("doc_type", choices=[d.id for d in DOCUMENT_TYPES])
    c.add_argument("file")
    c.add_argument("--period-end", help="Stichtag der SuSa, JJJJ-MM-TT")
    c.add_argument("--period-months", type=int, default=12)
    c.add_argument("--account-label", help="Bezeichnung des Kontos")
    c = cs.add_parser("diagnose", help="Diagnostik erstellen")
    c.add_argument("case_id")
    c = cs.add_parser("letters", help="Anforderungsschreiben erzeugen")
    c.add_argument("case_id")
    c = cs.add_parser("outcome", help="Ergebnis protokollieren")
    c.add_argument("case_id")
    c.add_argument("outcome", choices=OUTCOMES)
    c.add_argument("--lender-type", default="")
    c.add_argument("--amount", default="")
    c.add_argument("--rate", default="")
    c.add_argument("--weeks", default="")
    c.add_argument("--notes", default="")
    p_case.set_defaults(func=cmd_case)

    args = parser.parse_args(argv)
    return args.func(args)


# ---------------------------------------------------------------- intake commands


def _write_or_print(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"geschrieben: {out}")
    else:
        print(text)


def cmd_serve(args: argparse.Namespace) -> int:
    from .webapp.server import serve

    serve(host=args.host, port=args.port, data_dir=args.data_dir, open_browser=args.open,
          demo=args.demo, local=True if args.local else None)
    return 0


def cmd_user(args: argparse.Namespace) -> int:
    from .config import backends

    _, users, _, where = backends(args.data_dir, True if getattr(args, "local", False) else None)
    print(f"Ablage: {where}")
    try:
        if args.user_command == "add":
            p = users.create(args.email, args.name, args.role, args.password)
            print(f"Konto angelegt: {p.email} ({p.role})")
        elif args.user_command == "passwd":
            users.set_password(args.email, args.password)
            print("Passwort geaendert")
        else:
            for u in users.list():
                print(f"{u['role']:<14} {u['email']:<36} {u['name']}")
    except AuthError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_questionnaire(args: argparse.Namespace) -> int:
    q = get_questionnaire(args.audience)
    if args.format == "json":
        text = json.dumps(q.as_dict(), indent=2, ensure_ascii=False)
    elif args.format == "template":
        text = json.dumps(answers_template(q), indent=2, ensure_ascii=False)
    elif args.format == "html":
        text = markdown_to_html(questionnaire_markdown(q), q.title)
    else:
        text = questionnaire_markdown(q)
    _write_or_print(text, args.out)
    return 0


def cmd_documents(args: argparse.Namespace) -> int:
    if args.format == "json":
        text = json.dumps([d.as_dict() for d in DOCUMENT_TYPES], indent=2, ensure_ascii=False)
    elif args.format == "html":
        text = markdown_to_html(documents_markdown(), "Unterlagenliste")
    else:
        text = documents_markdown()
    _write_or_print(text, args.out)
    return 0


def cmd_bank(args: argparse.Namespace) -> int:
    try:
        a = analyse_bank_csv(Path(args.file), kontokorrent_limit=args.limit,
                             account_label=Path(args.file).name)
    except BankCsvError as exc:
        print(f"Kontoumsaetze nicht auswertbar: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(a.as_dict(), indent=2, ensure_ascii=False, default=str))
    return 0


def cmd_case(args: argparse.Namespace) -> int:
    store = LocalCaseStore(args.data_dir)
    cc = args.case_command
    try:
        if cc == "new":
            meta = store.create_case(args.company_name)
            print(f"Fall angelegt: {meta['case_id']}  ({store.root / meta['case_id']})")
        elif cc == "list":
            for m in store.list_cases():
                print(f"{m['case_id']}  {m['stage']:<24} {m['company_name']}")
        elif cc == "show":
            ov = wf.case_overview(store, args.case_id)
            print(json.dumps({k: ov[k] for k in (
                "stage_label", "answers", "missing_answers", "answer_errors",
                "outstanding_documents", "ready_for_diagnosis", "blocking",
                "assembly_notes", "latest_summary")}, indent=2, ensure_ascii=False, default=str))
        elif cc == "answers":
            data = json.loads(Path(args.file).read_text(encoding="utf-8"))
            store.save_answers(args.case_id, args.audience, data)
            ov = wf.case_overview(store, args.case_id)
            print(f"gespeichert. Fehlend: {ov['missing_answers'][args.audience] or 'nichts'}; "
                  f"Fehler: {ov['answer_errors'][args.audience] or 'keine'}")
        elif cc == "upload":
            meta = {}
            if args.period_end:
                meta = {"period_end": args.period_end, "period_months": args.period_months}
            if args.account_label:
                meta["account_label"] = args.account_label
            p = Path(args.file)
            entry = store.add_document(args.case_id, args.doc_type, p.name, p.read_bytes(), meta)
            print(f"hochgeladen: {entry['filename']} ({entry['doc_id']})")
        elif cc == "diagnose":
            res = wf.run_case_diagnostic(store, args.case_id)
            if not res["ok"]:
                print("Diagnostik nicht moeglich:", file=sys.stderr)
                for b in res["blocking"]:
                    print(f"  - {b}", file=sys.stderr)
                return 2
            s = res["summary"]
            print(f"Band {s['band']} ({s['score']}) -> {s['band_after_remediation']} "
                  f"({s['score_after_remediation']}); {s['verdict']}")
            print(f"Bericht: {store.root / args.case_id / 'artifacts' / 'diagnostik.html'}")
        elif cc == "letters":
            wf.generate_letters(store, args.case_id)
            print(f"Schreiben erzeugt in {store.root / args.case_id / 'artifacts'}")
        elif cc == "outcome":
            row = wf.record_outcome(store, args.case_id, {
                "outcome": args.outcome, "lender_type_routed": args.lender_type,
                "facility_amount_eur": args.amount, "rate_pct": args.rate,
                "weeks_to_decision": args.weeks, "notes": args.notes})
            print(f"protokolliert: {row['case_id']} {row['outcome']}")
    except CaseStoreError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
