# ADR-006: Fix the Bundesbank import, and check it against BACH

**Status:** Accepted
**Date:** 2026-09-27
**Corrects:** the figures in [ADR-002](ADR-002-bundesbank-calibration.md) and [ADR-005](ADR-005-sector-specific-scoring.md). Their decisions stand.

## Context

The scorecard's six calibrated factors are anchored to the quartiles of the
Bundesbank *Jahresabschlussstatistik (Verhältniszahlen)*, which we extract from
the published PDFs with `scripts/import_bundesbank_ratios.py`.

We loaded the BACH database (ECCBSO, Banque de France) for comparison. BACH's
German cells come from the Bundesbank's own firm-level accounts, but as a table
rather than through a PDF parser. Where both describe the same population,
they should agree closely. Many cells did not:

| 2023, all size classes | Shipped | BACH | Corrected |
|---|---|---|---|
| Inventories / total assets, median, transport | 27.5% | 0.1% | 0.1% |
| Inventories / total assets, median, hospitality | 28.4% | 2.3% | 2.2% |
| Trade receivables / revenue, median, hospitality | 6.4% | 1.0% | 0.8% |
| Equity ratio, median, wholesale | 24.5% | 41.6% | 36.8% |

The parser had two bugs:

1. **Wrong part of the PDF.** A page's sector was read from its section number
   alone ("noch: 10."). The Verhältniszahlen restart that numbering in part II
   (legal forms) and part IV (federal states). Those pages come later in the
   file, so they overwrote the sector tables. For example, "Gastgewerbe" held
   Nordrhein-Westfalen's figures, and "all sectors" held Baden-Württemberg
   manufacturing.
2. **Wrong legal form.** `"Kapitalgesellschaften" in text` is false for
   "Nicht**k**apitalgesellschaften", so partnership and sole-trader pages were
   stored as "all legal forms" and overwrote them. That is why wholesale and
   retail equity came out so low.

Every published edition (2020–2026) has the same layout, so the entire
dataset was affected, including the five-year history.

## Decision

1. **Fix the parser.** Only pages under "I. Unternehmen nach
   Wirtschaftszweigen" are read, and the legal form is taken from its own
   header line. Re-import all seven editions.
2. **Move the generic anchors to the corrected quartiles.** The method is
   unchanged (the average of the 2–10M and 10–50M classes, all sectors, q25/q50/q75 →
   58/70/82). Only the values move:

   | Factor | Old anchors | New anchors |
   |---|---|---|
   | Eigenkapitalquote | 14.8 / 35.1 / 56.9% | 13.0 / 33.2 / 56.6% |
   | EBIT-Marge | 1.35 / 4.75 / 9.95% | 1.4 / 4.5 / 9.65% |
   | Liquidität 2. Grades | 45.8 / 91.7 / 216.3% | 53.2 / 115.3 / 254.3% |
   | Gesamtkapitalrentabilität | 2.4 / 6.85 / 13.35% | 2.3 / 6.65 / 14.05% |
   | Anlagendeckungsgrad II | 122.1 / 218.2 / 464.5% | 101.2 / 195.2 / 533.7% |
   | Kreditorenlaufzeit | 15.1 / 27.2 / 49.5 days | 15.3 / 31.6 / 59.5 days |

   The sector curves need no code change: they read the corrected dataset.
3. **Keep BACH as a cross-check, not a calibration source.**
   `scripts/import_bach.py` extracts the German cells, and
   `tests/test_bach_crosscheck.py` compares medians for equity, inventories,
   receivables and pre-tax margin in the nine sectors and three size classes
   where both sources cover the same population. On the old dataset, 46 of 108
   checks fail. On the corrected one, all pass. BACH does not replace the
   Bundesbank figures because it has no second-degree liquidity, fixed-asset
   coverage or Bundesbank-definition return on assets. Its smallest class
   (< 10M EUR) also mixes micro firms into our 2–10M segment.
4. **Use BACH as peer context in the report, not in the score.** A new
   subsection of report section 8 (`peers.py`) compares the client with
   firms from the same country, the same WZ division and turnover class, and
   the year of the uploaded accounts. When a cell is empty it falls back from
   division to section to all sectors, and from size class to all sizes. For
   accounts newer than BACH's latest year, it uses that year and says so.
   Provisional years are flagged using the release calendar in the BACH
   userguide. Only quartiles are shown: BACH's weighted means describe the
   largest firms in a cell. Metrics are limited to the pairs whose
   definitions match ours: balance-sheet equity ratio, EBITDA, EBIT and
   pre-tax margins, and days receivable. This also gives sectors the
   scorecard scores generically (car dealers, real estate, energy) a
   comparison of their own.
5. **Don't redistribute BACH.** Its terms forbid redistribution, even free of
   charge. The extract lives in the git-ignored `data/reference/bach/`, and the
   cross-check and the report section skip without it. Before the extract
   goes to production, clear with the ECCBSO whether printing quartiles in a
   client report counts as redistribution.

## Consequences

- Sample cases before remediation → after:
  - Mueller: 65.6 B → 78.4 A becomes 65.2 B → **77.7 B**. The measures no
    longer reach band A, and the coach says so.
  - Nordlicht (wholesale): 52.3 C becomes **50.0 D**. ADR-005 said its 11%
    equity ratio was "close to normal for wholesale". With the corrected
    wholesale median of 36.7%, it is not.
  - Gastro: 4.5 becomes 9.0, still E.
  - Datenwerk: 87.6 becomes 85.2, still A.
  - Ihrig: 69.2 becomes 70.6, still B.
  - Hoffmann: 90.8 becomes 90.5, still A.
- ADR-005's example no longer holds: retail's median equity (29.5%) is close to
  the all-sector median, and it doesn't read as borderline on the generic
  curve. Construction (22.8%) is the sector where it does, and the test now uses
  construction.
- The methodology documents in `docs/methodik/` are regenerated.
- The scoring model published to Supabase (`scripts/publish_scoring_model.py`)
  still holds the old curves until it is re-published.
- `EBT_TO_EBIT_ADJUSTMENT` (0.5 points) is a hand-entered constant from the same
  publication and was not re-checked. BACH's EBIT and EBT medians differ by
  0.7–1.1 points for the SME classes, but BACH's EBIT includes extraordinary
  items, so that gap is not a direct replacement.
