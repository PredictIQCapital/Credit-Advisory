"""Case assembly: questionnaires + uploaded documents -> one canonical case.

Output is the same JSON payload `ingest.json_intake.load_case` accepts, so a
case built from uploads and a hand-written case go through the identical,
already-tested diagnostic path.

Precedence, when several sources state the same fact
====================================================
    observed (bank statement)  >  Steuerberater confirmation  >  client self-report

Observed data cannot be dressed up; a Steuerberater answers with professional
responsibility; a client answers from memory. Every field whose value came from
a choice between sources is recorded in `provenance`, and the report shows it,
so nobody has to guess where a number came from.

What assembly refuses to do
===========================
It never fills a gap with a guess that could flatter the file. Missing
Kontokorrent data stays missing (the factor is then excluded, visibly), and a
shareholder loan the client mentions but the SuSa does not show is flagged,
not added -- adding it would silently unbalance the balance sheet.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ..ai.extraction import to_statements
from ..ingest.bank_csv import BankAnalysis, BankCsvError, analyse_bank_csv
from ..ingest.datev import DatevMappingError, parse_datev_susa
from .. import nace
from ..formatting import de
from ..models import BalanceSheet, IncomeStatement
from .questionnaire import (
    AUDIENCE_STEUERBERATER,
    AUDIENCE_UNTERNEHMEN,
    AnswerCheck,
    check_answers,
    get_questionnaire,
)

# Questions without which no meaningful diagnostic is possible. The rest of the
# required questions (contact details, ...) matter for the engagement, not for
# the arithmetic, and are listed as outstanding rather than blocking.
DIAGNOSIS_CRITICAL = (
    "firmenname", "rechtsform", "branche", "mitarbeiter", "gruendungsjahr",
    "betrag", "zweck", "hat_gesellschafterdarlehen", "steuerrueckstaende",
    "bwa_frequenz", "bwa_stand",
)

SRC_BANK = "Kontoumsaetze"
SRC_STB = "Steuerberater"
SRC_SME = "Unternehmen (Selbstauskunft)"
SRC_SUSA = "DATEV-SuSa"
SRC_DEFAULT = "Standardannahme"
SRC_CONFIRMED = "Jahresabschluss (ausgelesen, vom Unternehmen bestaetigt)"
CONFIRMED_FIGURES = "figures_confirmed.json"


@dataclass
class Assembly:
    payload: Optional[dict] = None
    blocking: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    bank: list[BankAnalysis] = field(default_factory=list)
    datev: dict[str, dict] = field(default_factory=dict)
    sme_check: Optional[AnswerCheck] = None
    stb_check: Optional[AnswerCheck] = None

    @property
    def ready(self) -> bool:
        return self.payload is not None and not self.blocking

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "blocking": self.blocking,
            "notes": self.notes,
            "provenance": self.provenance,
            "bank": [b.as_dict() for b in self.bank],
            "datev": self.datev,
        }


def months_between(earlier: date, later: date) -> float:
    return float(max(0, (later.year - earlier.year) * 12 + later.month - earlier.month))


def _dc_to_dict(obj: Any) -> dict:
    out = {}
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        out[f.name] = v.isoformat() if isinstance(v, date) else v
    return out


def _pick(prov: dict, key: str, *candidates: tuple[Any, str], default: Any = None,
          default_src: str = SRC_DEFAULT) -> Any:
    """First non-None candidate wins; its source is recorded."""
    for value, src in candidates:
        if value is not None:
            prov[key] = src
            return value
    prov[key] = default_src
    return default


def build_payload(
    case_id: str,
    sme: dict,
    stb: dict,
    current: tuple[BalanceSheet, IncomeStatement],
    prior: Optional[tuple[BalanceSheet, IncomeStatement]] = None,
    bank: Optional[list[BankAnalysis]] = None,
    today: Optional[date] = None,
) -> tuple[dict, dict[str, str], list[str]]:
    """Pure assembly from already-parsed inputs. Returns (payload, provenance, notes).

    `sme` and `stb` are COERCED answer values (see questionnaire.check_answers).
    """
    today = today or date.today()
    bank = bank or []
    prov: dict[str, str] = {}
    notes: list[str] = []
    bs, gu = current

    # ------------------------------------------------------------ profile
    sector = sme["branche"]
    code = nace.parse(sme.get("nace_code"))
    if code is not None:
        # The code is a registered fact, the dropdown a self-assessment: the
        # code wins, and a contradiction is worth a line in the notes.
        prov["profile.sector"] = f"WZ 2008 {code.code}"
        if code.sector.value != sector:
            notes.append(f"Branche laut WZ-Code {code.code}: {code.sector.value} "
                         f"(Selbstauskunft: {sector}). Verwendet wird der WZ-Code.")
        sector = code.sector.value
    profile = {
        "name": sme["firmenname"],
        "legal_form": sme["rechtsform"],
        "sector": sector,
        "nace_code": code.code if code else None,
        "employees": sme["mitarbeiter"],
        "founded_year": sme["gruendungsjahr"],
        "hrb_number": sme.get("hrb_nummer"),
        "city": sme.get("sitz"),
        "country": sme.get("land") or "DE",
    }

    # ------------------------------------------------------ facilities
    facilities = []
    for row in sme.get("darlehen") or []:
        facilities.append({
            "lender": row["kreditgeber"],
            "facility_type": row["art"],
            "original_amount": row.get("urspruenglicher_betrag") or row["restschuld"],
            "outstanding": row["restschuld"],
            "interest_rate": row["zinssatz"],
            "annual_principal_repayment": row.get("tilgung_pro_jahr") or 0.0,
            "maturity_year": row.get("laufzeit_bis"),
            "collateralised": bool(row.get("besichert")),
        })
    prov["facilities"] = SRC_SME if facilities else SRC_DEFAULT
    bank_debt = bs.verb_kreditinstitute_kurz + bs.verb_kreditinstitute_lang
    if not facilities and bank_debt > 0 and sme.get("tilgung_gesamt_jahr") is not None:
        # Quick-check path: no loan list yet. Debt service = interest actually
        # paid (P&L) + the repayments the company states. Transparent estimate,
        # flagged as such -- the full engagement replaces it with the loan list.
        rate = gu.zinsaufwand / bank_debt if gu.zinsaufwand > 0 else 0.05
        facilities.append({
            "lender": "Summe Bankdarlehen (Schaetzung)",
            "facility_type": "Tilgungsdarlehen",
            "original_amount": bank_debt,
            "outstanding": bank_debt,
            "interest_rate": min(max(rate, 0.0), 0.25),
            "annual_principal_repayment": sme["tilgung_gesamt_jahr"],
            "maturity_year": None,
            "collateralised": False,
        })
        prov["facilities"] = "Schaetzung: Zinsaufwand laut GuV + Tilgung laut Unternehmen"
        notes.append(
            "Kapitaldienst geschaetzt aus Zinsaufwand (GuV) und angegebener Jahrestilgung. "
            "Die Darlehensliste im vollstaendigen Fragebogen macht ihn exakt.")

    # -------------------------------------------------------- balance sheet
    balance = _dc_to_dict(bs)
    prov["balance_sheet"] = SRC_SUSA

    kk_from_facilities = sum(
        f["outstanding"] for f in facilities if f["facility_type"] == "Kontokorrent"
    ) or None
    balance["kontokorrent_limit"] = _pick(
        prov, "balance_sheet.kontokorrent_limit",
        (sme.get("kontokorrent_limit"), SRC_SME), default=0.0,
    )
    balance["kontokorrent_inanspruchnahme"] = _pick(
        prov, "balance_sheet.kontokorrent_inanspruchnahme",
        (sme.get("kontokorrent_inanspruchnahme"), SRC_SME),
        (kk_from_facilities, "Darlehensliste (Kontokorrent)"),
        default=0.0,
    )
    balance["leasing_verpflichtungen"] = sme.get("leasing_verpflichtungen") or 0.0

    rr_stb = stb.get("rangruecktritt_bestaetigt")
    balance["gesellschafterdarlehen_rangruecktritt"] = bool(_pick(
        prov, "balance_sheet.gesellschafterdarlehen_rangruecktritt",
        (None if rr_stb is None else rr_stb == "ja", SRC_STB),
        (sme.get("rangruecktritt"), SRC_SME),
        default=False,
    ))
    if rr_stb is None and sme.get("rangruecktritt"):
        notes.append(
            "Rangruecktritt nur vom Unternehmen angegeben, nicht vom Steuerberater "
            "bestaetigt. Vor Vorlage bei der Bank Erklaerung pruefen."
        )

    gd_susa = bs.gesellschafterdarlehen
    gd_sme = sme.get("gesellschafterdarlehen_betrag")
    if sme.get("hat_gesellschafterdarlehen") and gd_susa <= 0:
        notes.append(
            f"Laut Fragebogen bestehen Gesellschafterdarlehen"
            f"{f' ({de(gd_sme)} EUR)' if gd_sme else ''}, die SuSa weist in den "
            "Konten 3600-3699 aber keine aus. Buchung beim Steuerberater klaeren -- "
            "der Betrag wird NICHT ergaenzt, weil das die Bilanz verfaelschen wuerde."
        )
    elif gd_susa > 0 and sme.get("hat_gesellschafterdarlehen") is False:
        notes.append(
            f"Die SuSa weist Gesellschafterdarlehen von {de(gd_susa)} EUR aus, der "
            "Fragebogen verneint solche Darlehen. Bitte klaeren."
        )
    elif gd_susa > 0 and gd_sme and abs(gd_susa - gd_sme) > max(1000, 0.05 * gd_susa):
        notes.append(
            f"Gesellschafterdarlehen laut SuSa {de(gd_susa)} EUR, laut Fragebogen "
            f"{de(gd_sme)} EUR. Es wird der SuSa-Wert verwendet."
        )

    # ---------------------------------------------------------- behaviour
    bwa_stand = _pick(prov, "behavior.bwa_stand",
                      (stb.get("bwa_stand"), SRC_STB), (sme.get("bwa_stand"), SRC_SME))
    behavior: dict[str, Any] = {
        "bwa_frequency": _pick(prov, "behavior.bwa_frequency",
                               (stb.get("bwa_frequenz"), SRC_STB),
                               (sme.get("bwa_frequenz"), SRC_SME), default="monatlich"),
        "bwa_age_months": months_between(bwa_stand, today) if bwa_stand else 12.0,
        "creditreform_bonitaetsindex": sme.get("creditreform_index"),
        "days_beyond_terms": sme.get("zahlungsverzug_tage") or 0,
        "has_planning_forecast": bool(_pick(
            prov, "behavior.has_planning_forecast",
            (stb.get("planrechnung_vorhanden"), SRC_STB),
            (sme.get("planrechnung_vorhanden"), SRC_SME), default=False)),
        "tax_arrears": bool(_pick(
            prov, "behavior.tax_arrears",
            (stb.get("steuerrueckstaende"), SRC_STB),
            (sme.get("steuerrueckstaende"), SRC_SME), default=False)),
    }
    prov["behavior.bwa_age_months"] = prov["behavior.bwa_stand"]
    if not bwa_stand:
        notes.append("Kein BWA-Stand angegeben -- als 12 Monate alt gewertet.")
    if stb.get("jahresabschluss_stichtag"):
        behavior["jahresabschluss_age_months"] = months_between(
            stb["jahresabschluss_stichtag"], today
        )
    if (stb.get("steuerrueckstaende") is not None and sme.get("steuerrueckstaende") is not None
            and stb["steuerrueckstaende"] != sme["steuerrueckstaende"]):
        notes.append(
            "Unternehmen und Steuerberater machen widerspruechliche Angaben zu "
            "Steuerrueckstaenden. Es gilt die Angabe des Steuerberaters."
        )
    if behavior["tax_arrears"] and stb.get("stundungsvereinbarung"):
        notes.append(
            "Steuerrueckstaende bestehen, eine Stundungsvereinbarung liegt vor. "
            "Vereinbarung dem Kreditantrag beilegen."
        )

    # Observed bank data overrides self-reported behaviour.
    with_balance = [b for b in bank if b.days_at_limit_12m is not None]
    behavior["overdraft_days_at_limit_12m"] = _pick(
        prov, "behavior.overdraft_days_at_limit_12m",
        (max((b.days_at_limit_12m for b in with_balance), default=None), SRC_BANK),
        (sme.get("tage_am_limit"), SRC_SME), default=0,
    )
    behavior["returned_direct_debits_12m"] = _pick(
        prov, "behavior.returned_direct_debits_12m",
        (sum(b.returned_direct_debits_12m for b in bank) if bank else None, SRC_BANK),
        (sme.get("ruecklastschriften_12m"), SRC_SME), default=0,
    )
    if bank and sme.get("tage_am_limit") is not None and with_balance:
        observed = behavior["overdraft_days_at_limit_12m"]
        stated = sme["tage_am_limit"]
        if abs(observed - stated) > 30:
            notes.append(
                f"Tage am Kontokorrentlimit: Selbstauskunft {stated}, laut "
                f"Kontoumsaetzen {observed} (hochgerechnet auf 12 Monate). "
                "Verwendet werden die Kontoumsaetze."
            )
    for b in bank:
        for w in b.warnings:
            notes.append(f"Kontoumsaetze {b.account_label or ''}: {w}".replace("  ", " "))

    # ------------------------------------------------------------ request
    request = {
        "amount": sme["betrag"],
        "purpose": sme["zweck"],
        "tenor_years": sme.get("laufzeit_jahre") or 5,
        "collateral_available": sme.get("sicherheiten_wert") or 0.0,
        "urgency_weeks": sme.get("benoetigt_in_wochen"),
    }
    if not sme.get("laufzeit_jahre"):
        notes.append("Keine Laufzeit angegeben -- mit 5 Jahren gerechnet.")

    payload: dict[str, Any] = {
        "case_id": case_id,
        "profile": profile,
        "balance_sheet": balance,
        "income_statement": _dc_to_dict(gu),
        "facilities": facilities,
        "behavior": behavior,
        "request": request,
    }
    if prior:
        payload["prior_year_balance"] = _dc_to_dict(prior[0])
        payload["prior_year_income"] = _dc_to_dict(prior[1])

    if stb.get("einmaleffekte_betrag"):
        notes.append(
            f"Steuerberater nennt Einmaleffekte von {de(stb['einmaleffekte_betrag'])} EUR"
            f"{': ' + stb['einmaleffekte_beschreibung'] if stb.get('einmaleffekte_beschreibung') else ''}. "
            "Nicht in den Kennzahlen bereinigt -- im Bankgespraech gesondert erlaeutern."
        )
    return payload, prov, notes


def assemble_case(store, case_id: str, today: Optional[date] = None) -> Assembly:
    """Build the case payload from everything stored for `case_id`."""
    asm = Assembly()
    sme_raw = store.load_answers(case_id, AUDIENCE_UNTERNEHMEN)
    stb_raw = store.load_answers(case_id, AUDIENCE_STEUERBERATER)
    asm.sme_check = check_answers(get_questionnaire(AUDIENCE_UNTERNEHMEN), sme_raw)
    asm.stb_check = check_answers(get_questionnaire(AUDIENCE_STEUERBERATER), stb_raw)
    sme, stb = asm.sme_check.values, asm.stb_check.values

    # --- questionnaire gates ---------------------------------------------
    if sme.get("datenschutz_einwilligung") is not True:
        asm.blocking.append(
            "Die Datenschutzeinwilligung des Unternehmens fehlt. Ohne sie duerfen "
            "die Daten nicht ausgewertet werden."
        )
    for qid, msg in asm.sme_check.errors.items():
        asm.blocking.append(f"Fragebogen Unternehmen, '{qid}': {msg}")
    for qid, msg in asm.stb_check.errors.items():
        asm.blocking.append(f"Fragebogen Steuerberater, '{qid}': {msg}")
    q = get_questionnaire(AUDIENCE_UNTERNEHMEN)
    for qid in DIAGNOSIS_CRITICAL:
        if qid not in sme and qid not in asm.sme_check.errors:
            asm.blocking.append(f"Fragebogen Unternehmen: '{q.question(qid).label}' fehlt.")
    if not stb:
        asm.notes.append(
            "Fragebogen des Steuerberaters liegt nicht vor -- alle Angaben beruhen "
            "auf der Selbstauskunft des Unternehmens."
        )

    docs = store.list_documents(case_id)
    has_susa = any(d["doc_type"] == "susa_aktuell" for d in docs)
    confirmed_raw = store.read_artifact(case_id, CONFIRMED_FIGURES)
    kontenrahmen = stb.get("kontenrahmen") or "SKR04"
    if kontenrahmen != "SKR04" and (has_susa or not confirmed_raw):
        asm.blocking.append(
            f"Kontenrahmen laut Steuerberater: {kontenrahmen}. Automatisch eingelesen "
            "wird derzeit nur SKR04 -- SuSa manuell erfassen oder Mapping kalibrieren."
        )

    # --- documents -------------------------------------------------------

    def _parse_susa(doc_type: str):
        entry = next((d for d in docs if d["doc_type"] == doc_type), None)
        if entry is None:
            return None
        meta = entry.get("meta") or {}
        try:
            period_end = date.fromisoformat(str(meta.get("period_end")))
            months = int(meta.get("period_months") or 12)
        except (TypeError, ValueError):
            asm.blocking.append(
                f"{entry['filename']}: Stichtag fehlt oder ist ungueltig. Beim Hochladen "
                "Stichtag (JJJJ-MM-TT) und Zeitraum in Monaten angeben."
            )
            return None
        try:
            bs_, gu_, diag = parse_datev_susa(
                store.read_document(case_id, entry["doc_id"]),
                period_end=period_end, period_months=months, kontenrahmen="SKR04",
            )
        except DatevMappingError as exc:
            asm.blocking.append(f"{entry['filename']}: {exc}")
            return None
        asm.datev[doc_type] = {"filename": entry["filename"], **diag,
                               "period_end": period_end.isoformat(),
                               "period_months": months}
        return bs_, gu_

    current = prior = None
    if kontenrahmen == "SKR04":
        current = _parse_susa("susa_aktuell")
        prior = _parse_susa("susa_vorjahr")
        if prior is None and not any(d["doc_type"] == "susa_vorjahr" for d in docs):
            asm.notes.append("Keine Vorjahres-SuSa -- Trendaussagen entfallen.")

    # No trial balance: fall back to figures read from the annual accounts --
    # only ever the CONFIRMED ones. The DATEV export, when present, always wins.
    figures_source = SRC_SUSA
    if current is None and not has_susa and confirmed_raw:
        conf = json.loads(confirmed_raw)
        current = to_statements(conf["figures"], date.fromisoformat(conf["period_end"]),
                                int(conf.get("period_months") or 12))
        figures_source = SRC_CONFIRMED
        asm.notes.append(
            f"Zahlen aus dem Jahresabschluss ({conf.get('method_label') or 'ausgelesen'}), "
            f"vom Unternehmen bestaetigt am {str(conf.get('confirmed_at', ''))[:10]}. "
            "Eine DATEV-Saldenliste wuerde sie ersetzen.")
    if current is None and not has_susa:
        asm.blocking.append(
            "Es fehlen die Zahlen: entweder die Summen- und Saldenliste (DATEV-CSV) oder "
            "ein hochgeladener und bestaetigter Jahresabschluss.")

    limit = sme.get("kontokorrent_limit")
    for entry in (d for d in docs if d["doc_type"] == "kontoumsaetze"):
        label = (entry.get("meta") or {}).get("account_label") or entry["filename"]
        try:
            asm.bank.append(analyse_bank_csv(
                store.read_document(case_id, entry["doc_id"]),
                kontokorrent_limit=limit, account_label=label,
            ))
        except BankCsvError as exc:
            asm.notes.append(f"Kontoumsaetze {label} nicht auswertbar: {exc}")

    if asm.blocking or current is None:
        return asm

    payload, prov, notes = build_payload(
        case_id, sme, stb, current, prior, asm.bank, today=today,
    )
    prov["balance_sheet"] = figures_source
    asm.payload, asm.provenance = payload, prov
    asm.notes.extend(notes)
    return asm
