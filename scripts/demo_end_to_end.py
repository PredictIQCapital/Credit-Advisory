"""End-to-end demonstration: raw DATEV export -> validated case -> diagnostic.

Shows the complete intake path a real engagement follows, and proves that the
DATEV route produces the same result as the hand-built JSON case.

Run:  python scripts/demo_end_to_end.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from credit_readiness import run_diagnostic                      # noqa: E402
from credit_readiness.ingest import parse_datev_susa             # noqa: E402
from credit_readiness.models import (                            # noqa: E402
    BehavioralData,
    ClientCase,
    CompanyProfile,
    FinancingRequest,
    LegalForm,
    LoanFacility,
    Sector,
)
from credit_readiness.reporting import render_markdown           # noqa: E402
from credit_readiness.validation import Severity, validate       # noqa: E402


def main() -> None:
    csv_path = ROOT / "data" / "samples" / "datev_susa_example.csv"

    print("1. DATEV-SuSa einlesen")
    balance, income, diag = parse_datev_susa(csv_path, period_end=date(2025, 12, 31))
    print(f"   zugeordnet {diag['mapped_volume']:,.0f} EUR, "
          f"nicht zugeordnet {diag['unmapped_share']*100:.2f}%")

    # A trial balance cannot know these. They come from the intake questionnaire,
    # and R01 in particular turns on the Rangruecktritt flag.
    balance.gesellschafterdarlehen_rangruecktritt = False
    balance.kontokorrent_limit = 500_000
    balance.kontokorrent_inanspruchnahme = 420_000

    case = ClientCase(
        case_id="DATEV-01",
        profile=CompanyProfile(
            name="Mueller Praezisionstechnik GmbH",
            legal_form=LegalForm.GMBH,
            sector=Sector.MANUFACTURING,
            employees=45,
            founded_year=2009,
        ),
        balance_sheet=balance,
        income_statement=income,
        facilities=[
            LoanFacility("Sparkasse Ostalb", "Tilgungsdarlehen",
                         2_000_000, 1_250_000, 0.048, 180_000),
            LoanFacility("Sparkasse Ostalb", "Kontokorrent",
                         500_000, 420_000, 0.095, 0),
        ],
        behavior=BehavioralData(
            bwa_age_months=5,
            bwa_frequency="quartalsweise",
            creditreform_bonitaetsindex=248,
            days_beyond_terms=6,
            overdraft_days_at_limit_12m=95,
        ),
        request=FinancingRequest(750_000, "Investition", 7, 400_000, 16),
    )

    print("\n2. Plausibilitaetspruefung")
    issues = validate(case)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    print(f"   Fehler: {len(errors)}   Warnungen/Hinweise: {len(issues) - len(errors)}")
    for issue in issues:
        print(f"     {issue}")

    print("\n3. Diagnostik")
    result = run_diagnostic(case)
    print(f"   Band {result.scorecard.band.value} "
          f"({result.scorecard.total_score}/100)  ->  "
          f"{result.simulation.after_band} ({result.simulation.after_score}) "
          "nach Massnahmen")
    print(f"   Einordnung: {result.verdict.value}")

    print(f"\n4. Befunde ({len(result.findings)})")
    for f in result.findings:
        print(f"   {f.rule_id}  {f.category.value:<28} {f.title}")

    print("\n5. Lender-Fit (aktuell moeglich)")
    for o in [o for o in result.routing_now if o.eligible][:3]:
        print(f"   {o.lender.name} (Fit {o.fit_score:.0f})")

    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    target = out / "DATEV-01_diagnostik.md"
    target.write_text(render_markdown(result), encoding="utf-8")
    print(f"\nBericht geschrieben: {target}")


if __name__ == "__main__":
    main()
