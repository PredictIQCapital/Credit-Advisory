"""Input validation.

Why this module exists, in one sentence: a confident diagnostic computed from a
broken input file is the worst failure mode this business has.

If a balance sheet does not balance, the most likely cause is a parsing or
data-entry error -- and every ratio downstream is then wrong in a way that looks
entirely plausible on the page. The client's Steuerberater will spot it, and the
credibility cost of that is far higher than the cost of refusing to run.

So: validate first, and make ERROR-level issues block by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import ClientCase
from .formatting import de

BALANCE_TOLERANCE_ABS = 1.0        # EUR
BALANCE_TOLERANCE_REL = 0.005      # 0.5% of total assets


class Severity(str, Enum):
    ERROR = "FEHLER"
    WARNING = "WARNUNG"
    INFO = "HINWEIS"


@dataclass
class ValidationIssue:
    severity: Severity
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.code}: {self.message}"


class ValidationError(RuntimeError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__(
            "Eingabedaten nicht plausibel:\n"
            + "\n".join(f"  {i}" for i in issues)
        )


def validate(case: ClientCase) -> list[ValidationIssue]:
    """Return every issue found. Callers decide whether to proceed."""
    issues: list[ValidationIssue] = []
    b = case.balance_sheet
    g = case.income_statement

    # --- the big one: does the balance sheet balance? --------------------
    aktiva = b.bilanzsumme
    passiva = (
        b.bilanzielles_eigenkapital
        + b.rueckstellungen
        + b.pensionsrueckstellungen
        + b.verb_kreditinstitute_kurz
        + b.verb_kreditinstitute_lang
        + b.verb_ll
        + b.sonstige_verbindlichkeiten_kurz
        + b.sonstige_verbindlichkeiten_lang
        + b.gesellschafterdarlehen
        + b.passive_rap
    )
    diff = aktiva - passiva
    tolerance = max(BALANCE_TOLERANCE_ABS, abs(aktiva) * BALANCE_TOLERANCE_REL)
    if abs(diff) > tolerance:
        issues.append(
            ValidationIssue(
                Severity.ERROR,
                "BILANZ_UNAUSGEGLICHEN",
                f"Aktiva ({de(aktiva)} EUR) und Passiva ({de(passiva)} EUR) "
                f"weichen um {de(diff)} EUR ab. Vor jeder Auswertung klaeren -- "
                "meist ein Zuordnungs- oder Erfassungsfehler.",
            )
        )

    # --- do the two statements belong to each other? ----------------------
    # The GuV result must equal the profit line carried in equity. A mismatch
    # means the BWA and the balance sheet are from different periods or
    # different runs -- an analyst checks this within the first minute, and so
    # must we, because every equity-based ratio depends on it.
    if g.period_months == 12 and b.jahresueberschuss == 0 and g.jahresueberschuss != 0:
        # An abridged balance sheet carries one aggregated equity line and no
        # separate result, so there is nothing to reconcile against. Say so
        # rather than blocking -- but say it, because the other possible cause
        # is that the reader missed the line.
        issues.append(
            ValidationIssue(
                Severity.WARNING,
                "KEIN_BILANZERGEBNIS",
                "Die Bilanz weist kein separates Jahresergebnis aus (aggregiertes "
                "Eigenkapital). Der Abgleich mit der GuV entfaellt -- bitte pruefen, "
                "ob das Eigenkapital vollstaendig erfasst ist.",
            )
        )
    elif g.period_months == 12:
        gu_result = g.jahresueberschuss
        bs_result = b.jahresueberschuss
        gap = abs(gu_result - bs_result)
        gap_tolerance = max(BALANCE_TOLERANCE_ABS, abs(aktiva) * 0.002)
        if gap > gap_tolerance:
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "ERGEBNIS_ABWEICHUNG",
                    f"Der Jahresueberschuss laut GuV ({de(gu_result)} EUR) weicht vom "
                    f"in der Bilanz ausgewiesenen Ergebnis ({de(bs_result)} EUR) um "
                    f"{de(gu_result - bs_result)} EUR ab. Stammen Bilanz und GuV aus "
                    "derselben Periode und demselben Auswertungslauf?",
                )
            )

    # --- structural sanity ------------------------------------------------
    if aktiva <= 0:
        issues.append(
            ValidationIssue(
                Severity.ERROR, "BILANZSUMME_NULL", "Bilanzsumme ist null oder negativ."
            )
        )

    if g.umsatzerloese <= 0:
        issues.append(
            ValidationIssue(
                Severity.ERROR,
                "KEIN_UMSATZ",
                "Keine Umsatzerloese erfasst -- Kennzahlen waeren nicht aussagekraeftig.",
            )
        )

    if not 1 <= g.period_months <= 12:
        issues.append(
            ValidationIssue(
                Severity.ERROR,
                "PERIODE_UNGUELTIG",
                f"period_months = {g.period_months}; zulaessig ist 1-12.",
            )
        )

    for field_name in (
        "vorraete",
        "forderungen_ll",
        "liquide_mittel",
        "sachanlagen",
        "verb_ll",
        "verb_kreditinstitute_kurz",
        "verb_kreditinstitute_lang",
    ):
        value = getattr(b, field_name)
        if value < 0:
            issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    "NEGATIVER_BESTAND",
                    f"{field_name} ist negativ ({de(value)} EUR). Vorzeichen pruefen.",
                )
            )

    # --- overdraft consistency -------------------------------------------
    if b.kontokorrent_limit > 0 and b.kontokorrent_inanspruchnahme > b.kontokorrent_limit:
        issues.append(
            ValidationIssue(
                Severity.WARNING,
                "KK_UEBERZIEHUNG",
                f"Kontokorrent ist mit {de(b.kontokorrent_inanspruchnahme)} EUR ueber "
                f"das Limit von {de(b.kontokorrent_limit)} EUR hinaus in Anspruch "
                "genommen. Als geduldete Ueberziehung ein eigenstaendiges Warnsignal.",
            )
        )

    # --- facilities vs balance sheet -------------------------------------
    if case.facilities:
        facility_debt = sum(
            f.outstanding for f in case.facilities if "leasing" not in f.facility_type.lower()
        )
        bank_debt = b.verb_kreditinstitute_kurz + b.verb_kreditinstitute_lang
        if bank_debt > 0:
            gap = abs(facility_debt - bank_debt) / bank_debt
            if gap > 0.10:
                issues.append(
                    ValidationIssue(
                        Severity.WARNING,
                        "DARLEHEN_ABWEICHUNG",
                        f"Summe der Einzeldarlehen ({de(facility_debt)} EUR) weicht um "
                        f"{de(gap*100)}% von den Bankverbindlichkeiten der Bilanz "
                        f"({de(bank_debt)} EUR) ab. Vollstaendigkeit pruefen -- eine "
                        "unvollstaendige Darlehensliste ueberschaetzt die "
                        "Kapitaldienstfaehigkeit.",
                    )
                )

    # --- data completeness (INFO: shapes what can be scored) --------------
    if not case.facilities:
        issues.append(
            ValidationIssue(
                Severity.INFO,
                "KEINE_DARLEHENSLISTE",
                "Keine Darlehen erfasst -- Kapitaldienstfaehigkeit nicht berechenbar.",
            )
        )
    if case.behavior.creditreform_bonitaetsindex is None:
        issues.append(
            ValidationIssue(
                Severity.INFO,
                "KEINE_AUSKUNFT",
                "Keine Creditreform-Auskunft hinterlegt -- der Kreditgeber sieht "
                "diesen Wert, die Diagnostik nicht.",
            )
        )
    if case.prior_year_income is None:
        issues.append(
            ValidationIssue(
                Severity.INFO,
                "KEIN_VORJAHR",
                "Kein Vorjahresvergleich moeglich -- Trendaussagen entfallen.",
            )
        )

    return issues


def assert_valid(case: ClientCase) -> list[ValidationIssue]:
    """Raise on ERROR-level issues; return the rest."""
    issues = validate(case)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    if errors:
        raise ValidationError(errors)
    return issues
