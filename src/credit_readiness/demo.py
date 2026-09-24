"""Demo data: four FICTIONAL companies at four stages of an engagement.

Used by `python -m credit_readiness serve --demo` (and start_demo.bat) so the
portal can be shown to an SME, a Steuerberater or an investor without touching
real client data. Everything lives in data/demo/, which is git-ignored and can
be deleted at any time -- it is re-created on the next demo start.

    Mueller Praezisionstechnik  complete: both questionnaires, all documents,
                                bank statements, analysis released  -> fixable
    Gastro Rheinblick           complete and analysed               -> genuine
                                credit risk; advised not to apply (the honest no)
    Nordlicht Handel            free quick check done (annual accounts read and
                                confirmed, instant result), nothing ordered yet
    Weber Holzbau               just registered: shows the guided flow from step 1

All logins use the password DEMO_PASSWORD.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from . import workflow as wf
from .auth import ROLE_BERATER, ROLE_STEUERBERATER, ROLE_UNTERNEHMEN, UserStore
from .casefile import LocalCaseStore

REPO = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO / "data" / "demo"
SAMPLES = REPO / "data" / "samples"
INTAKE = SAMPLES / "intake"
DEMO_PASSWORD = "demo1234"

# (email, name, role, company keys the account belongs to)
DEMO_USERS = [
    ("berater@demo.de", "Credit Readiness Team", ROLE_BERATER, []),
    ("anna.mueller@demo.de", "Anna Mueller", ROLE_UNTERNEHMEN, ["mueller"]),
    ("kanzlei@demo.de", "Kanzlei Beispiel Steuerberatung", ROLE_STEUERBERATER, ["mueller", "gastro"]),
    ("elif.yilmaz@demo.de", "Elif Yilmaz", ROLE_UNTERNEHMEN, ["gastro"]),
    ("jan.petersen@demo.de", "Jan Petersen", ROLE_UNTERNEHMEN, ["nordlicht"]),
    ("jonas.weber@demo.de", "Jonas Weber", ROLE_UNTERNEHMEN, ["weber"]),
]

DEMO_HINTS = {
    "berater@demo.de": ("Alle Faelle, Analyse, Freigabe", "All cases, analysis, report release"),
    "anna.mueller@demo.de": ("Mueller Praezisionstechnik - Ergebnis liegt vor", "Mueller Praezisionstechnik - result ready"),
    "kanzlei@demo.de": ("Kanzlei von Mueller und Gastro Rheinblick", "Tax firm of Mueller and Gastro Rheinblick"),
    "elif.yilmaz@demo.de": ("Gastro Rheinblick - die ehrliche Absage", "Gastro Rheinblick - the honest no"),
    "jan.petersen@demo.de": ("Nordlicht Handel - kostenloser Schnell-Check erledigt", "Nordlicht Handel - free quick check done"),
    "jonas.weber@demo.de": ("Weber Holzbau - gerade registriert", "Weber Holzbau - just registered"),
}


def placeholder_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF standing in for a real document."""
    content = f"BT /F1 14 Tf 60 780 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)
    return bytes(pdf)


def _pdf_escape(s: str) -> bytes:
    b = s.encode("cp1252", errors="replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def text_pdf(lines: list[str], per_page: int = 64) -> bytes:
    """A real multi-page text PDF (Courier, WinAnsi), one line per text object."""
    pages = [lines[i:i + per_page] for i in range(0, len(lines), per_page)] or [[]]
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
    font_id = 3
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    kids = []
    for page in pages:
        stream = b"".join(
            b"BT /F1 9 Tf 40 %d Td (%s) Tj ET\n" % (800 - 12 * i, _pdf_escape(ln))
            for i, ln in enumerate(page))
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
        content_id = len(objs)
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (content_id, font_id))
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(pdf)


def annual_accounts_pdf(payload: dict) -> bytes:
    """Render a sample case as a German annual financial statement (HGB layout)."""
    b, g = payload["balance_sheet"], payload["income_statement"]
    py = payload.get("prior_year_income") or {}
    end = b["period_end"]
    stichtag = f"{end[8:10]}.{end[5:7]}.{end[0:4]}"

    def amt(v) -> str:
        return _de(float(v or 0))

    def row(label: str, cur, prior=None) -> str:
        right = f"{amt(cur):>16}" + (f"  {amt(prior):>16}" if prior is not None else "")
        return f"{label:<58}{right}"

    def signed(label_pos: str, label_neg: str, v) -> str:
        v = float(v or 0)
        return row(label_neg if v < 0 else label_pos, abs(v))

    bank = float(b.get("verb_kreditinstitute_kurz") or 0) + float(b.get("verb_kreditinstitute_lang") or 0)
    lines = [
        payload["profile"]["name"],
        f"Jahresabschluss zum {stichtag}  -  FIKTIVES BEISPIEL",
        "",
        "BILANZ",
        "AKTIVA" + " " * 52 + "EUR",
        "A. Anlagevermoegen",
        row("I. Immaterielle Vermögensgegenstände", b.get("immaterielle_vermoegensgegenstaende")),
        row("II. Sachanlagen", b.get("sachanlagen")),
        row("III. Finanzanlagen", b.get("finanzanlagen")),
        "B. Umlaufvermoegen",
        row("I. Vorräte", b.get("vorraete")),
        row("II. 1. Forderungen aus Lieferungen und Leistungen", b.get("forderungen_ll")),
        row("II. 2. Sonstige Vermögensgegenstände", b.get("sonstige_vermoegensgegenstaende")),
        row("III. Wertpapiere", b.get("wertpapiere")),
        row("IV. Kassenbestand, Guthaben bei Kreditinstituten", b.get("liquide_mittel")),
        row("C. Rechnungsabgrenzungsposten", b.get("aktive_rap")),
        "",
        "PASSIVA" + " " * 51 + "EUR",
        "A. Eigenkapital",
        row("I. Gezeichnetes Kapital", b.get("gezeichnetes_kapital")),
        row("II. Kapitalrücklage", b.get("kapitalruecklage")),
        row("III. Gewinnrücklagen", b.get("gewinnruecklagen")),
        signed("IV. Gewinnvortrag", "IV. Verlustvortrag", b.get("gewinnvortrag")),
        signed("V. Jahresüberschuss", "V. Jahresfehlbetrag", b.get("jahresueberschuss")),
        "B. Rueckstellungen",
        row("1. Rückstellungen für Pensionen", b.get("pensionsrueckstellungen")),
        row("2. Sonstige Rückstellungen", b.get("rueckstellungen")),
        "C. Verbindlichkeiten",
        row("1. Verbindlichkeiten gegenüber Kreditinstituten", bank),
        row("   davon mit einer Restlaufzeit bis zu einem Jahr", b.get("verb_kreditinstitute_kurz")),
        row("2. Verbindlichkeiten aus Lieferungen und Leistungen", b.get("verb_ll")),
        row("3. Verbindlichkeiten gegenüber Gesellschaftern", b.get("gesellschafterdarlehen")),
        row("4. Sonstige Verbindlichkeiten", float(b.get("sonstige_verbindlichkeiten_kurz") or 0)
            + float(b.get("sonstige_verbindlichkeiten_lang") or 0)),
        row("   davon mit einer Restlaufzeit bis zu einem Jahr", b.get("sonstige_verbindlichkeiten_kurz")),
        row("D. Rechnungsabgrenzungsposten", b.get("passive_rap")),
        "",
        "GEWINN- UND VERLUSTRECHNUNG" + " " * 31 + f"{end[0:4]:>16}  {int(end[0:4]) - 1:>16}",
        row("1. Umsatzerlöse", g.get("umsatzerloese"), py.get("umsatzerloese")),
        row("2. Erhöhung oder Verminderung des Bestands", g.get("bestandsveraenderungen"), py.get("bestandsveraenderungen")),
        row("3. Sonstige betriebliche Erträge", g.get("sonstige_betriebliche_ertraege"), py.get("sonstige_betriebliche_ertraege")),
        row("4. Materialaufwand", g.get("materialaufwand"), py.get("materialaufwand")),
        row("5. Personalaufwand", g.get("personalaufwand"), py.get("personalaufwand")),
        row("6. Abschreibungen", g.get("abschreibungen"), py.get("abschreibungen")),
        row("7. Sonstige betriebliche Aufwendungen", g.get("sonstige_betriebliche_aufwendungen"), py.get("sonstige_betriebliche_aufwendungen")),
        row("8. Sonstige Zinsen und ähnliche Erträge", g.get("zinsertraege"), py.get("zinsertraege")),
        row("9. Zinsen und ähnliche Aufwendungen", g.get("zinsaufwand"), py.get("zinsaufwand")),
        row("10. Steuern vom Einkommen und vom Ertrag", g.get("steuern"), py.get("steuern")),
    ]
    return text_pdf(lines)


# ---------------------------------------------------------------------------
# Turn a hand-built sample case (data/samples/*.json) into an intake package
# ---------------------------------------------------------------------------

_SUSA_ACCOUNTS = [  # field, SKR04 account, sign applied by the parser
    ("immaterielle_vermoegensgegenstaende", 100, 1), ("sachanlagen", 400, 1),
    ("finanzanlagen", 800, 1), ("vorraete", 1000, 1), ("forderungen_ll", 1200, 1),
    ("sonstige_vermoegensgegenstaende", 1300, 1), ("wertpapiere", 1500, 1),
    ("liquide_mittel", 1800, 1), ("aktive_rap", 1900, 1),
    ("gezeichnetes_kapital", 2000, -1), ("kapitalruecklage", 2100, -1),
    ("gewinnruecklagen", 2200, -1), ("gewinnvortrag", 2300, -1),
    ("rueckstellungen", 3000, -1), ("pensionsrueckstellungen", 3100, -1),
    ("verb_kreditinstitute_kurz", 3150, -1), ("verb_kreditinstitute_lang", 3200, -1),
    ("verb_ll", 3300, -1), ("sonstige_verbindlichkeiten_kurz", 3400, -1),
    ("sonstige_verbindlichkeiten_lang", 3500, -1), ("gesellschafterdarlehen", 3600, -1),
    ("passive_rap", 3900, -1),
]
_GUV_ACCOUNTS = [
    ("umsatzerloese", 4000, -1), ("bestandsveraenderungen", 4500, -1),
    ("sonstige_betriebliche_ertraege", 4700, -1), ("materialaufwand", 5000, 1),
    ("personalaufwand", 6000, 1), ("abschreibungen", 6200, 1),
    ("sonstige_betriebliche_aufwendungen", 6300, 1), ("zinsertraege", 7000, -1),
    ("zinsaufwand", 7100, 1), ("steuern", 7600, 1),
]


def _de(v: float) -> str:
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


def case_to_susa(balance: Optional[dict], income: dict) -> bytes:
    """Write a DATEV-style trial balance that parses back to the given figures."""
    lines = ["Konto;Bezeichnung;Saldo"]
    for field, konto, sign in (_SUSA_ACCOUNTS if balance else []) + _GUV_ACCOUNTS:
        src = balance if konto < 4000 else income
        v = float(src.get(field) or 0)
        if v:
            lines.append(f"{konto:04d};{field};{_de(v * sign)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def case_to_answers(payload: dict, today: date) -> tuple[dict, dict]:
    p, b, beh, req = (payload["profile"], payload["balance_sheet"],
                      payload.get("behavior", {}), payload.get("request") or {})
    months = int(round(beh.get("bwa_age_months", 1)))
    y, m = today.year, today.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    sme = {
        "firmenname": p["name"], "rechtsform": p["legal_form"], "branche": p["sector"],
        "mitarbeiter": p["employees"], "gruendungsjahr": p["founded_year"],
        "sitz": p.get("city") or "", "land": "DE",
        "betrag": req.get("amount"), "zweck": req.get("purpose"),
        "laufzeit_jahre": req.get("tenor_years"), "sicherheiten_wert": req.get("collateral_available"),
        "benoetigt_in_wochen": req.get("urgency_weeks"), "bereits_abgelehnt": False,
        "darlehen": [{
            "kreditgeber": f["lender"], "art": f["facility_type"],
            "urspruenglicher_betrag": f["original_amount"], "restschuld": f["outstanding"],
            "zinssatz": str(round(f["interest_rate"] * 100, 2)).replace(".", ","),
            "tilgung_pro_jahr": f["annual_principal_repayment"],
            "laufzeit_bis": f.get("maturity_year"), "besichert": bool(f.get("collateralised")),
        } for f in payload.get("facilities", [])],
        "kontokorrent_limit": b.get("kontokorrent_limit"),
        "kontokorrent_inanspruchnahme": b.get("kontokorrent_inanspruchnahme"),
        "tage_am_limit": beh.get("overdraft_days_at_limit_12m", 0),
        "hat_gesellschafterdarlehen": (b.get("gesellschafterdarlehen") or 0) > 0,
        "gesellschafterdarlehen_betrag": b.get("gesellschafterdarlehen") or None,
        "rangruecktritt": bool(b.get("gesellschafterdarlehen_rangruecktritt")),
        "bwa_frequenz": beh.get("bwa_frequency", "monatlich"),
        "bwa_stand": f"{y:04d}-{m:02d}",
        "planrechnung_vorhanden": bool(beh.get("has_planning_forecast")),
        "zahlungsverzug_tage": beh.get("days_beyond_terms", 0),
        "ruecklastschriften_12m": beh.get("returned_direct_debits_12m", 0),
        "steuerrueckstaende": bool(beh.get("tax_arrears")),
        "creditreform_index": beh.get("creditreform_bonitaetsindex"),
        "datenschutz_einwilligung": True, "steuerberater_kontakt_erlaubt": True,
        "steuerberater_kanzlei": "Kanzlei Beispiel Steuerberatung (fiktiv)",
        "steuerberater_email": "kanzlei@demo.de",
    }
    stb = {
        "kanzlei": "Kanzlei Beispiel Steuerberatung (fiktiv)", "ansprechpartner": "Stefan Beispiel",
        "email": "kanzlei@demo.de", "kontenrahmen": "SKR04", "individuelle_konten": False,
        "jahresabschluss_festgestellt": True, "jahresabschluss_stichtag": b["period_end"],
        "bwa_frequenz": sme["bwa_frequenz"], "bwa_stand": sme["bwa_stand"],
        "rangruecktritt_bestaetigt": ("ja" if sme["rangruecktritt"] else "nein")
        if sme["hat_gesellschafterdarlehen"] else "keine Gesellschafterdarlehen",
        "steuerrueckstaende": sme["steuerrueckstaende"], "stundungsvereinbarung": False,
        "planrechnung_vorhanden": sme["planrechnung_vorhanden"], "freigabe_umgliederung": True,
    }
    return sme, stb


# ---------------------------------------------------------------------------


def _new_case(store, users_by_key, key: str, company: str) -> str:
    cid = store.create_case(company)["case_id"]
    for email, name, role, keys in DEMO_USERS:
        if key in keys:
            wf.add_member(store, cid, role, email)
            if role == ROLE_UNTERNEHMEN:
                # Every demo company signed at registration; those that invited
                # their tax firm also signed its release from confidentiality.
                ids = ["nutzungsbedingungen", "datenschutz"] + ([] if key == "weber" else ["schweigepflicht"])
                wf.sign_agreements(store, cid, ids, name, email, "127.0.0.1", "Demo")
    return cid


def _demo_thread(store, cid: str) -> None:
    """A short exchange, so the messages page is not empty in a presentation."""
    from types import SimpleNamespace
    anna = SimpleNamespace(email="anna.mueller@demo.de", name="Anna Mueller", role=ROLE_UNTERNEHMEN)
    team = SimpleNamespace(email="berater@demo.de", name="Credit Readiness Team", role="berater")
    wf.post_message(store, cid, anna, "Muss der Rangruecktritt notariell beurkundet werden, oder reicht "
                    "eine schriftliche Erklaerung der Gesellschafter?", "Frage zum Ergebnis")
    wf.post_message(store, cid, team, "Eine schriftliche Erklaerung reicht; eine Beurkundung ist nicht "
                    "noetig. Wichtig ist der qualifizierte Wortlaut -- wir stimmen den Entwurf mit Ihrer "
                    "Kanzlei ab und schicken ihn Ihnen diese Woche.", "Frage zum Ergebnis")


def _upload_pdf(store, cid, doc_type, name, text, by):
    store.add_document(cid, doc_type, name, placeholder_pdf(f"{text} - FIKTIVES BEISPIEL"),
                       {"uploaded_by": by})


def seed_demo(store: LocalCaseStore, today: Optional[date] = None) -> dict[str, str]:
    """Create demo users and cases in an EMPTY store. Returns {key: case_id}."""
    today = today or date.today()
    users = UserStore(store.root)
    if users.count():
        raise RuntimeError(f"{store.root} enthaelt bereits Konten -- Demo nur in leerer Ablage")
    for email, name, role, _ in DEMO_USERS:
        users.create(email, name, role, DEMO_PASSWORD)
    ids: dict[str, str] = {}
    sme_mail, stb_mail = "anna.mueller@demo.de", "kanzlei@demo.de"

    # 1. Mueller -- complete showcase --------------------------------------
    cid = ids["mueller"] = _new_case(store, users, "mueller", "Mueller Praezisionstechnik GmbH")
    _demo_thread(store, cid)
    sme = json.loads((INTAKE / "antworten_unternehmen.json").read_text(encoding="utf-8"))
    sme.update({"steuerberater_email": stb_mail, "ansprechpartner_email": sme_mail})
    store.save_answers(cid, "unternehmen", sme)
    stb = json.loads((INTAKE / "antworten_steuerberater.json").read_text(encoding="utf-8"))
    stb["email"] = stb_mail
    store.save_answers(cid, "steuerberater", stb)
    store.set_stage(cid, "unterlagen_angefordert", "Anforderungsschreiben versandt")
    for doc_type, name, meta, by in [
        ("susa_aktuell", "susa_2025.csv", {"period_end": "2025-12-31", "period_months": 12}, stb_mail),
        ("susa_vorjahr", "susa_2024.csv", {"period_end": "2024-12-31", "period_months": 12}, stb_mail),
        ("kontoumsaetze", "kontoumsaetze_kontokorrent.csv", {"account_label": "Kontokorrent Sparkasse Ostalb"}, sme_mail),
    ]:
        store.add_document(cid, doc_type, name, (INTAKE / name).read_bytes(), {**meta, "uploaded_by": by})
    for doc_type, name, text, by in [
        ("bwa_aktuell", "BWA_2026-04.pdf", "BWA April 2026", stb_mail),
        ("jahresabschluesse", "Jahresabschluss_2024.pdf", "Jahresabschluss 2024", stb_mail),
        ("steuerkonto", "Steuerkontoauszug_2026-08.pdf", "Steuerkontoauszug August 2026", stb_mail),
        ("handelsregisterauszug", "Handelsregisterauszug.pdf", "Handelsregisterauszug", sme_mail),
        ("darlehensvertraege", "Darlehensvertrag_Sparkasse.pdf", "Darlehensvertrag Tilgungsdarlehen", sme_mail),
        ("darlehensvertraege", "Kontokorrentvertrag_Sparkasse.pdf", "Kontokorrentvertrag", sme_mail),
        ("sicherheitenaufstellung", "Sicherheiten.pdf", "Aufstellung der Sicherheiten", sme_mail),
        ("gesellschafterliste", "Gesellschafterliste.pdf", "Gesellschafterliste", sme_mail),
        ("creditreform_auskunft", "Creditreform_Auskunft.pdf", "Creditreform-Auskunft (Index 248)", "berater@demo.de"),
    ]:
        _upload_pdf(store, cid, doc_type, name, text, by)
    mueller_payload = json.loads((SAMPLES / "case_01_mueller_praezisionstechnik.json").read_text(encoding="utf-8"))
    store.add_document(cid, "jahresabschluesse", "Jahresabschluss_2025.pdf",
                       annual_accounts_pdf(mueller_payload), {"uploaded_by": sme_mail})
    assert wf.run_quick_check(store, cid, today=today)["ok"]
    wf.place_order(store, cid, "report", sme_mail)
    wf.place_order(store, cid, "advisor", sme_mail, "Bitte Termin in KW 40.")
    wf.submit_case(store, cid, today=today)
    wf.generate_letters(store, cid, today=today)
    res = wf.run_case_diagnostic(store, cid, today=today)
    assert res["ok"], res
    wf.release_report(store, cid, True)
    store.update_meta(cid, advisor_note=(
        "Rangruecktritt mit Kanzlei abgestimmt, Entwurf liegt beim Anwalt. Umschuldung "
        "Kontokorrent in Tilgungsdarlehen mit Sparkasse im Gespraech. Planrechnung in Arbeit."))

    # 2. Gastro -- the honest no --------------------------------------------
    cid = ids["gastro"] = _new_case(store, users, "gastro", "Gastro Rheinblick GmbH")
    payload = json.loads((SAMPLES / "case_03_gastro_rheinblick.json").read_text(encoding="utf-8"))
    sme, stb = case_to_answers(payload, today)
    sme.update({"ansprechpartner": "Elif Yilmaz", "ansprechpartner_email": "elif.yilmaz@demo.de",
                "bereits_abgelehnt": True,
                "ablehnung_details": "Kreissparkasse, 06/2026: 'Ertragslage nicht ausreichend'.",
                "zweck_beschreibung": "Ueberbrueckung der Liquiditaet bis zur Sommersaison."})
    store.save_answers(cid, "unternehmen", sme)
    store.save_answers(cid, "steuerberater", stb)
    store.add_document(cid, "susa_aktuell", "susa_2025.csv",
                       case_to_susa(payload["balance_sheet"], payload["income_statement"]),
                       {"period_end": "2025-12-31", "period_months": 12, "uploaded_by": stb_mail})
    store.add_document(cid, "susa_vorjahr", "susa_2024_guv.csv",
                       case_to_susa(None, payload["prior_year_income"]),
                       {"period_end": "2024-12-31", "period_months": 12, "uploaded_by": stb_mail})
    for doc_type, name, text in [
        ("bwa_aktuell", "BWA_2026-02.pdf", "BWA Februar 2026"),
        ("jahresabschluesse", "Jahresabschluss_2025.pdf", "Jahresabschluss 2025"),
        ("jahresabschluesse", "Jahresabschluss_2024.pdf", "Jahresabschluss 2024"),
        ("handelsregisterauszug", "Handelsregisterauszug.pdf", "Handelsregisterauszug"),
        ("darlehensvertraege", "Kreditvertraege.pdf", "Kreditvertraege"),
    ]:
        _upload_pdf(store, cid, doc_type, name, text, "elif.yilmaz@demo.de")
    assert wf.run_quick_check(store, cid, today=today)["ok"]
    wf.place_order(store, cid, "report", "elif.yilmaz@demo.de")
    wf.submit_case(store, cid, today=today)
    res = wf.run_case_diagnostic(store, cid, today=today)
    assert res["ok"], res
    wf.release_report(store, cid, True)
    wf.record_outcome(store, cid, {
        "outcome": "ADVISED_NOT_TO_APPLY",
        "notes": "Verlust, Umsatzrueckgang, Steuerrueckstaende: keine Antragstellung. "
                 "Operative Sanierung mit Steuerberater, Neubewertung in 9 Monaten."})
    store.update_meta(cid, advisor_note=(
        "Ehrliche Absage: Aufbereitung wuerde nur eine besser aussehende Ablehnung erzeugen. "
        "Mandantin informiert, Neubewertung nach Sanierungsschritten vereinbart."))

    # 3. Nordlicht -- the free quick check, nothing ordered yet -------------
    cid = ids["nordlicht"] = _new_case(store, users, "nordlicht", "Nordlicht Handel GmbH & Co. KG")
    payload = json.loads((SAMPLES / "case_02_nordlicht_handel.json").read_text(encoding="utf-8"))
    sme, _ = case_to_answers(payload, today)
    keep = {"firmenname", "rechtsform", "branche", "mitarbeiter", "gruendungsjahr", "sitz", "land",
            "betrag", "zweck", "laufzeit_jahre", "sicherheiten_wert", "benoetigt_in_wochen",
            "kontokorrent_limit", "kontokorrent_inanspruchnahme", "tage_am_limit",
            "hat_gesellschafterdarlehen", "steuerrueckstaende", "bwa_frequenz", "bwa_stand",
            "creditreform_index", "zahlungsverzug_tage"}
    partial = {k: v for k, v in sme.items() if k in keep}
    partial.update({"ansprechpartner": "Jan Petersen", "ansprechpartner_email": "jan.petersen@demo.de",
                    "datenschutz_einwilligung": True, "ki_einwilligung": False,
                    "tilgung_gesamt_jahr": 65000,
                    "zweck_beschreibung": "Vorfinanzierung Wintersaison-Ware."})
    store.save_answers(cid, "unternehmen", partial)
    store.add_document(cid, "jahresabschluesse", "Jahresabschluss_2025.pdf", annual_accounts_pdf(payload),
                       {"uploaded_by": "jan.petersen@demo.de"})
    ext = wf.extract_figures(store, cid, actor="jan.petersen@demo.de")
    wf.confirm_figures(store, cid, {
        "figures": {k: v["value"] for k, v in ext["fields"].items()},
        "period_end": ext["period_end"], "period_months": 12}, "jan.petersen@demo.de")
    res = wf.run_quick_check(store, cid, today=today)
    assert res["ok"], res

    # 4. Weber -- just registered ------------------------------------------
    cid = ids["weber"] = _new_case(store, users, "weber", "Weber Holzbau GmbH")
    store.save_answers(cid, "unternehmen", {
        "firmenname": "Weber Holzbau GmbH", "ansprechpartner": "Jonas Weber",
        "ansprechpartner_email": "jonas.weber@demo.de", "datenschutz_einwilligung": True})
    return ids
