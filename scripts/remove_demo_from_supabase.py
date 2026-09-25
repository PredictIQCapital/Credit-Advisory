"""Remove the fictional demo companies and accounts from Supabase.

    python scripts/remove_demo_from_supabase.py          # show what would go
    python scripts/remove_demo_from_supabase.py --yes    # remove it

Run this before the first real client. Only accounts from demo.DEMO_USERS
and cases whose members are all demo accounts are touched; anything a real
person registered stays.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from credit_readiness.config import backends  # noqa: E402
from credit_readiness.demo import DEMO_USERS  # noqa: E402


def main() -> int:
    store, users, _, where = backends(local=False)
    demo_emails = {u[0] for u in DEMO_USERS}
    cases = []
    for meta in store.list_cases():
        members = {e for emails in (meta.get("members") or {}).values() for e in emails}
        if members and members <= demo_emails:
            cases.append(meta)
    accounts = [u["email"] for u in users.list() if u["email"] in demo_emails]
    print(f"{where}\n")
    for m in cases:
        print(f"  case     {m['case_id']}  {m['company_name']}")
    for e in accounts:
        print(f"  account  {e}")
    if not cases and not accounts:
        print("  no demo data found")
        return 0
    if "--yes" not in sys.argv:
        print("\nNothing removed. Run again with --yes to remove the above.")
        return 0
    for m in cases:
        store.delete_case(m["case_id"])
    for e in accounts:
        users.delete(e)
    print(f"\nremoved {len(cases)} case(s) and {len(accounts)} account(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
