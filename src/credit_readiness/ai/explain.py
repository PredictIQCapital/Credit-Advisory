"""Plain-language explanations of a result -- with guardrails on anything AI writes.

`explain()` asks the configured provider first. Its text is then checked
against the same wording rules the report is tested for; anything that sounds
like a rating, an approval promise or a probability is thrown away and the
deterministic template below is used instead. The client never sees AI text
that failed the check, and every attempt is logged.
"""

from __future__ import annotations

import re
from typing import Optional

from ..formatting import de

# Phrases that would turn an explanation into a rating or an approval promise.
FORBIDDEN = (
    r"garantiert", r"\bguarantee", r"wird (sicher |bestimmt )?genehmigt", r"will be approved",
    r"zusage (der|ihrer) bank", r"ausfallwahrscheinlichkeit von", r"probability of (default|approval)",
    r"\d+\s*%\s*(chance|wahrscheinlich|likely)", r"chance(n)? (auf|of) (eine )?(zusage|approval)",
    r"\brating von\b", r"bonitaetsnote", r"credit rating of", r"sicher bewilligt",
)
_FORBIDDEN_RE = re.compile("|".join(FORBIDDEN), re.I)


def violates_guardrails(text: str) -> Optional[str]:
    """The offending phrase, or None."""
    t = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    m = _FORBIDDEN_RE.search(t)
    return m.group(0) if m else None


FINDING_TEXT = {
    "R01": ("Ihr Gesellschafterdarlehen zaehlt derzeit als Schulden. Mit einem Rangruecktritt werten es fast alle Banken als Eigenkapital.",
            "Your shareholder loan currently counts as debt. With a subordination agreement almost every bank treats it as equity."),
    "R02": ("Ihre juengste BWA ist zu alt; Banken lesen das als schwaches Reporting.",
            "Your latest management report is too old; banks read this as weak reporting."),
    "R03": ("Fuer diesen Betrag erwarten Banken eine Planrechnung.",
            "For this amount banks expect a financial plan."),
    "R04": ("Ihr Kontokorrent ist dauerhaft ausgeschoepft - ein Warnsignal, das sich mit einem passenden Darlehen beheben laesst.",
            "Your overdraft is permanently maxed out - a red flag that a matching term loan can fix."),
    "R05": ("Ihre Kunden zahlen spaet; Factoring koennte den Kreditbedarf senken.",
            "Your customers pay late; factoring could reduce the credit need."),
    "R06": ("Langfristiges Vermoegen ist teils kurzfristig finanziert.",
            "Long-term assets are partly funded with short-term money."),
    "R07": ("Ihre Zahlen tragen die Rate, es fehlen aber Sicherheiten - loesbar ueber Foerderprogramme.",
            "Your numbers support the instalment but collateral is short - solvable through public programmes."),
    "R08": ("Es gibt substanzielle Schwaechen (z. B. Verluste), die sich nicht durch Aufbereitung beheben lassen.",
            "There are substantive weaknesses (e.g. losses) that presentation cannot fix."),
    "R09": ("Steuerrueckstaende sind fuer fast jede Bank ein Ausschlussgrund und muessen zuerst geklaert werden.",
            "Tax arrears rule out almost every bank and must be resolved first."),
    "R10": ("Ein hoher Lagerbestand bindet Liquiditaet.", "High inventory ties up cash."),
}


def template_explanation(summary: dict, lang: str) -> str:
    en = lang == "en"
    band, after = summary.get("band"), summary.get("band_after_remediation")
    verdict = summary.get("verdict", "")
    parts = []
    if verdict.startswith("nicht"):
        parts.append("Your file currently shows substantive weaknesses. Applying now would most likely produce a documented rejection, so we advise preparing first."
                     if en else "Ihre Unterlagen zeigen derzeit substanzielle Schwaechen. Ein Antrag jetzt wuerde voraussichtlich abgelehnt; wir raten, zuerst vorzubereiten.")
    elif after is None:
        parts.append(f"Your readiness band today is {band}. The points below cost you the most; the full report calculates what each measure changes."
                     if en else f"Ihr Readiness-Band ist heute {band}. Die folgenden Punkte kosten Sie am meisten; der vollstaendige Bericht rechnet durch, was jede Massnahme bewirkt.")
    elif band in ("A", "B") and after == band:
        parts.append(f"Your readiness band is {band}: your numbers already support financing. The focus is on terms and the right lender."
                     if en else f"Ihr Readiness-Band ist {band}: Ihre Zahlen tragen bereits eine Finanzierung. Der Fokus liegt auf Konditionen und dem passenden Kreditgeber.")
    else:
        parts.append(f"Your readiness band today is {band}. After the measures below, the calculation shows band {after}."
                     if en else f"Ihr Readiness-Band ist heute {band}. Nach den Massnahmen unten ergibt die Rechnung Band {after}.")
    for f in (summary.get("findings") or [])[:3]:
        txt = FINDING_TEXT.get(f.get("rule"))
        if txt:
            parts.append(txt[1] if en else txt[0])
    parts.append("This is a directional assessment, not a credit rating; the lender decides."
                 if en else "Das ist eine richtungsweisende Einschaetzung, kein Rating; die Entscheidung trifft der Kreditgeber.")
    return " ".join(parts)


def explain(provider, summary: dict, lang: str, question: Optional[str] = None,
            log=None) -> dict:
    """Returns {"text", "source": "ki"|"vorlage", "blocked": phrase|None}."""
    text, blocked, error = None, None, None
    try:
        text = provider.explain(summary, lang, question)
    except Exception as exc:  # noqa: BLE001 - never fail the page because of the AI
        error = str(exc)
    if text:
        blocked = violates_guardrails(text)
    if log:
        log(purpose="erklaerung" if not question else "frage", ok=bool(text) and not blocked,
            detail=blocked or error or "")
    if text and not blocked:
        return {"text": text, "source": "ki", "blocked": None}
    if question:
        fallback = ("I can only explain what is in your result. Please ask your advisor for anything beyond that."
                    if lang == "en" else "Ich kann nur erklaeren, was in Ihrem Ergebnis steht. Fuer alles Weitere sprechen Sie bitte Ihren Berater an.")
        return {"text": fallback + " " + template_explanation(summary, lang), "source": "vorlage", "blocked": blocked}
    return {"text": template_explanation(summary, lang), "source": "vorlage", "blocked": blocked}


def coverage_note(summary: dict, lang: str) -> str:
    cov = summary.get("coverage") or 0
    pct = de(cov * 100)
    return (f"Based on {pct}% of the assessment factors." if lang == "en"
            else f"Grundlage: {pct}% der Bewertungsfaktoren.")
