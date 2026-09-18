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

python scripts/generate_samples.py          # build the synthetic test cases
python -m credit_readiness batch data/samples
python -m credit_readiness diagnose data/samples/case_01_mueller_praezisionstechnik.json -o output/
python -m pytest -q
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
├── cli.py           diagnose / batch / datev
├── ingest/          json_intake (canonical), datev (SKR04)
└── reporting/       German client report
```

Zero runtime dependencies — standard library only. `pytest` for tests.

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
applied, lender type routed to, approved or not — belongs in
`data/reference/outcome_log.csv` from client one. Early on it is a spreadsheet,
not a model. It is what eventually lets the thresholds move from generic
convention to something calibrated on this business's own placement history.

## Data handling

Client data never enters version control. `.gitignore` excludes `data/clients/`
and `*_client_*.json`. Everything in `data/samples/` is **fictional**, generated
by `scripts/generate_samples.py`, and must never be presented as evidence about
the real market.

## Status

Phase 0 prototype: the diagnostic logic, validated on six synthetic cases. Per the
blueprint's own build order, the honest MVP is this engine run manually on the
first handful of real client files — automate a layer only once real volume makes
the manual version the bottleneck.

61 tests, all passing.
