"""Client-facing report rendering (Markdown).

Written in German, because the reader is the SME owner or their Steuerberater.

Two constraints shape every line of this module:

  * Wording discipline. The report must never read as a rating or an approval
    prediction. It states what a lender is likely to see and what can be changed.
  * Traceability. Every flagged weakness shows its raw value, so the client's
    own accountant can check the arithmetic. That is the trust mechanism.
"""

from __future__ import annotations

from ..benchmarks import CAVEAT, VINTAGE
from ..engine import DiagnosticResult
from ..remediation import FixCategory, Verdict
from ..formatting import de


def _pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{de(v * 100, digits)}%"


def _x(v: float | None) -> str:
    return "n/a" if v is None else f"{de(v, 2)}x"


def _eur(v: float | None) -> str:
    return "n/a" if v is None else f"{de(v)} EUR"


def _days(v: float | None) -> str:
    return "n/a" if v is None else f"{de(v)} Tage"


_VERDICT_GUIDANCE = {
    Verdict.ALREADY_BANKABLE: (
        "Das Unternehmen ist nach den vorliegenden Zahlen grundsaetzlich "
        "finanzierbar. Der Beratungsschwerpunkt liegt auf Konditionen und "
        "Lenderauswahl, nicht auf Aufbereitung."
    ),
    Verdict.FIXABLE_PRESENTATION: (
        "Die identifizierten Schwaechen betreffen Darstellung und Unterlagen, "
        "nicht die wirtschaftliche Substanz. Genau dieser Fall ist der Kern des "
        "Beratungsangebots."
    ),
    Verdict.FIXABLE_STRUCTURE: (
        "Die Schwaechen sind struktureller Natur - falsches Finanzierungsinstrument "
        "oder Besicherungsluecke. Behebbar, aber mit laengerer Vorlaufzeit als "
        "reine Aufbereitung."
    ),
    Verdict.GENUINE_RISK: (
        "ACHTUNG: Es liegen substanzielle Bonitaetsschwaechen vor. Diese sind "
        "durch Aufbereitung NICHT loesbar. Eine Antragstellung im aktuellen "
        "Zustand erzeugt eine dokumentierte Ablehnung, die spaetere Antraege "
        "zusaetzlich belastet."
    ),
}


_PROVENANCE_LABELS = {
    "balance_sheet": "Bilanz und GuV",
    "facilities": "Darlehensliste",
    "balance_sheet.kontokorrent_limit": "Kontokorrentlimit",
    "balance_sheet.kontokorrent_inanspruchnahme": "Kontokorrent-Inanspruchnahme",
    "balance_sheet.gesellschafterdarlehen_rangruecktritt": "Rangruecktritt",
    "behavior.bwa_stand": "BWA-Stand",
    "behavior.bwa_age_months": "BWA-Alter",
    "behavior.bwa_frequency": "BWA-Frequenz",
    "behavior.has_planning_forecast": "Planrechnung",
    "behavior.tax_arrears": "Steuerrueckstaende",
    "behavior.overdraft_days_at_limit_12m": "Tage am Kontokorrentlimit",
    "behavior.returned_direct_debits_12m": "Ruecklastschriften",
}


def render_markdown(result: DiagnosticResult, data_basis: dict | None = None) -> str:
    """Render the client report.

    `data_basis` is the optional assembly record (provenance, notes, parsed
    sources) of a case built from uploads; it adds section 9 so the reader can
    see which figure came from which source.
    """
    c = result.case
    r = result.ratios
    s = result.scorecard
    out: list[str] = []
    w = out.append

    # ---------------------------------------------------------------- header
    w(f"# Kreditfaehigkeits-Diagnostik: {c.profile.name}")
    w("")
    w(f"**Fall-ID:** {c.case_id}  ")
    w(f"**Erstellt:** {result.generated_on.isoformat()}  ")
    w(f"**Rechtsform:** {c.profile.legal_form.value}  ")
    nace_txt = f" (WZ {c.profile.nace_code})" if c.profile.nace_code else ""
    w(f"**Branche:** {c.profile.sector.value}{nace_txt}  ")
    w(f"**Mitarbeiter:** {c.profile.employees} ({c.profile.size_class})  ")
    if c.request:
        w(
            f"**Finanzierungsanfrage:** {_eur(c.request.amount)} "
            f"({c.request.purpose}, {c.request.tenor_years} Jahre)  "
        )
    w("")
    w(f"> {result.disclaimer}")
    w("")

    # ------------------------------------------------------------- verdict
    w("## 1. Ergebnis auf einen Blick")
    w("")
    w(f"| | |")
    w(f"|---|---|")
    w(f"| **Readiness-Band** | **{s.band.value}** - {s.band.interpretation} |")
    w(f"| Indikativer Gesamtwert | {de(s.total_score, 1)} / 100 |")
    w(f"| Bewertungsmassstab | {s.basis_label} |")
    g = result.scorecard_generic
    if g is not None and s.sector_specific:
        w(f"| Zum Vergleich: alle Branchen | {de(g.total_score, 1)} / 100, Band {g.band.value} |")
    w(f"| Datenabdeckung | {de(s.coverage*100)}% der Bewertungsfaktoren |")
    w(f"| **Einordnung** | **{result.verdict.value}** |")
    w("")
    w(_VERDICT_GUIDANCE[result.verdict])
    w("")
    if s.sector_specific:
        w("*Bewertungsmassstab:* Eigenkapital, Rentabilitaet, Liquiditaet, "
          "Anlagendeckung und Kreditorenlaufzeit werden an den Quartilen der "
          f"eigenen Branche gemessen ({s.sector.value}, Bundesbank). "
          "Kapitaldienstfaehigkeit, Verschuldung und Zinsdeckung gelten fuer alle "
          "Branchen gleich, weil sie die Rueckzahlung selbst betreffen. Der Wert "
          "\"alle Branchen\" zeigt, wie dieselben Zahlen ohne Branchenbezug "
          "aussehen -- Kreditgeber bewerten das Branchenrisiko zusaetzlich.")
        w("")

    sim = result.simulation
    if sim.applied:
        arrow = f"{de(sim.before_score, 1)} -> {de(sim.after_score, 1)}"
        band_txt = (
            f"Band {sim.before_band} -> {sim.after_band}"
            if sim.band_improved
            else f"Band {sim.before_band} (unveraendert)"
        )
        w(
            f"**Simulierte Wirkung der Massnahmen:** {arrow} Punkte "
            f"({'+' if sim.delta >= 0 else ''}{de(sim.delta, 1)}), {band_txt}."
        )
        w("")

    # ------------------------------------------------------- knock-out check
    # Deliberately before the ratios: a file can score respectably and still be
    # declined on one line, and the client should hear that line first.
    if result.rejection is not None:
        rej = result.rejection
        w("## 2. Ausschlusskriterien der Kreditgeber")
        w("")
        if rej.clean:
            w(f"Geprueft wurden {rej.checked} Kriterien, die bei Kreditgebern "
              "regelmaessig zur Ablehnung fuehren - unabhaengig von allen "
              "uebrigen Kennzahlen. **Keines davon liegt vor.**")
            w("")
            w("Das ist eine eigenstaendige Aussage und nicht dasselbe wie eine "
              "gute Bewertung: es bedeutet, dass das Gespraech ueber Konditionen "
              "ueberhaupt gefuehrt werden kann.")
        else:
            offen = [x for x in rej.reasons if not x.mitigated]
            if rej.knockouts:
                w(f"**{len(rej.knockouts)} K.-o.-Kriterium/-Kriterien festgestellt.** "
                  "Solange diese Punkte offen sind, ist eine Antragstellung nicht "
                  "sinnvoll: sie erzeugt eine dokumentierte Ablehnung, die jeden "
                  "spaeteren Antrag zusaetzlich belastet.")
            else:
                w(f"**{len(offen)} Befund(e)**, die im Kreditgespraech angesprochen "
                  "werden. Kein K.-o.-Kriterium, aber jeder Punkt braucht eine "
                  "vorbereitete Antwort.")
            w("")
            for reason in rej.reasons:
                flag = " *(durch Rangruecktritt entschaerft)*" if reason.mitigated else ""
                w(f"### {reason.code} - {reason.title} ({reason.severity.value}){flag}")
                w("")
                w(f"{reason.finding}")
                w("")
                w(f"**Wie ein Kreditgeber das liest.** {reason.consequence}")
                w("")
                w(f"**Was zu tun ist.** {reason.action}")
                w("")
                w(f"*Grundlage: {reason.source}*")
                w("")
            w("> Diese Pruefung ersetzt keine rechtliche Beurteilung. Ob sich aus "
              "einem Befund Pflichten ergeben - etwa nach 49 Abs. 3 GmbHG oder "
              "15a InsO -, ist mit dem Steuerberater oder einem Rechtsanwalt zu "
              "klaeren; diese Frage haengt an einer Fortfuehrungsprognose, die "
              "diese Auswertung nicht leisten kann.")
            w("")

    # --------------------------------------------------------------- ratios
    w("## 3. Kennzahlen")
    w("")
    w("| Kennzahl | Wert | Bewertung |")
    w("|---|---|---|")
    rows = [
        ("Eigenkapitalquote (wirtschaftlich)", _pct(r.eigenkapitalquote)),
        ("Eigenkapitalquote (bilanziell)", _pct(r.eigenkapitalquote_bilanziell)),
        ("Dynamischer Verschuldungsgrad", _x(r.dynamischer_verschuldungsgrad)),
        ("Kapitaldienstfaehigkeit (bestehend)", _x(r.kapitaldienstfaehigkeit)),
        ("Kapitaldienstfaehigkeit (inkl. neu)", _x(r.kapitaldienstfaehigkeit_inkl_neu)),
        ("Zinsdeckungsgrad", _x(r.zinsdeckungsgrad)),
        ("EBITDA-Marge", _pct(r.ebitda_marge)),
        ("EBIT-Marge", _pct(r.ebit_marge)),
        ("Liquiditaet 2. Grades", _pct(r.liquiditaet_2_grades, 0)),
        ("Anlagendeckungsgrad II", _pct(r.anlagendeckungsgrad_ii, 0)),
        ("Debitorenlaufzeit", _days(r.debitorenlaufzeit_tage)),
        ("Kreditorenlaufzeit", _days(r.kreditorenlaufzeit_tage)),
        ("Vorratsreichweite", _days(r.vorratsreichweite_tage)),
        ("Kontokorrent-Auslastung", _pct(r.kontokorrent_auslastung, 0)),
    ]
    score_by_key = {f.key: f for f in s.factors}
    key_for_label = {
        "Eigenkapitalquote (wirtschaftlich)": "eigenkapitalquote",
        "Dynamischer Verschuldungsgrad": "dynamischer_verschuldungsgrad",
        "Kapitaldienstfaehigkeit (inkl. neu)": "kapitaldienstfaehigkeit_inkl_neu",
        "EBIT-Marge": "ebit_marge",
        "Liquiditaet 2. Grades": "liquiditaet_2_grades",
        "Zinsdeckungsgrad": "zinsdeckungsgrad",
        "Kontokorrent-Auslastung": "kontokorrent_auslastung",
    }
    for label, value in rows:
        fk = key_for_label.get(label)
        fs = score_by_key.get(fk) if fk else None
        assessment = f"{de(fs.score)}/100" if fs and fs.score is not None else "-"
        w(f"| {label} | {value} | {assessment} |")
    w("")
    w(
        f"Absolut: Bilanzsumme {_eur(r.bilanzsumme)}, Umsatz (annualisiert) "
        f"{_eur(r.umsatz)}, EBITDA {_eur(r.ebitda)}, Kapitaldienst "
        f"{_eur(r.kapitaldienst)}."
    )
    w("")

    # ----------------------------------------------------------- weaknesses
    w("## 4. Was das Rating am staerksten belastet")
    w("")
    w("Sortiert nach gewichtetem Punktverlust - oben steht, was am meisten kostet.")
    w("")
    w("| Rang | Faktor | Wert | Punkte (0-100) | Gewicht | Punktverlust |")
    w("|---|---|---|---|---|---|")
    for i, f in enumerate(s.ranked_weaknesses[:8], start=1):
        w(
            f"| {i} | {f.label} | {f.format_value()} | {de(f.score)} | "
            f"{de(f.weight*100)}% | {de(f.points_lost, 1)} |"
        )
    w("")
    if s.missing_factors:
        w("**Nicht bewertbar mangels Daten:**")
        w("")
        for f in s.missing_factors:
            w(f"- {f.label}: {f.missing_reason}")
        w("")

    # ------------------------------------------------------------- findings
    w("## 5. Befunde und Massnahmen")
    w("")
    if not result.findings:
        w("Keine wesentlichen Befunde.")
        w("")
    for f in result.findings:
        fixable = "behebbar" if f.category.is_fixable else "NICHT durch Aufbereitung behebbar"
        w(f"### {f.rule_id} - {f.title}")
        w("")
        w(
            f"**Kategorie:** {f.category.value} ({fixable}) | "
            f"**Schweregrad:** {f.severity} | **Aufwand:** {f.effort.value} | "
            f"**Wirkung nach ca.:** {f.weeks_to_effect} Wochen"
        )
        w("")
        w(f"**Befund.** {f.observation}")
        w("")
        w(f"**Massnahme.** {f.remediation}")
        w("")
        flags = []
        if f.requires_steuerberater:
            flags.append("Abstimmung mit dem Steuerberater erforderlich")
        if f.requires_legal:
            flags.append("rechtliche Pruefung erforderlich")
        if flags:
            w(f"*{'; '.join(flags).capitalize()}.*")
            w("")
        if f.caveat:
            w(f"> **Einschraenkung.** {f.caveat}")
            w("")

    # ------------------------------------------------------------ simulation
    w("## 6. Simulation: Kennzahlen nach Umsetzung")
    w("")
    if not sim.applied:
        w("Keine kennzahlenwirksamen Massnahmen simulierbar.")
        w("")
    else:
        b, a = sim.before_ratios, sim.after_ratios
        w("| Kennzahl | vorher | nachher |")
        w("|---|---|---|")
        w(f"| Eigenkapitalquote | {_pct(b.eigenkapitalquote)} | {_pct(a.eigenkapitalquote)} |")
        w(
            f"| Dynamischer Verschuldungsgrad | {_x(b.dynamischer_verschuldungsgrad)} "
            f"| {_x(a.dynamischer_verschuldungsgrad)} |"
        )
        w(
            f"| Kapitaldienstfaehigkeit (inkl. neu) | {_x(b.kapitaldienstfaehigkeit_inkl_neu)} "
            f"| {_x(a.kapitaldienstfaehigkeit_inkl_neu)} |"
        )
        w(
            f"| Liquiditaet 2. Grades | {_pct(b.liquiditaet_2_grades, 0)} "
            f"| {_pct(a.liquiditaet_2_grades, 0)} |"
        )
        w(
            f"| Kontokorrent-Auslastung | {_pct(b.kontokorrent_auslastung, 0)} "
            f"| {_pct(a.kontokorrent_auslastung, 0)} |"
        )
        w(f"| **Gesamtwert** | **{de(sim.before_score, 1)}** | **{de(sim.after_score, 1)}** |")
        w(f"| **Band** | **{sim.before_band}** | **{sim.after_band}** |")
        w("")
        w("**Simuliert:** " + "; ".join(sim.applied))
        w("")
        if sim.skipped:
            w("**Nicht simuliert:** " + "; ".join(sim.skipped))
            w("")
        w(
            "> Die Simulation zeigt die rechnerische Wirkung der Massnahmen auf die "
            "Kennzahlen. Sie ist keine Zusage, dass ein Kreditgeber die Finanzierung "
            "danach gewaehrt."
        )
        w("")

    # -------------------------------------------------------------- routing
    w("## 7. Lender-Fit")
    w("")
    w("### Aktuelles Profil")
    w("")
    w("| Kreditgebertyp | Fit | Status | Begruendung |")
    w("|---|---|---|---|")
    for o in result.routing_now[:5]:
        status = "moeglich" if o.eligible else "aktuell ausgeschlossen"
        # For an excluded route the blockers ARE the useful information; showing
        # only its positive reasons would read as an endorsement of a dead end.
        detail = "; ".join(o.reasons if o.eligible else o.blockers)[:160] or "-"
        w(f"| {o.lender.name} | {de(o.fit_score)} | {status} | {detail} |")
    w("")
    newly = {o.lender.key for o in result.routing_after if o.eligible} - {
        o.lender.key for o in result.routing_now if o.eligible
    }
    if newly:
        w("### Nach Umsetzung der Massnahmen zusaetzlich erreichbar")
        w("")
        for o in result.routing_after:
            if o.lender.key in newly:
                w(f"- **{o.lender.name}** - {o.lender.description} {o.lender.notes}")
        w("")

    # ------------------------------------------------------------ benchmark
    w("## 8. Branchenvergleich")
    w("")
    w(f"*Datenstand Benchmark: {VINTAGE}*")
    w("")
    w("Verglichen wird mit der Verteilung der Unternehmen derselben Branche und "
      "Umsatzgroessenklasse. Das untere und das obere Viertel geben an, wo die "
      "Streuung liegt - der Median allein sagt wenig ueber die Bandbreite.")
    w("")
    w("| Kennzahl | Unternehmen | Unteres Viertel | Branchenmedian | Oberes Viertel | Einordnung |")
    w("|---|---|---|---|---|---|")

    def _fmt(metric: str, value):
        if metric in ("Eigenkapitalquote", "EBIT-Marge"):
            return _pct(value)
        if metric == "Debitorenlaufzeit":
            return _days(value)
        return _x(value)

    for cmp_ in result.benchmark:
        q = cmp_.quartiles
        lower, upper = (_fmt(cmp_.metric, q[0]), _fmt(cmp_.metric, q[2])) if q else ("n/a", "n/a")
        rank = ""
        if cmp_.percentile is not None:
            rank = f" ({de(cmp_.percentile, 0)}. Perzentil)"
        w(f"| {cmp_.metric} | {_fmt(cmp_.metric, cmp_.company_value)} | {lower} | "
          f"{_fmt(cmp_.metric, cmp_.sector_median)} | {upper} | {cmp_.verdict}{rank} |")
    w("")
    w(f"*{CAVEAT}*")
    w("")

    if result.sector_trends:
        years = result.sector_trends[0].years
        w(f"### Branchenmedian im Zeitverlauf ({years[0]}-{years[-1]})")
        w("")
        w("Die Bewertung nutzt das juengste Berichtsjahr. Der Verlauf zeigt, ob sich "
          "der Massstab selbst bewegt hat -- das interne Vergleichsmaterial einer "
          "Bank kann dem veroeffentlichten Stand vor- oder nachlaufen.")
        w("")
        w("| Kennzahl | " + " | ".join(str(y) for y in years) + " | Unternehmen |")
        w("|---|" + "---|" * (len(years) + 1))
        for t in result.sector_trends:
            cells = [_pct(m) for m in t.medians] + [""] * (len(years) - len(t.medians))
            company = _pct(t.company_value) if t.company_value is not None else "-"
            w(f"| {t.label} | " + " | ".join(cells) + f" | {company} |")
        w("")
        w(f"*Vergleichsgruppe: {result.sector_trends[0].basis}. Jedes Jahr aus der "
          f"juengsten Bundesbank-Ausgabe, die es enthaelt.*")
        w("")

    # ---------------------------------------------------------- sensitivity
    if result.sensitivity and result.sensitivity.scenarios:
        sens = result.sensitivity
        w("## 9. Szenariorechnung (Sensitivitaetsanalyse)")
        w("")
        w("Die EBA-Leitlinien zur Kreditvergabe (EBA/GL/2020/06, Tz. 131 und "
          "Tz. 156-158) verlangen, die Rueckzahlungsfaehigkeit nicht nur zum "
          "Stichtag, sondern unter unguenstigen Bedingungen zu beurteilen. Die "
          "folgenden Szenarien sind daher nicht frei gewaehlt - Tz. 158 nennt "
          "sie, den Zinsanstieg sogar mit der Groessenordnung.")
        w("")
        w("| Szenario | Punkte | Stufe | Veraenderung | Kapitaldienstfaehigkeit |")
        w("|---|---|---|---|---|")
        w(f"| Ausgangslage | {de(sens.base_score, 1)} | {sens.base_band.value} | - | "
          f"{_x(result.ratios.kapitaldienstfaehigkeit_inkl_neu)} |")
        for sc in sens.scenarios:
            w(f"| {sc.label} | {de(sc.score, 1)} | {sc.band.value} | "
              f"{de(sc.delta, 1)} | {_x(sc.dscr)} |")
        w("")
        for sc in sens.scenarios:
            w(f"- **{sc.label}:** {sc.assumption}")
        w("")
        worst = sens.worst
        if sens.is_resilient:
            w(f"**Einordnung:** Auch im haertesten gerechneten Szenario "
              f"({worst.label}) bleibt das Unternehmen in Stufe "
              f"{worst.band.value}. Das ist ein Argument, das im Kreditgespraech "
              "aktiv vorgetragen werden sollte - die Bank rechnet ohnehin so.")
        else:
            w(f"**Einordnung:** Im Szenario \"{worst.label}\" faellt das Ergebnis "
              f"auf {de(worst.score, 1)} Punkte (Stufe {worst.band.value}). "
              "Rechnen Sie damit, dass der Kreditgeber diese Rechnung selbst "
              "anstellt, und bereiten Sie eine Antwort darauf vor.")
            if worst.equity_wiped_out:
                w("")
                w("Im selben Szenario ist das wirtschaftliche Eigenkapital "
                  "aufgezehrt. Das ist der Punkt, an dem aus einer Konditionen- "
                  "eine Bestandsfrage wird.")
        w("")

    # ----------------------------------------------------------- next steps
    w("## 10. Naechste Schritte")
    w("")
    if result.verdict is Verdict.GENUINE_RISK:
        w("1. Keine Antragstellung im aktuellen Zustand.")
        w("2. Befunde der Kategorie *Substanzielles Kreditrisiko* mit dem "
          "Steuerberater besprechen.")
        w("3. Operative Massnahmen definieren und Neubewertung in 6-12 Monaten.")
    else:
        ordered = sorted(
            [f for f in result.findings if f.category.is_fixable],
            key=lambda f: f.weeks_to_effect,
        )
        effort_adj = {"gering": "geringer", "mittel": "mittlerer", "hoch": "hoher"}
        for i, f in enumerate(ordered, start=1):
            adj = effort_adj.get(f.effort.value, f.effort.value)
            w(f"{i}. **{f.title}** ({adj} Aufwand, ca. {f.weeks_to_effect} Wochen)")
        w(f"{len(ordered)+1}. Unterlagenpaket zusammenstellen und erst danach "
          "Gespraech mit dem in Abschnitt 6 genannten Kreditgebertyp fuehren.")
    w("")

    # --------------------------------------------------------- data basis
    if data_basis:
        w("## 11. Datengrundlage")
        w("")
        prov = data_basis.get("provenance") or {}
        if prov:
            w("| Angabe | Quelle |")
            w("|---|---|")
            for key, src in sorted(prov.items()):
                w(f"| {_PROVENANCE_LABELS.get(key, key)} | {src} |")
            w("")
        for d in (data_basis.get("datev") or {}).values():
            w(
                f"- DATEV-SuSa *{d['filename']}* (Stichtag {d['period_end']}, "
                f"{d['period_months']} Monate): {de(d['unmapped_share']*100, 2)}% des "
                "Volumens nicht zugeordnet."
            )
        for b in data_basis.get("bank") or []:
            w(
                f"- Kontoumsaetze *{b['account_label']}*: {b['first_date']} bis "
                f"{b['last_date']} ({b['days_covered']} Tage, {b['transaction_count']} "
                "Buchungen)."
            )
        notes = data_basis.get("notes") or []
        if notes:
            w("")
            w("**Hinweise zur Datenlage:**")
            w("")
            for n in notes:
                w(f"- {n}")
        w("")

    w("---")
    w("")
    w(f"*{result.disclaimer}*")
    w("")

    return "\n".join(out)
