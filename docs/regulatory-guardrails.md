# Regulatory Guardrails

**Status: engineering guidance, not legal advice.** Every item marked OPEN needs a
paid consultation with a German commercial lawyer before the first paying client.
The blueprint says this too; it is repeated here because the code enforces some of
these boundaries and a future contributor needs to know why.

## The line we are staying on

This business sells **advisory triage**. It does not sell ratings, and it does not
lend. Three regimes sit nearby, and we stay outside all three by design.

### 1. Banking licence — 32 KWG

**Not applicable, and must stay that way.** A licence is required for lending or
deposit-taking on the company's own balance sheet. This business never touches a
client's loan capital. Nothing in the roadmap should change that.

### 2. Credit rating agency — EU CRA Regulation (1060/2009)

**Deliberately avoided.** A credit rating is an opinion on creditworthiness issued
using an established and defined ranking system, published or distributed by
subscription. Issuing those is a BaFin-supervised activity.

Controls enforced in code (`scorecard.py`, `reporting/report.py`):

| Control | Where | Test |
|---|---|---|
| No output labelled a rating, score in notches, or PD | `Band.interpretation` | `test_report_never_claims_approval` |
| Vocabulary is "Readiness-Band", "indikativ", "richtungsweisend" | `engine.DISCLAIMER` | `test_report_always_carries_the_disclaimer` |
| Every factor exposes value, weight, breakpoints, points lost | `FactorScore` | `test_ranked_weaknesses_ordered_by_points_lost` |
| No machine-learned component; piecewise-linear only | `scorecard.interpolate` | — |
| Disclaimer on every report, twice | `render_markdown` | `test_report_always_carries_the_disclaimer` |
| No phrase asserting credit will be granted | report wording | `test_every_mention_of_zusage_is_negated_or_descriptive` |

**The free self-serve check raises this question more sharply** than one-to-one
advice: an automated indication shown to many companies at scale is closer to
"distributed" than a report an advisor hands over. The controls: the quick
check shows an indicative band and the weaknesses, never a probability or an
approval prediction, carries the disclaimer, and the full report is released
by a person. Have a lawyer review the quick check's wording before launch.

AI is used to read documents and explain results, never to score -- see
[ai-and-data-protection.md](ai-and-data-protection.md).

**If anyone later proposes replacing the rules engine with a trained model,
that decision has to be taken with legal advice, not as a technical upgrade.**
The explainability is not an implementation detail; it is the compliance posture
and the client trust mechanism at once.

### 3. Credit brokering — 34c GewO (Kreditvermittlung)

**OPEN — the single most important question to resolve before invoicing.**

The blueprint's own read: a flat advisory fee earned regardless of outcome is
plausibly outside 34c; a success fee tied to placing a loan plausibly falls
inside it, requiring Gewerbeamt registration, a Führungszeugnis, and professional
liability insurance — weeks, not months.

The architecture is built so this decision can be made late without a rewrite:

- `routing.py` ranks **lender types**, never named institutions, and produces a
  recommendation rather than a placement.
- The diagnostic is a standalone, separately priced product. A client can pay for
  it, fix their own file, and never use a placement service.

If the success-fee model is adopted, `routing.py` is where the regulatory surface
changes, and the module docstring says so.

### 4. What the company hands its bank — the bank pack

**OPEN — include in the lawyer's review of the quick check.** The company can
download a PDF for its bank that includes its readiness band. That is the
client showing its own advisory result, not us distributing an assessment, and
the document is built to stay that way: it states the source (reviewed report
or automatic quick check), says on every page that the band is not a rating
and not a loan promise, and the terms oblige the company not to remove that
note. We never send it to a lender ourselves. Every download is logged
(`bankpack_downloads` in the case record).

## GDPR — not optional

**Agreements before data** (`agreements.py`). A company enters nothing until it
has signed the terms and acknowledged the privacy notice; the tax advisor can
only be invited after the release from confidentiality (§ 57 StBerG). Each
signature is an append-only record with typed name, account, time, IP address
and a SHA-256 of the exact text shown (Art. 7(1) GDPR: the controller must be
able to demonstrate consent); withdrawals are new records. **All four texts
are drafts and need legal review before the first real client** -- bump the
version and every company signs again.


The data handled here is financial, sometimes distress-adjacent, and always
commercially sensitive.

| Requirement | Implementation |
|---|---|
| EU hosting | Frankfurt region; no US sub-processors without an assessment. Database and file storage: Supabase project in eu-central-1 (Frankfurt), verified 2026-09-25; region cannot be changed after creation |
| Encryption | at rest and in transit |
| Data processing agreements | with **every** vendor, including the open-banking aggregator |
| Documented legal basis | per client, in the engagement letter |
| Retention limits | defined per document class before first intake |
| Client data out of version control | enforced in `.gitignore` (`data/clients/`) |

Open-banking access is rented from a licensed PSD2 account-information provider
(finAPI, Tink or comparable) precisely so that no BaFin/ZAG licence of our own is
required. That boundary must not be crossed for convenience.

### The local portal, and what hosting it would take

`python -m credit_readiness serve` starts the website and portal bound to
`127.0.0.1`. It has accounts with three roles (advisor, company, tax advisor)
and enforces who may see and change what, but it stores files unencrypted in
`data/clients/` and is meant for one situation: the founder working through
client files on their own laptop with full-disk encryption (BitLocker) on.

What is already in place:

| Control | Where |
|---|---|
| GDPR consent is a hard gate: no consent, no analysis | `intake/assemble.py` |
| Passwords hashed with PBKDF2-SHA256 (600k iterations, per-user salt) | `auth.py` |
| Sessions: random 256-bit tokens, HttpOnly + SameSite=Strict cookie, 8h sliding expiry | `auth.py`, `webapp/server.py` |
| Temporary lockout after repeated failed logins | `auth.py` |
| Role/permission matrix enforced server-side on every request; other clients' cases answer 404 | `webapp/server.py` |
| Client sees the report only after the advisor releases it; internal files never | `webapp/server.py`, `workflow.release_report` |
| Members can delete only their own uploads | `webapp/server.py` |
| Cross-site write requests rejected (Origin check) | `webapp/server.py` |
| Strict Content-Security-Policy, no inline script, `nosniff`, `no-referrer` | `webapp/server.py` |
| Case IDs, document IDs, artifact names whitelisted; filenames sanitised | `casefile.py` |
| Upload type and size limits per document type | `casefile.py`, `intake/documents.py` |
| All client text rendered via `textContent` / HTML-escaped | `webapp/static/app.js`, `reporting/html.py` |
| SHA-256 of every uploaded file recorded | `casefile.py` |
| Client data never committed | `.gitignore` |

What hosting additionally requires, **before** the first real client file goes
online: e-mail invitations and password reset (instead of one-time passwords
shown on screen), optional two-factor login, TLS, encryption at rest,
Frankfurt-region hosting, a DPA with the hosting and database providers, audit
logging, retention and deletion rules per document class, and rate limiting.
The `CaseStore` interface is where the database and object storage plug in.

## Liability

`remediation.py` attaches a caveat to every recommendation, and flags which need
Steuerberater or legal sign-off. This is not decoration:

- **R01 (Rangrücktritt)** carries insolvency and tax consequences. It must never
  be recommended unilaterally. The code marks it `requires_steuerberater=True`
  and `requires_legal=True`, and the report prints both.
- Ratio reclassification or restatement always needs the client's own accountant
  to sign off. That is also what makes Steuerberater a referral channel rather
  than only a compliance step.

Before the first paying client: professional liability insurance in force, and an
engagement letter that scopes explicitly what is and is not promised.

## The honest-decline rule

`R08` classifies substantive weakness as `GENUINE_RISK` and refuses to simulate it
away. `classify()` lets one substantive finding outrank any number of cosmetic
ones.

This is a commercial control as much as an ethical one. Polishing the presentation
of a distressed borrower produces a better-looking rejection, damages the client,
and poisons the outcome dataset that is supposed to become the moat. Declining
those engagements is the product working correctly.

## Austria

Everything above is researched for **Germany only**. Austrian market sizing and
regulatory specifics have not been checked with the same rigour and must not be
assumed to mirror Germany — see the blueprint's own risk list.
