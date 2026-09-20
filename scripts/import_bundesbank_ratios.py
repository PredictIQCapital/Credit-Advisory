"""Extract sector ratio quartiles from the Bundesbank Jahresabschlussstatistik.

Source
------
Deutsche Bundesbank, Statistische Fachreihe "Jahresabschlussstatistik
(Verhaeltniszahlen)", published annually and free of charge.

Why the quartiles and not the averages
--------------------------------------
The publication carries two kinds of figure. The *gewogene Durchschnitte* are
weighted by each firm's share of the reference base, so they are dominated by
the largest companies in the group -- useless for a Mittelstand benchmark. The
*Quartilswerte* are firm-level distribution points; the Bundesbank's own
methodological note says they "zeigen die fuer den jeweiligen Bereich typischen
Werte" and are unaffected by extremes. Those are what this script extracts.

One consequence, stated in the source and worth repeating: quartiles are not
additive. The 50% quartile of equity and the 50% quartile of debt do not add up
to a balance sheet. Each ratio's distribution stands on its own.

Usage
-----
    python scripts/import_bundesbank_ratios.py <folder-with-pdfs>

Writes one JSON per publication into data/reference/bundesbank/ plus a
manifest. Re-running is idempotent.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "reference" / "bundesbank"

# Bundesbank section number -> our Sector enum value (models.Sector).
# Mapping decisions worth knowing:
#   - PROFESSIONAL_SERVICES maps to the parent "Unternehmensdienstleistungen",
#     which is broader than our label (it also holds staffing and facility
#     services). The narrower 13a/13b would fit better but split the population.
#   - HEALTHCARE maps to 14b) Gesundheitswesen, a sub-section.
SECTION_TO_SECTOR = {
    "1.": "__alle__",
    "4.": "Verarbeitendes Gewerbe",
    "7.": "Baugewerbe",
    "8b)": "Grosshandel",
    "8c)": "Einzelhandel",
    "9.": "Verkehr und Lagerei",
    "10.": "Gastgewerbe",
    "11.": "Information und Kommunikation",
    "13.": "Freiberufliche und technische Dienstleistungen",
    "14b)": "Gesundheitswesen",
    "14.": "Sonstige Dienstleistungen",
}

# (label, unit) -> our key. The same label appears under two different bases,
# so the unit is part of the identity.
ROWS = {
    ("Materialaufwand", "gesamtleistung"): "materialaufwand_pct_gesamtleistung",
    ("Personalaufwand", "gesamtleistung"): "personalaufwand_pct_gesamtleistung",
    ("Abschreibungen", "gesamtleistung"): "abschreibungen_pct_gesamtleistung",
    ("Jahresergebnis", "gesamtleistung"): "jahresergebnis_pct_gesamtleistung",
    ("Sachanlagen", "bilanzsumme"): "sachanlagen_pct_bilanzsumme",
    ("Vorraete", "bilanzsumme"): "vorraete_pct_bilanzsumme",
    ("Eigenmittel", "bilanzsumme"): "eigenmittel_pct_bilanzsumme",
    ("Kurzfristige Verbindlichkeiten", "bilanzsumme"): "kurzfr_verbindlichkeiten_pct_bilanzsumme",
    ("Verbindlichkeiten gegenueber Kreditinstituten", "bilanzsumme"): "bankschulden_pct_bilanzsumme",
    ("Jahresergebnis vor Gewinnsteuern", "umsatz"): "ergebnis_vor_steuern_pct_umsatz",
    ("Jahresergebnis und Abschreibungen", "umsatz"): "cashflow_pct_umsatz",
    ("Forderungen aus Lieferungen und Leistungen", "umsatz"): "forderungen_ll_pct_umsatz",
    ("Jahresergebnis und Zinsaufwendungen", "bilanzsumme"): "ergebnis_plus_zins_pct_bilanzsumme",
    ("Jahresergebnis und Abschreibungen", "fremdmittel"): "cashflow_pct_nettofremdmittel",
    ("Langfristig verfuegbares Kapital", "anlagevermoegen"): "langfr_kapital_pct_anlagevermoegen",
    ("Liquide Mittel und kurzfristige Forderungen", "kurzfr_verbindlichkeiten"): "liquiditaet_2_pct",
    ("Verbindlichkeiten aus Lieferungen und Leistungen", "materialaufwand"): "verb_ll_pct_materialaufwand",
}

UNIT_PATTERNS = [
    (r"% der Gesamtleistung", "gesamtleistung"),
    (r"% der Bilanzsumme", "bilanzsumme"),
    (r"% des Umsatzes", "umsatz"),
    (r"% der Fremdmittel", "fremdmittel"),
    (r"% des Anlageverm", "anlagevermoegen"),
    (r"% der kurzfristigen Verbindlichkeiten", "kurzfr_verbindlichkeiten"),
    (r"% des Materialaufwands", "materialaufwand"),
]

SIZE_CLASSES = ["insgesamt", "unter_2m", "2_bis_10m", "10_bis_50m", "ab_50m"]

# Editions up to 2021 print "25.9", later ones "25,9". Thousands are spaces
# in both, so whichever separator appears is unambiguously the decimal one.
_NUM = re.compile(r"^-?\s?\d{1,3}(?:[    ]\d{3})*(?:[.,]\d+)?$")


def _fold(text: str) -> str:
    """Umlauts to ASCII, whitespace collapsed -- labels must match exactly."""
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                 ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue")):
        text = text.replace(a, b)
    return re.sub(r"[\s  ]+", " ", text).strip()


def _number(token: str):
    t = token.replace(" ", " ").replace(" ", " ").strip()
    if t in (".", "-", "", "x"):
        return None
    t = t.replace("- ", "-").replace(" ", "").replace(",", ".")
    if t.count(".") > 1:          # never seen, but do not silently mangle it
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_quartile_page(text: str) -> dict | None:
    """One quartile page -> {years, legal_form, section, rows}."""
    if "Quartil" not in text:
        return None

    section = re.search(r"noch: (\d+[a-z]?[.)]) ", text)
    if not section:
        return None
    sec = section.group(1)

    form = "alle_rechtsformen"
    if "Kapitalgesellschaften" in text:
        form = "nichtkapitalgesellschaften" if "Nichtkapitalgesellschaften" in text else "kapitalgesellschaften"

    years = re.findall(r"Vergleichbarer Kreis (\d{4})/(\d{4})", text)
    if not years:
        return None
    year_pair = [int(years[0][0]), int(years[0][1])]

    has_sizes = "Unternehmen mit Ums" in text
    columns = SIZE_CLASSES if has_sizes else ["insgesamt"]
    expected = len(columns) * 2

    lines = [ln.strip() for ln in text.split("\n")]
    unit = None
    label_parts: list[str] = []
    rows: dict[str, dict] = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln:
            i += 1
            continue

        matched_unit = next((u for pat, u in UNIT_PATTERNS if re.match(pat, ln)), None)
        if matched_unit:
            unit = matched_unit
            i += 1
            continue

        # A block always opens with the 25% quartile. Anything else that looks
        # like a quartile marker is a data value, handled below.
        if ln == "25":
            label = _fold(" ".join(label_parts))
            label_parts = []
            start = i
            block: dict[str, list] = {}
            for quartile in ("25", "50", "75"):
                if i >= len(lines) or lines[i] != quartile:
                    break
                i += 1
                values = []
                while i < len(lines) and len(values) < expected and _NUM.match(lines[i].strip()):
                    values.append(_number(lines[i]))
                    i += 1
                block[quartile] = values
            key = ROWS.get((label, unit))
            if key and len(block) == 3 and all(len(v) == expected for v in block.values()):
                rows[key] = block
            if i == start:          # never leave the cursor where it was
                i += 1
            continue

        if not _NUM.match(ln):
            label_parts.append(ln)
            if len(label_parts) > 4:
                label_parts = label_parts[-4:]
        i += 1

    if not rows:
        return None
    return {"section": sec, "legal_form": form, "years": year_pair,
            "columns": columns, "rows": rows}


def reshape(page: dict) -> dict:
    """{metric: {size_class: {year: {q25,q50,q75}}}} -- one entry per cell."""
    out: dict[str, dict] = {}
    for metric, block in page["rows"].items():
        per_size: dict[str, dict] = {}
        for ci, size in enumerate(page["columns"]):
            per_year: dict[str, dict] = {}
            for yi, year in enumerate(page["years"]):
                idx = ci * 2 + yi
                vals = {q: block[q][idx] for q in ("25", "50", "75")}
                if all(v is not None for v in vals.values()):
                    per_year[str(year)] = {"q25": vals["25"], "q50": vals["50"], "q75": vals["75"]}
            if per_year:
                per_size[size] = per_year
        if per_size:
            out[metric] = per_size
    return out


def parse_pdf(path: Path) -> dict:
    import pymupdf

    doc = pymupdf.open(path)
    # The cover page carries the real edition ("Mai 2026"); file names do not.
    cover = doc[0].get_text() if doc.page_count else ""
    edition = re.search(r"(?:Januar|Februar|März|April|Mai|Juni|Juli|August|"
                        r"September|Oktober|November|Dezember)\s+(\d{4})", cover)
    result: dict = {
        "source": "Deutsche Bundesbank, Statistische Fachreihe "
                  "Jahresabschlussstatistik (Verhaeltniszahlen)",
        "edition": edition.group(1) if edition else path.stem,
        "file": path.name,
        "basis": "Quartilswerte (Verteilung ueber die Unternehmen), nicht hochgerechnet",
        "sectors": {},
    }
    for page in doc:
        parsed = parse_quartile_page(page.get_text())
        if not parsed:
            continue
        sector = SECTION_TO_SECTOR.get(parsed["section"])
        if not sector:
            continue
        bucket = result["sectors"].setdefault(sector, {})
        bucket.setdefault(parsed["legal_form"], {}).update(reshape(parsed))
        result.setdefault("years", [])
        for y in parsed["years"]:
            if y not in result["years"]:
                result["years"].append(y)
    result["years"] = sorted(result.get("years", []))
    return result


PACKAGE_FILE = ROOT / "src" / "credit_readiness" / "reference" / "bundesbank_quartiles.json"

# What the engine itself needs: the newest edition, its latest reporting year,
# all legal forms together, and only the metrics we actually compare against.
PACKAGE_METRICS = [
    "eigenmittel_pct_bilanzsumme",
    "liquiditaet_2_pct",
    "ergebnis_vor_steuern_pct_umsatz",
    "forderungen_ll_pct_umsatz",
    "langfr_kapital_pct_anlagevermoegen",
    "bankschulden_pct_bilanzsumme",
    "vorraete_pct_bilanzsumme",
    "cashflow_pct_nettofremdmittel",
]


def build_package_dataset(editions: list[dict]) -> dict:
    """Condense the newest edition into the file the engine loads at runtime."""
    newest = max(editions, key=lambda e: (e["edition"], e["years"][-1]))
    year = str(newest["years"][-1])
    sectors: dict[str, dict] = {}
    for sector, forms in newest["sectors"].items():
        series = forms.get("alle_rechtsformen") or next(iter(forms.values()))
        per_size: dict[str, dict] = {}
        for metric in PACKAGE_METRICS:
            for size, years in series.get(metric, {}).items():
                if year in years:
                    per_size.setdefault(size, {})[metric] = years[year]
        if per_size:
            sectors[sector] = per_size
    return {
        "source": newest["source"],
        "edition": newest["edition"],
        "reporting_year": int(year),
        "legal_form": "alle_rechtsformen",
        "basis": newest["basis"],
        "caveat": "Erfassungsgrad der Umsatzklasse 2-10 Mio EUR rund 14%, "
                  "10-50 Mio EUR rund 42% -- kleinere Unternehmen sind im "
                  "Datenpool der Bundesbank unterrepraesentiert.",
        "sectors": sectors,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    folder = Path(argv[1])
    pdfs = sorted(folder.glob("*jahresabschlussstatistik-verhaeltniszahlen-data.pdf"))
    if not pdfs:
        print(f"no Bundesbank PDFs found in {folder}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    parsed_editions = []
    for pdf in pdfs:
        data = parse_pdf(pdf)
        if not data["sectors"]:
            print(f"  {pdf.name}: nothing parsed -- layout differs, skipped")
            continue
        parsed_editions.append(data)
        target = OUT_DIR / f"verhaeltniszahlen_{data['edition']}.json"
        target.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        sectors = len(data["sectors"])
        metrics = sum(len(v.get("alle_rechtsformen", {})) for v in data["sectors"].values())
        print(f"  {target.name}: {sectors} sectors, {metrics} metric series, years {data['years']}")
        manifest.append({"edition": data["edition"], "file": target.name,
                         "years": data["years"], "sectors": sorted(data["sectors"])})

    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"source": "Deutsche Bundesbank, Jahresabschlussstatistik "
                              "(Verhaeltniszahlen), Quartilswerte",
                    "editions": manifest}, indent=1, ensure_ascii=False),
        encoding="utf-8")
    package = build_package_dataset(parsed_editions)
    PACKAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PACKAGE_FILE.write_text(json.dumps(package, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\n{len(manifest)} editions -> {OUT_DIR.relative_to(ROOT)}")
    print(f"engine dataset  -> {PACKAGE_FILE.relative_to(ROOT)} "
          f"(Ausgabe {package['edition']}, Berichtsjahr {package['reporting_year']}, "
          f"{len(package['sectors'])} Branchen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
