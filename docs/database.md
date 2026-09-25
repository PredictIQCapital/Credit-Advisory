# Database (Supabase, Frankfurt)

Supabase project in **eu-central-1**. The portal's server is the only client:
it uses the secret key, which bypasses row-level security. Every table has RLS
on and **no policies**, and the browser roles (`anon`, `authenticated`) have no
grants — the publishable key reads nothing (tested).

Changes to the structure are SQL files in `supabase/migrations/`, applied in
order and recorded in `app_meta.migrations`:

```bash
python scripts/supabase_db.py check   # connection + region
python scripts/supabase_db.py plan    # migrations not yet applied
python scripts/supabase_db.py apply   # apply them, one transaction each
```

## Schema `app` — the cases

| Table | Holds | Notes |
|---|---|---|
| `users` | name, role, link to the Supabase Auth user | passwords live in Supabase Auth |
| `sessions` | SHA-256 of each login cookie, expiry | never the token itself |
| `login_failures` | failed logins, for the 5-minute lockout | |
| `cases`, `case_counters` | case record; gap-free numbering `CRA-YYYY-NNNN` | `app.next_case_id(year)` |
| `answers` | the two questionnaires | audited |
| `documents` | file records; the files are in Storage bucket `case-files` (private) | audited (names, never content) |
| `artifacts` | reports, summaries, letters | |
| `records` | signed agreements and messages | **append-only** (trigger) |
| `results`, `result_factors` | every quick check and report, with **model version** and every factor | **append-only** |
| `audit_log` | changes to cases, answers and documents | append-only; deleted with its case (GDPR Art. 17) |
| `outcomes` | the outcome log | |

Triggers: `*_append_only` (records, results, result_factors, audit_log),
`*_audit` (cases, answers, documents), `*_touch` (`updated_at`).
Deleting a case removes everything that belongs to it, including results and
the audit trail.

Views: `v_latest_results` (latest result per case), `v_pipeline` (cases per
stage and band), `v_band_distribution` (bands by sector),
`v_unpublished_models` (results whose model version was not published —
should always be empty).

## Schema `scoring` — the model, as data

The scoring **rules** are written and tested in Python. The `scoring` schema
holds a read-only copy of every model version that was used, so any stored
result can be traced to the exact weights, curves and Bundesbank data that
produced it.

| Table | Holds |
|---|---|
| `model_versions` | version (`m-` + fingerprint of the content), publication time |
| `factors` | the 13 factors: weight, unit, calibration source |
| `curves` | score curves: generic (`*`) and per sector and size class |
| `bands` | band thresholds A–E |
| `settings` | anchor scores, size classes, benchmark vintage |
| `sectors`, `nace_ranges`, `nace_sections` | WZ 2008 / NACE → benchmark sector |
| `knockouts` | the eight knock-out criteria and their sources |
| `benchmarks` | Bundesbank quartiles, five reporting years |

Published rows cannot be changed (trigger); a changed model is a new version.

Functions (service role only):

```sql
select scoring.factor_score('eigenkapitalquote', 0.18, 'Einzelhandel', 5000000);  -- points 0-100
select scoring.interpolate(1.3, 'kapitaldienstfaehigkeit_inkl_neu');               -- generic curve
select scoring.band_for(66.4);                                                     -- 'B'
select scoring.sector_for_nace('C25.62');                                          -- 'Verarbeitendes Gewerbe'
select scoring.size_class(5000000);                                                -- '2_bis_10m'
select scoring.current_version();
```

`tests/test_model_export.py` checks, against the live project, that these
functions score exactly like the Python engine (to 0.0001 points).

**After any change to weights, curves, bands, the NACE mapping, the knock-out
catalogue or the Bundesbank data**, publish the new version before deploying:

```bash
python scripts/publish_scoring_model.py          # does nothing if already published
python scripts/publish_scoring_model.py --check
```

## Other scripts

```bash
python scripts/check_supabase.py                  # keys and services reachable
python scripts/migrate_to_supabase.py data/demo   # copy a local data folder over
python scripts/remove_demo_from_supabase.py       # list (--yes: remove) demo data
CRA_SUPABASE_TESTS=1 python -m pytest tests/test_store_contract.py tests/test_model_export.py
```
