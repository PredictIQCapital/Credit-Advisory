"""Client-facing report rendering (Markdown).

Written in German, because the reader is the SME owner or their Steuerberater.

Two constraints shape every line of this module:

  * Wording discipline. The report must never read as a rating or an approval
    prediction. It states what a lender is likely to see and what can be changed.
  * Traceability. Every flagged weakness shows its raw value, so the client's
    own accountant can check the arithmetic. That is the trust mechanism.
"""

from __future__ import annotations

from ..benchmarks import VINTAGE
from ..engine import DiagnosticResult
from ..remediation import FixCategory, Verdict


def _pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f}%"


def _x(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}x"


def _eur(v: float | None) -> str:
    return "n/a" if v is None else f"{v:,.0f} EUR"


def _days(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0f} Tage"


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


def render_markdown(result: DiagnosticResult) -> str:
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
    w(f"**Branche:** {c.profile.sector.value}  ")
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
    w(f"| Indikativer Gesamtwert | {s.total_score:.1f} / 100 |")
    w(f"| Datenabdeckung | {s.coverage*100:.0f}% der Bewertungsfaktoren |")
    w(f"| **Einordnung** | **{result.verdict.value}** |")
    w("")
    w(_VERDICT_GUIDANCE[result.verdict])
    w("")

    sim = result.simulation
    if sim.applied:
        arrow = f"{sim.before_score:.1f} -> {sim.after_score:.1f}"
        band_txt = (
            f"Band {sim.before_band} -> {sim.after_band}"
            if sim.band_improved
            else f"Band {sim.before_band} (unveraendert)"
        )
        w(
            f"**Simulierte Wirkung der Massnahmen:** {arrow} Punkte "
            f"({sim.delta:+.1f}), {band_txt}."
        )
        w("")

    # --------------------------------------------------------------- ratios
    w("## 2. Kennzahlen")
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
        assessment = f"{fs.score:.0f}/100" if fs and fs.score is not None else "-"
        w(f"| {label} | {value} | {assessment} |")
    w("")
    w(
        f"Absolut: Bilanzsumme {_eur(r.bilanzsumme)}, Umsatz (annualisiert) "
        f"{_eur(r.umsatz)}, EBITDA {_eur(r.ebitda)}, Kapitaldienst "
        f"{_eur(r.kapitaldienst)}."
    )
    w("")

    # ----------------------------------------------------------- weaknesses
    w("## 3. Was das Rating am staerksten belastet")
    w("")
    w("Sortiert nach gewichtetem Punktverlust - oben steht, was am meisten kostet.")
    w("")
    w("| Rang | Faktor | Wert | Punkte (0-100) | Gewicht | Punktverlust |")
    w("|---|---|---|---|---|---|")
    for i, f in enumerate(s.ranked_weaknesses[:8], start=1):
        w(
            f"| {i} | {f.label} | {f.format_value()} | {f.score:.0f} | "
            f"{f.weight*100:.0f}% | {f.points_lost:.1f} |"
        )
    w("")
    if s.missing_factors:
        w("**Nicht bewertbar mangels Daten:**")
        w("")
        for f in s.missing_factors:
            w(f"- {f.label}: {f.missing_reason}")
        w("")

    # ------------------------------------------------------------- findings
    w("## 4. Befunde und Massnahmen")
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
    w("## 5. Simulation: Kennzahlen nach Umsetzung")
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
        w(f"| **Gesamtwert** | **{sim.before_score:.1f}** | **{sim.after_score:.1f}** |")
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
    w("## 6. Lender-Fit")
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
        w(f"| {o.lender.name} | {o.fit_score:.0f} | {status} | {detail} |")
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
    w("## 7. Branchenvergleich")
    w("")
    w(f"*Datenstand Benchmark: {VINTAGE}*")
    w("")
    w("| Kennzahl | Unternehmen | Branchenmedian | Einordnung |")
    w("|---|---|---|---|")
    for cmp_ in result.benchmark:
        cv = cmp_.company_value
        if cmp_.metric in ("Eigenkapitalquote", "EBIT-Marge"):
            cv_s, med_s = _pct(cv), _pct(cmp_.sector_median)
        elif cmp_.metric == "Debitorenlaufzeit":
            cv_s, med_s = _days(cv), _days(cmp_.sector_median)
        else:
            cv_s, med_s = _x(cv), _x(cmp_.sector_median)
        w(f"| {cmp_.metric} | {cv_s} | {med_s} | {cmp_.verdict} |")
    w("")

    # ----------------------------------------------------------- next steps
    w("## 8. Naechste Schritte")
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
        for i, f in enumerate(ordered, start=1):
            w(f"{i}. **{f.title}** ({f.effort.value}er Aufwand, ca. {f.weeks_to_effect} Wochen)")
        w(f"{len(ordered)+1}. Unterlagenpaket zusammenstellen und erst danach "
          "Gespraech mit dem in Abschnitt 6 genannten Kreditgebertyp fuehren.")
    w("")
    w("---")
    w("")
    w(f"*{result.disclaimer}*")
    w("")

    return "\n".join(out)
