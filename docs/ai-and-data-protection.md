# AI and data protection

**Status: engineering guidance, not legal advice.** Items marked **OPEN** need a
data-protection lawyer or external DPO before real client data is processed on
a server. Read together with [regulatory-guardrails.md](regulatory-guardrails.md).

## 1. What the AI does, and what it deliberately does not

| Task | Who does it | Why |
|---|---|---|
| Read balance sheet and P&L from an annual-accounts PDF or scan | AI (Claude) or the local rules reader | Saves the client typing; works on any layout |
| Decide which figures are used | **The client**, who confirms each figure | A proposal is not an input until a person confirmed it |
| Check the figures | Deterministic checks (assets = liabilities, P&L result = balance-sheet result) | Catches extraction slips before they reach a ratio |
| Readiness band, findings, simulation, lender type | **Rules-and-ratios engine only** | Explainable, auditable, legally defensible (ADR-001) |
| Explain a result in plain words, answer questions | AI, grounded only in the engine's result | Makes the result understandable |
| Guardrail on every AI text | Deterministic filter (`ai/explain.py`) | Rejects approval promises, odds, rating language |
| Release of the full report | A human advisor | The blueprint's model: every flag is reviewed |

The rule to keep when the product grows: **AI may read and explain; it never
scores.** Replacing the engine by a model is a legal decision (ADR-001), not a
refactor.

## 2. Configuration: nothing leaves the machine unless deliberately switched on

| Setting | Effect |
|---|---|
| default (`CRA_AI_PROVIDER` unset) | Local rules reader. Text PDFs only; no data leaves the server. Explanations from templates. |
| `CRA_AI_PROVIDER=anthropic` + `pip install "credit-readiness[ai]"` + Anthropic credentials | Claude (`claude-opus-5`) reads PDFs and scans and writes explanations |
| `CRA_AI_INFERENCE_GEO=<region>` | Passed to the API as `inference_geo`, to pin where inference runs. Check which regions Anthropic offers and whether they meet the transfer requirements. |

Even with Claude switched on, a document is sent **only** if the company ticked
the separate AI consent (`ki_einwilligung`). Without it, the portal refuses and
offers manual entry. The server-side refusal fallback (`fallbacks: "default"`)
is enabled; a refusal is shown to the client as "please enter manually".

## 3. EU AI Act

- **High-risk category (Annex III, 5(b))**: AI systems *intended to evaluate the
  creditworthiness of natural persons or establish their credit score*. Our AI
  does neither: it transcribes figures and explains a rules-based result.
  **OPEN:** confirm with a lawyer, in particular for **sole proprietors
  (Einzelunternehmen)**, who are natural persons.
- **Transparency (Art. 50)**: the portal labels AI-generated explanations and
  AI-read figures as such. Implemented.
- **Human oversight**: every extracted figure is confirmed by the client; the
  full report is released by an advisor. Implemented.

## 4. GDPR

| Topic | What we do | Status |
|---|---|---|
| Legal basis | Contract (Art. 6(1)(b)) for the analysis; **consent** (Art. 6(1)(a)) for AI processing by an external provider, voluntary with an alternative | Implemented in the product; **OPEN:** wording checked by a lawyer |
| Consent records | Stored as questionnaire answers with the case; AI consent separate | Implemented |
| Data minimisation towards the AI | Only the document to read; for explanations only the result summary (no names, no documents) | Implemented (`ai/providers.py::_explainable`) |
| Processor agreements (Art. 28) | Hosting, database, AI provider (Anthropic), e-mail, payment provider | **OPEN** before go-live |
| International transfer (Art. 44 ff.) | AI provider outside the EU: transfer basis (adequacy/SCCs), EU inference region if available | **OPEN** |
| No training on client data | Only providers whose commercial terms exclude training on API data; fixed in the DPA | **OPEN** (contractual) |
| Records of processing (Art. 30) | One entry per purpose: analysis, AI reading, AI explanation, outcome log | **OPEN** |
| DPIA (Art. 35) | Likely required: financial data, new technology, systematic evaluation | **OPEN** before go-live |
| Right to erasure (Art. 17) | "Delete my account and data" in the portal removes cases, documents and account | Implemented |
| Outcome log | Keeps a pseudonymous row (case ID, sector, figures, outcome; no names or documents) on legitimate interest to validate the method; removed on request | Implemented; **OPEN:** balancing test documented |
| Retention | Periods per document class (e.g. uploads deleted 12 months after case closure) | **OPEN** |
| Security (Art. 32) | See section 5 | Partly implemented |
| Breach process (Art. 33/34) | 72-hour notification process, contact list | **OPEN** |
| Audit trail of AI use | Every AI call logged per case (time, purpose, provider, model, SHA-256 of input, actor) without storing content | Implemented (`artifacts/ai_log.json`) |

## 5. Technical and organisational measures

Implemented in the code today: role-based access enforced server-side, PBKDF2
password hashes, HttpOnly/SameSite session cookies, login lockout, strict CSP,
origin checks, upload type/size limits, sanitised file names, SHA-256 of every
upload, client data excluded from git, human release of reports, AI consent
gate, AI audit log, self-service erasure.

Before go-live: TLS, encryption at rest, EU (Frankfurt) hosting, database-backed
`CaseStore` and `UserStore`, e-mail invitations and password reset, optional
two-factor login, backups with restore test, centralised logging with alerting,
penetration test, least-privilege access for staff, secrets management for the
Anthropic key.

## 6. Checklist before the first real client file online

1. DPA with hosting, database, AI provider, e-mail and payment providers.
2. Transfer basis for the AI provider; inference region chosen.
3. DPIA written; records of processing complete.
4. Privacy notice and consent texts reviewed by a lawyer (incl. AI consent).
5. Retention schedule implemented; erasure tested end to end.
6. EU AI Act classification confirmed in writing, including sole proprietors.
7. §34c GewO decision taken (see regulatory-guardrails.md).
8. Security items in section 5 done; penetration test passed.
9. Professional liability insurance in force.
10. The free check's wording reviewed for CRA-Regulation risk: it is shown
    self-serve and at scale, so "indicative band + weaknesses", never "your
    bank score" or approval odds.
