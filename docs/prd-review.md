# Product plan review: what is built, what was added, what is left

Reviewed against *SME Loan Scoring & Lending Platform — Product Requirements
Document* (whiteboard transcription), 2026-09-24. Branch `prd-phase-1-2`.

## Phase 1 & 2 — status

| PRD item | Status | Where |
|---|---|---|
| 2.1.1 Account opening, profile | Existed | `auth.py`, portal registration |
| 2.1.2 Document upload under headings | Existed | `intake/documents.py`, portal |
| 2.1.2 Free-text note per upload | **Added** | upload `note`, shown next to the file |
| 2.1.3 Structured questions: amount, sector, prior rejection | Existed | `intake/questionnaire.py` (45 company questions) |
| 2.1.4 Ratios on a dashboard | Existed | `ratios.py`, portal result view |
| 2.1.4 AI/OCR extraction | Existed | `ai/extraction.py`: Claude reads scanned PDFs and images; figures count only after the company confirms them |
| 2.1.4 Projections (time-series) | **Added** | `projection.py`: damped trend, DSCR per year over the loan |
| 2.1.5 Industry comparison, Bundesbank | Existed | `benchmarks.py` |
| 2.1.5 Last 5 years of sector medians | **Added** | 2019–2023, each year from the newest edition that publishes it |
| 2.1.6 EBA exclusion first | Existed | `rejection_risk.py`: 8 knock-out checks, reported before the score (ADR-004) |
| 2.1.6 Weighted average of ratios | Existed | `scorecard.py` |
| 2.1.6 Bands differ by sector, generic fallback | **Added** | sector curves (ADR-005) |
| 2.2 Document list | **Extended** | cash flow statement; collateral split into free and pledged; 3 years of accounts |
| 2.3 Sector by NACE code | **Added** | `nace.py`: the WZ 2008 code determines the sector |
| 2.4.7 Scope for improvement for weak applicants | **Added** | `improvement.py`: target, points, euro gap, path to next band |
| 2.4.8 Alternative lenders (KfW, fintech, banks) | Existed | `routing.py`: 7 lender *types*; named institutions deliberately not listed (see 34c below) |
| 2.4.9 Collateral evaluation module | Not built | Flagged "longer-term" in the PRD. Collateral is captured, not valued. |

One design choice differs from the PRD wording. The PRD says to run the
exclusion rules and only then score. The engine runs both and reports the
knock-outs first. A company with tax arrears still gets its score and
improvement plan, because it needs both to know what to fix.

## Open items from PRD section 5

| Item | Answer |
|---|---|
| "BAW" | Almost certainly **BWA**, the Betriebswirtschaftliche Auswertung (monthly management accounts from DATEV). Already on the list as mandatory. |
| Years of statements | Asked for **3**; **2** are required, because young companies and many banks work with two. Confirm whether 3 should become mandatory. |
| Financial plan threshold | **€100,000**, already implemented as a conditional requirement. |
| Onboarding questions | 45 company and 20 tax-advisor questions exist, each with its reason; see `docs/intake/`. |
| Bundesbank 5-year data, licensing | Published free by the Bundesbank. Seven editions (reporting years 2016–2023) are extracted in `data/reference/bundesbank/`. |
| Comparable-company ratios | Same source: the quartiles are firm-level, by sector and revenue class. |
| EBA exclusion criteria | EBA/GL/2020/06 sets no hard rules; the eight encoded knock-outs and their sources are in ADR-004. |
| Phase 3 flow (Case 1 vs 2) | Still open; see below before deciding. |
| "BR platform" by "Praxa/Pravea" | Could not identify. Please supply the name. |

## Phase 3 and 4 — not built, and why

These phases change the regulatory position of the business. The code is not
the hard part, so each needs a legal decision before any build. The current
architecture keeps all of them possible later (`docs/regulatory-guardrails.md`).

| Feature | What it triggers | Decision needed |
|---|---|---|
| Lender feed, SME–lender matching (Cases 1–2) | **§34c GewO** credit brokering once placement is paid for. Sending scores to many banks also looks closer to *distributing* ratings under the EU CRA Regulation. | Fee model; lawyer review of the CRA question; explicit per-lender GDPR consent from each SME. |
| Automated loan agreement generation | The contract is the lender's. Drafting it for third parties is a legal service (**RDG**), and terms that change automatically are pricing decisions that belong to the lender. | Whether this is a white-label tool the lender operates, rather than our product. |
| Bill discounting / factoring | Factoring is a financial service under **§1 Abs. 1a Nr. 9 KWG** (BaFin licence) if we run it; referring to a partner is brokering. | Partner model only, via the unnamed "BR platform". |
| Cross-sell: insurance | **§34d GewO** insurance intermediary. | Registration, or referral without commission. |
| Cross-sell: credit cards, overdraft | Issuing is a licensed activity; referring is brokering (§34c). | As for the lender feed. |

Recommended order: first run the Phase 1–2 engine on the first real client
files, as the README already says; the outcome log is the asset. Resolve the
§34c question with a lawyer. Then build the Phase 3 lender feed as a
consent-based export of the released report, not as a live API.

## Still to do on this branch's work

- **Methodology documents** (`docs/methodik/`, DE and EN PDFs): add sector
  curves, NACE classification, projection and improvement plan. They currently
  describe all-sector anchoring only.
- **Named lenders in routing**: kept at the type level on purpose (§34c).
