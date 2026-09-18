"""JSON intake -- the canonical, reliable case format.

Everything else (DATEV parsing, PDF/OCR) is a convenience that ultimately
produces this structure. Keeping one canonical format means the diagnostic is
testable without any parsing dependency.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ..models import (
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


def _parse_date(value: Any, default: date | None = None) -> date:
    if value is None:
        return default or date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _fields_of(cls) -> set[str]:
    return set(getattr(cls, "__dataclass_fields__", {}).keys())


def _build(cls, payload: dict[str, Any], **overrides):
    """Instantiate a dataclass from a dict, ignoring unknown keys.

    Unknown keys are dropped rather than raising: client intake files are
    hand-edited in practice, and a stray comment field should not fail a run.
    Missing REQUIRED keys still raise, which is the behaviour we want.
    """
    allowed = _fields_of(cls)
    kwargs = {k: v for k, v in payload.items() if k in allowed}
    kwargs.update(overrides)
    return cls(**kwargs)


def load_case(payload: dict[str, Any]) -> ClientCase:
    """Build a ClientCase from a plain dict."""
    p = payload["profile"]
    profile = _build(
        CompanyProfile,
        p,
        legal_form=LegalForm(p["legal_form"]),
        sector=Sector(p["sector"]),
    )

    bs_payload = payload["balance_sheet"]
    balance = _build(
        BalanceSheet, bs_payload, period_end=_parse_date(bs_payload.get("period_end"))
    )

    gu_payload = payload["income_statement"]
    income = _build(
        IncomeStatement, gu_payload, period_end=_parse_date(gu_payload.get("period_end"))
    )

    facilities = [_build(LoanFacility, f) for f in payload.get("facilities", [])]
    behavior = _build(BehavioralData, payload.get("behavior", {}))

    request = None
    if payload.get("request"):
        request = _build(FinancingRequest, payload["request"])

    prior_income = None
    if payload.get("prior_year_income"):
        pi = payload["prior_year_income"]
        prior_income = _build(
            IncomeStatement, pi, period_end=_parse_date(pi.get("period_end"))
        )

    prior_balance = None
    if payload.get("prior_year_balance"):
        pb = payload["prior_year_balance"]
        prior_balance = _build(
            BalanceSheet, pb, period_end=_parse_date(pb.get("period_end"))
        )

    return ClientCase(
        profile=profile,
        balance_sheet=balance,
        income_statement=income,
        facilities=facilities,
        behavior=behavior,
        request=request,
        prior_year_income=prior_income,
        prior_year_balance=prior_balance,
        case_id=payload.get("case_id", "UNTITLED"),
    )


def load_case_file(path: str | Path) -> ClientCase:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return load_case(data)
