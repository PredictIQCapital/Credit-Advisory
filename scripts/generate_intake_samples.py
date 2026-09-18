"""Generate a complete, FICTIONAL intake package for one engagement.

Mirrors sample CASE-01 (Mueller Praezisionstechnik GmbH), but the way a real
engagement arrives: two questionnaires, DATEV exports, a bank statement CSV,
and PDF evidence documents -- instead of one hand-built JSON file.

    data/samples/intake/
      antworten_unternehmen.json       SME questionnaire answers
      antworten_steuerberater.json     Steuerberater questionnaire answers
      susa_2025.csv                    current-year SuSa (copy of the DATEV fixture)
      susa_2024.csv                    prior-year SuSa (balanced)
      kontoumsaetze_kontokorrent.csv   12 months, Sparkasse-style export, cp1252
      *.pdf                            placeholder evidence documents

Nothing here describes a real company. Run:  python scripts/generate_intake_samples.py
"""

from __future__ import annotations

import json
import math
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "samples" / "intake"

ANTWORTEN_UNTERNEHMEN = {
    "firmenname": "Mueller Praezisionstechnik GmbH",
    "rechtsform": "GmbH",
    "branche": "Verarbeitendes Gewerbe",
    "mitarbeiter": 45,
    "gruendungsjahr": 2009,
    "sitz": "Schwaebisch Gmuend",
    "land": "DE",
    "hrb_nummer": "HRB 000000 (fiktiv)",
    "betrag": "750.000",
    "zweck": "Investition",
    "zweck_beschreibung": "Neue 5-Achs-Fraesmaschine fuer die Serienfertigung.",
    "laufzeit_jahre": 7,
    "sicherheiten_wert": 400000,
    "sicherheiten_beschreibung": "Sicherungsuebereignung der neuen Maschine",
    "benoetigt_in_wochen": 16,
    "bereits_abgelehnt": True,
    "ablehnung_details": "Hausbank, 04/2026: 'Eigenkapitalquote zu niedrig'.",
    "hausbank": "Sparkasse Ostalb",
    "darlehen": [
        {
            "kreditgeber": "Sparkasse Ostalb",
            "art": "Tilgungsdarlehen",
            "urspruenglicher_betrag": 2000000,
            "restschuld": 1250000,
            "zinssatz": "4,8",
            "tilgung_pro_jahr": 180000,
            "laufzeit_bis": 2032,
            "besichert": True,
        },
        {
            "kreditgeber": "Sparkasse Ostalb",
            "art": "Kontokorrent",
            "urspruenglicher_betrag": 500000,
            "restschuld": 420000,
            "zinssatz": "9,5",
            "tilgung_pro_jahr": 0,
            "besichert": False,
        },
    ],
    "kontokorrent_limit": 500000,
    "kontokorrent_inanspruchnahme": 420000,
    "tage_am_limit": 40,
    "leasing_verpflichtungen": 0,
    "hat_gesellschafterdarlehen": True,
    "gesellschafterdarlehen_betrag": 600000,
    "rangruecktritt": False,
    "bereitschaft_einlage": False,
    "bwa_frequenz": "quartalsweise",
    "bwa_stand": "2026-04",
    "planrechnung_vorhanden": False,
    "zahlungsverzug_tage": 6,
    "ruecklastschriften_12m": 0,
    "steuerrueckstaende": False,
    "creditreform_index": 248,
    "datenschutz_einwilligung": True,
    "steuerberater_kontakt_erlaubt": True,
    "steuerberater_kanzlei": "Kanzlei Beispiel Steuerberatung (fiktiv)",
    "steuerberater_email": "kanzlei@example.de",
    "ansprechpartner": "Anna Mueller",
    "ansprechpartner_email": "a.mueller@example.de",
    "ansprechpartner_telefon": "",
}

ANTWORTEN_STEUERBERATER = {
    "kanzlei": "Kanzlei Beispiel Steuerberatung (fiktiv)",
    "ansprechpartner": "Stefan Beispiel",
    "email": "kanzlei@example.de",
    "kontenrahmen": "SKR04",
    "individuelle_konten": False,
    "jahresabschluss_festgestellt": True,
    "jahresabschluss_stichtag": "2025-12-31",
    "bwa_frequenz": "quartalsweise",
    "bwa_stand": "2026-04",
    "rangruecktritt_bestaetigt": "nein",
    "steuerrueckstaende": False,
    "planrechnung_vorhanden": False,
    "einmaleffekte_betrag": 35000,
    "einmaleffekte_beschreibung": "Umzug des Lagers",
    "bilanzierungswahlrechte": "",
    "besondere_risiken": "Abhaengigkeit von zwei Grosskunden (zusammen ca. 45% Umsatz).",
    "freigabe_umgliederung": True,
}


def susa_2024() -> str:
    """Prior-year trial balance, built to balance exactly (JU carried by parser)."""
    guv = {  # account: signed DATEV balance (credits negative)
        4000: -7_650_000, 5000: 3_920_000, 6000: 2_480_000, 6200: 238_000,
        6300: 745_000, 7100: 88_000, 7600: 52_000,
    }
    ju = -sum(guv.values())            # 127.000
    passiva = {
        2000: -25_000, 2200: -95_000, 2300: -30_000, 3000: -330_000,
        3150: -380_000, 3200: -1_430_000, 3300: -640_000, 3400: -220_000,
        3500: -400_000, 3600: -600_000,
    }
    aktiva_fixed = {100: 70_000, 400: 2_150_000, 1000: 720_000, 1200: 1_080_000,
                    1300: 85_000, 1900: 20_000}
    total_passiva = -sum(passiva.values()) + ju
    cash = total_passiva - sum(aktiva_fixed.values())
    rows = {**aktiva_fixed, 1800: cash, **passiva, **guv}
    names = {100: "Konzessionen", 400: "Technische Anlagen", 1000: "Roh-, Hilfs- und Betriebsstoffe",
             1200: "Forderungen LuL", 1300: "Sonstige Vermoegensgegenstaende", 1800: "Bank",
             1900: "Aktive RAP", 2000: "Gezeichnetes Kapital", 2200: "Gewinnruecklagen",
             2300: "Gewinnvortrag", 3000: "Rueckstellungen", 3150: "Bankverb. kurzfristig",
             3200: "Bankverb. langfristig", 3300: "Verb. LuL", 3400: "Sonst. Verb. kurzfristig",
             3500: "Sonst. Verb. langfristig", 3600: "Gesellschafterdarlehen",
             4000: "Umsatzerloese", 5000: "Materialaufwand", 6000: "Personalaufwand",
             6200: "Abschreibungen", 6300: "Sonst. betriebl. Aufwendungen",
             7100: "Zinsaufwand", 7600: "Steuern"}

    def de(v: float) -> str:
        s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return ("-" if v < 0 else "") + s

    lines = ["Konto;Bezeichnung;Saldo"]
    lines += [f"{k:04d};{names[k]};{de(v)}" for k, v in sorted(rows.items())]
    return "\n".join(lines) + "\n"


def kontoumsaetze(seed: int = 7) -> str:
    """12 months of a Kontokorrent account hovering near its 500k limit.

    Sparkasse-style export: preamble lines, newest first, German number format,
    Windows-1252 umlauts -- the awkward parts of real exports, on purpose.
    """
    rng = random.Random(seed)
    start, end = date(2025, 1, 1), date(2025, 12, 31)
    days = (end - start).days + 1
    target = []
    for i in range(days):
        seasonal = math.sin(2 * math.pi * (i / days) * 2 - 0.6)   # two cycles a year
        target.append(-395_000 + 100_000 * seasonal + rng.uniform(-6_000, 6_000))
    target[-1] = -420_000.0

    rows = []
    balance = -380_000.0
    for i in range(days):
        d = start + timedelta(days=i)
        if d.weekday() >= 5:
            continue
        delta = round(target[i] - balance, 2)
        receipt = round(rng.uniform(15_000, 45_000), 2)
        payment = round(receipt - delta, 2)
        balance = round(balance + receipt, 2)
        rows.append((d, "Gutschrift", f"Zahlung Kunde RE-{rng.randint(10000, 99999)}",
                     "Kunde Gmbh", receipt, balance))
        balance = round(balance - payment, 2)
        rows.append((d, "Überweisung", "Lieferant Material / Löhne", "Lieferant AG",
                     -payment, balance))

    def de(v: float) -> str:
        s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return ("-" if v < 0 else "") + s

    out = [
        "Umsatzanzeige;Kontokorrent Mueller Praezisionstechnik GmbH (fiktiv)",
        "Zeitraum;01.01.2025 - 31.12.2025",
        "",
        "Buchungstag;Valutadatum;Buchungstext;Verwendungszweck;"
        "Begünstigter/Zahlungspflichtiger;Betrag;Saldo;Währung",
    ]
    for d, typ, zweck, partner, amount, bal in reversed(rows):
        ds = d.strftime("%d.%m.%Y")
        out.append(f"{ds};{ds};{typ};{zweck};{partner};{de(amount)};{de(bal)};EUR")
    return "\n".join(out) + "\n"


def placeholder_pdf(text: str) -> bytes:
    """A minimal valid one-page PDF. Stands in for a real scanned document."""
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


PDFS = {
    "handelsregisterauszug.pdf": "Handelsregisterauszug - FIKTIVES BEISPIEL",
    "bwa_2026_04.pdf": "BWA April 2026 - FIKTIVES BEISPIEL",
    "jahresabschluss_2024.pdf": "Jahresabschluss 2024 - FIKTIVES BEISPIEL",
    "kreditvertrag_tilgungsdarlehen.pdf": "Kreditvertrag - FIKTIVES BEISPIEL",
    "kreditvertrag_kontokorrent.pdf": "Kontokorrentvertrag - FIKTIVES BEISPIEL",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "antworten_unternehmen.json").write_text(
        json.dumps(ANTWORTEN_UNTERNEHMEN, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "antworten_steuerberater.json").write_text(
        json.dumps(ANTWORTEN_STEUERBERATER, indent=2, ensure_ascii=False), encoding="utf-8")
    shutil.copyfile(ROOT / "data" / "samples" / "datev_susa_example.csv", OUT / "susa_2025.csv")
    (OUT / "susa_2024.csv").write_text(susa_2024(), encoding="utf-8")
    (OUT / "kontoumsaetze_kontokorrent.csv").write_bytes(kontoumsaetze().encode("cp1252"))
    for name, text in PDFS.items():
        (OUT / name).write_bytes(placeholder_pdf(text))
    # A real, machine-readable annual financial statement for the quick check.
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "src"))
    from credit_readiness.demo import annual_accounts_pdf
    case01 = json.loads((ROOT / "data" / "samples" / "case_01_mueller_praezisionstechnik.json").read_text(encoding="utf-8"))
    (OUT / "jahresabschluss_2025.pdf").write_bytes(annual_accounts_pdf(case01))
    for p in sorted(OUT.iterdir()):
        print(f"geschrieben: {p.name}")


if __name__ == "__main__":
    main()
