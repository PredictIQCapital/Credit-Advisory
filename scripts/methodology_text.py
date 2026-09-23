"""Every user-visible string of the methodology document, in both languages.

The document is generated from the live modules, so the numbers can never drift
from the engine. The prose is the one part that is written rather than derived,
and keeping it here -- rather than inline in the builder -- is what makes a
second language possible without a second document to maintain.

German is the original. English is a translation of it, not a separate text:
when the two disagree, the German is the one that was reasoned about, because
the audience that would ever challenge this document works in German.

`{...}` placeholders are filled by the builder. Each language must carry the
same placeholders; test_methodology_text.py checks that.
"""

from __future__ import annotations

# --------------------------------------------------------------- labels

LABELS = {
    "de": {
        "section": "Abschnitt",
        "title": "Scoring-Methodik",
        "subtitle": "Kennzahlen, Gewichte, Schwellenwerte und Szenariorechnung",
        "doc_title": "Scoring-Methodik &mdash; Credit Readiness Advisory",
        "footer": "Scoring-Methodik &middot; Credit Readiness Advisory &middot; Stand {stand}",
        "page": "Seite",
        "fact_factors": "gewichtete Faktoren",
        "fact_calibrated": "davon empirisch kalibriert",
        "fact_weight": "kalibriertes Gewicht",
        "fact_scenarios": "Stressszenarien",
        "fact_knockouts": "Ausschlusskriterien",
        # table headers
        "th_factor": "Faktor",
        "th_weight": "Gewicht",
        "th_kind": "Art",
        "th_origin": "Regulatorische Herkunft",
        "th_breakpoints": "Stuetzstellen (Kennzahlenwert = Punkte, linear interpoliert)",
        "th_no": "Nr.",
        "th_eba_metric": "Kennzahl laut EBA Anhang 3 B",
        "th_covered": "Abgedeckt",
        "th_implementation": "Umsetzung",
        "th_code": "Code",
        "th_criterion": "Kriterium",
        "th_condition": "Bedingung",
        "th_basis": "Grundlage",
        "th_scenario": "Szenario",
        "th_assumption": "Annahme und Fundstelle",
        "th_level": "Stufe",
        "th_points": "Punkte",
        "th_meaning": "Bedeutung",
        "th_value": "Wert",
        "th_contribution": "Beitrag",
        "th_delta": "Delta",
        "th_source": "Quelle",
        "th_taken": "Was daraus uebernommen ist",
        "tag_calibrated": "kalibriert",
        "tag_convention": "Konvention",
        "convention_plain": "Konvention",
        "bundesbank_prefix": "Bundesbank",
        "total": "Gesamtergebnis",
        "baseline": "Ausgangslage",
        "lang_switch": "English",
    },
    "en": {
        "section": "Section",
        "title": "Scoring Methodology",
        "subtitle": "Ratios, weights, thresholds and scenario analysis",
        "doc_title": "Scoring Methodology &mdash; Credit Readiness Advisory",
        "footer": "Scoring Methodology &middot; Credit Readiness Advisory &middot; as at {stand}",
        "page": "Page",
        "fact_factors": "weighted factors",
        "fact_calibrated": "empirically calibrated",
        "fact_weight": "calibrated weight",
        "fact_scenarios": "stress scenarios",
        "fact_knockouts": "knock-out criteria",
        "th_factor": "Factor",
        "th_weight": "Weight",
        "th_kind": "Type",
        "th_origin": "Regulatory origin",
        "th_breakpoints": "Breakpoints (ratio value = points, linearly interpolated)",
        "th_no": "No.",
        "th_eba_metric": "Metric per EBA Annex 3 B",
        "th_covered": "Covered",
        "th_implementation": "How it is handled",
        "th_code": "Code",
        "th_criterion": "Criterion",
        "th_condition": "Condition",
        "th_basis": "Basis",
        "th_scenario": "Scenario",
        "th_assumption": "Assumption and source",
        "th_level": "Band",
        "th_points": "Points",
        "th_meaning": "Meaning",
        "th_value": "Value",
        "th_contribution": "Contribution",
        "th_delta": "Delta",
        "th_source": "Source",
        "th_taken": "What is taken from it",
        "tag_calibrated": "calibrated",
        "tag_convention": "convention",
        "convention_plain": "Convention",
        "bundesbank_prefix": "Bundesbank",
        "total": "Total",
        "baseline": "Base case",
        "lang_switch": "Deutsch",
    },
}

# ------------------------------------------------- calibrated series labels

CALIBRATED = {
    "de": {
        "eigenkapitalquote": "Eigenmittel / Bilanzsumme",
        "ebit_marge": "Ergebnis vor Steuern / Umsatz",
        "liquiditaet_2_grades": "Liquiditaet 2. Grades",
        "gesamtkapitalrentabilitaet_bbk": "(Jahresergebnis + Zins) / Bilanzsumme",
        "anlagendeckungsgrad_ii": "Langfr. Kapital / Anlagevermoegen",
        "kreditorenlaufzeit_tage": "Verb. aus LuL / Materialaufwand",
    },
    "en": {
        "eigenkapitalquote": "Equity / total assets",
        "ebit_marge": "Pre-tax result / revenue",
        "liquiditaet_2_grades": "Quick ratio",
        "gesamtkapitalrentabilitaet_bbk": "(Net result + interest) / total assets",
        "anlagendeckungsgrad_ii": "Long-term capital / fixed assets",
        "kreditorenlaufzeit_tage": "Trade payables / materials expense",
    },
}

FACTOR_LABELS = {
    "en": {
        "eigenkapitalquote": "Equity ratio (economic)",
        "kapitaldienstfaehigkeit_inkl_neu": "Debt service coverage incl. new facility (DSCR)",
        "dynamischer_verschuldungsgrad": "Dynamic gearing (net debt / EBITDA)",
        "ebit_marge": "EBIT margin",
        "liquiditaet_2_grades": "Quick ratio",
        "zinsdeckungsgrad": "Interest coverage (EBIT / interest)",
        "gesamtkapitalrentabilitaet_bbk": "Return on assets (net result + interest)",
        "anlagendeckungsgrad_ii": "Fixed-asset coverage II",
        "kreditorenlaufzeit_tage": "Days payable outstanding",
        "kontokorrent_auslastung": "Overdraft utilisation",
        "bwa_age_months": "Currency of the monthly accounts (BWA)",
        "creditreform_bonitaetsindex": "Creditreform credit index",
        "zahlungsverhalten": "Payment behaviour",
    },
}

HERKUNFT = {
    "de": {
        "eigenkapitalquote": "EBA Anh. 3 Nr. 6; Bundesbank-Modellkennzahl",
        "kapitaldienstfaehigkeit_inkl_neu": "EBA Anh. 3 Nr. 14, 19; MaRisk BTO 1.2.1 Tz. 1",
        "dynamischer_verschuldungsgrad": "EBA Anh. 3 Nr. 10; Bundesbank-Zusatzkennzahl",
        "ebit_marge": "EBA Anh. 3 Nr. 24; Bundesbank-Modellkennzahl",
        "liquiditaet_2_grades": "EBA Anh. 3 Nr. 16; Bundesbank-Modellkennzahl",
        "zinsdeckungsgrad": "EBA Anh. 3 Nr. 21",
        "gesamtkapitalrentabilitaet_bbk": "EBA Anh. 3 Nr. 18",
        "anlagendeckungsgrad_ii": "Goldene Bilanzregel; Bundesbank-Verhaeltniszahl",
        "kreditorenlaufzeit_tage": "Bundesbank-Zusatzkennzahl (Kreditorenziel)",
        "kontokorrent_auslastung": "EBA Tz. 121 d (Inanspruchnahme zugesagter Linien)",
        "bwa_age_months": "EBA Anh. 2 B Nr. 3 (Aktualitaet der Rechnungslegung)",
        "creditreform_bonitaetsindex": "EBA Anh. 2 B Nr. 8, 9 (externe Auskunft/Rating)",
        "zahlungsverhalten": "EBA Tz. 121 d (Zahlungsverhalten, Steuer-/Sozialabgaben)",
    },
    "en": {
        "eigenkapitalquote": "EBA Annex 3 no. 6; Bundesbank model ratio",
        "kapitaldienstfaehigkeit_inkl_neu": "EBA Annex 3 no. 14, 19; MaRisk BTO 1.2.1 para. 1",
        "dynamischer_verschuldungsgrad": "EBA Annex 3 no. 10; Bundesbank additional ratio",
        "ebit_marge": "EBA Annex 3 no. 24; Bundesbank model ratio",
        "liquiditaet_2_grades": "EBA Annex 3 no. 16; Bundesbank model ratio",
        "zinsdeckungsgrad": "EBA Annex 3 no. 21",
        "gesamtkapitalrentabilitaet_bbk": "EBA Annex 3 no. 18",
        "anlagendeckungsgrad_ii": "Golden balance-sheet rule; Bundesbank ratio",
        "kreditorenlaufzeit_tage": "Bundesbank additional ratio (days payable)",
        "kontokorrent_auslastung": "EBA para. 121 d (drawings on committed lines)",
        "bwa_age_months": "EBA Annex 2 B no. 3 (currency of the accounts)",
        "creditreform_bonitaetsindex": "EBA Annex 2 B no. 8, 9 (external report/rating)",
        "zahlungsverhalten": "EBA para. 121 d (payment behaviour, tax and social security)",
    },
}

# EBA/GL/2020/06 Annex 3 B. Metric names stay in the guideline's own English.
EBA_ANHANG3 = {
    "de": [
        ("6", "ja", "Eigenkapitalquote (wirtschaftlich), Gewicht 0,16"),
        ("7", "teilweise", "Ueber Eigenkapitalquote und dyn. Verschuldungsgrad abgedeckt; "
         "nicht zusaetzlich gewichtet, um Verschuldung nicht dreifach zu zaehlen."),
        ("8", "ja", "Eingangsgroesse fuer DSCR, Verschuldungsgrad und Marge"),
        ("9", "nein", "Objektkennzahl der Immobilienfinanzierung"),
        ("10", "ja", "Dyn. Verschuldungsgrad, Gewicht 0,11"),
        ("11", "nein", "Setzt Marktwerte voraus; im Mittelstand nicht verfuegbar"),
        ("12", "nein", "Objektkennzahl der Immobilienfinanzierung"),
        ("13", "teilweise", "Ueber Debitoren- und Kreditorenlaufzeit sowie "
         "Anlagendeckung; keine eigene Kennzahl"),
        ("14", "ja", "Kapitaldienstfaehigkeit, Gewicht 0,20"),
        ("15", "nein", "Setzt eine Kapitalflussrechnung voraus; kleine Gesellschaften erstellen keine"),
        ("16", "ja", "Liquiditaet 2. Grades, Gewicht 0,07 (strenger als Liquiditaet 3. Grades)"),
        ("17", "teilweise", "Ueber die Szenariorechnung, nicht ueber eine Planungsrechnung"),
        ("18", "ja", "Gesamtkapitalrentabilitaet, Gewicht 0,05"),
        ("19", "ja", "Nenner der Kapitaldienstfaehigkeit"),
        ("20", "nein", "Projektfinanzierungskennzahl"),
        ("21", "ja", "Zinsdeckungsgrad, Gewicht 0,05"),
        ("22", "nein", "Bei duennem oder negativem Buchkapital instabil bis irrefuehrend - "
         "und genau das ist im inhabergefuehrten Mittelstand haeufig"),
        ("23", "teilweise", "Ueber die Gesamtkapitalrentabilitaet"),
        ("24", "ja", "EBIT-Marge, Gewicht 0,09"),
        ("25", "teilweise", "Wird berechnet und im Bericht ausgewiesen, aber nicht gewichtet: "
         "ein Jahresvergleich traegt keine Gewichtung"),
    ],
    "en": [
        ("6", "yes", "Equity ratio (economic), weight 0.16"),
        ("7", "partly", "Covered through the equity ratio and dynamic gearing; not weighted "
         "separately, so that leverage is not counted three times."),
        ("8", "yes", "Input to the DSCR, to gearing and to the margin"),
        ("9", "no", "A property metric, for real estate finance"),
        ("10", "yes", "Dynamic gearing, weight 0.11"),
        ("11", "no", "Requires market values; not available for private SMEs"),
        ("12", "no", "A property metric, for real estate finance"),
        ("13", "partly", "Through days receivable, days payable and fixed-asset coverage; "
         "no metric of its own"),
        ("14", "yes", "Debt service coverage, weight 0.20"),
        ("15", "no", "Requires a cash flow statement; small companies do not prepare one"),
        ("16", "yes", "Quick ratio, weight 0.07 (stricter than the current ratio)"),
        ("17", "partly", "Through the scenario analysis, not through a forecast"),
        ("18", "yes", "Return on assets, weight 0.05"),
        ("19", "yes", "The denominator of debt service coverage"),
        ("20", "no", "A project finance metric"),
        ("21", "yes", "Interest coverage, weight 0.05"),
        ("22", "no", "Unstable to the point of being misleading where book equity is thin or "
         "negative - which is common in owner-managed SMEs"),
        ("23", "partly", "Through return on assets"),
        ("24", "yes", "EBIT margin, weight 0.09"),
        ("25", "partly", "Computed and shown in the report, but not weighted: a single "
         "year-on-year comparison does not carry a weight"),
    ],
}

EBA_METRIC_NAMES = [
    "Equity ratio", "(Long-term) debt-to-equity ratio", "EBITDA", "Debt yield",
    "Interest bearing debt / EBITDA", "Enterprise value", "Capitalisation rate",
    "Asset quality", "Total debt service coverage ratio", "Cash debt coverage ratio",
    "Coverage ratio (current assets / short-term debt)", "Future cash flow analysis",
    "Return on assets", "Debt service", "Loan to cost", "Interest coverage ratio",
    "Return on equity ratio", "Return on capital employed", "Net profit margin",
    "Turnover evolution",
]

TAG_CLASS = {"ja": "yes", "teilweise": "part", "nein": "no",
             "yes": "yes", "partly": "part", "no": "no"}

# --------------------------------------------------------- knock-out catalogue

KNOCKOUTS = {
    "en": {
        "KO01": ("Loss of half the share capital",
                 "Balance-sheet equity < 50% of subscribed capital",
                 "Sec. 49(3) GmbHG; Banque de France note 4-/6"),
        "KO02": ("Balance-sheet over-indebtedness",
                 "Balance-sheet equity negative",
                 "Sec. 19 InsO; EBA/GL/2020/06 para. 128 a"),
        "KO03": ("Overdraft limit breached",
                 "Drawings > the advised limit",
                 "Article 178 CRR (definition of default)"),
        "KO04": ("Tax arrears",
                 "Arrears owed to the tax office",
                 "EBA/GL/2020/06 para. 121 d"),
        "KO05": ("Returned direct debits",
                 "Returned direct debits in the last 12 months; 3 or more is serious",
                 "Banque de France note 8"),
        "KO06": ("Consecutive losses",
                 "Net loss in the current and the prior year",
                 "Banque de France note 6"),
        "KO07": ("Interest absorbing EBITDA",
                 "Interest expense >= 50% of EBITDA; 100% or more is serious",
                 "Banque de France note 6"),
        "KO08": ("Accounts too old",
                 "Most recent accounts >= 23 months old",
                 "Banque de France note X"),
    },
}

COVER_LEDE = {
    "de": "Dieses Dokument beschreibt vollstaendig, wie die Bereitschaftsstufe "
          "eines Unternehmens zustande kommt: welche Kennzahlen eingehen, woher "
          "jeder einzelne Schwellenwert stammt und was bewusst nicht modelliert "
          "wird. Es ist so geschrieben, dass ein Steuerberater oder ein "
          "Kreditanalyst jeden Wert nachrechnen und jeder Annahme widersprechen kann.",
    "en": "This document sets out in full how a company's readiness band comes "
          "about: which ratios feed it, where every single threshold comes from, "
          "and what is deliberately not modelled. It is written so that a tax "
          "adviser or a credit analyst can recompute every value and disagree "
          "with every assumption.",
}

# sensitivity.SCENARIOS carries its label and assumption in German. Only the
# English rendering lives here; the German is read from the module itself, so
# the report and this document cannot disagree about what was assumed.
SCENARIOS = {
    "en": {
        "zinsschock": (
            "Interest rates +200 basis points",
            "All credit facilities become 2.00 percentage points more expensive "
            "(EBA/GL/2020/06 para. 158 k). For comparison: in the adverse scenario of "
            "the 2025 EU-wide stress test German long-term rates rise by about 1.1 "
            "percentage points - so this is the harder test."),
        "umsatzrueckgang": (
            "Revenue down 10%",
            "Revenue -10%, of which 65% variable costs fall away with it; fixed costs "
            "remain (EBA/GL/2020/06 para. 158 a). The order of magnitude follows the "
            "adverse scenario of the 2025 EU-wide stress test, which assumes German GDP "
            "7.5% lower on a cumulative basis."),
        "kombiniert": (
            "Combined: revenue -10% and rates +200 bp",
            "Both events at once (EBA/GL/2020/06 para. 156 expressly permits a "
            "multifactor analysis)."),
    },
}

BAND_INTERPRETATION = {
    "en": {
        "A": "Likely financeable on standard terms",
        "B": "Financeable; terms probably improvable",
        "C": "Borderline - the typical decline and mispricing zone",
        "D": "Decline likely without restructuring or a guarantee",
        "E": "Substantial credit weakness",
    },
}
