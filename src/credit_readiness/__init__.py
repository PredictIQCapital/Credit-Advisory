"""Credit Readiness Advisory - diagnostic engine.

A rules-and-ratios triage tool for German/Austrian SME credit files.

It answers one question: if this file went to a lender today, which factors
would pull it below an approvable line, and which of those are fixable before
the client ever reapplies.

It is NOT a credit rating agency tool and does not estimate default
probabilities. See scorecard.py and docs/regulatory-guardrails.md.
"""

from .engine import DISCLAIMER, DiagnosticResult, run_diagnostic
from .models import (
    BalanceSheet,
    BehavioralData,
    ClientCase,
    CompanyProfile,
    FinancingRequest,
    IncomeStatement,
    LegalForm,
    LoanFacility,
    Sector,
)
from .ratios import RatioSet, compute_ratios
from .remediation import FixCategory, Finding, Verdict
from .scorecard import Band, ScorecardResult, evaluate

__version__ = "0.3.0"

__all__ = [
    "BalanceSheet",
    "Band",
    "BehavioralData",
    "ClientCase",
    "CompanyProfile",
    "DISCLAIMER",
    "DiagnosticResult",
    "FinancingRequest",
    "FixCategory",
    "Finding",
    "IncomeStatement",
    "LegalForm",
    "LoanFacility",
    "RatioSet",
    "ScorecardResult",
    "Sector",
    "Verdict",
    "compute_ratios",
    "evaluate",
    "run_diagnostic",
]
