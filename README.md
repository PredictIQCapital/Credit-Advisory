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

```bash
git clone <this repo> && cd credit-readiness-advisory
python -m pip install -e ".[dev]"

python -m credit_readiness serve --open     # client portal on http://127.0.0.1:8765
python -m pytest -q
```

On Windows, double-click **`start_portal.bat`** instead; it starts the portal
and opens the browser, with no installation step.

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
CASE-01    Mueller Praezisionstechnik   C       64.5  ->    83.4 A     behebbar - Struktur
CASE-02    Nordlicht Handel GmbH & Co.  D       46.1  ->    61.3 C     behebbar - Struktur
CASE-03    Gastro Rheinblick GmbH       E        3.6  ->     7.7 E     substanzielles Kreditrisiko
CASE-06    Hoffmann Medizintechnik      A       97.4  ->    97.4 A     bereits finanzierbar
```

## What it does

**Intake** (see [docs/inputs-outputs.md](docs/inputs-outputs.md) for every input and output):

- **Two questionnaires**: 41 questions for the company, 20 for its Steuerberater.
  Each question says *why* it is asked. Printable versions in [docs/intake/](docs/intake/).
- **Document catalogue**: 14 document types, who supplies each, required or
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
   thresholds. Every factor exposes its value, weight, and points lost.
4. **Diagnose** — classify each weakness as `Darstellung`, `Unterlagen`,
   `Produktwahl`, `Besicherung`, or `substanzielles Kreditrisiko`.
5. **Simulate** — apply the remediations to a copy and show before/after.
6. **Route** — rank lender *types* for the current and the corrected profile.
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
├── benchmarks.py    sector medians                          [PLACEHOLDER DATA]
├── engine.py        orchestrator -> DiagnosticResult
├── intake/          questionnaires, document catalogue, case assembly
├── ingest/          json_intake (canonical), datev (SKR04), bank_csv
├── casefile.py      CaseStore interface + local folder store   [SWAP FOR DATABASE]
├── workflow.py      overview, diagnose, letters, outcome (used by portal and CLI)
├── reporting/       report, HTML, letters, printable forms, summary JSON
├── webapp/          local portal: JSON API + single-page front end
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
| **Sector benchmarks are placeholder numbers** | `benchmarks.py` | Replace with Bundesbank *Verhältniszahlen aus Jahresabschlüssen deutscher Unternehmen*. Data task, not a code task — keep the shape, swap the values, record the vintage. |
| **DATEV mapping is uncalibrated** | `ingest/datev.py` | Validate SKR04 ranges against three real Steuerberater exports. SKR03 raises rather than guessing. |
| **Scorecard thresholds are convention, not calibration** | `scorecard.py` | Re-validate against real placement outcomes as the outcome log grows. |
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

The local portal binds to `127.0.0.1` only and has no login: it is a tool for
the founder's own machine (with disk encryption on), not a hosted service.

## Status

Phase 0: the diagnostic engine plus a complete local intake workflow
(questionnaires, uploads, letters, portal, outcome log), validated on synthetic
cases. A case assembled from uploaded questionnaires, DATEV exports and a bank
statement reproduces the hand-built reference case exactly. Per the
blueprint's own build order, the honest MVP is this engine run manually on the
first handful of real client files — automate a layer only once real volume makes
the manual version the bottleneck.

143 tests, all passing.
