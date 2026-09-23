"""Section prose of the methodology document, German and English.

Split from methodology_text.py only for size. Each entry is the body of one
section; `{...}` placeholders are filled by the builder and both languages must
carry the same set -- tests/test_methodology_text.py enforces that.

German is the original and English a translation of it. Where the two could be
read differently, the German governs: it is the version the audience that would
challenge this document actually reads.
"""

from __future__ import annotations

DE = {
    "s01_h": "Zweck und Abgrenzung",
    "s01": """
  <p>Das Verfahren erzeugt eine <b>indikative Bereitschaftsstufe</b> (A bis E).
  Sie beschreibt, wie ein Kreditantrag mit dieser Datenlage bei einem typischen
  Kreditgeber voraussichtlich gelesen wird &ndash; und was daran veraenderbar ist.</p>
  <div class="note stop">
    <b>Was dies ausdruecklich nicht ist.</b> Kein Rating im Sinne der
    EU-Ratingverordnung (EG) Nr. 1060/2009, keine Ausfallwahrscheinlichkeit,
    keine Kreditentscheidung und keine Zusage. Es wird keine PD geschaetzt und
    keine ausgegeben. Jede Kreditentscheidung trifft ausschliesslich der
    jeweilige Kreditgeber nach eigenen Massstaeben.
  </div>
  <p>Drei Konstruktionsregeln folgen daraus und sind im Code durchgesetzt, nicht
  nur hier behauptet:</p>
  <ul>
    <li><b>Nachvollziehbarkeit.</b> Jeder Faktor gibt seinen Rohwert, seine
    Stuetzstellen, sein Gewicht und seinen Punktbeitrag aus. Es gibt keine
    Groesse, die nicht zeilenweise erklaerbar ist.</li>
    <li><b>Kein maschinelles Lernen.</b> Ausschliesslich stueckweise lineare
    Interpolation ueber offengelegte Schwellenwerte.</li>
    <li><b>Keine Ratingsprache.</b> Die Begriffe sind &bdquo;Stufe&ldquo; und
    &bdquo;indikativ&ldquo;.</li>
  </ul>""",

    "s02_h": "Regulatorische Grundlage",
    "s02_intro": """<p>Die Auswahl der Kennzahlen stammt nicht aus dem Lehrbuch,
  sondern aus drei Quellen, die beschreiben, was Kreditgeber im Euroraum
  tatsaechlich pruefen muessen beziehungsweise pruefen:</p>""",
    "s02_src1_n": "EBA/GL/2020/06",
    "s02_src2_n": "MaRisk (BaFin)",
    "s02_src3_n": "Bundesbank-Bonitaetsanalyse (ICAS)",
    "s02_src1_t": "Leitlinien fuer die Kreditvergabe und Ueberwachung, gueltig seit 30.06.2021",
    "s02_src1": """Anhang 3 Abschnitt B nennt die Kennzahlen, die ein Institut bei
        Unternehmenskrediten beruecksichtigen soll (Abschnitt 3). Tz. 121 und
        128 regeln, was in die Analyse der Finanzlage gehoert; Tz. 120 stellt
        klar, dass Sicherheiten <i>kein</i> vorrangiges Kriterium sein duerfen;
        Tz. 131 und 156&ndash;158 verlangen die Szenariorechnung.""",
    "s02_src2_t": "Rundschreiben 10/2021, Anlage 1, BTO 1.2",
    "s02_src2": """BTO 1.2.1 Tz. 1 verlangt die Analyse der Risikofaktoren
        &bdquo;unter besonderer Beruecksichtigung der Kapitaldienstfaehigkeit&ldquo;
        &ndash; daher traegt die Kapitaldienstfaehigkeit hier das groesste
        Einzelgewicht. BTO 1.4 Tz. 3 verlangt qualitative neben quantitativen
        Kriterien.""",
    "s02_src3_t": "Beschreibung des Verfahrens, Stand Dezember 2023",
    "s02_src3": """Die Kennzahlen, mit denen eine Zentralbank aus HGB-Abschluessen die
        Bonitaet deutscher Unternehmen einschaetzt: EBITDA, Gesamtverschuldung
        (bereinigt), Liquiditaet, Umsatzrendite, Entschuldungsfaehigkeit,
        bereinigte Eigenmittelquote und Kreditorenziel. Ausserdem die
        empirischen Verteilungen (Abschnitt 6) und die Methodik der
        Szenariorechnung (Abschnitt 8).""",
    "s02_note": """
    <b>Der wichtigste Befund aus der Auswertung dieser Quellen:
    Schwellenwerte gibt keine von ihnen vor.</b>
    EBA Anhang 1 verlangt vom Institut, &bdquo;acceptable ... ratio limits&ldquo;
    <i>festzulegen</i>, nennt aber keine Zahlen. MaRisk regelt den Prozess, nicht
    die Kennzahlenhoehe. Die Aufsicht bestimmt also <i>welche</i> Kennzahlen und
    <i>dass</i> Grenzen existieren muessen &ndash; die Hoehe ist eine eigene,
    begruendungspflichtige Entscheidung. Genau deshalb sind in diesem Dokument
    Kennzahlenauswahl (Abschnitt 3) und Schwellenwerte (Abschnitte 5 und 6)
    getrennt dargestellt und getrennt belegt.""",

    "s03_h": "Abgleich mit EBA Anhang 3",
    "s03": """<p>Anhang 3 Abschnitt B der EBA-Leitlinien listet zwanzig Kennzahlen fuer
  Kredite an Unternehmen. Die Leitlinie verlangt, sie zu beruecksichtigen
  &bdquo;to an extent that is applicable and appropriate to the specific credit
  proposal&ldquo; (Tz. 128 e). Die folgende Tabelle sagt fuer jede einzelne, was
  damit geschieht &ndash; einschliesslich der Faelle, in denen bewusst nichts
  geschieht.</p>""",

    "s04_h": "Faktoren und Gewichte",
    "s04_intro": """<p>Die Gewichte summieren sich auf 100%. Faellt ein Faktor mangels
  Daten aus, werden die verbleibenden Gewichte proportional hochgerechnet; der
  Bericht weist die erreichte Abdeckung aus. Eine duenne Akte wird dadurch nicht
  bestraft &ndash; sie wird als duenn gekennzeichnet.</p>""",
    "s04_note1": """
    <b>Eine Ausnahme von der Umverteilung.</b> Ist das EBITDA null oder negativ,
    ist der dynamische Verschuldungsgrad rechnerisch nicht definiert. Der Faktor
    wird dann nicht weggelassen, sondern mit null Punkten bewertet: ein
    Unternehmen ohne operativen Ueberschuss kann seine Schulden nicht aus dem
    Geschaeft zurueckfuehren, und ein Weglassen wuerde genau den Fall
    schoenrechnen, auf den es ankommt.""",
    "s04_note2": """
    <b>Warum Sicherheiten nicht bewertet werden.</b> EBA Tz. 120: Sicherheiten
    sind der zweite Ausweg, nicht die primaere Rueckzahlungsquelle, und duerfen
    eine Kreditvergabe nicht fuer sich rechtfertigen. Eine Besicherungsluecke
    erscheint deshalb als Befund und Massnahme im Bericht, aber nicht als
    punktewirksamer Faktor.""",

    "s05_h": "Schwellenwerte im Einzelnen",
    "s05": """<p>Zwischen zwei Stuetzstellen wird linear interpoliert, ausserhalb wird
  gekappt. Damit ist jeder Punktwert von Hand nachrechenbar &ndash; das ist der
  Grund fuer diese Konstruktion und nicht ein Nebeneffekt.</p>""",

    "s06_h": "Woher die Schwellenwerte stammen",
    "s06_h3a": "Kalibrierte Faktoren",
    "s06_p1": """<p>Sechs der {n_factors} Faktoren &ndash; zusammen {cal_pct}% des
  Gewichts &ndash; sind an die <b>Quartilswerte der Jahresabschlussstatistik der
  Deutschen Bundesbank</b> (Verhaeltniszahlen) gebunden: alle Branchen, die
  Umsatzgroessenklassen 2&ndash;10 Mio. und 10&ndash;50 Mio. EUR im Mittel,
  juengstes Berichtsjahr. Datenstand: {vintage}.</p>
  <p>Die Verankerung lautet:</p>""",
    "s06_kv1": "25. Perzentil", "s06_kv1s": "= 58 Punkte (Untergrenze Stufe C)",
    "s06_kv2": "Median", "s06_kv2s": "= 70 Punkte (Mitte Stufe B)",
    "s06_kv3": "75. Perzentil", "s06_kv3s": "= 82 Punkte (Stufe A)",
    "s06_p2": """<p>Die Begruendung ist einen Schritt lang: die EZB-Unternehmensbefragung
  SAFE weist rund 14% der Antragsteller als in erheblichen
  Finanzierungsschwierigkeiten aus. Ein Unternehmen im Median seiner
  Groessenklasse gehoert also nicht zu den Problemfaellen, sondern ist
  finanzierbar &ndash; Stufe B. Eine reine Perzentilabbildung wuerde den
  Medianbetrieb auf 50 Punkte setzen und damit behaupten, die Haelfte des
  deutschen Mittelstands sei ein Grenzfall. Das waere empirisch falsch.</p>""",
    "s06_note1": """
    <b>Bei &bdquo;je niedriger, desto besser&ldquo; drehen sich die Anker um.</b>
    Fuer die Kreditorenlaufzeit ist das 25. Perzentil das gute Ende; die
    Zuordnung lautet dort 25. Perzentil = 82, Median = 70, 75. Perzentil = 58.
    Diese Kurve ist ausserdem die einzige, die bei 82 Punkten gedeckelt ist:
    schnelles Bezahlen ist kein Bonitaetsbeleg, sondern nur das Fehlen eines
    Warnsignals.""",
    "s06_p3": """<p><b>Enden jenseits der Quartile.</b> Die Statistik liefert drei Punkte,
  keine Verteilung. Die Kurvenenden sind daher nicht extrapoliert, sondern auf
  wirtschaftlich bedeutsame Grenzen gezogen &ndash; Eigenkapital null, Marge
  negativ, Anlagendeckung unter 100%.</p>""",
    "s06_h3b": "Nicht kalibrierte Faktoren",
    "s06_p4": """<p>Fuer die uebrigen Faktoren enthaelt die Publikation keine vergleichbare
  Reihe. Ihre Kurven sind begruendete Konvention und als solche gekennzeichnet:
  Kapitaldienstfaehigkeit, dynamischer Verschuldungsgrad, Zinsdeckungsgrad,
  Kontokorrent-Auslastung, Aktualitaet der BWA, Creditreform-Index und
  Zahlungsverhalten.</p>""",
    "s06_note2": """
    <b>Eine Uebersetzung, die bewusst unterbleibt.</b> Die Bundesbank
    veroeffentlicht &bdquo;Cashflow in % der Nettofremdmittel&ldquo;. Das ist
    <i>nicht</i> unser dynamischer Verschuldungsgrad: anderer Zaehler (Cashflow
    nach Zins und Steuern statt EBITDA) und ein weit breiterer Nenner
    (saemtliche Verbindlichkeiten statt nur der Finanzschulden). Eine Umrechnung
    waere eine als Kalibrierung verkleidete Schaetzung. Der Faktor bleibt daher
    Konvention &ndash; und ist der erste Kandidat fuer eine Revision, sobald das
    Ergebnisprotokoll genug echte Platzierungen enthaelt.""",

    "s07_h": "Von Punkten zu Stufen",
    "s07_note": """
    <b>Die Stufengrenzen selbst sind nicht empirisch hergeleitet.</b> Sie sind
    so gesetzt, dass der Medianbetrieb in Stufe B und das untere Quartil in
    Stufe C liegt &ndash; also aus derselben SAFE-Ueberlegung wie die
    Faktorenanker, nicht aus beobachteten Ablehnungsquoten. Wer diese Zuordnung
    angreift, greift zu Recht die schwaechste Stelle des Verfahrens an. Sie
    aendert sich, sobald genug dokumentierte Kreditentscheidungen vorliegen.""",

    "s08_h": "Szenariorechnung",
    "s08_p1": """<p>Eine Stichtagskennzahl aus dem Vorjahresabschluss beantwortet die
  falsche Frage. Der Kreditgeber will nicht wissen, wie das Unternehmen am 31.
  Dezember aussah, sondern ob es den Kapitaldienst auch dann noch traegt, wenn
  es schlechter laeuft. Beide Aufsichtsquellen verlangen das ausdruecklich
  (EBA Tz. 131 und 156&ndash;158, MaRisk BTO 1.2.1 Tz. 1).</p>""",
    "s08_h3": "Wie der Schock durch den Abschluss gerechnet wird",
    "s08_p2": """<p>Der Mechanismus folgt dem veroeffentlichten Vorgehen der Deutschen
  Bundesbank zur Stressrechnung im eigenen Bonitaetsanalysesystem
  (Technical Paper 02/2023, Abschnitt 5.2). Dort wird eine Kostenposition
  gestresst; die Verrechnung ist unabhaengig davon, welcher Schock es ist:</p>
  <ul>
    <li>Mehrkosten beziehungsweise Deckungsbeitragsverlust ermitteln;</li>
    <li>Finanzierung zuerst aus liquiden Mitteln, danach ueber eine kurzfristige
      Bankverbindlichkeit;</li>
    <li>Zinsaufwand auf die neue Inanspruchnahme zum bisherigen Durchschnittssatz
      erhoehen, weil die Zinslast selbst bonitaetsrelevant ist;</li>
    <li>Steueraufwand mit dem unternehmenseigenen effektiven Satz mindern
      (nie unter null);</li>
    <li>vermindertes Ergebnis ins Eigenkapital durchbuchen;</li>
    <li>saemtliche Kennzahlen auf dem gestressten Abschluss neu rechnen.</li>
  </ul>""",
    "s08_note1": """
    <b>Der Zinsschock trifft die Kreditvertraege, nicht nur die GuV.</b>
    Tz. 158 k spricht von einer Erhoehung &bdquo;on all credit facilities of the
    borrower&ldquo;. Verteuert wuerde nur die Zinszeile, bliebe der Kapitaldienst
    &ndash; und damit die Kapitaldienstfaehigkeit, die entscheidende Kennzahl
    &ndash; unveraendert. Deshalb wird der Zinssatz jedes einzelnen Darlehens
    erhoeht.""",
    "s08_note2": """
    <b>Was die Szenariorechnung nicht ist.</b> Keine Prognose und keine
    Wahrscheinlichkeitsaussage. Sie sagt: unter diesen benannten Annahmen
    verschiebt sich die Stufe von X nach Y. Die Annahmen stehen im Bericht neben
    dem Ergebnis, damit der Unternehmer ihnen widersprechen kann &ndash; er kennt
    seinen variablen Kostenanteil besser als wir.""",

    "s09_h": "Ausschlusskriterien",
    "s09_p1": """<p>Eine gewichtete Punktzahl beantwortet die Frage, wie sich eine Akte
  insgesamt liest. Sie kann nicht beantworten, ob darin etwas steht, das das
  Gespraech unabhaengig vom Gesamtergebnis beendet &ndash; ein gewichteter
  Mittelwert laesst einen starken Faktor einen fatalen ausgleichen. Das sind
  zwei verschiedene Fragen und sie brauchen zwei verschiedene Verfahren.</p>""",
    "s09_p2": """<p>Diese {n_ko} Kriterien werden deshalb getrennt geprueft und getrennt
  berichtet, vor den Kennzahlen. Keiner der Schwellenwerte stammt von uns:</p>""",
    "s09_note1": """
    <b>Diese Pruefung ist keine rechtliche Beurteilung.</b> Ob sich aus einem
    Befund Pflichten ergeben &ndash; etwa nach 49 Abs. 3 GmbHG oder 15a InsO
    &ndash; haengt an einer Fortfuehrungsprognose, die dieses Verfahren nicht
    leisten kann und nicht zu leisten vorgibt. Der Bericht benennt den Zustand
    und verweist die Bewertung an den Steuerberater oder einen Rechtsanwalt.""",
    "s09_note2": """
    <b>Warum ein sauberes Ergebnis eine eigene Aussage ist.</b> &bdquo;Keines
    dieser Kriterien liegt vor&ldquo; ist nicht dasselbe wie eine gute
    Bewertung. Es bedeutet, dass ueber Konditionen ueberhaupt gesprochen werden
    kann &ndash; und genau das ist die Information, die ein Unternehmer vor der
    Antragstellung braucht.""",

    "s10_h": "Rechenweg an einem Beispiel",
    "s10_p1": """<p>Vollstaendiger Durchlauf am fiktiven Musterfall Mueller
  Praezisionstechnik GmbH. Alle Werte sind aus dem laufenden System erzeugt,
  nicht abgeschrieben.</p>""",
    "s10_p2": """<p>Die Szenariorechnung zum selben Fall:</p>""",
    "s10_p3": """<p>Die Lesart: der Betrieb ist zum Stichtag finanzierbar (Stufe B), haelt
  aber einen Umsatzrueckgang von 10% nicht aus, weil die Kapitaldienstfaehigkeit
  dann unter 1,0 faellt. Das ist die Information, die im Kreditgespraech ohnehin
  auftaucht &ndash; nur eben ohne Vorbereitung.</p>""",

    "s11_h": "Grenzen des Verfahrens",
    "s11": """<p>Vollstaendige Aufzaehlung dessen, was dieses Verfahren nicht kann. Sie
  gehoert in dieses Dokument, weil eine Methodenbeschreibung ohne
  Schwaechenliste als Verkaufsunterlage taugt und sonst zu nichts.</p>
  <ul>
    <li><b>Keine Ausfallvalidierung.</b> Die Gewichte und Stufengrenzen sind an
    Verteilungen und an Fachurteil verankert, nicht an beobachteten Ausfaellen.
    Es gibt bislang keine Ergebnisdaten, gegen die sich das Verfahren
    zurueckrechnen liesse.</li>
    <li><b>Datenstand der Vergleichswerte.</b> {vintage}. {caveat}</li>
    <li><b>Qualitative Faktoren fehlen weitgehend.</b> MaRisk BTO 1.4 Tz. 3
    verlangt qualitative Kriterien. Abgedeckt sind nur Aktualitaet der
    Rechnungslegung, externe Auskunft und Zahlungsverhalten. Managementqualitaet,
    Marktstellung, Kunden- und Lieferantenabhaengigkeit (EBA Tz. 132&ndash;136)
    gehen nicht in die Punktzahl ein; sie erscheinen als Befund.</li>
    <li><b>Keine ESG-Bewertung.</b> EBA Tz. 126&ndash;127 verlangt die Beurteilung
    von ESG-Risiken. Das Verfahren leistet das derzeit nicht.</li>
    <li><b>Keine Planungsrechnung.</b> EBA Tz. 129 erwartet Finanzprojektionen.
    Bewertet wird der letzte Abschluss zuzueglich Szenarien; eine fehlende
    integrierte Planung wird als Befund ausgewiesen, nicht ersetzt.</li>
    <li><b>Branchenunterscheidung nur im Vergleich.</b> Die Schwellenwerte gelten
    branchenuebergreifend; nur der Branchenvergleich im Bericht ist
    branchenspezifisch. Die Bundesbank waehlt ihre Modellkennzahlen dagegen je
    Branche neu aus.</li>
    <li><b>Ein Faktor kann ausfallen.</b> Dienstleister ohne Materialaufwand
    haben keine Kreditorenlaufzeit; das Gewicht wird dann umverteilt und die
    Abdeckung sinkt entsprechend.</li>
  </ul>""",

    "s12_h": "Aenderungen dieser Fassung",
    "s12": """<p>Ergebnis der Auswertung der EBA-Leitlinien, der MaRisk-Erlaeuterungen
  und der Bundesbank-Veroeffentlichungen:</p>
  <ul>
    <li><b>Drei Faktoren neu aufgenommen</b>, alle drei empirisch kalibriert:
    Gesamtkapitalrentabilitaet (EBA Anhang 3 Nr. 18), Anlagendeckungsgrad II und
    Kreditorenlaufzeit (beide Bundesbank-Verhaeltniszahlen). Der kalibrierte
    Gewichtsanteil steigt damit von 40% auf {cal_pct}%.</li>
    <li><b>Gewichte neu austariert</b>, damit die Summe 100% bleibt. Die
    Kapitaldienstfaehigkeit bleibt unveraendert bei 20% und damit das groesste
    Einzelgewicht &ndash; MaRisk BTO 1.2.1 Tz. 1.</li>
    <li><b>Szenariorechnung neu eingefuehrt</b> (Abschnitt 8). Das war die
    groesste Luecke gegenueber den Leitlinien: gefordert in Tz. 131 und
    156&ndash;158, bisher gar nicht abgebildet.</li>
    <li><b>Gesamtkapitalrentabilitaet in der Bundesbank-Definition</b>
    (Jahresergebnis zuzueglich Zinsaufwand) statt auf EBIT-Basis, damit die
    veroeffentlichten Quartile ohne Umrechnung gelten. Beide Varianten werden
    berechnet; bewertet wird die uebernommene.</li>
    <li><b>Zwei bisher ungenutzte Bundesbank-Reihen</b> in den Datensatz
    aufgenommen, den die Anwendung zur Laufzeit laedt.</li>
    <li><b>Ausschlusskriterien neu eingefuehrt</b> (Abschnitt 9). Auswertung der
    EBA-Benchmarking-Berichte, des Rating-Leitfadens der Banque de France und
    der Ausfalldefinition nach Artikel 178 CRR. Die Punktzahl allein kann
    K.-o.-Befunde nicht abbilden, weil ein gewichteter Mittelwert sie
    ausgleicht.</li>
    <li><b>Kontokorrent-Ueberziehung heraufgestuft.</b> Bisher eine blosse
    Warnung in der Plausibilitaetspruefung. Nach Artikel 178 CRR gilt ein
    Kontokorrent als ueberfaellig, sobald die eingeraeumte Linie ueberschritten
    ist &ndash; das ist ein Ausfallmerkmal, keine Auffaelligkeit.</li>
    <li><b>Szenariogroessen an der Aufsicht verankert.</b> Der Umsatzrueckgang
    von 10% war bisher gesetzt; er steht jetzt neben dem adversen Szenario des
    EU-weiten Stresstests 2025, das fuer Deutschland ein kumuliert 7,5%
    niedrigeres BIP unterstellt. Umgekehrt zeigt derselbe Vergleich, dass
    unser Zinsschock von 200 Basispunkten fast doppelt so hart ist wie die
    dort unterstellten rund 110 Basispunkte.</li>
  </ul>""",
    "s12_note": """
    <b>Dieses Dokument wird erzeugt, nicht gepflegt.</b> Saemtliche Faktoren,
    Gewichte, Stuetzstellen, Stufengrenzen, Szenarien und das Rechenbeispiel
    werden bei jedem Lauf aus den produktiven Modulen gelesen
    (<code>scripts/build_methodology_pdf.py</code>). Eine Abweichung zwischen
    diesem Papier und der Anwendung kann es nicht geben.""",
}

EN = {
    "s01_h": "Purpose and scope",
    "s01": """
  <p>The method produces an <b>indicative readiness band</b> (A to E). It
  describes how a credit application with this data behind it is likely to read
  to a typical lender &ndash; and which parts of that are changeable.</p>
  <div class="note stop">
    <b>What this explicitly is not.</b> Not a rating within the meaning of EU
    Regulation (EC) No 1060/2009, not a probability of default, not a credit
    decision and not an offer. No PD is estimated and none is published. Every
    credit decision is taken solely by the lender concerned, on its own
    standards.
  </div>
  <p>Three construction rules follow from that, and they are enforced in code,
  not merely asserted here:</p>
  <ul>
    <li><b>Traceability.</b> Every factor exposes its raw value, its
    breakpoints, its weight and the points it contributed. There is no figure
    that cannot be explained line by line.</li>
    <li><b>No machine learning.</b> Piecewise-linear interpolation over
    published thresholds, and nothing else.</li>
    <li><b>No rating vocabulary.</b> The words are &bdquo;band&ldquo; and
    &bdquo;indicative&ldquo;.</li>
  </ul>""",

    "s02_h": "Regulatory basis",
    "s02_intro": """<p>The choice of ratios does not come from a textbook. It comes from
  three sources that describe what lenders in the euro area are required to
  examine, and what they in fact examine:</p>""",
    "s02_src1_n": "EBA/GL/2020/06",
    "s02_src2_n": "MaRisk (BaFin)",
    "s02_src3_n": "Bundesbank credit assessment system (ICAS)",
    "s02_src1_t": "Guidelines on loan origination and monitoring, in force since 30 June 2021",
    "s02_src1": """Annex 3 section B names the metrics an institution should consider for
        lending to enterprises (section 3). Paragraphs 121 and 128 govern what
        belongs in the analysis of the financial position; paragraph 120 makes
        clear that collateral must <i>not</i> be a predominant criterion;
        paragraphs 131 and 156&ndash;158 require the scenario analysis.""",
    "s02_src2_t": "Circular 10/2021, Annex 1, BTO 1.2",
    "s02_src2": """BTO 1.2.1 para. 1 requires the risk factors to be analysed
        &bdquo;with particular regard to debt service capacity&ldquo; &ndash;
        which is why debt service coverage carries the largest single weight
        here. BTO 1.4 para. 3 requires qualitative criteria alongside
        quantitative ones.""",
    "s02_src3_t": "Description of the procedure, as at December 2023",
    "s02_src3": """The ratios with which a central bank assesses the creditworthiness of
        German companies from HGB accounts: EBITDA, adjusted total debt,
        liquidity, return on sales, debt repayment capability, adjusted equity
        ratio and days payable. Also the empirical distributions (section 6)
        and the method behind the scenario analysis (section 8).""",
    "s02_note": """
    <b>The most important finding from reading these sources: none of them sets
    threshold values.</b>
    EBA Annex 1 requires the institution to <i>define</i> &bdquo;acceptable ...
    ratio limits&ldquo;, but names no figures. MaRisk governs the process, not
    the level of any ratio. The supervisor therefore settles <i>which</i> ratios
    and <i>that</i> limits must exist &ndash; how high is a separate decision
    that has to be justified on its own. That is precisely why this document
    presents and evidences the choice of ratios (section 3) and the thresholds
    (sections 5 and 6) separately.""",

    "s03_h": "Mapped against EBA Annex 3",
    "s03": """<p>Annex 3 section B of the EBA guidelines lists twenty metrics for
  lending to enterprises. The guideline requires them to be considered
  &bdquo;to an extent that is applicable and appropriate to the specific credit
  proposal&ldquo; (para. 128 e). The table below states, for every one of them,
  what happens &ndash; including the cases where deliberately nothing does.</p>""",

    "s04_h": "Factors and weights",
    "s04_intro": """<p>The weights sum to 100%. Where a factor cannot be computed for
  want of data, the remaining weights are scaled up proportionally and the
  report states the coverage achieved. A thin file is not punished for being
  thin &ndash; it is labelled as thin.</p>""",
    "s04_note1": """
    <b>One exception to the redistribution.</b> Where EBITDA is zero or
    negative, dynamic gearing is arithmetically undefined. The factor is then
    not dropped but scored at zero: a company with no operating surplus cannot
    repay its debt out of the business, and dropping the factor would flatter
    exactly the case that matters.""",
    "s04_note2": """
    <b>Why collateral is not scored.</b> EBA para. 120: collateral is the
    second way out, not the primary source of repayment, and cannot by itself
    justify a lending decision. A collateral shortfall therefore appears as a
    finding and an action in the report, but not as a factor that moves
    points.""",

    "s05_h": "The thresholds in full",
    "s05": """<p>Between two breakpoints the score is interpolated linearly; beyond
  them it is clamped. Every point value can therefore be recomputed by hand
  &ndash; that is the reason for this construction, not a side effect of it.</p>""",

    "s06_h": "Where the thresholds come from",
    "s06_h3a": "Calibrated factors",
    "s06_p1": """<p>Six of the {n_factors} factors &ndash; together {cal_pct}% of the
  weight &ndash; are tied to the <b>quartile values of the Deutsche Bundesbank's
  annual accounts statistics</b> (Verhaeltniszahlen): all sectors, the
  EUR 2&ndash;10m and 10&ndash;50m revenue size classes averaged, latest
  reporting year. Data as at: {vintage}.</p>
  <p>The anchoring is:</p>""",
    "s06_kv1": "25th percentile", "s06_kv1s": "= 58 points (lower edge of band C)",
    "s06_kv2": "Median", "s06_kv2s": "= 70 points (middle of band B)",
    "s06_kv3": "75th percentile", "s06_kv3s": "= 82 points (band A)",
    "s06_p2": """<p>The reasoning is one step long: the ECB's SAFE survey puts roughly
  14% of applicants in significant financing difficulty. A company at the median
  of its size class is therefore not a problem case but financeable &ndash; band
  B. Mapping percentiles directly would put the median firm at 50 points and so
  assert that half of the German Mittelstand is a borderline case. That would be
  empirically wrong.</p>""",
    "s06_note1": """
    <b>For &bdquo;lower is better&ldquo; ratios the anchors invert.</b> For days
    payable the 25th percentile is the good end, so the mapping there is 25th
    percentile = 82, median = 70, 75th percentile = 58. That curve is also the
    only one capped below 100: paying suppliers quickly is not evidence of
    creditworthiness, only the absence of a warning sign.""",
    "s06_p3": """<p><b>The ends beyond the quartiles.</b> The statistics give three points,
  not a distribution. The ends of each curve are therefore not extrapolated but
  drawn to economically meaningful limits &ndash; zero equity, a negative
  margin, fixed-asset coverage below 100%.</p>""",
    "s06_h3b": "Factors that are not calibrated",
    "s06_p4": """<p>For the remaining factors the publication carries no comparable
  series. Their curves are reasoned convention and are labelled as such: debt
  service coverage, dynamic gearing, interest coverage, overdraft utilisation,
  currency of the monthly accounts, the Creditreform index and payment
  behaviour.</p>""",
    "s06_note2": """
    <b>One translation deliberately not made.</b> The Bundesbank publishes
    &bdquo;cash flow as a percentage of net borrowed funds&ldquo;. That is
    <i>not</i> our dynamic gearing: a different numerator (cash flow after
    interest and tax, rather than EBITDA) and a far wider denominator (all
    liabilities, rather than financial debt alone). Converting one into the
    other would be a guess dressed up as a calibration. The factor therefore
    stays convention &ndash; and is the first candidate for revision once the
    outcome log holds enough real placements.""",

    "s07_h": "From points to bands",
    "s07_note": """
    <b>The band thresholds themselves are not empirically derived.</b> They are
    set so that the median firm lands in band B and the lower quartile in band C
    &ndash; that is, from the same SAFE reasoning as the factor anchors, not
    from observed decline rates. Anyone attacking this mapping is attacking the
    weakest point of the method, and rightly so. It changes once enough
    documented credit decisions exist.""",

    "s08_h": "Scenario analysis",
    "s08_p1": """<p>A point-in-time ratio from last year's accounts answers the wrong
  question. The lender does not want to know how the company looked on 31
  December, but whether it still carries the debt service when things go
  against it. Both supervisory sources require this explicitly (EBA paras. 131
  and 156&ndash;158, MaRisk BTO 1.2.1 para. 1).</p>""",
    "s08_h3": "How the shock is worked through the accounts",
    "s08_p2": """<p>The mechanism follows the Deutsche Bundesbank's own published approach
  to stressing a financial statement inside its credit assessment system
  (Technical Paper 02/2023, section 5.2). There a cost line is stressed; the
  plumbing is the same whatever the shock is:</p>
  <ul>
    <li>determine the additional cost, or the contribution lost;</li>
    <li>fund it from cash first, then through short-term bank borrowing;</li>
    <li>raise the interest charge on that new borrowing at the existing average
      rate, because the interest burden is itself rating-relevant;</li>
    <li>reduce the tax charge at the company's own effective rate (never below
      zero);</li>
    <li>carry the reduced result through to equity;</li>
    <li>recompute every ratio on the stressed accounts.</li>
  </ul>""",
    "s08_note1": """
    <b>The rate shock hits the loan agreements, not just the P&amp;L.</b>
    Paragraph 158 k speaks of an increase &bdquo;on all credit facilities of the
    borrower&ldquo;. Had only the interest line been raised, debt service
    &ndash; and with it debt service coverage, the decisive ratio &ndash; would
    have stayed unchanged. The rate on each individual facility is therefore
    raised.""",
    "s08_note2": """
    <b>What the scenario analysis is not.</b> Not a forecast and not a statement
    of probability. It says: on these stated assumptions the band moves from X
    to Y. The assumptions are printed next to the result so that the owner can
    disagree with them &ndash; they know their own variable cost share better
    than we do.""",

    "s09_h": "Knock-out criteria",
    "s09_p1": """<p>A weighted score answers the question of how a file reads overall. It
  cannot answer whether there is something in it that ends the conversation
  regardless of the total &ndash; a weighted average by construction lets a
  strong factor offset a fatal one. Those are two different questions and they
  need two different methods.</p>""",
    "s09_p2": """<p>These {n_ko} criteria are therefore checked separately and reported
  separately, ahead of the ratios. None of the thresholds is ours:</p>""",
    "s09_note1": """
    <b>This check is not a legal assessment.</b> Whether a finding gives rise to
    an obligation &ndash; under Sec. 49(3) GmbHG or Sec. 15a InsO, say &ndash;
    turns on a going-concern prognosis that this method cannot make and does not
    claim to make. The report names the condition and refers the judgement to
    the tax adviser or a lawyer.""",
    "s09_note2": """
    <b>Why a clean result is a statement in its own right.</b> &bdquo;None of
    these criteria applies&ldquo; is not the same as a good score. It means the
    conversation about terms can be had at all &ndash; and that is exactly the
    information a business owner needs before applying.""",

    "s10_h": "A worked example",
    "s10_p1": """<p>A complete run on the fictional sample case Mueller
  Praezisionstechnik GmbH. Every value is produced by the running system, not
  transcribed.</p>""",
    "s10_p2": """<p>The scenario analysis for the same case:</p>""",
    "s10_p3": """<p>How to read it: the business is financeable at the balance sheet date
  (band B), but does not survive a 10% fall in revenue, because debt service
  coverage then drops below 1.0. That is information which surfaces in the
  credit conversation anyway &ndash; only without preparation.</p>""",

    "s11_h": "Limitations of the method",
    "s11": """<p>A complete list of what this method cannot do. It belongs in this
  document, because a description of a method without a list of its weaknesses
  serves as a sales brochure and as nothing else.</p>
  <ul>
    <li><b>No default validation.</b> The weights and band thresholds are
    anchored in distributions and in professional judgement, not in observed
    defaults. There is as yet no outcome data against which the method could be
    back-tested.</li>
    <li><b>Vintage of the benchmark data.</b> {vintage}. {caveat}</li>
    <li><b>Qualitative factors are largely absent.</b> MaRisk BTO 1.4 para. 3
    requires qualitative criteria. Only the currency of the accounts, the
    external credit report and payment behaviour are covered. Management
    quality, market position, customer and supplier concentration (EBA paras.
    132&ndash;136) do not enter the score; they appear as findings.</li>
    <li><b>No ESG assessment.</b> EBA paras. 126&ndash;127 require ESG risks to
    be assessed. The method does not currently do this.</li>
    <li><b>No forecast.</b> EBA para. 129 expects financial projections. What is
    assessed is the most recent accounts plus scenarios; a missing integrated
    forecast is reported as a finding, not substituted for.</li>
    <li><b>Sector differentiation only in the comparison.</b> The thresholds
    apply across sectors; only the sector comparison in the report is
    sector-specific. The Bundesbank, by contrast, reselects its model ratios for
    each sector.</li>
    <li><b>One factor can drop out.</b> Service businesses with no materials
    expense have no days-payable figure; its weight is then redistributed and
    coverage falls accordingly.</li>
  </ul>""",

    "s12_h": "Changes in this version",
    "s12": """<p>The result of reading the EBA guidelines, the MaRisk explanatory notes
  and the Bundesbank publications:</p>
  <ul>
    <li><b>Three factors added</b>, all three empirically calibrated: return on
    assets (EBA Annex 3 no. 18), fixed-asset coverage II and days payable (both
    Bundesbank ratios). The calibrated share of the weight rises from 40% to
    {cal_pct}%.</li>
    <li><b>Weights rebalanced</b> so that the total stays at 100%. Debt service
    coverage stays at 20% and remains the largest single weight &ndash; MaRisk
    BTO 1.2.1 para. 1.</li>
    <li><b>Scenario analysis introduced</b> (section 8). This was the largest
    gap against the guidelines: required by paras. 131 and 156&ndash;158, and
    previously not implemented at all.</li>
    <li><b>Return on assets on the Bundesbank definition</b> (net result plus
    interest) rather than on an EBIT basis, so that the published quartiles
    apply without conversion. Both variants are computed; the adopted one is
    scored.</li>
    <li><b>Two previously unused Bundesbank series</b> added to the dataset the
    application loads at runtime.</li>
    <li><b>Knock-out criteria introduced</b> (section 9). From reading the EBA
    benchmarking reports, the Banque de France rating guide and the definition
    of default in Article 178 CRR. The score alone cannot express a knock-out,
    because a weighted average offsets it.</li>
    <li><b>Overdraft breach upgraded.</b> Previously a mere warning in the
    plausibility check. Under Article 178 CRR an overdraft counts as past due
    once the advised limit is exceeded &ndash; that is an indicator of default,
    not an anomaly.</li>
    <li><b>Scenario sizes anchored to the supervisor.</b> The 10% fall in
    revenue was previously simply set; it now stands next to the adverse
    scenario of the 2025 EU-wide stress test, which assumes German GDP 7.5%
    lower on a cumulative basis. The same comparison shows, conversely, that our
    200 basis point rate shock is nearly twice the roughly 110 basis points
    assumed there.</li>
  </ul>""",
    "s12_note": """
    <b>This document is generated, not maintained.</b> Every factor, weight,
    breakpoint, band threshold, scenario and the worked example are read from
    the production modules on each run
    (<code>scripts/build_methodology_pdf.py</code>). A divergence between this
    paper and the application is not possible.""",
}

SECTIONS = {"de": DE, "en": EN}
