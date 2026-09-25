"""Copy a local data folder (cases, files, accounts, outcome log) into Supabase.

    python scripts/migrate_to_supabase.py data/demo            # the demo, passwords demo1234
    python scripts/migrate_to_supabase.py data/clients         # client data, new temp passwords
    python scripts/migrate_to_supabase.py data/demo --replace  # overwrite cases already there

Case ids, document ids, dates and every record are kept as they are, so links,
letters and the agreement proofs stay valid. Passwords cannot move: the folder
store keeps PBKDF2 hashes, Supabase Auth keeps its own. Demo accounts get the
demo password again; any other account gets a random temporary password,
printed once, to be changed on first login.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from credit_readiness.auth import UserStore  # noqa: E402
from credit_readiness.casefile import LocalCaseStore  # noqa: E402
from credit_readiness.casefile_supabase import LOGO_TYPES, _MIME  # noqa: E402
from credit_readiness.config import supabase_client  # noqa: E402
from credit_readiness.demo import DEMO_PASSWORD  # noqa: E402
from credit_readiness.supa import SupabaseError, q  # noqa: E402


def migrate_users(sb, src: UserStore, demo: bool) -> list[tuple[str, str]]:
    temp = []
    existing = {u["email"] for u in sb.select("users", "select=email")}
    for u in src._load().values():
        if u["email"] in existing:
            print(f"  account  {u['email']}: already there, kept")
            continue
        pw = DEMO_PASSWORD if demo else secrets.token_urlsafe(12)
        user = sb.admin_create_user(u["email"], pw, u["name"])
        sb.insert("users", {"email": u["email"], "name": u["name"], "role": u["role"],
                            "auth_id": user["id"], "created_at": u.get("created_at")}, returning=False)
        if not demo:
            temp.append((u["email"], pw))
        print(f"  account  {u['email']} ({u['role']})")
    return temp


def migrate_case(sb, src: LocalCaseStore, case_id: str, replace: bool) -> None:
    if sb.select("cases", f"case_id=eq.{q(case_id)}&select=case_id"):
        if not replace:
            print(f"  case     {case_id}: already there, skipped (--replace to overwrite)")
            return
        from credit_readiness.casefile_supabase import SupabaseCaseStore
        SupabaseCaseStore(sb).delete_case(case_id)
    meta = src.get_meta(case_id)
    sb.insert("cases", {"case_id": case_id, "meta": meta, "company_name": meta["company_name"],
                        "stage": meta["stage"], "created_at": meta["created_at"],
                        "updated_at": meta.get("updated_at", meta["created_at"])}, returning=False)
    for aud in ("unternehmen", "steuerberater"):
        answers = src.load_answers(case_id, aud)
        if answers:
            sb.insert("answers", {"case_id": case_id, "audience": aud, "data": answers}, returning=False)
    docs = src.list_documents(case_id)
    for d in docs:
        path = f"{case_id}/{d['doc_id']}/{d['filename']}"
        sb.upload(path, src.read_document(case_id, d["doc_id"]),
                  _MIME.get(d["filename"].rsplit(".", 1)[-1].lower(), "application/octet-stream"))
        sb.insert("documents", {"doc_id": d["doc_id"], "case_id": case_id, "doc_type": d["doc_type"],
                                "filename": d["filename"], "storage_path": path, "size": d["size"],
                                "sha256": d["sha256"], "uploaded_at": d["uploaded_at"],
                                "meta": d.get("meta") or {}}, returning=False)
    arts = src.list_artifacts(case_id)
    for name in arts:
        sb.insert("artifacts", {"case_id": case_id, "name": name,
                                "content": src.read_artifact(case_id, name)}, returning=False)
    n_rec = 0
    for kind in ("agreements", "messages"):
        for r in src.list_records(case_id, kind):
            sb.insert("records", {"case_id": case_id, "kind": kind, "record": r}, returning=False)
            n_rec += 1
    logo = src.get_logo(case_id)
    if logo:
        ext = next(e for e, t in LOGO_TYPES.items() if t == logo[1])
        sb.upload(f"{case_id}/logo.{ext}", logo[0], logo[1])
        meta["logo_ext"] = ext
        sb.update("cases", f"case_id=eq.{q(case_id)}", {"meta": meta})
    print(f"  case     {case_id} {meta['company_name']}: {len(docs)} files, {len(arts)} outputs, "
          f"{n_rec} records{', logo' if logo else ''}")


def sync_counters(sb) -> None:
    """Continue numbering after the highest case id per year."""
    top: dict[int, int] = {}
    for r in sb.select("cases", "select=case_id"):
        _, year, n = r["case_id"].split("-")
        top[int(year)] = max(top.get(int(year), 0), int(n))
    for year, n in top.items():
        sb.insert("case_counters", {"year": year, "last_number": n}, upsert=True, returning=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="local data folder, e.g. data/demo")
    ap.add_argument("--replace", action="store_true", help="overwrite cases that already exist")
    args = ap.parse_args()
    folder = (ROOT / args.folder).resolve() if not Path(args.folder).is_absolute() else Path(args.folder)
    if not folder.is_dir():
        print(f"{folder} not found")
        return 1
    demo = folder.name == "demo"
    sb = supabase_client()
    src = LocalCaseStore(folder)
    print(f"from {folder}\nto   {sb.url}\n")
    try:
        temp = migrate_users(sb, UserStore(folder), demo)
        for meta in sorted(src.list_cases(), key=lambda m: m["case_id"]):
            migrate_case(sb, src, meta["case_id"], args.replace)
        outcomes = src.read_outcomes()
        if outcomes:
            known = {r["row"].get("case_id") for r in sb.select("outcomes", "select=row")}
            new = [o for o in outcomes if o.get("case_id") not in known]
            for o in new:
                sb.insert("outcomes", {"row": o}, returning=False)
            print(f"  outcomes {len(new)} new row(s)")
        sync_counters(sb)
    except SupabaseError as e:
        print(f"\nStopped: {e}")
        return 1
    if temp:
        print("\nTemporary passwords (shown once -- hand over securely, change on first login):")
        for email, pw in temp:
            print(f"  {email}: {pw}")
    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
