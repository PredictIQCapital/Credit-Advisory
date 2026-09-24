# ADR-005: Score the calibrated factors against the client's own sector

**Status:** Accepted
**Date:** 2026-09-24
**Builds on:** [ADR-002](ADR-002-bundesbank-calibration.md), [ADR-003](ADR-003-eba-marisk-alignment.md).

## Context

ADR-002 anchored six factors to Bundesbank quartiles, but to the *all-sector*
quartiles only. The sector cells were already in the dataset and were used for
the report's comparison table, not for the score. The gap is large for exactly
the sectors this product sees most often (2–10M EUR revenue, 2023):

| Median | All sectors | Retail | Wholesale | Healthcare |
|---|---|---|---|---|
| Equity ratio | 32.7% | 20.9% | 20.9% | 35.0% |
| Liquidity (2nd degree) | 92% | 75% | 67% | 211% |

A retailer at the retail median equity ratio scored about 62 points, which is
borderline, although it is exactly typical for its sector. The product spec
(PRD section 2.1, item 6) asks for sector-specific bands, with a generic
fallback where sector data is missing.

## Decision

1. **The six calibrated factors are scored on sector curves.** The
   q25/median/q75 anchors (58/70/82 points) move onto the quartiles of the
   client's sector *and* revenue class. That is the Bundesbank's own notion of
   comparable companies.
2. **Tails are handled by meaning, not symmetry.** The weak tail stays at its
   absolute economic limits (zero equity, a negative margin, 120 days to pay
   suppliers). A weak sector does not make insolvency less likely. The strong
   tail stretches in proportion to the upper-quartile anchor.
3. **Repayment factors never move.** DSCR, net debt / EBITDA and interest cover
   measure whether the loan can be repaid, and the answer does not depend on
   the sector.
4. **Fallback is explicit.** A sector without a usable published cell keeps the
   generic curve, and the factor's note says so. Companies whose WZ code has no
   Bundesbank sector (agriculture, energy, motor-vehicle trade, real estate,
   ...) are classified as `Andere Branche` and scored generically.
5. **Both scores are reported.** Sector scoring answers "is this company
   typical for its sector?". It does not answer "is this sector risky?", which
   lenders price separately. The report and the portal therefore show the
   all-sector score alongside the sector score.
6. **The sector comes from the WZ 2008 / NACE code** when one is given
   (`nace.py`). The code is a registered fact, while the dropdown is a
   self-assessment, and the sector now moves the score.

## Consequences

- Sample cases move by −0.2 to +0.6 points. Nordlicht (wholesale) goes from
  D to C: its 11% equity ratio is weak in absolute terms but close to normal
  for wholesale. After remediation, Mueller (manufacturing) crosses into A,
  because manufacturers carry more fixed assets and their fixed-asset coverage
  quartiles sit lower.
- Every sector curve is tested: anchors meet the sector quartiles, curves stay
  monotone, zero equity scores the same everywhere, and the repayment factors
  are identical across sectors.
- Scoring still uses the latest reporting year. The five-year history
  (2019–2023) is shown as context in the report, not averaged into the anchors.
  A lender's internal benchmark is a single current table too.
- The methodology documents (`docs/methodik/`, DE and EN) still describe
  all-sector anchoring and need a section on this change.
