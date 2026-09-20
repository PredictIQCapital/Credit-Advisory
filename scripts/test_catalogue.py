"""The test catalogue, as data.

docs/testing/test-plan.md carries the detail -- what each sample file must
contain and why. This module carries only the IDs and one-liners, so the
workbook's Testprotokoll sheet and the plan cannot drift apart on the IDs.

Areas:
  DOC   reading annual accounts        VAL   plausibility, must block or warn
  DTV   DATEV and BWA                  RULE  one case per fixability rule
  BNK   bank statement exports         BAND  band thresholds and edge cases
  AI    the AI path                    SEC   permissions and security
  UX    usability and presentation
"""

from __future__ import annotations

TESTS: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("DOC", "Auslesen von Jahresabschluessen", [
        ("DOC-01", "Standard-Jahresabschluss GmbH (Text-PDF)", "Alle 33 Felder, Bilanzprobe OK"),
        ("DOC-02", "Verkuerzte Bilanz (Kleinstkapitalgesellschaft)", "Nur Hauptgruppen; Fehlendes wird gemeldet, nicht geraten"),
        ("DOC-03", "'davon mit einer Restlaufzeit bis zu einem Jahr'", "Kurz- und langfristig korrekt getrennt"),
        ("DOC-04", "GmbH & Co. KG (Kapitalanteile statt gez. Kapital)", "Eigenkapital korrekt"),
        ("DOC-05", "Einzelunternehmen (Eigenkapital in einer Zeile)", "Eigenkapital korrekt"),
        ("DOC-06", "Zahlen in TEUR", "Faktor 1.000 erkannt oder Auslesung verweigert"),
        ("DOC-07", "Vorjahresspalte links statt rechts", "Aktuelles Jahr ausgelesen"),
        ("DOC-08", "Nicht durch Eigenkapital gedeckter Fehlbetrag (Aktivseite)", "Eigenkapital negativ"),
        ("DOC-09", "Scan oder Foto, leicht schief", "Lokal: klarer Fehler. Claude: liest"),
        ("DOC-10", "Beschaedigte oder passwortgeschuetzte Datei", "Klare Meldung, kein Absturz"),
        ("DOC-11", "Falsches Dokument (z. B. Rechnung)", "Keine Zahlen, Hinweis an den Nutzer"),
        ("DOC-12", "Langer Geschaeftsbericht mit Anhang", "Richtige Tabellen gefunden"),
        ("DOC-13", "Absichtlich unausgeglichene Bilanz", "Konsistenzpruefung schlaegt an"),
    ]),
    ("DTV", "DATEV und BWA", [
        ("DTV-01", "SuSa SKR04, laufendes Jahr, CSV in cp1252", "Eingelesen, deutsche Zahlen korrekt"),
        ("DTV-02", "SuSa Vorjahr", "Vorjahresvergleich und Umsatzwachstum"),
        ("DTV-03", "SuSa nach SKR03", "Ausdrueckliche Ablehnung statt Schaetzung"),
        ("DTV-04", "BWA ueber 6 Monate (Rumpfperiode)", "Annualisierung greift"),
        ("DTV-05", "Unbekannte Kontenbereiche", "Gemeldet, nicht stillschweigend ignoriert"),
    ]),
    ("BNK", "Kontoumsaetze", [
        ("BNK-01", "Sparkassen-CSV", "Tage am Limit und Ruecklastschriften erkannt"),
        ("BNK-02", "Anderes Bankformat", "Eingelesen oder klar abgelehnt"),
        ("BNK-03", "Deutsche Zahlen (1.234,56)", "Korrekt interpretiert"),
        ("BNK-04", "Zwei und vier Ruecklastschriften", "Index faellt um 24, dann um 30 - Deckel bei 30"),
    ]),
    ("VAL", "Plausibilitaet: muss blockieren oder warnen", [
        ("VAL-01", "Aktiva-Passiva-Luecke groesser 0,5%", "FEHLER, Auswertung verweigert"),
        ("VAL-02", "Ergebnis GuV weicht vom Ergebnis der Bilanz ab", "FEHLER, Auswertung verweigert"),
        ("VAL-03", "Periodenlaenge 13 Monate", "FEHLER"),
        ("VAL-04", "Umsatz null", "FEHLER"),
        ("VAL-05", "Kontokorrent ueber das Limit gezogen", "WARNUNG, laeuft weiter"),
        ("VAL-06", "Darlehensliste weicht ueber 10% von den Bankschulden ab", "WARNUNG"),
        ("VAL-07", "Negativer Bestand, z. B. Vorraete", "WARNUNG"),
        ("VAL-08", "Keine Darlehensliste", "HINWEIS, DSCR nicht bewertet, Abdeckung unter 100%"),
    ]),
    ("RULE", "Behebbarkeitsregeln, je ein Fall", [
        ("RULE-R01", "Gesellschafterdarlehen ohne Rangruecktritt, EK-Quote unter 20%", "R01, Band steigt in der Simulation"),
        ("RULE-R02", "BWA sieben Monate alt", "R02, Schweregrad wesentlich"),
        ("RULE-R03", "Finanzierungswunsch ab 100.000 EUR ohne Planrechnung", "R03"),
        ("RULE-R04", "KK-Auslastung 85% bei positivem EBITDA", "R04, nicht R08"),
        ("RULE-R05", "Debitorenlaufzeit 60 Tage, Forderungen ueber 50.000", "R05"),
        ("RULE-R06", "Anlagendeckungsgrad II unter 1", "R06"),
        ("RULE-R07", "DSCR ab 1,10, Sicherheiten unter 60% des Wunsches", "R07"),
        ("RULE-R08", "EBITDA negativ", "R08, nicht behebbar, keine Wegsimulation"),
        ("RULE-R09", "Steuerrueckstaende", "R09, kritisch, nicht behebbar"),
        ("RULE-R10", "Vorratsreichweite ueber 90 Tage, Vorraete ueber 50.000", "R10"),
    ]),
    ("BAND", "Bandgrenzen und Sonderfaelle", [
        ("BAND-01", "Score knapp ueber und unter 78", "A / B"),
        ("BAND-02", "Score knapp ueber und unter 65", "B / C"),
        ("BAND-03", "Score knapp ueber und unter 52", "C / D"),
        ("BAND-04", "Score knapp ueber und unter 38", "D / E"),
        ("BAND-05", "Keine Auskunft und keine Darlehen", "Abdeckung 75%, Renormierung korrekt"),
        ("BAND-06", "EBITDA null oder negativ", "Verschuldungsgrad mit 0 bewertet, nicht weggelassen"),
    ]),
    ("AI", "KI-Pfad", [
        ("AI-01", "Keine KI-Einwilligung", "Dokument wird nicht uebermittelt"),
        ("AI-02", "KI liest eine Zahl falsch", "Konsistenzpruefung blockiert"),
        ("AI-03", "Nutzer korrigiert eine Zahl", "Der korrigierte Wert wird gerechnet"),
        ("AI-04", "Frage: Werde ich genehmigt?", "Leitplanke greift, Vorlagentext"),
        ("AI-05", "Frage nach der Ausfallwahrscheinlichkeit", "Leitplanke greift"),
        ("AI-06", "PDF mit eingebetteten Anweisungen", "Als Daten behandelt, nicht befolgt"),
        ("AI-07", "KI-Protokoll", "Nur Hash, kein Inhalt gespeichert"),
        ("AI-08", "KI-Dienst nicht erreichbar", "Vorlagentext, Seite funktioniert weiter"),
    ]),
    ("SEC", "Rechte und Sicherheit", [
        ("SEC-01", "Fremden Fall ueber die URL aufrufen", "404, kein Datenabfluss"),
        ("SEC-02", "Steuerberater ruft den Fragebogen des Unternehmens auf", "Nicht sichtbar"),
        ("SEC-03", "Bericht vor der Freigabe", "Fuer das Unternehmen nicht sichtbar"),
        ("SEC-04", "Konto loeschen", "Faelle, Dokumente und Zugang entfernt"),
        ("SEC-05", "Zehn Fehlanmeldungen", "Sperre greift"),
        ("SEC-06", "Upload einer .exe oder sehr grossen Datei", "Abgelehnt"),
        ("SEC-07", "Abmelden", "Sitzung ungueltig, Cookie HttpOnly"),
    ]),
    ("UX", "Bedienung und Darstellung", [
        ("UX-01", "Kompletter Gratis-Check auf dem Handy", "Ohne Hilfe durchfuehrbar"),
        ("UX-02", "Sprachumschaltung DE/EN", "Keine deutschen Reste im englischen Modus"),
        ("UX-03", "Deutsches Zahlenformat", "In jedem Kundendokument"),
        ("UX-04", "Umlaute in Briefen und Bericht", "Korrekt dargestellt"),
        ("UX-05", "Seite mitten im Ablauf neu laden", "Fortschritt bleibt erhalten"),
        ("UX-06", "Bericht drucken", "Sauberer Umbruch, Hinweis auf jeder Seite"),
        ("UX-07", "Echter Unternehmer testet ohne Erklaerung", "Kommt allein durch - der eigentliche Test"),
    ]),
]
