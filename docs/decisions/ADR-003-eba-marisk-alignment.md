# ADR-003: Align the factor set and method with EBA/GL/2020/06 and MaRisk

**Status:** Accepted
**Date:** 2026-09-22
**Constrained by:** [ADR-001](ADR-001-rules-not-machine-learning.md).
**Builds on:** [ADR-002](ADR-002-bundesbank-calibration.md).

## Context

ADR-002 fixed *where the thresholds come from*. It left open the prior question:
why these ten ratios and not others? The honest answer at the time was "because
they are the ones German credit analysis talks about" — defensible, but not
something you can point at a source for when a bank partner asks.

Three supervisory sources were read in full for this decision:

* **EBA/GL/2020/06**, Guidelines on loan origination and monitoring. Annex 3
  section B lists twenty metrics an institution should consider for lending to
  enterprises; Annex 1 lists the criteria it must set limits on; Annex 2 lists
  the evidence it must collect; paragraphs 118–167 set out the assessment.
* **MaRisk** (BaFin Rundschreiben 10/2021), Anlage 1, BTO 1.2 and BTO 1.4.
* **Bundesbank credit assessment system (ICAS)**, the December 2023 description
  of the ratio set a central bank actually uses to estimate a German SME's PD
  from HGB accounts, plus Technical Paper 02/2023 on stressing a statement.

### The finding that shaped everything else

**None of them publishes threshold values.** EBA Annex 1 requires an institution
to define "acceptable ... ratio limits" and leaves the numbers to the
institution. MaRisk prescribes process, not figures — BTO 1.2.4 explicitly
leaves the intensive-care trigger criteria to each institution's discretion.

So the supervisors settle *which* metrics and *that* limits must exist. They do
not settle *how high*. That splits cleanly into two separately defensible
decisions, and the code and the methodology document now keep them apart: the
metric set cites the regulators, the thresholds cite the Bundesbank
distribution.

### The gap that mattered most

The product scored a point in time. EBA paragraph 131 (micro and small) and
156–158 (medium and large) require an assessment of repayment capacity *under
adverse conditions*, and 158(k) names a figure: a 200 basis point increase on
all of the borrower's credit facilities. MaRisk BTO 1.2.1 Tz. 1 says the same in
German terms — risks to the borrower's future position must enter the
Kapitaldienstfähigkeit assessment. We did none of it.

## Decision

**1. Three factors added, all calibrated, none invented.**

| Factor | Weight | Source |
|---|---|---|
| Gesamtkapitalrentabilität (Jahresergebnis + Zinsaufwand) | 0.05 | EBA Annex 3 no. 18 |
| Anlagendeckungsgrad II | 0.05 | Bundesbank Verhältniszahl; goldene Bilanzregel |
| Kreditorenlaufzeit | 0.04 | Bundesbank ICAS additional ratio |

All three were already computed and discarded, and all three turned out to have
a published quartile series we had imported but never exported to the engine.
Calibrated weight rises from 40% to 46%, calibrated factors from 3 to 6.

**2. Return on assets adopts the Bundesbank's definition, not ours.**
The published series is *result after tax plus interest over total assets*; our
existing ratio is EBIT over total assets. Converting between them needs an
assumption about the tax charge and asset turnover — a guess dressed as a
calibration, which is exactly what ADR-002 forbids. So the scored factor is a
new ratio computed the published way. Both live in `ratios.py`.

**3. Weights rebalanced to keep the sum at 1.00, with one protected.**
Kapitaldienstfähigkeit stays at 0.20 and remains the largest single weight,
because MaRisk BTO 1.2.1 Tz. 1 puts it under *besondere Berücksichtigung*.

**4. Sensitivity analysis added** (`sensitivity.py`), with three scenarios taken
from EBA 158: +200bp on all facilities (158 k), a 10% revenue decline with only
variable costs following (158 a), and both together (156 permits multifactor).
The mechanism follows Bundesbank Technical Paper 02/2023 §5.2 — fund the hit
from cash then short-term bank debt, charge interest on the new borrowing, cut
the tax charge at the borrower's own effective rate, carry the loss into equity,
re-run every ratio. Using a central bank's published plumbing beats inventing
our own.

**5. Collateral still scores nothing.** EBA paragraph 120 says collateral must
not be a predominant criterion and is the second way out, not the primary
source of repayment. It stays a finding, never a factor. This was already true;
it is now true *for a citable reason*.

## Alternatives rejected

**Scoring the Bundesbank "Cashflow in % der Nettofremdmittel" series to
calibrate the leverage factor.** Still rejected, for the reason ADR-002 gave:
different numerator (cash flow after interest and tax, not EBITDA) and a much
wider denominator (all liabilities, not financial debt). Net Debt/EBITDA remains
convention.

**Adding Debitorenlaufzeit as a fourth new factor.** It is the mirror of
Kreditorenlaufzeit inside the cash conversion cycle; scoring both would
double-weight working capital. EBA paragraph 153 asks institutions to *assess*
the cash conversion cycle, which the report does narratively.

**Adding Return on equity (EBA Annex 3 no. 22).** Unstable to the point of being
misleading when book equity is thin or negative — which describes a large part
of this segment. Listed as deliberately excluded rather than quietly omitted.

**A new remediation rule for the maturity mismatch.** Written, then deleted:
R06 already covered it, with an identical simulation. R06 gained
`anlagendeckungsgrad_ii` in its `affected_factors` instead.

## Consequences

The reference case moves from 66.4 to 65.0 (still band B), and — more
substantively — from band A to band B *after remediation* (80.3 → 77.7). That is
not a regression. The new factors expose a maturity mismatch that the
recommended Umschuldung closes only to exactly 100% Anlagendeckung, still below
the sector's lower quartile of 122%. The old scorecard could not see it.

Two things this does not buy. The band thresholds themselves are still not
empirically derived — they follow from the same ECB SAFE reasoning as the factor
anchors, and remain the weakest point in the method. And the sensitivity
analysis is not a forecast: it says the band moves from X to Y on stated
assumptions printed next to the result, so the owner — who knows their own
variable cost share better than we do — can disagree with them.

Still absent against the guidelines, and now written down as such in
`docs/methodik/`: ESG assessment (EBA 126–127), financial projections
(EBA 129), and most qualitative factors (EBA 132–136, MaRisk BTO 1.4 Tz. 3).
