# Reference data

## outcome_log.csv — the actual moat

Per the blueprint: the long-term defensibility is not any single data source, it
is **outcome tracking**. Every engagement's flagged weaknesses, the remediation
applied, the lender type routed to, and whether it was approved.

Treat it as an asset from client one. Early on this is a spreadsheet, not a model.

`outcome` values: `APPROVED`, `APPROVED_BETTER_TERMS`, `REJECTED`,
`WITHDRAWN`, `ADVISED_NOT_TO_APPLY`, `PENDING`.

Note that `ADVISED_NOT_TO_APPLY` counts as value delivered, not a lost case —
see the success metrics in the blueprint.

Two things this log eventually answers that no amount of desk research can:

1. **Is the "fixable vs genuinely uncreditworthy" split real, and what is it?**
   The blueprint's 5,000–8,000/year estimate is explicitly an unvalidated planning
   assumption. This log is how it gets tested.
2. **Are the scorecard thresholds right?** They are currently convention, not
   calibration. Enough rows, and they can be fitted to actual placement outcomes.

## Still to be added

- Bundesbank *Verhältniszahlen aus Jahresabschlüssen deutscher Unternehmen*
  (replaces the placeholders in `benchmarks.py`)
- Current KfW programme conditions (Merkblätter), for `routing.py`
- Bürgschaftsbank conditions per Bundesland
