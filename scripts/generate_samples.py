"""Generate synthetic SME test cases.

These are FICTIONAL companies built to exercise specific diagnostic paths. They
are not anonymised real clients and must never be presented as evidence of
anything about the real market.

Each case targets one archetype from the blueprint's thesis:

    case_01  mixed fixable      profitable Mittelstaendler, equity understated
    case_02  structure          wrong instrument: permanent overdraft + slow debtors
    case_03  genuine risk       the honest-decline case
    case_04  collateral gap     strong earnings, asset-light, nothing to pledge
    case_05  pure presentation  bankable but documented badly
    case_06  already bankable   control case: should produce no drama

Run:  python scripts/generate_samples.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"


def case_01() -> dict:
    """Profitable precision engineering GmbH whose equity is understated.

    Shareholder loan sits as debt for want of a subordination declaration; the
    overdraft is permanently drawn; debtors are slow. Everything real is fine.
    """
    return {
        "case_id": "CASE-01",
        "profile": {
            "name": "Mueller Praezisionstechnik GmbH",
            "legal_form": "GmbH",
            "sector": "Verarbeitendes Gewerbe",
            "employees": 45,
            "founded_year": 2009,
            "city": "Schwaebisch Gmuend",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "immaterielle_vermoegensgegenstaende": 60_000,
            "sachanlagen": 2_100_000,
            "vorraete": 780_000,
            "forderungen_ll": 1_150_000,
            "sonstige_vermoegensgegenstaende": 90_000,
            "liquide_mittel": 180_000,
            "aktive_rap": 25_000,
            "gezeichnetes_kapital": 25_000,
            "gewinnruecklagen": 95_000,
            "gewinnvortrag": 95_000,
            "jahresueberschuss": 230_000,
            "rueckstellungen": 350_000,
            "verb_kreditinstitute_kurz": 420_000,
            "verb_kreditinstitute_lang": 1_250_000,
            "verb_ll": 680_000,
            "sonstige_verbindlichkeiten_kurz": 240_000,
            "sonstige_verbindlichkeiten_lang": 400_000,
            "gesellschafterdarlehen": 600_000,
            "gesellschafterdarlehen_rangruecktritt": False,
            "kontokorrent_limit": 500_000,
            "kontokorrent_inanspruchnahme": 420_000,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 8_200_000,
            "sonstige_betriebliche_ertraege": 45_000,
            "materialaufwand": 4_180_000,
            "personalaufwand": 2_650_000,
            "abschreibungen": 245_000,
            "sonstige_betriebliche_aufwendungen": 790_000,
            "zinsaufwand": 95_000,
            "steuern": 55_000,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 7_650_000,
            "materialaufwand": 3_920_000,
            "personalaufwand": 2_480_000,
            "abschreibungen": 238_000,
            "sonstige_betriebliche_aufwendungen": 745_000,
            "zinsaufwand": 88_000,
        },
        "facilities": [
            {
                "lender": "Sparkasse Ostalb",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 2_000_000,
                "outstanding": 1_250_000,
                "interest_rate": 0.048,
                "annual_principal_repayment": 180_000,
                "maturity_year": 2032,
                "collateralised": True,
            },
            {
                "lender": "Sparkasse Ostalb",
                "facility_type": "Kontokorrent",
                "original_amount": 500_000,
                "outstanding": 420_000,
                "interest_rate": 0.095,
                "annual_principal_repayment": 0,
            },
        ],
        "behavior": {
            "bwa_age_months": 5,
            "bwa_frequency": "quartalsweise",
            "creditreform_bonitaetsindex": 248,
            "days_beyond_terms": 6,
            "overdraft_days_at_limit_12m": 95,
            "jahresabschluss_age_months": 8,
            "has_planning_forecast": False,
        },
        "request": {
            "amount": 750_000,
            "purpose": "Investition",
            "tenor_years": 7,
            "collateral_available": 400_000,
            "urgency_weeks": 16,
        },
    }


def case_02() -> dict:
    """Wholesaler financing its customers through its own credit line."""
    return {
        "case_id": "CASE-02",
        "profile": {
            "name": "Nordlicht Handel GmbH & Co. KG",
            "legal_form": "GmbH & Co. KG",
            "sector": "Grosshandel",
            "employees": 28,
            "founded_year": 2014,
            "city": "Bremen",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "sachanlagen": 420_000,
            "vorraete": 1_850_000,
            "forderungen_ll": 2_240_000,
            "liquide_mittel": 60_000,
            "sonstige_vermoegensgegenstaende": 70_000,
            "gezeichnetes_kapital": 50_000,
            "gewinnruecklagen": 220_000,
            "gewinnvortrag": 130_000,
            "jahresueberschuss": 116_000,
            "rueckstellungen": 145_000,
            "verb_kreditinstitute_kurz": 1_480_000,
            "verb_kreditinstitute_lang": 320_000,
            "verb_ll": 1_690_000,
            "sonstige_verbindlichkeiten_kurz": 489_000,
            "kontokorrent_limit": 1_500_000,
            "kontokorrent_inanspruchnahme": 1_460_000,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 11_400_000,
            "materialaufwand": 8_950_000,
            "personalaufwand": 1_420_000,
            "abschreibungen": 95_000,
            "sonstige_betriebliche_aufwendungen": 640_000,
            "zinsaufwand": 148_000,
            "steuern": 31_000,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 10_900_000,
            "materialaufwand": 8_520_000,
            "personalaufwand": 1_360_000,
            "abschreibungen": 92_000,
            "sonstige_betriebliche_aufwendungen": 610_000,
            "zinsaufwand": 121_000,
        },
        "facilities": [
            {
                "lender": "Volksbank Bremen",
                "facility_type": "Kontokorrent",
                "original_amount": 1_500_000,
                "outstanding": 1_460_000,
                "interest_rate": 0.089,
                "annual_principal_repayment": 0,
            },
            {
                "lender": "Volksbank Bremen",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 500_000,
                "outstanding": 320_000,
                "interest_rate": 0.052,
                "annual_principal_repayment": 65_000,
                "maturity_year": 2029,
            },
        ],
        "behavior": {
            "bwa_age_months": 2,
            "bwa_frequency": "monatlich",
            "creditreform_bonitaetsindex": 289,
            "days_beyond_terms": 14,
            "overdraft_days_at_limit_12m": 210,
            "has_planning_forecast": False,
        },
        "request": {
            "amount": 600_000,
            "purpose": "Betriebsmittel",
            "tenor_years": 5,
            "collateral_available": 150_000,
            "urgency_weeks": 12,
        },
    }


def case_03() -> dict:
    """The honest-decline case: loss-making, shrinking, overleveraged."""
    return {
        "case_id": "CASE-03",
        "profile": {
            "name": "Gastro Rheinblick GmbH",
            "legal_form": "GmbH",
            "sector": "Gastgewerbe",
            "employees": 34,
            "founded_year": 2017,
            "city": "Koeln",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "sachanlagen": 1_450_000,
            "immaterielle_vermoegensgegenstaende": 180_000,
            "vorraete": 85_000,
            "forderungen_ll": 45_000,
            "liquide_mittel": 22_000,
            "gezeichnetes_kapital": 25_000,
            "gewinnvortrag": -137_000,
            "jahresueberschuss": -458_000,
            "rueckstellungen": 120_000,
            "verb_kreditinstitute_kurz": 380_000,
            "verb_kreditinstitute_lang": 1_180_000,
            "verb_ll": 295_000,
            "sonstige_verbindlichkeiten_kurz": 377_000,
            "kontokorrent_limit": 400_000,
            "kontokorrent_inanspruchnahme": 380_000,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 2_980_000,
            "materialaufwand": 1_090_000,
            "personalaufwand": 1_520_000,
            "abschreibungen": 210_000,
            "sonstige_betriebliche_aufwendungen": 520_000,
            "zinsaufwand": 98_000,
            "steuern": 0,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 3_780_000,
            "materialaufwand": 1_310_000,
            "personalaufwand": 1_680_000,
            "abschreibungen": 215_000,
            "sonstige_betriebliche_aufwendungen": 545_000,
            "zinsaufwand": 92_000,
        },
        "facilities": [
            {
                "lender": "Kreissparkasse Koeln",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 1_600_000,
                "outstanding": 1_180_000,
                "interest_rate": 0.051,
                "annual_principal_repayment": 145_000,
                "maturity_year": 2033,
            },
            {
                "lender": "Kreissparkasse Koeln",
                "facility_type": "Kontokorrent",
                "original_amount": 400_000,
                "outstanding": 380_000,
                "interest_rate": 0.102,
                "annual_principal_repayment": 0,
            },
        ],
        "behavior": {
            "bwa_age_months": 7,
            "bwa_frequency": "quartalsweise",
            "creditreform_bonitaetsindex": 384,
            "days_beyond_terms": 28,
            "returned_direct_debits_12m": 3,
            "overdraft_days_at_limit_12m": 265,
            "tax_arrears": True,
            "has_planning_forecast": False,
        },
        "request": {
            "amount": 350_000,
            "purpose": "Betriebsmittel",
            "tenor_years": 5,
            "collateral_available": 40_000,
            "urgency_weeks": 6,
        },
    }


def case_04() -> dict:
    """Asset-light IT services: earnings are fine, there is simply nothing to pledge."""
    return {
        "case_id": "CASE-04",
        "profile": {
            "name": "Datenwerk Consulting GmbH",
            "legal_form": "GmbH",
            "sector": "Information und Kommunikation",
            "employees": 52,
            "founded_year": 2016,
            "city": "Leipzig",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "immaterielle_vermoegensgegenstaende": 95_000,
            "sachanlagen": 210_000,
            "forderungen_ll": 1_420_000,
            "sonstige_vermoegensgegenstaende": 85_000,
            "liquide_mittel": 640_000,
            "gezeichnetes_kapital": 50_000,
            "kapitalruecklage": 150_000,
            "gewinnruecklagen": 320_000,
            "gewinnvortrag": 260_000,
            "jahresueberschuss": 485_000,
            "rueckstellungen": 285_000,
            "verb_kreditinstitute_kurz": 0,
            "verb_kreditinstitute_lang": 180_000,
            "verb_ll": 340_000,
            "sonstige_verbindlichkeiten_kurz": 380_000,
            "kontokorrent_limit": 300_000,
            "kontokorrent_inanspruchnahme": 0,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 7_850_000,
            "materialaufwand": 1_180_000,
            "personalaufwand": 5_100_000,
            "abschreibungen": 105_000,
            "sonstige_betriebliche_aufwendungen": 820_000,
            "zinsaufwand": 12_000,
            "steuern": 148_000,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 6_420_000,
            "materialaufwand": 980_000,
            "personalaufwand": 4_280_000,
            "abschreibungen": 98_000,
            "sonstige_betriebliche_aufwendungen": 690_000,
            "zinsaufwand": 14_000,
        },
        "facilities": [
            {
                "lender": "Sparkasse Leipzig",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 300_000,
                "outstanding": 180_000,
                "interest_rate": 0.045,
                "annual_principal_repayment": 60_000,
                "maturity_year": 2029,
            }
        ],
        "behavior": {
            "bwa_age_months": 2,
            "bwa_frequency": "monatlich",
            "creditreform_bonitaetsindex": 195,
            "days_beyond_terms": 2,
            "overdraft_days_at_limit_12m": 0,
            "has_planning_forecast": True,
        },
        "request": {
            "amount": 1_200_000,
            "purpose": "Wachstum",
            "tenor_years": 6,
            "collateral_available": 180_000,
            "urgency_weeks": 20,
        },
    }


def case_05() -> dict:
    """Bankable business, badly documented. The purest 'presentation' case."""
    return {
        "case_id": "CASE-05",
        "profile": {
            "name": "Ihrig Sanitaer- und Heizungstechnik GmbH",
            "legal_form": "GmbH",
            "sector": "Baugewerbe",
            "employees": 22,
            "founded_year": 2005,
            "city": "Kassel",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "sachanlagen": 1_000_000,
            "vorraete": 240_000,
            "forderungen_ll": 520_000,
            "liquide_mittel": 310_000,
            "gezeichnetes_kapital": 25_000,
            "gewinnruecklagen": 232_000,
            "gewinnvortrag": 140_000,
            "jahresueberschuss": 96_000,
            "rueckstellungen": 165_000,
            "verb_kreditinstitute_kurz": 90_000,
            "verb_kreditinstitute_lang": 560_000,
            "verb_ll": 322_000,
            "sonstige_verbindlichkeiten_kurz": 120_000,
            "gesellschafterdarlehen": 320_000,
            "gesellschafterdarlehen_rangruecktritt": False,
            "kontokorrent_limit": 250_000,
            "kontokorrent_inanspruchnahme": 90_000,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 3_640_000,
            "materialaufwand": 1_580_000,
            "personalaufwand": 1_480_000,
            "abschreibungen": 92_000,
            "sonstige_betriebliche_aufwendungen": 330_000,
            "zinsaufwand": 34_000,
            "steuern": 28_000,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 3_480_000,
            "materialaufwand": 1_510_000,
            "personalaufwand": 1_420_000,
            "abschreibungen": 90_000,
            "sonstige_betriebliche_aufwendungen": 318_000,
            "zinsaufwand": 36_000,
        },
        "facilities": [
            {
                "lender": "Kasseler Sparkasse",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 800_000,
                "outstanding": 560_000,
                "interest_rate": 0.044,
                "annual_principal_repayment": 80_000,
                "maturity_year": 2032,
            },
            {
                "lender": "Kasseler Sparkasse",
                "facility_type": "Kontokorrent",
                "original_amount": 250_000,
                "outstanding": 90_000,
                "interest_rate": 0.091,
                "annual_principal_repayment": 0,
            },
        ],
        "behavior": {
            "bwa_age_months": 9,
            "bwa_frequency": "jaehrlich",
            "creditreform_bonitaetsindex": 262,
            "days_beyond_terms": 4,
            "overdraft_days_at_limit_12m": 0,
            "jahresabschluss_age_months": 14,
            "has_planning_forecast": False,
        },
        "request": {
            "amount": 400_000,
            "purpose": "Investition",
            "tenor_years": 8,
            "collateral_available": 350_000,
            "urgency_weeks": 20,
        },
    }


def case_06() -> dict:
    """Control case: strong on every dimension. Should generate no drama."""
    return {
        "case_id": "CASE-06",
        "profile": {
            "name": "Hoffmann Medizintechnik GmbH",
            "legal_form": "GmbH",
            "sector": "Verarbeitendes Gewerbe",
            "employees": 78,
            "founded_year": 1998,
            "city": "Tuttlingen",
        },
        "balance_sheet": {
            "period_end": "2025-12-31",
            "sachanlagen": 3_200_000,
            "immaterielle_vermoegensgegenstaende": 140_000,
            "finanzanlagen": 260_000,
            "vorraete": 1_180_000,
            "forderungen_ll": 1_340_000,
            "liquide_mittel": 1_850_000,
            "gezeichnetes_kapital": 200_000,
            "kapitalruecklage": 400_000,
            "gewinnruecklagen": 2_763_000,
            "gewinnvortrag": 610_000,
            "jahresueberschuss": 967_000,
            "rueckstellungen": 690_000,
            "verb_kreditinstitute_kurz": 120_000,
            "verb_kreditinstitute_lang": 1_340_000,
            "verb_ll": 690_000,
            "sonstige_verbindlichkeiten_kurz": 190_000,
            "kontokorrent_limit": 800_000,
            "kontokorrent_inanspruchnahme": 0,
        },
        "income_statement": {
            "period_end": "2025-12-31",
            "period_months": 12,
            "umsatzerloese": 14_600_000,
            "sonstige_betriebliche_ertraege": 85_000,
            "materialaufwand": 6_100_000,
            "personalaufwand": 5_180_000,
            "abschreibungen": 480_000,
            "sonstige_betriebliche_aufwendungen": 1_580_000,
            "zinsaufwand": 68_000,
            "steuern": 310_000,
        },
        "prior_year_income": {
            "period_end": "2024-12-31",
            "umsatzerloese": 13_900_000,
            "materialaufwand": 5_840_000,
            "personalaufwand": 4_950_000,
            "abschreibungen": 465_000,
            "sonstige_betriebliche_aufwendungen": 1_510_000,
            "zinsaufwand": 71_000,
        },
        "facilities": [
            {
                "lender": "Kreissparkasse Tuttlingen",
                "facility_type": "Tilgungsdarlehen",
                "original_amount": 2_500_000,
                "outstanding": 1_340_000,
                "interest_rate": 0.041,
                "annual_principal_repayment": 220_000,
                "maturity_year": 2031,
                "collateralised": True,
            }
        ],
        "behavior": {
            "bwa_age_months": 1,
            "bwa_frequency": "monatlich",
            "creditreform_bonitaetsindex": 168,
            "days_beyond_terms": 0,
            "overdraft_days_at_limit_12m": 0,
            "has_planning_forecast": True,
        },
        "request": {
            "amount": 1_500_000,
            "purpose": "Investition",
            "tenor_years": 8,
            "collateral_available": 1_400_000,
            "urgency_weeks": 26,
        },
    }


CASES = {
    "case_01_mueller_praezisionstechnik.json": case_01,
    "case_02_nordlicht_handel.json": case_02,
    "case_03_gastro_rheinblick.json": case_03,
    "case_04_datenwerk_consulting.json": case_04,
    "case_05_ihrig_sanitaer.json": case_05,
    "case_06_hoffmann_medizintechnik.json": case_06,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, builder in CASES.items():
        payload = builder()
        (OUT / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"geschrieben: {filename}")
    print(f"\n{len(CASES)} Testfaelle in {OUT}")


if __name__ == "__main__":
    main()
