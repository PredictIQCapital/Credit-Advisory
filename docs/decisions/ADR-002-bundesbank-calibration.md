# ADR-002: Calibrate part of the scorecard against the Bundesbank distribution

**Status:** Accepted
**Date:** 2026-09-20
**Supersedes nothing. Constrained by:** [ADR-001](ADR-001-rules-not-machine-learning.md)

## Context

The scorecard's breakpoints were conventional: drawn from how German credit
analysis talks about ratios, with no reference to how German SMEs are actually
distributed. Two problems followed.

First, the curves were not consistent with each other. Scoring the Bundesbank
quartiles through the old breakpoints put the *same median firm* at 91 points on
equity and 22 on leverage. A total built from factors that disagree that
violently about what "average" means is not measuring one thing.

Second, the equity factor — the heaviest at 20% — saturated at 40%, while the
published median for the 2–50M EUR revenue classes is 35%. Half of German SMEs
were scoring 88 points or better on a fifth of the scorecard.

The Deutsche Bundesbank publishes *Jahresabschlussstatistik
(Verhältniszahlen)* annually and free of charge, including **firm-level
quartiles** by sector, revenue size class and legal form. That is a published,
citable distribution — the kind of anchor ADR-001 asks for, and not a model.

## Decision

Calibrate the three factors the publication genuinely supports, and say plainly
that the rest remain convention.

**Calibrated:** `eigenkapitalquote` (20%), `ebit_marge` (12%),
`liquiditaet_2_grades` (8%) — 40% of the scorecard's weight.

Anchor points: **25th percentile → 58, median → 70, 75th percentile → 82**,
using all sectors and the average of the 2–10M and 10–50M EUR revenue classes,
latest reporting year.

The anchors come from one step of reasoning. The ECB SAFE survey puts roughly
14% of applicants in significant difficulty. So a company at the median of its
size class should land in band B ("financeable, terms improvable"), the lower
quartile in band C ("borderline"), the upper quartile at the band A line.
Anchoring on percentiles alone — median → 50 — would have declared half of
German SMEs borderline cases, which the approval data does not support.

Beyond the published quartiles the tails stay conventional. Three points are not
a distribution, so the ends are drawn to economically meaningful limits (zero
equity, negative margin) rather than extrapolated from the slope.

**Not calibrated, and why:** the publication carries no comparable series for
debt service capacity, overdraft utilisation, reporting cadence, credit-agency
index or payment behaviour. Its leverage measure — cash flow in percent of total
liabilities less cash — is not our net financial debt over EBITDA: the numerator
is after-tax cash flow rather than EBITDA, and the denominator includes trade
payables and provisions. Translating one into the other would be a guess wearing
the costume of a calibration.

**Band thresholds (78/65/52/38) are unchanged.** They now carry an implied
percentile reading they did not have before. Re-deriving them needs placement
outcomes, not more reference data.

## Consequences

- Sample cases moved: the reference case goes 64.5 C → 66.4 B before
  remediation, the strongest case 97.4 → 93.3. Weak files rise slightly (zero
  equity is no longer scored as near-catastrophic), strong files fall (40%
  equity no longer maxes a factor out).
- `benchmarks.py` serves real data instead of placeholders. Several placeholder
  medians were badly wrong — Gastgewerbe equity was entered as 12% against a
  published median of 30.8%.
- The scorecard is now **internally inconsistent by construction**: 40% of its
  weight is distribution-anchored, 60% is convention. This is visible rather
  than hidden, and it is the top item for revision once the outcome log holds
  real placements. The leverage and debt-service factors are where to start.
- A new edition of the publication changes the anchors.
  `tests/test_scorecard.py::test_bundesbank_anchors` re-derives them from the
  shipped dataset and fails if breakpoints and data drift apart.
- Coverage of our target segment in the Bundesbank pool is thin: ~14% of
  turnover in the 2–10M class, ~42% in 10–50M, and the firms in it reached the
  pool through banks and credit insurers. The dataset therefore describes
  companies already in credit relationships. The caveat is carried in
  `benchmarks.CAVEAT` and printed in every client report.

## Revisit when

A new Bundesbank edition is published (re-run the importer, move the anchors),
or the outcome log holds enough placements to calibrate the band thresholds and
the uncalibrated factors on real decisions rather than on reference data.
