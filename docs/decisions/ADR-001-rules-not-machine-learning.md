# ADR-001: Rules and ratios, not a machine-learned score

**Status:** Accepted
**Date:** 2026-09-18

## Context

The founder's background is bank credit risk modelling — PD/LGD estimation,
application scorecards, calculation engines. The technically natural instinct is
to train a model. There is even a plausible data story: the outcome log will grow.

## Decision

The diagnostic is a transparent rules-and-ratios engine. Piecewise-linear
interpolation over published thresholds. No machine-learned component.

## Rationale

Three reasons, in order of weight:

1. **Regulatory.** Explainability is what keeps the tool clearly on the advisory
   side of the EU CRA Regulation line. An opaque score that ranks creditworthiness
   is much closer to a rating than a ratio table with stated thresholds.

2. **Trust and saleability.** The client is an SME owner and their Steuerberater.
   The product is not the number — it is the sentence *"your equity ratio reads as
   10.1% because a 600,000 EUR shareholder loan lacks a subordination declaration,
   and here is what changes if you obtain one."* A model output cannot be argued
   with by an accountant; a ratio can, and being argued with is how the advice
   earns its fee.

3. **Data reality.** At 2–3 engagements a month, there will be tens of outcomes in
   year one, not thousands. There is no training set. Pretending otherwise would
   produce a model fitted to noise and wrapped in false authority.

## Consequences

- Thresholds are convention, not calibration, and are documented as such in
  `scorecard.py`. They must be re-validated as the outcome log grows.
- Calibration, when it comes, should first mean *adjusting the breakpoints* using
  real outcomes — still transparent — before any consideration of a learned model.
- **Replacing the engine with a model is a legal decision, not a technical
  upgrade.** It must not happen as an incremental refactor.

## Revisit when

The outcome log holds enough placements for the threshold calibration to be
statistically meaningful, AND legal advice has confirmed what a fitted model does
to the CRA Regulation position.
