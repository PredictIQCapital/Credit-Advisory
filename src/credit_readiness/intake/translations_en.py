"""English texts for the questionnaires and the document catalogue.

The German definitions in questionnaire.py / documents.py stay the source of
truth (they are what clients and Steuerberater sign). This module only adds an
English rendering for the portal's language switch -- for investors, for the
founder's own review, and for international shareholders of a client.

`tests/test_intake.py` checks that every question, section, option and
document has an English text, so a new question cannot ship untranslated.
"""

from __future__ import annotations

from copy import deepcopy

QUESTIONNAIRE_EN = {
    "unternehmen": (
        "Questionnaire for the company",
        "These answers complete your accounting data with what no trial balance "
        "shows. Each question says why we ask it. If you do not know something, "
        "leave it blank -- a gap is better than a guess.",
    ),
    "steuerberater": (
        "Questionnaire for the tax advisor",
        "Your client is having its creditworthiness analysed. We make no "
        "reclassification or revaluation without your approval. Where both you and "
        "the client answer the same point, your confirmation takes precedence.",
    ),
}

SECTION_EN = {
    ("unternehmen", "unternehmen"): ("1. Company", "Basic data, used to compare you with your sector and size class."),
    ("unternehmen", "vorhaben"): ("2. Financing need", "What you want to finance. This decides which kind of lender fits at all -- often more than the ratios do."),
    ("unternehmen", "finanzierungen"): ("3. Existing financing", "All current loans, overdraft lines and leases. An incomplete list makes your debt capacity look better than the bank will see it."),
    ("unternehmen", "gesellschafter"): ("4. Shareholders", "Banks treat shareholder loans as equity or as debt, depending on how they are documented."),
    ("unternehmen", "verhalten"): ("5. Reporting and payment behaviour", "Soft factors. They weigh more in a bank rating than most owners expect -- and they are the cheapest to improve."),
    ("unternehmen", "einwilligung"): ("6. Consent and contact", "We cannot start without these."),
    ("steuerberater", "kanzlei"): ("1. Firm", ""),
    ("steuerberater", "buchhaltung"): ("2. Bookkeeping and year-end accounts", "Needed to read the trial balance correctly."),
    ("steuerberater", "bestaetigungen"): ("3. Confirmations", "These points often decide whether a weakness is fixable or not."),
    ("steuerberater", "sondereffekte"): ("4. One-off effects and assessment", "We adjust nothing automatically. These answers inform the advice, not the ratios."),
}

# (label, help, why). Empty strings where the German has none.
QUESTION_EN: dict[tuple[str, str], tuple[str, str, str]] = {
    # ------------------------------------------------------------- company
    ("unternehmen", "firmenname"): ("Company name", "", ""),
    ("unternehmen", "rechtsform"): ("Legal form", "", ""),
    ("unternehmen", "branche"): ("Sector", "", "Your ratios are compared with the sector median -- a low equity ratio means something different in hospitality than in IT."),
    ("unternehmen", "mitarbeiter"): ("Number of employees (full-time equivalents)", "", ""),
    ("unternehmen", "gruendungsjahr"): ("Year founded", "", ""),
    ("unternehmen", "sitz"): ("Registered office (city)", "", ""),
    ("unternehmen", "land"): ("Country", "", ""),
    ("unternehmen", "hrb_nummer"): ("Commercial register number", "e.g. HRB 12345, Amtsgericht Ulm", ""),
    ("unternehmen", "betrag"): ("Amount you want to finance", "", ""),
    ("unternehmen", "zweck"): ("Purpose", "", ""),
    ("unternehmen", "zweck_beschreibung"): ("Short description of the project", "", ""),
    ("unternehmen", "laufzeit_jahre"): ("Preferred term", "", "The term sets the annual instalment and therefore your debt-service capacity."),
    ("unternehmen", "sicherheiten_wert"): ("Value of available collateral", "", "A rejection despite sound numbers is often a collateral problem -- which public guarantee programmes can solve."),
    ("unternehmen", "sicherheiten_beschreibung"): ("What collateral?", "Land charges, machinery, assignment of receivables, guarantees", ""),
    ("unternehmen", "benoetigt_in_wochen"): ("When do you need the money?", "", ""),
    ("unternehmen", "bereits_abgelehnt"): ("Has this request already been rejected?", "", ""),
    ("unternehmen", "ablehnung_details"): ("By whom, and with what reason?", "", "A documented rejection affects the next application. We need to know about it."),
    ("unternehmen", "hausbank"): ("Main bank", "", ""),
    ("unternehmen", "darlehen"): ("Current loans and credit lines", "", "Interest plus repayment on all loans is your debt service -- the single most important figure in a bank rating."),
    ("unternehmen", "darlehen.kreditgeber"): ("Lender", "e.g. Sparkasse Ostalb", ""),
    ("unternehmen", "darlehen.art"): ("Type of financing", "", ""),
    ("unternehmen", "darlehen.urspruenglicher_betrag"): ("Original amount", "", ""),
    ("unternehmen", "darlehen.restschuld"): ("Outstanding / drawn amount", "", ""),
    ("unternehmen", "darlehen.zinssatz"): ("Interest rate", "For variable rates, the current rate.", ""),
    ("unternehmen", "darlehen.tilgung_pro_jahr"): ("Repayment per year", "0 for an overdraft line.", ""),
    ("unternehmen", "darlehen.laufzeit_bis"): ("Matures in (year)", "", ""),
    ("unternehmen", "darlehen.besichert"): ("Secured?", "", ""),
    ("unternehmen", "kontokorrent_limit"): ("Overdraft limit (all lines combined)", "", ""),
    ("unternehmen", "kontokorrent_inanspruchnahme"): ("Overdraft currently drawn", "", ""),
    ("unternehmen", "tage_am_limit"): ("On how many days in the last 12 months was the overdraft (almost) fully drawn?", "An estimate is fine. It is replaced by your bank statements once uploaded.", "A permanently maxed-out overdraft is one of the strongest warning signs for banks -- and often easy to fix with the right loan."),
    ("unternehmen", "leasing_verpflichtungen"): ("Total outstanding lease obligations", "", ""),
    ("unternehmen", "tilgung_gesamt_jahr"): ("Total annual repayments on all bank loans (estimate)", "Only needed while the loan list above is empty.", "Together with the interest expense from your annual accounts this gives your debt service -- also for the quick check."),
    ("unternehmen", "ki_einwilligung"): ("I consent to uploaded annual accounts being sent to an AI service provider for automatic reading.", "Voluntary. Without consent we read locally or you enter the figures yourself.", "The AI only reads figures; the assessment uses transparent rules only. You confirm every figure before it is used."),
    ("unternehmen", "hat_gesellschafterdarlehen"): ("Have shareholders lent money to the company?", "", ""),
    ("unternehmen", "gesellschafterdarlehen_betrag"): ("Amount of shareholder loans", "", ""),
    ("unternehmen", "rangruecktritt"): ("Is there a subordination agreement (Rangruecktritt) for these loans?", "A written declaration that the loan ranks behind all other creditors in insolvency.", "With subordination, almost every bank counts the loan as economic equity. It is the most common single lever."),
    ("unternehmen", "bereitschaft_einlage"): ("Would shareholders be willing to inject additional capital?", "", ""),
    ("unternehmen", "bwa_frequenz"): ("How often is a management report (BWA) prepared?", "", ""),
    ("unternehmen", "bwa_stand"): ("Month of the latest management report (BWA)", "", "An outdated BWA is read as weak internal reporting."),
    ("unternehmen", "planrechnung_vorhanden"): ("Is there a current financial plan (P&L plan / cash-flow plan)?", "", ""),
    ("unternehmen", "zahlungsverzug_tage"): ("On average, how many days after the due date do you pay suppliers?", "0 if you pay on time.", ""),
    ("unternehmen", "ruecklastschriften_12m"): ("Number of returned direct debits in the last 12 months", "", ""),
    ("unternehmen", "steuerrueckstaende"): ("Are there currently any tax arrears?", "", "A knock-out criterion for almost every bank. We need to know before the bank does."),
    ("unternehmen", "creditreform_index"): ("Creditreform credit index (if known)", "Between 100 (very good) and 600 (default).", ""),
    ("unternehmen", "datenschutz_einwilligung"): ("I consent to the processing of the submitted data for the purpose of the creditworthiness analysis.", "", ""),
    ("unternehmen", "steuerberater_kontakt_erlaubt"): ("You may contact our tax advisor directly.", "", "Every reclassification needs your tax advisor's approval."),
    ("unternehmen", "steuerberater_kanzlei"): ("Your tax advisor's firm", "", ""),
    ("unternehmen", "steuerberater_email"): ("Your tax advisor's e-mail", "", ""),
    ("unternehmen", "ansprechpartner"): ("Your name", "", ""),
    ("unternehmen", "ansprechpartner_email"): ("Your e-mail", "", ""),
    ("unternehmen", "ansprechpartner_telefon"): ("Your phone number", "", ""),
    # --------------------------------------------------------- tax advisor
    ("steuerberater", "kanzlei"): ("Firm", "", ""),
    ("steuerberater", "ansprechpartner"): ("Contact person", "", ""),
    ("steuerberater", "email"): ("E-mail", "", ""),
    ("steuerberater", "telefon"): ("Phone", "", ""),
    ("steuerberater", "kontenrahmen"): ("Chart of accounts used", "", "The account mapping depends entirely on it. Currently only SKR04 is read automatically."),
    ("steuerberater", "individuelle_konten"): ("Are there individual changes to the standard chart of accounts?", "", ""),
    ("steuerberater", "individuelle_konten_details"): ("Which?", "", ""),
    ("steuerberater", "jahresabschluss_festgestellt"): ("Have the latest annual accounts been formally adopted?", "", ""),
    ("steuerberater", "jahresabschluss_stichtag"): ("Balance-sheet date of the latest annual accounts", "", ""),
    ("steuerberater", "bwa_frequenz"): ("Management report (BWA) frequency", "", ""),
    ("steuerberater", "bwa_stand"): ("Month of the latest available BWA", "", ""),
    ("steuerberater", "rangruecktritt_bestaetigt"): ("Is there a qualified subordination agreement for shareholder loans?", "", ""),
    ("steuerberater", "steuerrueckstaende"): ("Are there tax arrears?", "", ""),
    ("steuerberater", "stundungsvereinbarung"): ("Is there a deferral or instalment agreement with the tax office?", "", ""),
    ("steuerberater", "planrechnung_vorhanden"): ("Is there an integrated financial plan, or can one be prepared?", "", ""),
    ("steuerberater", "einmaleffekte_betrag"): ("One-off, non-recurring expenses in the last financial year", "", ""),
    ("steuerberater", "einmaleffekte_beschreibung"): ("Which?", "", ""),
    ("steuerberater", "bilanzierungswahlrechte"): ("Were accounting options used that materially affect equity?", "", ""),
    ("steuerberater", "besondere_risiken"): ("Are you aware of risks not visible in the numbers?", "", "A finding the bank discovers later costs more trust than one we address beforehand."),
    ("steuerberater", "freigabe_umgliederung"): ("You are willing to review proposed reclassifications (e.g. subordination).", "", ""),
}

OPTION_EN = {
    "Verarbeitendes Gewerbe": "Manufacturing",
    "Baugewerbe": "Construction",
    "Grosshandel": "Wholesale",
    "Einzelhandel": "Retail",
    "Verkehr und Lagerei": "Transport and logistics",
    "Gastgewerbe": "Hospitality",
    "Information und Kommunikation": "Information and communication",
    "Freiberufliche und technische Dienstleistungen": "Professional and technical services",
    "Gesundheitswesen": "Healthcare",
    "Sonstige Dienstleistungen": "Other services",
    "Betriebsmittel": "Working capital",
    "Investition": "Investment",
    "Wachstum": "Growth",
    "Umschuldung": "Refinancing",
    "Tilgungsdarlehen": "Term loan",
    "Kontokorrent": "Overdraft line",
    "Foerderkredit": "Development-bank loan",
    "Leasing": "Leasing",
    "Sonstiges": "Other",
    "monatlich": "monthly",
    "quartalsweise": "quarterly",
    "jaehrlich": "annually",
    "ja": "yes",
    "nein": "no",
    "keine Gesellschafterdarlehen": "no shareholder loans",
    "anderer": "other",
    "SKR03": "SKR03",
    "SKR04": "SKR04",
    "DE": "Germany",
    "AT": "Austria",
    # Legal forms are proper names and stay as they are.
    "GmbH": "GmbH", "UG (haftungsbeschraenkt)": "UG (haftungsbeschraenkt)",
    "GmbH & Co. KG": "GmbH & Co. KG", "Einzelunternehmen": "Sole proprietorship",
    "OHG": "OHG", "KG": "KG", "AG": "AG", "GbR": "GbR",
}

# (title, description, why, condition_text)
DOCUMENT_EN = {
    "susa_aktuell": ("Trial balance, current year (DATEV export)", "DATEV export as CSV (semicolon) with the columns Konto and Saldo. Year-end or current interim trial balance.", "The main source of every balance-sheet and P&L ratio. Read automatically and checked for plausibility.", ""),
    "susa_vorjahr": ("Trial balance, prior year (DATEV export)", "As above, for the closed prior year.", "Shows the trend. Falling revenue with negative margins is a finding only the year-on-year comparison reveals.", ""),
    "bwa_aktuell": ("Current management report (BWA)", "Management report no older than 2-3 months.", "Banks require a current BWA; its age is read as a sign of the quality of internal reporting.", ""),
    "jahresabschluesse": ("Annual accounts of the last 2-3 years", "Balance sheet, P&L and notes, one file per year. The latest one is read automatically for the quick check.", "The basis of every credit decision and a mandatory part of any loan application.", ""),
    "steuerkonto": ("Tax account statement or tax clearance certificate", "Current statement of the tax office account.", "Proves there are no tax arrears -- a knock-out criterion for banks.", ""),
    "stundungsvereinbarung": ("Deferral or instalment agreement with the tax office", "Written agreement on existing tax arrears.", "Without it, a loan application with tax arrears is practically hopeless.", "required if there are tax arrears"),
    "planrechnung": ("Financial plan (P&L plan, cash-flow plan, balance-sheet plan)", "Integrated plan for at least 24 months.", "From around EUR 100,000 banks expect a forward view, not only a backward one.", "required from EUR 100,000 requested"),
    "kontoumsaetze": ("Bank transactions of the last 6-12 months (CSV export)", "CSV export from online banking, one file per business account, with booking date, amount and ideally balance.", "The single most valuable source: account data is live and cannot be dressed up. Shows overdraft use and returned debits.", ""),
    "darlehensvertraege": ("Loan and lease agreements", "All current loan, overdraft and lease agreements.", "Terms, maturities, collateral and covenants can only be read from the contracts.", "required if you have current loans"),
    "handelsregisterauszug": ("Current commercial register extract", "No older than 3 months.", "Standard part of every loan application; proves who may represent the company.", ""),
    "rangruecktrittserklaerung": ("Subordination agreement (Rangruecktritt)", "Signed declaration subordinating the shareholder loans.", "Only with the document will the bank count the loan as equity.", "required if a subordination is stated"),
    "sicherheitenaufstellung": ("List of collateral", "Land register extracts, valuations, machinery lists.", "Decides whether there is a collateral gap and how large it is.", ""),
    "gesellschafterliste": ("List of shareholders", "Current list of shareholders.", "Ownership structure; relevant for guarantees and public funding programmes.", ""),
    "creditreform_auskunft": ("Creditreform report", "Business credit report with credit index. We obtain it.", "Shows what the lender already sees before opening your file. Please also enter the index in the questionnaire.", ""),
}


def questionnaire_with_english(q: dict) -> dict:
    """Return a copy of Questionnaire.as_dict() with *_en fields added."""
    aud = q["audience"]
    out = deepcopy(q)
    out["title_en"], out["intro_en"] = QUESTIONNAIRE_EN[aud]
    for s in out["sections"]:
        s["title_en"], s["intro_en"] = SECTION_EN[(aud, s["id"])]
        for question in s["questions"]:
            _add_question_en(aud, question, prefix="")
    return out


def _add_question_en(aud: str, question: dict, prefix: str) -> None:
    label, help_, why = QUESTION_EN[(aud, prefix + question["id"])]
    question["label_en"], question["help_en"], question["why_en"] = label, help_, why
    if "options" in question:
        question["options_en"] = [OPTION_EN[o] for o in question["options"]]
    for f in question.get("fields", []):
        _add_question_en(aud, f, prefix=question["id"] + ".")


def document_with_english(d: dict) -> dict:
    out = dict(d)
    out["title_en"], out["description_en"], out["why_en"], out["condition_text_en"] = DOCUMENT_EN[d["id"]]
    return out
