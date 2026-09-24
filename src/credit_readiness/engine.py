"""Orchestrator: one case in, one complete diagnostic out.

This is the only entry point callers should need. Everything it returns is
plain data, so the same result object feeds the CLI, the report writer, the
outcome-tracking log, and (later) an API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from . import benchmarks
from .models import ClientCase
from .ratios import RatioSet, compute_ratios
from .remediation import (
    Finding,
    SimulationResult,
    Verdict,
    classify,
    diagnose,
    simulate,
)
from .improvement import ImprovementPlan, plan as plan_improvements
from .projection import Projection, project
from .routing import RoutingOption, route
from .rejection_risk import RejectionScreen, screen as screen_rejection
from .scorecard import ScorecardResult, evaluate
from .sensitivity import SensitivityResult, analyse as analyse_sensitivity
from .validation import Severity, ValidationIssue, assert_valid, validate

DISCLAIMER = (
    "Richtungsweisende Einschaetzung der Kreditfaehigkeit auf Basis oeffentlich "
    "bekannter Analysepraxis. KEIN Rating, keine Ausfallwahrscheinlichkeit, keine "
    "Zusage oder Prognose einer Kreditentscheidung. Jede Kreditentscheidung trifft "
    "ausschliesslich der jeweilige Kreditgeber nach eigenen Massstaeben."
)


@dataclass
class DiagnosticResult:
    case: ClientCase
    ratios: RatioSet
    scorecard: ScorecardResult
    findings: list[Finding]
    verdict: Verdict
    simulation: SimulationResult
    routing_now: list[RoutingOption]
    routing_after: list[RoutingOption]
    benchmark: list[benchmarks.BenchmarkComparison] = field(default_factory=list)
    sensitivity: Optional[SensitivityResult] = None
    rejection: Optional[RejectionScreen] = None
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    #: The same file on the all-sector curves. Printed next to the sector score
    #: because sector scoring says "typical for its sector", not "low-risk
    #: sector" -- lenders price the latter separately (ADR-005).
    scorecard_generic: Optional[ScorecardResult] = None
    sector_trends: list[benchmarks.SectorTrend] = field(default_factory=list)
    projection: Optional[Projection] = None
    improvements: Optional[ImprovementPlan] = None
    generated_on: date = field(default_factory=date.today)
    disclaimer: str = DISCLAIMER

    @property
    def data_warnings(self) -> list[ValidationIssue]:
        return [i for i in self.validation_issues if i.severity is Severity.WARNING]

    @property
    def top_weaknesses(self) -> list:
        return self.scorecard.ranked_weaknesses[:5]

    @property
    def is_engageable(self) -> bool:
        """Whether this is a case the advisory can actually help.

        Used for pipeline triage and -- more importantly -- for validating the
        blueprint's 'fixable vs genuinely uncreditworthy' split against real
        cases instead of assumption.
        """
        return self.verdict in (
            Verdict.FIXABLE_PRESENTATION,
            Verdict.FIXABLE_STRUCTURE,
        )


def run_diagnostic(case: ClientCase, strict: bool = True) -> DiagnosticResult:
    """Run the full diagnostic.

    `strict=True` (the default) refuses to analyse a file with ERROR-level data
    problems, because a plausible-looking diagnostic computed from a broken
    balance sheet is worse than no diagnostic at all. Pass strict=False only for
    exploratory work on known-dirty data.
    """
    issues = assert_valid(case) if strict else validate(case)

    ratios = compute_ratios(case)
    scorecard = evaluate(case, ratios)
    findings = diagnose(case, ratios, scorecard)
    verdict = classify(findings, scorecard)
    sim = simulate(case, findings)

    routing_now = route(case, ratios, scorecard, label="aktuell")

    # Route the post-remediation profile too: the whole pitch is that the
    # corrected file reaches lenders the current one cannot.
    import copy

    corrected = copy.deepcopy(case)
    for f in findings:
        if f.simulate and (f.category.is_fixable or f.rule_id == "R09"):
            f.simulate(corrected)
    corrected_ratios = compute_ratios(corrected)
    corrected_card = evaluate(corrected, corrected_ratios)
    routing_after = route(corrected, corrected_ratios, corrected_card, label="nach Massnahmen")

    return DiagnosticResult(
        case=case,
        ratios=ratios,
        scorecard=scorecard,
        findings=findings,
        verdict=verdict,
        simulation=sim,
        routing_now=routing_now,
        routing_after=routing_after,
        benchmark=benchmarks.compare_all(case.profile.sector, ratios),
        sensitivity=analyse_sensitivity(case, scorecard),
        rejection=screen_rejection(case, ratios),
        validation_issues=issues,
        scorecard_generic=evaluate(case, ratios, sector_specific=False),
        sector_trends=benchmarks.sector_trends(case.profile.sector, ratios),
        projection=project(case),
        improvements=plan_improvements(case, ratios, scorecard),
    )
