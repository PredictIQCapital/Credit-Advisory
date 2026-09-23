# ADR-004: Check knock-out reasons separately from the score

**Status:** Accepted
**Date:** 2026-09-23
**Builds on:** [ADR-003](ADR-003-eba-marisk-alignment.md).

## Context

A folder of 58 supervisory and bank documents was reviewed (EBA stress test
methodologies and results, EBA credit risk benchmarking 2014–2023, EBA
insolvency benchmarks, World Bank credit scoring guidelines, Banque de France
rating guide, KfW reports, Bundesbank discussion papers). Most of it turned out
to be irrelevant to an SME readiness product — collateral mobilisation manuals,
Pfandbrief reporting, an equal-pay report, French regional deposit statistics.
Four things in it were not.

**1. A weighted score structurally cannot express a knock-out.** This is the
central finding, and it is not from any single document — it follows from what
the documents describe lenders doing. A weighted average lets a strong factor
offset a fatal one. Gastro Rheinblick scores 4.5 and is obviously finished; but
a file at 70 points with tax arrears is *also* finished, and the scorecard
cannot say so, because 4% weight on payment behaviour cannot outvote the other
96%. Knock-outs are a different question and need different machinery.

**2. The Banque de France publishes its distress criteria as checkable
conditions.** Its rating reference guide (September 2026) states, for each weak
grade, what makes a company fall into it: equity below half of share capital;
losses in three consecutive years; financial charges absorbing a very high
share of EBITDA; payment incidents above 2% of purchases; accounts whose
year-end is more than 23 months old. No other source in the set states distress
as arithmetic rather than as principle.

**3. CRR Article 178 makes a breached overdraft limit a default indicator.**
"Overdrafts will be considered as being past due once the customer has breached
an advised limit." We had this as a mere WARNING in validation. That is an
understatement of exactly the kind this product exists to correct.

**4. The supervisory adverse scenario is published and quantified.** The
ESRB/EBA 2025 EU-wide stress test puts German real GDP 7.5% below baseline
cumulatively, unemployment up ~5pp, long-term rates up ~110bp, commercial
property down a third.

## Decision

**1. A separate knock-out screen** (`rejection_risk.py`), run alongside the
scorecard and reported *before* the ratios. Eight checks, none of whose
thresholds are ours:

| Code | Condition | Source |
|---|---|---|
| KO01 | Equity < half of share capital | §49 Abs. 3 GmbHG; BdF note 4-/6 |
| KO02 | Negative balance-sheet equity | §19 InsO; EBA Tz. 128 a |
| KO03 | Overdraft over the advised limit | CRR Art. 178 |
| KO04 | Tax arrears | EBA Tz. 121 d |
| KO05 | Returned direct debits | BdF note 8 |
| KO06 | Losses in consecutive years | BdF note 6 |
| KO07 | Interest ≥ 50% of EBITDA | BdF note 6 |
| KO08 | Accounts ≥ 23 months old | BdF note X |

Each finding carries what is true, how a lender reads it, what to do about it,
and where the criterion comes from. A client challenged on one of these will
ask for the source, and "our model says so" is not an answer.

**2. German statutory triggers, adapted rather than copied.** The Banque de
France condition is French company law. The German equivalent is §49 Abs. 3
GmbHG — losing half the Stammkapital obliges the managing director to convene
the shareholders. That is objective, sits in data we already hold, and no
competitor tool tells an owner-manager about it.

**3. Scenario sizes positioned against the supervisory calibration.** The 10%
revenue decline stays, but is no longer a free choice: it is stated next to the
ESRB/EBA scenario's 7.5% German GDP contraction, with the reasoning that
firm-level revenue is more volatile than aggregate GDP. The same comparison
shows our +200bp rate shock is nearly double the supervisory ~110bp — a point
in the borrower's favour whenever a file survives it.

## Alternatives rejected

**Folding knock-outs into the score as very heavy factors, or as a hard cap.**
This is the obvious move and it is wrong twice over. A 40%-weight "tax arrears"
factor would distort every other weight and still not guarantee a decline; a
cap that forces the band to E would hide *which* condition caused it behind a
number. The finding is the product, not the points.

**Concluding insolvency.** Declined, firmly. Whether a filing obligation under
§15a InsO exists turns on a going-concern prognosis this engine cannot
evaluate. The checks name the condition and route the judgement to the
Steuerberater. A test asserts the over-indebtedness text never says "insolvent"
and always says "Fortführungsprognose".

**Adding an ESG factor** on the strength of the Banque de France now folding
transition and physical climate risk into its ICAS ratings. Real and coming,
but it needs carbon-cost and insurability data we do not collect. Stays on the
limitations list rather than becoming a guessed factor.

**Back-testing the model**, as the World Bank guidelines require (Policy
Recommendation 4: ROC/PR validation). Impossible without outcome data. Recorded
as the governance gap it is; not faked.

## Consequences

Two of six sample cases now carry findings. Gastro Rheinblick shows four, two
of them knock-outs — which is right, and which the score alone communicated
only as "band E, substantial weakness". The other four report a clean screen,
which is itself a statement worth making: it means the conditions conversation
can be had at all.

The overdraft upgrade is the change most likely to surprise a client. A drawn
overdraft over its limit was previously a warning about presentation; it is now
named as what the regulation calls it. That will occasionally be unwelcome, and
it is the point.

A false positive here costs more than a missed one — telling a solvent company
that half its share capital is gone would end an engagement — so every check is
pinned on both sides of its threshold in `tests/test_rejection_risk.py`.
