"""Domain model for German/Austrian SME financials (HGB structure).

Deliberately mirrors the HGB 266 (Bilanz) and 275 (GuV, Gesamtkostenverfahren)
layouts so that a DATEV BWA / Jahresabschluss maps onto it with minimal
translation. Every field is the value a Steuerberater would recognise by name.

All monetary amounts are EUR, as floats. Precision beyond the cent is irrelevant
here: every downstream use is a ratio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class LegalForm(str, Enum):
    GMBH = "GmbH"
    UG = "UG (haftungsbeschraenkt)"
    GMBH_CO_KG = "GmbH & Co. KG"
    EINZELUNTERNEHMEN = "Einzelunternehmen"
    OHG = "OHG"
    KG = "KG"
    AG = "AG"
    GBR = "GbR"


class Sector(str, Enum):
    """Coarse sector buckets aligned to Bundesbank ratio publications."""

    MANUFACTURING = "Verarbeitendes Gewerbe"
    CONSTRUCTION = "Baugewerbe"
    WHOLESALE = "Grosshandel"
    RETAIL = "Einzelhandel"
    TRANSPORT = "Verkehr und Lagerei"
    HOSPITALITY = "Gastgewerbe"
    IT_SERVICES = "Information und Kommunikation"
    PROFESSIONAL_SERVICES = "Freiberufliche und technische Dienstleistungen"
    HEALTHCARE = "Gesundheitswesen"
    OTHER_SERVICES = "Sonstige Dienstleistungen"


@dataclass
class CompanyProfile:
    name: str
    legal_form: LegalForm
    sector: Sector
    employees: int
    founded_year: int
    hrb_number: Optional[str] = None
    city: Optional[str] = None
    country: str = "DE"

    @property
    def age_years(self) -> int:
        return date.today().year - self.founded_year

    @property
    def size_class(self) -> str:
        """EU size classes. The blueprint targets small + medium (10-249)."""
        if self.employees < 10:
            return "micro"
        if self.employees < 50:
            return "small"
        if self.employees < 250:
            return "medium"
        return "large"


@dataclass
class BalanceSheet:
    """HGB 266 Bilanz. Field names follow the German original."""

    period_end: date

    # --- AKTIVA ---
    immaterielle_vermoegensgegenstaende: float = 0.0   # incl. goodwill
    sachanlagen: float = 0.0                           # tangible fixed assets
    finanzanlagen: float = 0.0
    vorraete: float = 0.0                              # inventory
    forderungen_ll: float = 0.0                        # trade receivables
    sonstige_vermoegensgegenstaende: float = 0.0
    wertpapiere: float = 0.0
    liquide_mittel: float = 0.0                        # cash + bank
    aktive_rap: float = 0.0                            # prepaid expenses

    # --- PASSIVA ---
    gezeichnetes_kapital: float = 0.0
    kapitalruecklage: float = 0.0
    gewinnruecklagen: float = 0.0
    gewinnvortrag: float = 0.0                         # may be negative
    jahresueberschuss: float = 0.0                     # may be negative

    ausstehende_einlagen: float = 0.0                  # deducted from equity
    rueckstellungen: float = 0.0
    pensionsrueckstellungen: float = 0.0

    verb_kreditinstitute_kurz: float = 0.0             # bank debt < 1yr
    verb_kreditinstitute_lang: float = 0.0             # bank debt > 1yr
    verb_ll: float = 0.0                               # trade payables
    sonstige_verbindlichkeiten_kurz: float = 0.0
    sonstige_verbindlichkeiten_lang: float = 0.0
    passive_rap: float = 0.0

    # --- Items that decide fixability, not just size ---
    gesellschafterdarlehen: float = 0.0                # shareholder loan
    gesellschafterdarlehen_rangruecktritt: bool = False
    kontokorrent_limit: float = 0.0                    # overdraft facility
    kontokorrent_inanspruchnahme: float = 0.0          # drawn amount
    leasing_verpflichtungen: float = 0.0               # off-balance-sheet

    # --- Derived ---
    @property
    def anlagevermoegen(self) -> float:
        return (
            self.immaterielle_vermoegensgegenstaende
            + self.sachanlagen
            + self.finanzanlagen
        )

    @property
    def umlaufvermoegen(self) -> float:
        return (
            self.vorraete
            + self.forderungen_ll
            + self.sonstige_vermoegensgegenstaende
            + self.wertpapiere
            + self.liquide_mittel
        )

    @property
    def bilanzsumme(self) -> float:
        return self.anlagevermoegen + self.umlaufvermoegen + self.aktive_rap

    @property
    def bilanzielles_eigenkapital(self) -> float:
        """Equity as it appears on the balance sheet."""
        return (
            self.gezeichnetes_kapital
            + self.kapitalruecklage
            + self.gewinnruecklagen
            + self.gewinnvortrag
            + self.jahresueberschuss
            - self.ausstehende_einlagen
        )

    @property
    def wirtschaftliches_eigenkapital(self) -> float:
        """Economic equity, as a bank analyst would restate it.

        A shareholder loan WITH a Rangruecktritt (subordination declaration) is
        treated as equity-like by essentially every German lender. Without one,
        it is plain debt. This single distinction is the most common fixable
        presentation defect in the target segment -- see fixability.py.
        """
        ek = self.bilanzielles_eigenkapital
        if self.gesellschafterdarlehen_rangruecktritt:
            ek += self.gesellschafterdarlehen
        return ek

    @property
    def finanzverbindlichkeiten(self) -> float:
        """Interest-bearing debt (excludes trade payables)."""
        debt = self.verb_kreditinstitute_kurz + self.verb_kreditinstitute_lang
        if not self.gesellschafterdarlehen_rangruecktritt:
            debt += self.gesellschafterdarlehen
        return debt

    @property
    def nettofinanzverbindlichkeiten(self) -> float:
        return max(
            0.0,
            self.finanzverbindlichkeiten - self.liquide_mittel - self.wertpapiere,
        )

    @property
    def kurzfristige_verbindlichkeiten(self) -> float:
        return (
            self.verb_kreditinstitute_kurz
            + self.verb_ll
            + self.sonstige_verbindlichkeiten_kurz
        )

    @property
    def langfristiges_kapital(self) -> float:
        """Equity plus long-term debt -- the numerator of Anlagendeckung II."""
        return (
            self.wirtschaftliches_eigenkapital
            + self.verb_kreditinstitute_lang
            + self.sonstige_verbindlichkeiten_lang
            + self.pensionsrueckstellungen
        )

    @property
    def kontokorrent_auslastung(self) -> Optional[float]:
        """Overdraft utilisation. Sustained >80% is a classic bank red flag."""
        if self.kontokorrent_limit <= 0:
            return None
        return self.kontokorrent_inanspruchnahme / self.kontokorrent_limit


@dataclass
class IncomeStatement:
    """HGB 275 GuV, Gesamtkostenverfahren."""

    period_end: date
    period_months: int = 12

    umsatzerloese: float = 0.0
    bestandsveraenderungen: float = 0.0
    sonstige_betriebliche_ertraege: float = 0.0
    materialaufwand: float = 0.0
    personalaufwand: float = 0.0
    abschreibungen: float = 0.0
    sonstige_betriebliche_aufwendungen: float = 0.0
    zinsertraege: float = 0.0
    zinsaufwand: float = 0.0
    steuern: float = 0.0

    @property
    def gesamtleistung(self) -> float:
        return (
            self.umsatzerloese
            + self.bestandsveraenderungen
            + self.sonstige_betriebliche_ertraege
        )

    @property
    def ebitda(self) -> float:
        return (
            self.gesamtleistung
            - self.materialaufwand
            - self.personalaufwand
            - self.sonstige_betriebliche_aufwendungen
        )

    @property
    def ebit(self) -> float:
        return self.ebitda - self.abschreibungen

    @property
    def ebt(self) -> float:
        return self.ebit + self.zinsertraege - self.zinsaufwand

    @property
    def jahresueberschuss(self) -> float:
        return self.ebt - self.steuern

    @property
    def annualisation_factor(self) -> float:
        """BWAs arrive mid-year; ratios must compare like with like."""
        return 12.0 / self.period_months if self.period_months else 1.0

    def annualised(self, value: float) -> float:
        return value * self.annualisation_factor


@dataclass
class LoanFacility:
    """An existing facility. Drives the Kapitaldienst (debt service) figure."""

    lender: str
    facility_type: str            # Tilgungsdarlehen, Kontokorrent, Leasing, ...
    original_amount: float
    outstanding: float
    interest_rate: float          # decimal, e.g. 0.058
    annual_principal_repayment: float
    maturity_year: Optional[int] = None
    collateralised: bool = False

    @property
    def annual_interest(self) -> float:
        return self.outstanding * self.interest_rate

    @property
    def annual_debt_service(self) -> float:
        return self.annual_interest + self.annual_principal_repayment


@dataclass
class BehavioralData:
    """Soft factors. In a real bank scorecard these carry real weight, and in
    this segment they are also the cheapest things to fix."""

    bwa_age_months: float = 1.0                # months since latest BWA
    bwa_frequency: str = "monatlich"           # monatlich | quartalsweise | jaehrlich
    creditreform_bonitaetsindex: Optional[int] = None   # 100 (best) - 600 (worst)
    days_beyond_terms: float = 0.0             # avg payment delay to suppliers
    returned_direct_debits_12m: int = 0
    overdraft_days_at_limit_12m: int = 0       # days at/over the KK limit
    jahresabschluss_age_months: float = 6.0
    has_planning_forecast: bool = False        # Planrechnung / forecast provided
    tax_arrears: bool = False                  # Steuerrueckstaende


@dataclass
class FinancingRequest:
    """What the client actually wants -- shapes routing more than ratios do."""

    amount: float
    purpose: str                  # Betriebsmittel, Investition, Wachstum, Umschuldung
    tenor_years: int = 5
    collateral_available: float = 0.0
    urgency_weeks: Optional[int] = None


@dataclass
class ClientCase:
    """Everything one engagement needs in a single object."""

    profile: CompanyProfile
    balance_sheet: BalanceSheet
    income_statement: IncomeStatement
    facilities: list[LoanFacility] = field(default_factory=list)
    behavior: BehavioralData = field(default_factory=BehavioralData)
    request: Optional[FinancingRequest] = None
    prior_year_income: Optional[IncomeStatement] = None
    prior_year_balance: Optional[BalanceSheet] = None
    case_id: str = "UNTITLED"

    @property
    def kapitaldienst(self) -> float:
        """Total annual debt service across existing facilities."""
        return sum(f.annual_debt_service for f in self.facilities)

    @property
    def kapitaldienst_inkl_neu(self) -> float:
        """Debt service including the requested new facility.

        Annuity approximation at an assumed 6.5% -- deliberately conservative,
        because understating future debt service is how a 'fixed' file gets
        rejected anyway.
        """
        base = self.kapitaldienst
        if not self.request:
            return base
        rate, n = 0.065, max(1, self.request.tenor_years)
        annuity = self.request.amount * (rate * (1 + rate) ** n) / ((1 + rate) ** n - 1)
        return base + annuity
