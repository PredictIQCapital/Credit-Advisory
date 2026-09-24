# Credit Readiness Advisory

Diagnostic engine for German and Austrian SME credit files.

It answers one question: **if this file went to a lender today, which factors
would pull it below an approvable line — and which of those are fixable before
the client ever reapplies?**

> **This is not a credit rating tool.** It produces a directional readiness
> indication, never a rating or a probability of default. See
> [docs/regulatory-guardrails.md](docs/regulatory-guardrails.md) — that boundary
> is enforced in code and covered by tests.

---

## Quick start

**See it working (demo):** double-click **`start_demo.bat`**, or run

```bash
python -m credit_readiness serve --demo --open      # http://127.0.0.1:8766 via the .bat
```

This starts three pages with four fictional companies:

| Page | For whom |
|---|---|
| `/` | the public website: what we do, how it works, pricing (DE/EN) |
| `/investors` | investor one-pager: problem, solution, market, model, status |
| `/app` | the portal: log in or register, then a view per role |

Companies get a workspace: a sidebar that opens on hover (overview, company,
financing, documents, figures, result, plan, history) and a dashboard with
score, next steps, ratios against the sector, plan, company data, document
status and recent activity. Annual accounts and trial balances are uploaded
into a grid of statements by fiscal year; every document can carry a note.

Demo logins (password `demo1234`, also shown as one-click buttons on the login page):

| Login | Role | What you see |
|---|---|---|
| `berater@demo.de` | advisor | pipeline of all cases; run analysis; release reports; letters; outcomes |
| `anna.mueller@demo.de` | company | workspace complete; released report: fixable, B -> A |
| `elif.yilmaz@demo.de` | company | the honest no: genuine credit risk, advised not to apply |
| `jan.petersen@demo.de` | company | free quick check done (band C), documents still open |
| `jonas.weber@demo.de` | company | just registered: empty workspace, next steps on the dashboard |
| `kanzlei@demo.de` | tax advisor | only its clients' cases; confirmations, uploads, sign-off sheet |

Delete `data/demo/` to reset the demo; it is re-created on the next start.

**Real use:** double-click **`start_portal.bat`** (data in `data/clients/`). Create your
advisor account first:

```bash
python -m credit_readiness user add you@firm.de "Your Name" --role berater --password "..."
```

Companies then register themselves on the website, or you create a case and invite them.

The portal is the everyday tool: create a case, fill in or import the two
questionnaires, upload documents, generate the request letters, run the
diagnostic, print the report, record the outcome. Everything it does is also
available from the command line:

```bash
python -m credit_readiness case new "Firma GmbH"
python -m credit_readiness case answers CRA-2026-0001 unternehmen antworten.json
python -m credit_readiness case upload CRA-2026-0001 susa_aktuell susa.csv --period-end 2025-12-31
python -m credit_readiness case upload CRA-2026-0001 kontoumsaetze konto.csv
python -m credit_readiness case letters CRA-2026-0001
python -m credit_readiness case diagnose CRA-2026-0001
python -m credit_readiness case outcome CRA-2026-0001 APPROVED_BETTER_TERMS --amount 750000

python -m credit_readiness questionnaire unternehmen --format html -o fragebogen.html
python -m credit_readiness documents                         # document checklist
python -m credit_readiness bank konto.csv --limit 500000     # analyse a bank export
```

To see a complete engagement run end to end on fictional data:

```bash
python scripts/generate_intake_samples.py   # questionnaires, DATEV exports, bank CSV, PDFs
python scripts/demo_intake_flow.py          # case -> uploads -> letters -> diagnostic -> outcome
```

Hand-built cases and the batch mode still work:

```bash
python scripts/generate_samples.py
python -m credit_readiness batch data/samples
python -m credit_readiness diagnose data/samples/case_01_mueller_praezisionstechnik.json -o output/
```

Sample output:

```
Fall       Unternehmen                  Band   Score  ->   Score Band  Einordnung
CASE-01    Mueller Praezisionstechnik   B       65.6  ->    78.4 A     behebbar - Struktur
CASE-02    Nordlicht Handel GmbH & Co.  C       52.3  ->    63.6 C     behebbar - Struktur
CASE-03    Gastro Rheinblick GmbH       E        4.5  ->     8.4 E     substanzielles Kreditrisiko
CASE-06    Hoffmann Medizintechnik      A       90.8  ->    90.8 A     bereits finanzierbar
```

## Products

| Tier | Price (indicative) | What happens |
|---|---|---|
| **Credit check** | free | Company uploads its annual accounts, the reader (local rules or Claude) proposes the figures, the company confirms them, answers ~12 questions, and gets an instant readiness band + top 3 weaknesses with a plain-language explanation |
| **Full report** | EUR 390 | Complete questionnaire and documents, full diagnostic, reviewed and released by an advisor |
| **Advisory** | from EUR 1,500 | Calls, Steuerberater sign-off, support up to the bank meeting |

**AI reads and explains; transparent rules decide.** See
[docs/ai-and-data-protection.md](docs/ai-and-data-protection.md). By default the
local reader is used and no data leaves the machine. To use Claude:

```bash
pip install "credit-readiness[ai]"          # anthropic SDK
set CRA_AI_PROVIDER=anthropic                # plus Anthropic credentials (ANTHROPIC_API_KEY)
```

Only do this after the data processing agreement with the provider is in place.

## What it does

**Intake** (see [docs/inputs-outputs.md](docs/inputs-outputs.md) for every input and output):

- **Two questionnaires**: 45 questions for the company, 20 for its Steuerberater.
  The company's WZ 2008 / NACE code, when given, determines its sector.
  Each question says *why* it is asked. Printable versions in [docs/intake/](docs/intake/).
- **Document catalogue**: 15 document types, who supplies each, required or
  conditional, accepted formats, and why it matters.
- **Automatic reading** of the two structured sources: the DATEV Summen- und
  Saldenliste (current and prior year) and bank-statement CSVs (days at the
  overdraft limit, returned direct debits). PDFs are filed, never OCR'd.
- **Case assembly** with a strict precedence (bank data > Steuerberater > client)
  and a provenance record for every contested figure.
- **Letters**: document requests to the client and the Steuerberater, listing only
  what is still missing, and a sign-off letter for every proposed reclassification.
- **Outcome log**: one row per engagement, the proprietary dataset from client one.

**Diagnostic:**

1. **Validate** — refuses to analyse a file whose balance sheet does not balance.
   A confident diagnostic from a broken input is this business's worst failure mode.
2. **Compute ratios** — the metrics a German bank's rating engine actually uses,
   annualised correctly when working from a mid-year BWA.
3. **Score** — transparent weighted scorecard, piecewise-linear over published
   thresholds. Every factor exposes its value, weight, and points lost. The
   Bundesbank-calibrated factors are anchored to the client's own sector and
   revenue class ([ADR-005](docs/decisions/ADR-005-sector-specific-scoring.md));
   the all-sector score is shown alongside.
4. **Diagnose** — classify each weakness as `Darstellung`, `Unterlagen`,
   `Produktwahl`, `Besicherung`, or `substanzielles Kreditrisiko`.
5. **Simulate** — apply the remediations to a copy and show before/after.
6. **Route** — rank lender *types* for the current and the corrected profile.
   **Improve** — for each ratio below the sector-typical level: the target,
   the points it would add, and the gap in euros on the client's own balance
   sheet. **Project** — revenue, EBITDA and debt service coverage over the
   coming years, next to the stress scenarios.
7. **Report** — a German-language client report with the disclaimer on every page.

### The distinction the whole business rests on

The blueprint's thesis is that a meaningful share of rejected German SMEs are
creditworthy but *presented* badly. The engine is built to separate those two
populations honestly:

```
Gesellschafterdarlehen ohne Rangruecktritt   -> Darstellung      -> fixable in 2 weeks
Dauerinanspruchnahme des Kontokorrents       -> Produktwahl      -> fixable in 8 weeks
Besicherungsluecke bei tragfaehigem DSCR     -> Besicherung      -> KfW / Buergschaftsbank
EBITDA negativ, Umsatz -21%, Steuerrueckstaende -> KREDITRISIKO  -> decline the engagement
```

`R08` refuses to simulate substantive weakness away, and one substantive finding
outranks any number of cosmetic ones. **Declining those cases is the product
working correctly** — polishing a distressed file produces a better-looking
rejection and poisons the outcome dataset that is meant to become the moat.

## Architecture

```
src/credit_readiness/
├── models.py        HGB 266 / 275 domain objects; economic-equity restatement
├── validation.py    input plausibility; ERROR blocks by default
├── ratios.py        ratio computation, partial-year annualisation
├── scorecard.py     factor weights, breakpoints, banding    [REGULATORY]
├── remediation.py   fixability rules R01-R10 + simulation   [CORE IP]
├── routing.py       lender-type matching                    [REGULATORY]
├── benchmarks.py    sector quartiles + 5-year history, Bundesbank [REAL DATA]
├── nace.py          WZ 2008 / NACE code -> benchmark sector
├── improvement.py   ratio gaps to the sector-typical level, in points and EUR
├── projection.py    damped-trend projection of DSCR over the loan
├── engine.py        orchestrator -> DiagnosticResult
├── ai/              document reading (rules | Claude), explanations, guardrails, audit log
├── intake/          questionnaires, document catalogue, case assembly
├── ingest/          json_intake (canonical), datev (SKR04), bank_csv
├── casefile.py      CaseStore interface + local folder store   [SWAP FOR DATABASE]
├── auth.py          accounts, roles, sessions (PBKDF2)          [SWAP FOR DATABASE]
├── demo.py          fictional demo companies for presentations
├── workflow.py      overview, diagnose, letters, outcome (used by portal and CLI)
├── reporting/       report, HTML, letters, printable forms, summary JSON
├── webapp/          website, investor page, portal (API + front end, DE/EN)
├── formatting.py    German number format for all client documents
└── cli.py           diagnose / batch / datev / serve / case / questionnaire / bank
```

Zero runtime dependencies — standard library only, including the portal.
`pytest` for tests.

### Connecting GitHub, Vercel and a database later

The code is arranged so these are additions, not rewrites:

- **Database / file storage**: implement the `CaseStore` interface in
  `casefile.py` (about a dozen methods). The portal, CLI and workflow only talk
  to that interface.
- **Hosted web app**: `webapp/server.py` is a thin HTTP layer over `workflow.py`.
  A production deployment replaces that one file (and adds authentication, TLS,
  EU hosting). The front end in `webapp/static/` talks to a plain JSON API.
- **GitHub**: `git remote add origin <url> && git push -u origin <branch>`.

## Before the first paying client

Four things in this repo are deliberately unfinished, and each is flagged in the
code it affects:

| Item | Where | What is needed |
|---|---|---|
| ~~Sector benchmarks are placeholder numbers~~ **done** | `benchmarks.py` | Loaded from the Bundesbank *Verhältniszahlen* (firm-level quartiles, by sector and revenue class). Three scorecard factors are now calibrated against that distribution — see [ADR-002](docs/decisions/ADR-002-bundesbank-calibration.md). Re-run the importer when a new edition appears. |
| **DATEV mapping is uncalibrated** | `ingest/datev.py` | Validate SKR04 ranges against three real Steuerberater exports. SKR03 raises rather than guessing. |
| **Six of ten scorecard factors are still convention** | `scorecard.py` | Equity, EBIT margin and quick ratio are anchored to the Bundesbank distribution; debt service capacity, leverage, interest cover, overdraft use, reporting cadence and payment behaviour have no published series and need real placement outcomes. |
| **34c GewO applicability** | `docs/regulatory-guardrails.md` | Paid legal consultation, driven by the chosen fee structure. |

The outcome log is the asset. Every engagement — flagged weaknesses, remediation
applied, lender type routed to, approved or not — is appended to
`data/clients/outcome_log.csv` by the portal ("Ergebnis" tab) from client one;
`data/reference/outcome_log.csv` documents the columns. Early on it is a spreadsheet,
not a model. It is what eventually lets the thresholds move from generic
convention to something calibrated on this business's own placement history.

## Data handling

Client data never enters version control. `.gitignore` excludes `data/clients/`
and `*_client_*.json`. Everything in `data/samples/` is **fictional**, generated
by `scripts/generate_samples.py`, and must never be presented as evidence about
the real market. The same holds for `data/samples/intake/`, generated by
`scripts/generate_intake_samples.py`.

The portal binds to `127.0.0.1` only. It has accounts and roles, but it is a
tool for the founder's own machine (with disk encryption on), not yet a hosted
service -- see docs/regulatory-guardrails.md for what hosting requires.

## Status

Phase 0: the diagnostic engine plus a complete local intake workflow
(questionnaires, uploads, letters, portal, outcome log), validated on synthetic
cases. A case assembled from uploaded questionnaires, DATEV exports and a bank
statement reproduces the hand-built reference case exactly. Per the
blueprint's own build order, the honest MVP is this engine run manually on the
first handful of real client files — automate a layer only once real volume makes
the manual version the bottleneck.

585 tests, all passing.

The product plan (PRD) is checked against this build in
[docs/prd-review.md](docs/prd-review.md), including why Phases 3 and 4 wait
for a legal decision.
