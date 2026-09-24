/* Credit Readiness -- the company workspace.
 *
 * One place for everything a company does here: a sidebar that opens when the
 * pointer comes near it, a dashboard that says where the case stands and what
 * is next, and one page per job (company data, financing need, documents,
 * figures, result, plan, history). Loaded after app.js and uses its helpers.
 */
"use strict";

// ------------------------------------------------------------------ icons

const ICON_PATHS = {
  home: ["M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"],
  building: ["M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16", "M16 9h2a2 2 0 0 1 2 2v10", "M2 21h20", "M8 7h4M8 11h4M8 15h4"],
  euro: ["M17.5 6.5A7 7 0 1 0 17.5 17.5", "M4 10h9M4 14h9"],
  file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5", "M9 13h6M9 17h4"],
  check: ["M9 11l3 3 8-8", "M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h9"],
  chart: ["M4 20V10M10 20V4M16 20v-7M22 20H2"],
  card: ["M3 6h18a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z", "M2 10h20", "M6 15h4"],
  clock: ["M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z", "M12 7v5l3 2"],
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
  upload: ["M12 16V4", "M7 9l5-5 5 5", "M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"],
  pen: ["M4 20h4L19 9l-4-4L4 16z", "M13 7l4 4"],
  plus: ["M12 5v14M5 12h14"],
  menu: ["M3 6h18M3 12h18M3 18h18"],
  users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M22 21v-2a4 4 0 0 0-3-3.9", "M16 3.1a4 4 0 0 1 0 7.8"],
  arrow: ["M5 12h14", "M13 6l6 6-6 6"],
};

function icon(name, size) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size || 20);
  svg.setAttribute("height", size || 20);
  svg.setAttribute("class", "svgi");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICON_PATHS[name] || []) {
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

// ------------------------------------------------------------------ state

const WS_NAV = [
  { id: "overview", icon: "home", de: "Übersicht", en: "Overview" },
  { id: "company", icon: "building", de: "Unternehmen", en: "Company" },
  { id: "financing", icon: "euro", de: "Finanzierung", en: "Financing" },
  { id: "documents", icon: "file", de: "Unterlagen", en: "Documents" },
  { id: "figures", icon: "check", de: "Zahlen prüfen", en: "Check figures" },
  { id: "result", icon: "chart", de: "Ergebnis", en: "Result" },
  { id: "plan", icon: "card", de: "Tarif", en: "Plan" },
  { id: "history", icon: "clock", de: "Verlauf", en: "History" },
];

const WS_SECTIONS = {
  company: ["unternehmen", "verhalten", "einwilligung"],
  financing: ["vorhaben", "finanzierungen", "gesellschafter"],
};

const GRID_TYPES = new Set(["jahresabschluesse", "kapitalflussrechnung", "susa_aktuell", "susa_vorjahr"]);

const DOC_GROUPS = [
  { de: "Unternehmen", en: "Company", ids: ["handelsregisterauszug", "gesellschafterliste"] },
  { de: "Finanzierungen und Sicherheiten", en: "Loans and collateral", ids: ["darlehensvertraege", "sicherheitenaufstellung", "rangruecktrittserklaerung"] },
  { de: "Bank", en: "Bank", ids: ["kontoumsaetze"] },
  { de: "Steuern und Planung", en: "Tax and planning", ids: ["steuerkonto", "stundungsvereinbarung", "planrechnung"] },
  { de: "Holen wir für Sie ein", en: "We obtain these for you", ids: ["creditreform_auskunft"] },
];

/** The one result the company may see: the released report, else the free check. */
function wsResult(ov) {
  if (ov.report_released && ov.latest_summary) return { kind: "report", r: ov.latest_summary };
  if (ov.quick_check) return { kind: "quick", r: ov.quick_check };
  return null;
}

function wsPlan(ov) {
  if (hasOrder(ov, "advisor")) return "advisor";
  if (hasOrder(ov, "report")) return "report";
  return "quick";
}

const planName = (key) => t(S.meta.products[key].de.replace("Vollstaendiger", "Vollständiger"), S.meta.products[key].en);

function sectionGap(ov, ids) {
  const secs = ov.sections.unternehmen.filter((s) => ids.includes(s.id));
  const missing = secs.reduce((a, s) => a + (s.required - s.answered_required), 0);
  const done = secs.every((s) => s.complete);
  return { missing, done };
}

function docProgress(ov) {
  const own = ov.documents.filter((d) => d.required && d.source !== "berater");
  return { done: own.filter((d) => d.satisfied).length, total: own.length };
}

/** Everything still to do, in the order that gets the company to a result fastest. */
function wsTodos(ov) {
  const cid = ov.meta.case_id;
  const res = wsResult(ov);
  const grid = ov.doc_matrix;
  const cell = (row) => grid.rows.find((r) => r.id === row).cells[0];
  const latestIn = ["ok", "explained"].includes(cell("bilanz").state) && ["ok", "explained"].includes(cell("guv").state);
  const company = sectionGap(ov, WS_SECTIONS.company);
  const fin = sectionGap(ov, WS_SECTIONS.financing);
  const stb = ((ov.members || {}).steuerberater || []).length > 0;
  const outstanding = [...ov.outstanding_documents.unternehmen, ...ov.outstanding_documents.steuerberater];
  const items = [
    { done: company.done, page: "company", title: t("Unternehmensdaten ergänzen", "Complete company details"),
      sub: company.missing ? t(`${company.missing} Pflichtangaben offen`, `${company.missing} required answers open`) : t("Rechtsform, Branche, Reporting", "Legal form, sector, reporting") },
    { done: fin.done, page: "financing", title: t("Finanzierungswunsch beschreiben", "Describe your financing need"),
      sub: fin.missing ? t(`${fin.missing} Pflichtangaben offen`, `${fin.missing} required answers open`) : t("Betrag, Zweck, bestehende Kredite", "Amount, purpose, existing loans") },
    { done: latestIn, page: "documents", title: t(`Jahresabschluss ${grid.columns[0]} hochladen`, `Upload the ${grid.columns[0]} annual accounts`),
      sub: t("Bilanz und GuV – meist ein PDF", "Balance sheet and P&L – usually one PDF") },
  ];
  if (!ov.report_released) {
    items.push({ done: !!ov.figures_confirmed, page: "figures", title: t("Zahlen prüfen und bestätigen", "Check and confirm the figures"),
      sub: t("Wir lesen sie aus, Sie bestätigen", "We read them, you confirm") });
  }
  items.push({ done: !!res, page: "result", title: t("Kostenlosen Schnell-Check berechnen", "Calculate your free quick check"),
    sub: t("Readiness-Band, Kennzahlen, größte Hebel", "Readiness band, ratios, biggest levers") });
  items.push({ done: stb, page: "documents", title: t("Steuerberatung einladen", "Invite your tax advisor"),
    sub: t("Sie lädt Saldenlisten und BWA direkt hoch", "They upload trial balances and BWA directly") });
  items.push({ done: outstanding.length === 0, page: "documents", title: t("Restliche Unterlagen", "Remaining documents"),
    sub: outstanding.length ? t(`${outstanding.length} offen`, `${outstanding.length} open`) : t("Alles da", "All in") });
  if (hasOrder(ov, "report")) {
    items.push({ done: !!ov.submitted_at, page: "plan", title: t("An Ihren Berater übermitteln", "Send to your advisor"),
      sub: t("Für den vollständigen Bericht", "For the full report") });
  }
  return items.map((x) => Object.assign(x, { href: `case/${cid}/${x.page}` }));
}

// ------------------------------------------------------------------ shell

function wsShell(ov, page, content, headAction) {
  const cid = ov.meta.case_id;
  const res = wsResult(ov);
  const todos = wsTodos(ov).filter((x) => !x.done).length;
  const dp = docProgress(ov);
  const raw = ov.raw_answers.unternehmen || {};
  const badges = {
    overview: todos ? el("span", { class: "nb warn", text: String(todos) }) : null,
    documents: el("span", { class: "nb" + (dp.done === dp.total ? " ok" : ""), text: `${dp.done}/${dp.total}` }),
    figures: ov.figures_confirmed ? el("span", { class: "nb ok", text: "✓" }) : null,
    result: res ? el("span", { class: `nb band-${res.r.band}`, text: res.r.band }) : null,
    plan: el("span", { class: "nb plain", text: wsPlan(ov) === "quick" ? t("Free", "Free") : wsPlan(ov) === "report" ? "390 €" : "Pro" }),
  };
  const logout = el("button", { class: "side-item", type: "button" }, icon("logout"), el("span", { class: "lbl", text: t("Abmelden", "Log out") }));
  logout.addEventListener("click", () => guarded(logout, async () => {
    await api("POST", "/api/auth/logout");
    S.me = null; S.ov = null; S.ovCid = null;
    go("login");
  }));
  const side = el("aside", { class: "side", "aria-label": t("Navigation", "Navigation") },
    el("a", { class: "side-brand", href: `#case/${cid}/overview` }, logoMark(), el("span", { class: "lbl" }, "Credit Readiness")),
    el("div", { class: "side-co" },
      el("div", { class: "co-av", text: initials(ov.meta.company_name) }),
      el("div", { class: "lbl" },
        el("b", { text: ov.meta.company_name }),
        el("span", { text: [raw.branche && optLabel(sectorQ(), raw.branche), cid].filter(Boolean).join(" · ") }))),
    el("nav", { class: "side-nav" }, WS_NAV.map((n) => el("a", {
      class: "side-item" + (n.id === page ? " active" : ""), href: `#case/${cid}/${n.id}`, title: t(n.de, n.en),
    }, icon(n.icon), el("span", { class: "lbl", text: t(n.de, n.en) }), badges[n.id] || null))),
    el("div", { class: "side-foot" },
      el("div", { class: "side-me" }, el("div", { class: "avatar", text: initials(S.me.name) }),
        el("div", { class: "lbl" }, el("b", { text: S.me.name }), el("span", { text: S.me.email }))),
      el("div", { class: "lbl side-lang" }, langToggle(), el("a", { class: "small", href: "/", text: t("Website", "Website") })),
      logout));
  const menuBtn = el("button", { class: "ws-menu", type: "button", "aria-label": t("Menü", "Menu"), onclick: () => side.classList.toggle("open") }, icon("menu"));
  const title = WS_NAV.find((n) => n.id === page);
  const head = el("header", { class: "ws-head" },
    menuBtn,
    el("div", {}, el("div", { class: "crumbs", text: `${ov.meta.company_name} · ${cid}` }), el("h1", { text: t(title.de, title.en) })),
    headAction || null);
  const main = el("main", { class: "ws-main" },
    S.meta.demo ? el("div", { class: "demo-ribbon", text: t("Demo-Umgebung – alle Unternehmen und Zahlen sind fiktiv.", "Demo environment – all companies and figures are fictional.") }) : null,
    el("div", { class: "ws-body" }, head, content, accountFooter()));
  return el("div", { class: "ws" }, side, main);
}

function sectorQ() {
  return S.meta.questionnaires.unternehmen.sections.flatMap((s) => s.questions).find((q) => q.id === "branche");
}

// ------------------------------------------------------------------ router

function renderSmeCase(ov, part) {
  const page = WS_NAV.some((n) => n.id === part) ? part : "overview";
  const pages = {
    overview: wsOverview, company: (o) => wsForm(o, "company"), financing: (o) => wsForm(o, "financing"),
    documents: wsDocuments, figures: wsFigures, result: wsResultPage, plan: wsPlanPage, history: wsHistory,
  };
  const [content, action] = pages[page](ov);
  const root = document.getElementById("root");
  const y = S.wsPage === page ? window.scrollY : 0;
  S.wsPage = page;
  root.className = "";
  root.replaceChildren(wsShell(ov, page, content, action));
  window.scrollTo(0, y);
}

const rerender = (page) => () => renderSmeCase(S.ov, page);

// ------------------------------------------------------------------ overview

function wsOverview(ov) {
  const todos = wsTodos(ov);
  const next = todos.find((x) => !x.done);
  const action = next ? el("a", { class: "btn btn-primary", href: "#" + next.href }, next.title, " ", icon("arrow", 16)) : null;
  const res = wsResult(ov);
  const content = el("div", { class: "dash" },
    el("section", { class: "card span2" }, scoreBlock(ov, res)),
    el("section", { class: "card" }, todoBlock(todos)),
    el("section", { class: "card span2" }, ratiosBlock(res)),
    el("section", { class: "card" }, planBlock(ov)),
    el("section", { class: "card" }, companyBlock(ov)),
    el("section", { class: "card" }, docsBlock(ov)),
    el("section", { class: "card" }, activityBlock(ov, 6)));
  return [el("div", {},
    el("p", { class: "ws-hello", text: t(`Guten Tag, ${S.me.name.split(" ")[0]}. ${statusLine(ov)}`, `Hello ${S.me.name.split(" ")[0]}. ${statusLine(ov)}`) }),
    content), action];
}

function statusLine(ov) {
  if (ov.report_released) return t("Ihr vollständiger Bericht liegt vor.", "Your full report is ready.");
  if (ov.submitted_at) return t("Ihr Berater arbeitet an Ihrem Bericht.", "Your advisor is working on your report.");
  if (ov.quick_check) return t("Ihr Schnell-Check ist fertig.", "Your quick check is ready.");
  const open = wsTodos(ov).filter((x) => !x.done).length;
  return t(`Noch ${open} Schritte bis zum Ergebnis.`, `${open} steps to go.`);
}

const BAND_STATUS = { A: "good", B: "good", C: "warn", D: "bad", E: "bad" };

function gauge(res) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 120 120");
  svg.setAttribute("class", "gauge " + (res ? BAND_STATUS[res.band] : "none"));
  const mk = (cls, dash) => {
    const c = document.createElementNS(ns, "circle");
    for (const [k, v] of Object.entries({ cx: 60, cy: 60, r: 50, class: cls })) c.setAttribute(k, v);
    if (dash !== undefined) {
      const len = 2 * Math.PI * 50;
      c.setAttribute("stroke-dasharray", `${len * dash} ${len}`);
    }
    return c;
  };
  svg.append(mk("track"));
  if (res && res.score != null) svg.append(mk("fill", Math.max(0.02, Math.min(1, res.score / 100))));
  const txt = document.createElementNS(ns, "text");
  for (const [k, v] of Object.entries({ x: 60, y: 60, "text-anchor": "middle", "dominant-baseline": "central", class: "g-band" })) txt.setAttribute(k, v);
  txt.textContent = res ? res.band : "?";
  svg.append(txt);
  return svg;
}

function scoreBlock(ov, res) {
  const cid = ov.meta.case_id;
  if (!res) {
    const steps = wsTodos(ov).filter((x) => ["company", "financing", "documents", "figures", "result"].includes(x.page)).slice(0, 5);
    return el("div", { class: "score" },
      gauge(null),
      el("div", { class: "score-txt" },
        el("div", { class: "eyebrow", text: t("Ihr Readiness-Band", "Your readiness band") }),
        el("h2", { text: t("Noch kein Ergebnis", "No result yet") }),
        el("p", { class: "muted", text: t("Mit dem letzten Jahresabschluss und ein paar Angaben berechnen wir kostenlos, wie eine Bank Ihre Zahlen liest.", "With your latest annual accounts and a few answers we calculate, free of charge, how a bank reads your numbers.") }),
        el("ol", { class: "mini-steps" }, steps.map((s) => el("li", { class: s.done ? "done" : "" }, el("a", { href: "#" + s.href, text: s.title }))))));
  }
  const r = res.r;
  const after = res.kind === "report" && r.band_after_remediation && r.band_after_remediation !== r.band;
  return el("div", { class: "score" },
    gauge(r),
    el("div", { class: "score-txt" },
      el("div", { class: "eyebrow", text: res.kind === "report" ? t("Vollständiger Bericht · geprüft", "Full report · reviewed") : t("Schnell-Check · vorläufig", "Quick check · preliminary") }),
      el("div", { class: "score-num" }, el("span", { class: "big", text: nf(r.score, 1) }), el("span", { class: "of", text: " / 100" })),
      el("p", { class: "score-band", text: bandText(r.band) }),
      r.score_generic != null && r.scoring_basis && !r.scoring_basis.startsWith("Alle") ? el("p", { class: "small muted", text: t(
        `Gemessen an Ihrer Branche. Ohne Branchenbezug: ${nf(r.score_generic, 1)} (Band ${r.band_generic}).`,
        `Measured against your sector. Without the sector view: ${nf(r.score_generic, 1)} (band ${r.band_generic}).`) }) : null,
      after ? el("div", { class: "after" }, t("Nach den Maßnahmen: ", "After the measures: "), el("span", { class: `band-chip band-${r.band_after_remediation}`, text: r.band_after_remediation }), ` ${nf(r.score_after_remediation, 1)} / 100`) : null,
      el("a", { class: "link-arrow", href: `#case/${cid}/result` }, t("Details ansehen", "See details"), icon("arrow", 14))),
    leversBlock(r.improvements));
}

/** The three biggest levers: what reaching the sector-typical level would add. */
function leversBlock(items) {
  if (!items || !items.length) return null;
  return el("div", { class: "levers" },
    el("div", { class: "eyebrow", text: t("Größte Hebel", "Biggest levers") }),
    items.slice(0, 3).map((i) => el("div", { class: "lever" },
      el("span", { class: "gain", text: `+${nf(i.points_gain, 1)}` }),
      el("div", {}, el("b", { text: i.factor }),
        el("small", { text: `${i.current} → ${i.target}` + (i.euro_gap ? ` · ${eur(Math.round(i.euro_gap / 1000) * 1000)}` : "") })))));
}

function todoBlock(todos) {
  const open = todos.filter((x) => !x.done).length;
  return el("div", {},
    el("div", { class: "card-head" }, el("h3", { text: t("Ihre nächsten Schritte", "Your next steps") }),
      el("span", { class: "muted small", text: t(`${todos.length - open} von ${todos.length} erledigt`, `${todos.length - open} of ${todos.length} done`) })),
    el("div", { class: "meter" }, el("span", { style: `width:${Math.round((todos.length - open) / todos.length * 100)}%` })),
    el("ul", { class: "todo" }, todos.map((x) => el("li", { class: x.done ? "done" : "" },
      el("a", { href: "#" + x.href },
        el("span", { class: "tick", text: x.done ? "✓" : "" }),
        el("span", {}, el("b", { text: x.title }), el("small", { text: x.sub })))))));
}

const METRIC_EN = {
  "Eigenkapitalquote": "Equity ratio", "EBIT-Marge": "EBIT margin", "Liquiditaet 2. Grades": "Quick ratio",
  "Anlagendeckungsgrad II": "Fixed-asset coverage", "Debitorenlaufzeit": "Days sales outstanding",
};
const METRIC_DE = { "Liquiditaet 2. Grades": "Liquidität 2. Grades" };
const metricLabel = (m) => (lang() === "en" ? METRIC_EN[m] || m : METRIC_DE[m] || m);
// Worded as better/weaker, not above/below: for days sales outstanding a
// higher number is the weaker one.
const VERDICT = {
  "ueber Branchenmedian": ["besser als die Branche", "better than sector", "good"],
  "im Rahmen": ["im Branchenrahmen", "in line with sector", "neutral"],
  "unter Branchenmedian": ["schwächer als die Branche", "weaker than sector", "warn"],
};

/** Company value against the sector's middle half (q25-q75) and median. */
function rangeBar(b) {
  const days = b.metric === "Debitorenlaufzeit";
  const fmt = (v) => (v == null ? "–" : days ? `${nf(v)} ${t("Tage", "days")}` : pct(v));
  const v = VERDICT[b.verdict] || [b.verdict, b.verdict, "neutral"];
  if (b.value == null || b.q25 == null) {
    return el("div", { class: "rb" }, el("div", { class: "rb-top" }, el("span", { class: "rb-l", text: metricLabel(b.metric) }), el("b", { text: fmt(b.value) })),
      el("div", { class: "small muted", text: t("keine Branchendaten", "no sector data") }));
  }
  const span = Math.max(b.q75 - b.q25, Math.abs(b.median) * 0.2, 1e-6);
  const lo = Math.min(b.value, b.q25) - span * 0.35;
  const hi = Math.max(b.value, b.q75) + span * 0.35;
  const x = (val) => `${Math.max(0, Math.min(100, (val - lo) / (hi - lo) * 100))}%`;
  const tip = t(`Unternehmen ${fmt(b.value)} · Branchenmedian ${fmt(b.median)} · mittlere Hälfte ${fmt(b.q25)}–${fmt(b.q75)}`,
    `Company ${fmt(b.value)} · sector median ${fmt(b.median)} · middle half ${fmt(b.q25)}–${fmt(b.q75)}`);
  return el("div", { class: "rb", title: tip },
    el("div", { class: "rb-top" },
      el("span", { class: "rb-l", text: metricLabel(b.metric) }),
      el("span", {}, el("b", { text: fmt(b.value) }), el("span", { class: `rb-v ${v[2]}`, text: " · " + t(v[0], v[1]) }))),
    el("div", { class: "rb-track" },
      el("span", { class: "rb-iqr", style: `left:${x(b.q25)};width:calc(${x(b.q75)} - ${x(b.q25)})` }),
      el("span", { class: "rb-med", style: `left:${x(b.median)}` }),
      el("span", { class: `rb-dot ${v[2]}`, style: `left:${x(b.value)}` })),
    el("div", { class: "rb-scale" }, el("span", { text: t(`Median ${fmt(b.median)}`, `median ${fmt(b.median)}`) })));
}

function ratiosBlock(res) {
  if (!res) {
    return el("div", {}, el("div", { class: "card-head" }, el("h3", { text: t("Kennzahlen im Branchenvergleich", "Ratios against your sector") })),
      el("div", { class: "empty" }, el("p", { class: "muted", text: t("Erscheinen hier, sobald Ihr Schnell-Check berechnet ist: Eigenkapital, Rendite, Liquidität – jeweils gegen die Bundesbank-Werte Ihrer Branche.", "Appear here once your quick check is calculated: equity, returns, liquidity – each against the Bundesbank figures for your sector.") })));
  }
  const k = res.r.key_ratios || {};
  return el("div", {},
    el("div", { class: "card-head" }, el("h3", { text: t("Kennzahlen im Branchenvergleich", "Ratios against your sector") }),
      el("span", { class: "legend" }, el("i", { class: "lg-iqr" }), t("mittlere Hälfte der Branche", "middle half of sector"), el("i", { class: "lg-med" }), t("Median", "median"))),
    el("div", { class: "tiles" },
      tile(t("Kapitaldienstfähigkeit", "Debt service cover"), xf(k.kapitaldienstfaehigkeit_inkl_neu), t("inkl. Wunschkredit · Banken erwarten ≥ 1,2x", "incl. new loan · banks expect ≥ 1.2x")),
      tile(t("Verschuldung / EBITDA", "Net debt / EBITDA"), xf(k.dynamischer_verschuldungsgrad), t("Jahre bis schuldenfrei", "years to repay")),
      tile(t("Umsatz", "Revenue"), eur(k.umsatz), `EBITDA ${eur(k.ebitda)}`)),
    el("div", { class: "rbs" }, (res.r.benchmark || []).map(rangeBar)));
}

function tile(label, value, sub) {
  return el("div", { class: "tile" }, el("div", { class: "l", text: label }), el("div", { class: "v", text: value }), el("div", { class: "s", text: sub }));
}

function planBlock(ov) {
  const cid = ov.meta.case_id;
  const cur = wsPlan(ov);
  const nextKey = cur === "quick" ? "report" : cur === "report" ? "advisor" : null;
  return el("div", { class: "plan-card" },
    el("div", { class: "card-head" }, el("h3", { text: t("Ihr Tarif", "Your plan") })),
    el("div", { class: "plan-now" }, el("b", { text: planName(cur) }), el("span", { class: "pill ok", text: cur === "quick" ? t("kostenlos", "free") : t("gebucht", "booked") })),
    el("ul", { class: "feature-list small" }, PLAN_FEATURES[cur]().slice(0, 3).map((f) => el("li", { text: f }))),
    nextKey ? el("div", { class: "upsell" },
      el("div", { class: "small muted", text: t("Nächste Stufe", "Next level") }),
      el("b", { text: `${planName(nextKey)} · ${price(nextKey)}` }),
      el("a", { class: "btn btn-dark btn-sm", href: `#case/${cid}/plan`, text: t("Tarife vergleichen", "Compare plans") })) : null);
}

function companyBlock(ov) {
  const cid = ov.meta.case_id;
  const a = ov.raw_answers.unternehmen || {};
  const rows = [
    [t("Rechtsform", "Legal form"), a.rechtsform],
    [t("Branche", "Sector"), a.branche ? optLabel(sectorQ(), a.branche) + (a.nace_code ? ` (${a.nace_code})` : "") : null],
    [t("Mitarbeiter", "Employees"), a.mitarbeiter],
    [t("Gegründet", "Founded"), a.gruendungsjahr],
    [t("Sitz", "Registered office"), a.sitz],
    [t("Wunschkredit", "Requested loan"), a.betrag ? `${eur(Number(String(a.betrag).replace(/\./g, "").replace(",", ".")))}${a.zweck ? " · " + a.zweck : ""}${a.laufzeit_jahre ? " · " + a.laufzeit_jahre + t(" J.", " yrs") : ""}` : null],
  ];
  return el("div", {},
    el("div", { class: "card-head" }, el("h3", { text: t("Unternehmen", "Company") }), el("a", { class: "small", href: `#case/${cid}/company`, text: t("Bearbeiten", "Edit") })),
    el("dl", { class: "facts" }, rows.map(([k, v]) => [el("dt", { text: k }), el("dd", { class: v ? "" : "muted", text: v || t("fehlt", "missing") })])));
}

function docsBlock(ov) {
  const cid = ov.meta.case_id;
  const grid = ov.doc_matrix;
  const dp = docProgress(ov);
  return el("div", {},
    el("div", { class: "card-head" }, el("h3", { text: t("Unterlagen", "Documents") }), el("span", { class: "muted small", text: t(`${dp.done} von ${dp.total} Pflicht`, `${dp.done} of ${dp.total} required`) })),
    el("div", { class: "meter" }, el("span", { style: `width:${dp.total ? Math.round(dp.done / dp.total * 100) : 100}%` })),
    el("table", { class: "mini-grid" },
      el("thead", {}, el("tr", {}, el("th"), grid.columns.map((y) => el("th", { text: String(y) })))),
      el("tbody", {}, grid.rows.map((r) => el("tr", {},
        el("th", { text: lang() === "en" ? r.title_en : r.title_de }),
        r.cells.map((c) => el("td", {}, el("span", { class: "dot " + c.state, title: CELL_STATE[c.state] ? t(...CELL_STATE[c.state]) : c.state }))))))),
    el("a", { class: "link-arrow", href: `#case/${cid}/documents` }, t("Zu den Unterlagen", "Go to documents"), icon("arrow", 14)));
}

function historyText(e) {
  const doc = e.doc_type && S.meta.documents.find((d) => d.id === e.doc_type);
  switch (e.kind) {
    case "created": return [t("Fall angelegt", "Case created"), ""];
    case "stage": return [stageLabel(e.stage), e.text];
    case "upload": return [doc ? qtext(doc, "title") : t("Unterlage", "Document"), e.text];
    case "order": return [t(`Bestellt: ${planName(e.product)}`, `Ordered: ${planName(e.product)}`), e.text];
    case "quick_check": return [t("Schnell-Check berechnet", "Quick check calculated"), ""];
    case "submitted": return [t("An Berater übermittelt", "Sent to advisor"), ""];
    default: return [e.kind, e.text];
  }
}

function activityBlock(ov, limit) {
  const cid = ov.meta.case_id;
  const items = (ov.history || []).slice(0, limit);
  return el("div", {},
    el("div", { class: "card-head" }, el("h3", { text: t("Letzte Aktivität", "Recent activity") }), el("a", { class: "small", href: `#case/${cid}/history`, text: t("Alle", "All") })),
    timeline(items));
}

function timeline(items) {
  if (!items.length) return el("p", { class: "muted small", text: t("Noch nichts passiert.", "Nothing yet.") });
  return el("ol", { class: "tl" }, items.map((e) => {
    const [head, sub] = historyText(e);
    return el("li", { class: "tl-" + e.kind },
      el("span", { class: "tl-dot" }),
      el("div", {}, el("b", { text: head }), sub ? el("span", { class: "tl-sub", text: sub }) : null),
      el("time", { text: fdate(e.at) }));
  }));
}

// ------------------------------------------------------------------ forms

function wsForm(ov, key) {
  const ids = WS_SECTIONS[key];
  const form = qForm("unternehmen", ids, ov.raw_answers.unternehmen || {}, ov.answer_errors.unternehmen || {});
  const gap = sectionGap(ov, ids);
  const save = el("button", { class: "btn btn-primary", text: t("Speichern", "Save") });
  save.addEventListener("click", () => guarded(save, async () => {
    const n = await saveAnswers("unternehmen", form.collect());
    const errs = Object.keys(n.answer_errors.unternehmen).filter((k) => ids.some((sid) => sectionHasQ(sid, k)));
    if (errs.length) { toast(t("Bitte die markierten Angaben prüfen", "Please check the highlighted answers"), true); return renderSmeCase(n, key); }
    toast(t("Gespeichert", "Saved"));
    renderSmeCase(n, key);
  }));
  const intro = key === "company"
    ? t("Stammdaten, Reporting und Zahlungsverhalten. Pflichtfelder sind mit * markiert; jede Frage sagt, warum wir sie stellen.", "Company data, reporting and payment behaviour. Required fields are marked *; every question says why we ask it.")
    : t("Was Sie finanzieren möchten, und was schon besteht. Das bestimmt, welche Kreditgeber passen.", "What you want to finance and what already exists. This decides which lenders fit.");
  return [el("div", { class: "form-page" },
    el("div", { class: "card" }, el("p", { class: "muted", style: "margin:0 0 6px", text: intro }),
      gap.missing ? nextBanner("warn", t(`${gap.missing} Pflichtangaben offen`, `${gap.missing} required answers open`), t("Speichern geht jederzeit – auch unvollständig.", "You can save at any time – even incomplete.")) : nextBanner("done", t("Alle Pflichtangaben vollständig", "All required answers complete"), ""),
      form.node),
    el("div", { class: "save-bar" }, el("span", { class: "small muted", text: t("Änderungen werden erst mit „Speichern“ übernommen.", "Changes are kept once you click Save.") }), save)), null];
}

function sectionHasQ(sectionId, qid) {
  const s = S.meta.questionnaires.unternehmen.sections.find((x) => x.id === sectionId);
  return s && s.questions.some((q) => q.id === qid);
}

// ------------------------------------------------------------------ documents

const CELL_STATE = {
  ok: ["liegt vor", "received"], missing: ["fehlt – erforderlich", "missing – required"],
  open: ["empfohlen", "recommended"], explained: ["erklärt", "explained"], na: ["nicht nötig", "not needed"],
};
const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function pickFile(accept, onFile) {
  const input = el("input", { type: "file", accept, hidden: true });
  input.addEventListener("change", () => { if (input.files[0]) onFile(input.files[0]); input.value = ""; });
  document.body.append(input);
  input.click();
  setTimeout(() => input.remove(), 60000);
}

async function uploadBody(file, body) {
  if (file.size > S.meta.max_upload_mb * 1024 * 1024) throw new Error(t("Datei zu groß", "File too large"));
  const res = await api("POST", `/api/cases/${S.ovCid}/documents`, Object.assign({ filename: file.name, content_base64: await fileToBase64(file) }, body));
  setOv(res.overview);
  toast(t(`${file.name} hochgeladen`, `${file.name} uploaded`));
  return res;
}

function dropTarget(node, onFile) {
  node.addEventListener("dragover", (e) => { e.preventDefault(); node.classList.add("over"); });
  node.addEventListener("dragleave", () => node.classList.remove("over"));
  node.addEventListener("drop", (e) => { e.preventDefault(); node.classList.remove("over"); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); });
}

function noteToggle(key, value, editable, onChange) {
  const wrap = el("div", { class: "cell-note" });
  const show = () => {
    // replaceChildren would print a null argument as the text "null".
    wrap.replaceChildren(...[value ? el("span", { class: "note-txt", text: value }) : null,
      editable ? el("button", { class: "icon-btn", type: "button", title: t("Anmerkung", "Note"), onclick: edit }, icon("pen", 14), el("span", { text: value ? t("ändern", "edit") : t("Anmerkung", "Note") })) : null].filter(Boolean));
  };
  const edit = () => {
    const input = el("input", { type: "text", maxlength: 500, value: value || "", placeholder: t("z. B. „gegründet 2025“ oder „Entwurf“", "e.g. \"founded 2025\" or \"draft\"") });
    const saveNote = () => guarded(null, async () => {
      const v = input.value.trim();
      if (v !== (value || "")) {
        setOv(await api("PUT", `/api/cases/${S.ovCid}/document-notes`, { key, note: v }));
        onChange();
      } else show();
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") saveNote(); if (e.key === "Escape") show(); });
    input.addEventListener("blur", saveNote);
    wrap.replaceChildren(input);
    input.focus();
  };
  show();
  return wrap;
}

function fileChip(f, canEdit, onChange) {
  const mine = S.me.role === "berater" || (f.meta && f.meta.uploaded_by === S.me.email);
  return el("div", { class: "chip" },
    icon("file", 14),
    el("a", { href: `/api/cases/${S.ovCid}/documents/${f.doc_id}`, title: f.filename, text: f.filename }),
    canEdit && mine ? el("button", { class: "x", type: "button", title: t("entfernen", "remove"), text: "×", onclick: (ev) => guarded(ev.currentTarget, async () => {
      if (!confirm(t(`${f.filename} entfernen?`, `Remove ${f.filename}?`))) return;
      setOv(await api("DELETE", `/api/cases/${S.ovCid}/documents/${f.doc_id}`));
      onChange();
    }) }) : null);
}

/** The financial-statements grid: statements as rows, fiscal years as columns. */
function statementsGrid(ov, opts) {
  const grid = ov.doc_matrix;
  const canUpload = opts.canUpload;
  const onChange = opts.onChange;
  const annualDef = S.meta.documents.find((d) => d.id === "jahresabschluesse");
  const accept = (row) => (row === "susa" ? ".csv" : annualDef.formats.map((x) => "." + x).join(","));
  const setCfg = (body) => guarded(null, async () => { setOv(await api("PUT", `/api/cases/${S.ovCid}/doc-matrix`, body)); onChange(); });

  const thisYear = new Date().getFullYear();
  const yearSel = el("select", { disabled: !canUpload, onchange: (e) => setCfg({ first_year: Number(e.target.value) }) },
    Array.from({ length: 10 }, (_, i) => thisYear - i).map((y) => el("option", { value: y, text: String(y), selected: y === grid.first_year })));
  const monthSel = el("select", { disabled: !canUpload, onchange: (e) => setCfg({ fy_end_month: Number(e.target.value) }) },
    MONTHS.map((m, i) => el("option", { value: i + 1, text: lang() === "en" ? MONTHS_EN[i] : m, selected: i + 1 === grid.fy_end_month })));

  const upload = (row, year) => (file) => guarded(null, async () => {
    await uploadBody(file, { cell: { row, year } });
    onChange();
  });

  const head = el("tr", {}, el("th", { class: "g-rowh", text: t("Unterlage", "Document") }),
    grid.columns.map((y, i) => el("th", {},
      el("div", { class: "g-year" }, el("b", { text: String(y) }),
        el("small", { text: i === 0 ? t("Jahr 1 · aktuellstes", "Year 1 · latest") : t(`Jahr ${i + 1}`, `Year ${i + 1}`) }),
        canUpload && i === grid.years - 1 && grid.years > 2 ? el("button", { class: "icon-btn g-rm", type: "button", title: t("Spalte entfernen", "Remove column"), text: "×", onclick: () => setCfg({ years: grid.years - 1 }) }) : null))),
    canUpload && grid.years < 6 ? el("th", { class: "g-add" }, el("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => setCfg({ years: grid.years + 1 }) }, icon("plus", 14), t(" Jahr", " Year"))) : null);

  const body = grid.rows.map((r) => el("tr", {},
    el("th", { class: "g-rowh" }, el("b", { text: lang() === "en" ? r.title_en : r.title_de }), el("small", { text: lang() === "en" ? r.hint_en : r.hint_de })),
    r.cells.map((c) => {
      const td = el("td", { class: "g-cell " + c.state });
      const add = upload(r.id, c.year);
      const parts = [];
      if (c.state === "na") {
        parts.push(el("span", { class: "muted small", text: t("nicht nötig", "not needed") }));
      } else {
        parts.push(el("span", { class: "g-state", text: t(...CELL_STATE[c.state]) }));
        c.files.forEach((f) => parts.push(fileChip(f, canUpload, onChange)));
        if (canUpload) {
          if (c.combined_candidate) {
            parts.push(el("button", { class: "btn btn-soft btn-sm", type: "button", onclick: (ev) => guarded(ev.currentTarget, async () => {
              setOv(await api("PUT", `/api/cases/${S.ovCid}/documents/${c.combined_candidate}/meta`, { part: "bilanz_guv" }));
              toast(t("GuV als Teil des Bilanz-PDFs vermerkt", "P&L marked as part of the balance-sheet PDF"));
              onChange();
            }) }, t("✓ Im Bilanz-PDF enthalten", "✓ Included in the balance-sheet PDF")));
          }
          parts.push(el("button", { class: "up-btn", type: "button", onclick: () => pickFile(accept(r.id), add) },
            icon("upload", 14), c.files.length ? t("Ersetzen", "Replace") : t("Hochladen", "Upload")));
          dropTarget(td, add);
        }
        parts.push(noteToggle(`${r.id}:${c.year}`, c.note, canUpload, onChange));
      }
      td.append(...parts);
      return td;
    }),
    canUpload && grid.years < 6 ? el("td", { class: "g-add" }) : null));

  const other = grid.other.length ? el("div", { class: "g-other" },
    el("div", { class: "small muted", text: t("Weitere Dateien ohne Jahreszuordnung:", "Further files without a year:") }),
    grid.other.map((f) => fileChip(f, canUpload, onChange))) : null;

  return el("div", { class: "card grid-card" },
    el("div", { class: "card-head wrap" },
      el("div", {}, el("h3", { text: t("Jahresabschlüsse und Saldenlisten", "Annual accounts and trial balances") }),
        el("p", { class: "muted small", style: "margin:2px 0 0", text: t("Eine Zeile je Unterlage, eine Spalte je Geschäftsjahr. Datei auf ein Feld ziehen oder „Hochladen“ klicken – Jahr und Art ordnen wir automatisch zu.", "One row per document, one column per fiscal year. Drag a file onto a cell or click Upload – we file year and type automatically.") })),
      el("div", { class: "g-cfg" },
        el("label", {}, t("Letztes Geschäftsjahr", "Latest fiscal year"), yearSel),
        el("label", {}, t("Geschäftsjahr endet im", "Fiscal year ends in"), monthSel))),
    el("div", { class: "table-wrap" }, el("table", { class: "sgrid" }, el("thead", {}, head), el("tbody", {}, body))),
    el("div", { class: "g-legend" }, ["ok", "missing", "open", "explained", "na"].map((s) => el("span", {}, el("i", { class: "dot " + s }), t(...CELL_STATE[s])))),
    other);
}

const BWA_PERIODS = [["1", "1 Monat", "1 month"], ["1-3", "1–3 Monate", "1–3 months"], ["1-6", "1–6 Monate", "1–6 months"], ["1-12", "1–12 Monate", "1–12 months"]];

function bwaCard(ov, opts) {
  const s = ov.documents.find((d) => d.id === "bwa_aktuell");
  const def = S.meta.documents.find((d) => d.id === "bwa_aktuell");
  const f = s.files[0];
  const now = new Date();
  const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const period = el("select", {}, BWA_PERIODS.map(([v, de, en]) => el("option", { value: v, text: t(de, en), selected: v === ((f && f.meta.bwa_period) || "1-12") })));
  const stand = el("input", { type: "month", value: (f && f.meta.bwa_stand) || `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}` });
  const add = (file) => guarded(null, async () => {
    await uploadBody(file, { doc_type: "bwa_aktuell", bwa_period: period.value, bwa_stand: stand.value });
    opts.onChange();
  });
  const row = el("div", { class: "bwa-row" + (s.satisfied ? " ok" : "") },
    el("div", { class: "bwa-main" },
      el("div", { class: "tt" }, el("b", { text: qtext(def, "title") }), el("span", { class: "pill " + (s.satisfied ? "ok" : s.required ? "bad" : ""), text: s.satisfied ? t("liegt vor", "received") : reqLabel(s) })),
      el("div", { class: "small muted", text: qtext(def, "why") }),
      f ? el("div", { class: "chips" }, fileChip(f, opts.canUpload, opts.onChange),
        f.meta.bwa_period ? el("span", { class: "pill", text: t(...BWA_PERIODS.find((p) => p[0] === f.meta.bwa_period).slice(1)) }) : null,
        f.meta.bwa_stand ? el("span", { class: "pill", text: t(`Stand ${f.meta.bwa_stand}`, `as of ${f.meta.bwa_stand}`) }) : null) : null,
      noteToggle("bwa_aktuell", s.note, opts.canUpload, opts.onChange)),
    opts.canUpload ? el("div", { class: "bwa-ctl" },
      el("label", {}, t("Zeitraum", "Period"), period),
      el("label", {}, t("Stand (Monat)", "As of (month)"), stand),
      el("button", { class: "up-btn", type: "button", onclick: () => pickFile(def.formats.map((x) => "." + x).join(","), add) }, icon("upload", 14), f ? t("Ersetzen", "Replace") : t("Hochladen", "Upload"))) : null);
  if (opts.canUpload) dropTarget(row, add);
  return el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: t("Laufende Zahlen (BWA)", "Current figures (BWA)") })), row);
}

function inviteCard(ov, onChange) {
  const invited = (ov.members || {}).steuerberater || [];
  const raw = ov.raw_answers.unternehmen || {};
  const email = el("input", { type: "email", value: raw.steuerberater_email || "", placeholder: "kanzlei@beispiel.de" });
  const name = el("input", { type: "text", value: raw.steuerberater_kanzlei || "", placeholder: t("Kanzlei", "Firm") });
  const btn = el("button", { class: "btn btn-dark btn-sm", text: t("Einladen", "Invite") });
  btn.addEventListener("click", () => guarded(btn, async () => {
    const res = await api("POST", `/api/cases/${S.ovCid}/invite`, { role: "steuerberater", email: email.value, name: name.value });
    setOv(res.overview);
    showInvite(res.invite);
    onChange();
  }));
  return el("div", { class: "card invite" },
    el("div", { class: "card-head" }, el("h3", {}, icon("users", 18), t(" Steuerberatung", " Tax advisor"))),
    invited.length
      ? el("p", { class: "small", text: t(`Eingeladen: ${invited.join(", ")}. Ihre Kanzlei sieht nur diesen Fall und lädt Saldenlisten, BWA und Steuerunterlagen direkt hoch.`, `Invited: ${invited.join(", ")}. Your firm sees only this case and uploads trial balances, BWA and tax documents directly.`) })
      : el("p", { class: "small muted", text: t("Saldenlisten, BWA und Steuerunterlagen kommen meist von der Kanzlei. Laden Sie sie ein – sie bekommt einen eigenen, auf Ihren Fall beschränkten Zugang.", "Trial balances, BWA and tax documents usually come from the firm. Invite them – they get their own access, limited to your case.") }),
    invited.length ? null : el("div", { class: "invite-f" }, name, email, btn));
}

function wsDocuments(ov) {
  const opts = { canUpload: true, onChange: rerender("documents") };
  const byId = Object.fromEntries(ov.documents.map((d) => [d.id, d]));
  const defs = Object.fromEntries(S.meta.documents.map((d) => [d.id, d]));
  const dp = docProgress(ov);
  const groups = DOC_GROUPS.map((g) => el("div", { class: "doc-grp" },
    el("h4", { text: t(g.de, g.en) }),
    g.ids.filter((id) => byId[id]).map((id) => docCard(byId[id], defs[id], { canUpload: (d) => d.source !== "berater", onChange: opts.onChange }))));
  const content = el("div", { class: "docs-page" },
    el("div", { class: "docs-top" },
      el("div", { class: "card progress-card" },
        el("div", { class: "card-head" }, el("h3", { text: t("Fortschritt", "Progress") }), el("b", { text: `${dp.done} / ${dp.total}` })),
        el("div", { class: "meter" }, el("span", { style: `width:${dp.total ? Math.round(dp.done / dp.total * 100) : 100}%` })),
        el("p", { class: "small muted", style: "margin:8px 0 0", text: t("Pflichtunterlagen von Ihnen und Ihrer Steuerberatung. Fehlt etwas aus gutem Grund, schreiben Sie eine Anmerkung – dann gilt es als erklärt.", "Required documents from you and your tax advisor. If something is missing for a good reason, add a note – it then counts as explained.") })),
      inviteCard(ov, opts.onChange)),
    statementsGrid(ov, opts),
    bwaCard(ov, opts),
    el("div", { class: "card" }, el("div", { class: "card-head" }, el("h3", { text: t("Weitere Unterlagen", "Other documents") })), groups));
  return [content, null];
}

// ------------------------------------------------------------------ figures

function wsFigures(ov) {
  const cid = ov.meta.case_id;
  if (ov.report_released) {
    return [el("div", { class: "card" }, el("p", { text: t("Ihr Bericht ist freigegeben; die Zahlen hat Ihr Berater mit den Unterlagen abgeglichen.", "Your report is released; your advisor reconciled the figures with the documents.") })), null];
  }
  const has = ov.documents.find((d) => d.id === "jahresabschluesse").files.length > 0;
  const read = el("button", { class: "btn btn-dark", text: ov.extraction ? t("Erneut auslesen", "Read again") : t("Zahlen aus dem Jahresabschluss auslesen", "Read figures from the annual accounts"), disabled: !has });
  const consentNeeded = S.meta.ai.external && (ov.raw_answers.unternehmen || {}).ki_einwilligung !== true;
  const consent = el("input", { type: "checkbox" });
  read.addEventListener("click", () => guarded(read, async () => {
    if (consentNeeded) {
      if (!consent.checked) throw new Error(t("Bitte der KI-Auslesung zustimmen – oder Zahlen manuell eintragen.", "Please consent to AI reading – or enter the figures manually."));
      await saveAnswers("unternehmen", Object.assign({}, ov.raw_answers.unternehmen, { ki_einwilligung: true }));
    }
    read.textContent = t("Lese aus …", "Reading …");
    const res = await api("POST", `/api/cases/${cid}/extract`, {});
    setOv(res.overview);
    toast(t(`${Object.keys(res.extraction.fields).length} Positionen gefunden – bitte prüfen`, `${Object.keys(res.extraction.fields).length} items found – please check`));
    renderSmeCase(S.ov, "figures");
  }));
  const top = el("div", { class: "card" },
    aiBadge(),
    has ? null : nextBanner("warn", t("Zuerst den Jahresabschluss hochladen", "Upload the annual accounts first"), t("Im Bereich Unterlagen, Spalte „Jahr 1“.", "In Documents, column 'Year 1'."), el("a", { class: "btn btn-ghost btn-sm", href: `#case/${cid}/documents`, text: t("Zu den Unterlagen", "Go to documents") })),
    consentNeeded ? el("label", { class: "checkbox" }, consent, el("span", { text: t("Ich willige ein, dass mein Jahresabschluss zur Auslesung an den KI-Dienstleister übermittelt wird.", "I consent to my annual accounts being sent to the AI provider for reading.") })) : null,
    el("div", { class: "actions" }, read));
  return [el("div", {}, top, qcFigures(ov)), null];
}

// ------------------------------------------------------------------ result

function wsResultPage(ov) {
  const cid = ov.meta.case_id;
  const res = wsResult(ov);
  const calc = el("button", { class: "btn btn-primary", text: ov.quick_check ? t("Neu berechnen", "Recalculate") : t("Schnell-Check berechnen", "Calculate quick check") });
  calc.addEventListener("click", () => guarded(calc, async () => {
    const r = await api("POST", `/api/cases/${cid}/quickcheck`);
    setOv(r.overview);
    S.lastQuick = r.ok ? null : r;
    toast(r.ok ? t("Ergebnis berechnet", "Result calculated") : t("Noch nicht möglich – siehe Hinweise", "Not possible yet – see notes"), !r.ok);
    renderSmeCase(S.ov, "result");
  }));
  const action = ov.report_released ? null : calc;
  if (res && res.kind === "report") {
    const [tone, title, text] = verdictInfo(res.r);
    return [el("div", { class: "result-page" },
      el("div", { class: "dash" },
        el("section", { class: "card span2" }, scoreBlock(ov, res)),
        el("section", { class: `card verdict ${tone}` }, el("h3", { text: title }), el("p", { text: text }),
          el("div", { class: "small muted", text: t("Passender Kreditgebertyp nach den Maßnahmen", "Best-fitting lender type after the fixes") }),
          el("b", { text: lenderLabel(res.r.top_lender_after) }))),
      el("section", { class: "card" }, ratiosBlock(res)),
      // The released report's findings, levers, projection and download; its
      // own header repeats the score card above and is hidden (workspace.css).
      el("div", { class: "rv-trim" }, resultView(res.r, cid, false)),
      explainBox(cid, "report")), null];
  }
  if (!res) {
    const failed = S.lastQuick && !S.lastQuick.ok ? S.lastQuick : null;
    const steps = wsTodos(ov).filter((x) => ["company", "financing", "documents", "figures"].includes(x.page)).slice(0, 4);
    return [el("div", { class: "card" },
      el("div", { class: "score" }, gauge(null), el("div", { class: "score-txt" },
        el("h2", { text: t("Ihr kostenloser Schnell-Check", "Your free quick check") }),
        el("p", { class: "muted", text: t("Dafür brauchen wir:", "For this we need:") }),
        el("ol", { class: "mini-steps" }, steps.map((s) => el("li", { class: s.done ? "done" : "" }, el("a", { href: "#" + s.href, text: s.title })))),
        failed ? nextBanner("warn", t("Noch nicht möglich", "Not possible yet"), failed.blocking.join(" · ")) : null,
        el("div", { class: "actions" }, calc)))), null];
  }
  const q = res.r;
  const [tone, title, text] = verdictInfo({ verdict: q.verdict });
  return [el("div", { class: "result-page" },
    el("div", { class: "dash" },
      el("section", { class: "card span2" }, scoreBlock(ov, res)),
      el("section", { class: `card verdict ${tone}` }, el("h3", { text: title }), el("p", { text: text }))),
    el("section", { class: "card" }, ratiosBlock(res)),
    el("section", { class: "card" },
      el("div", { class: "card-head" }, el("h3", { text: t("Die drei wichtigsten Punkte", "The three most important points") })),
      q.top_findings.map((f, i) => {
        const txt = FINDING[f.rule] ? FINDING[f.rule][lang()] : [f.title, ""];
        return el("div", { class: "fcard" }, el("div", { class: "n", text: String(i + 1) }),
          el("div", {}, el("h4", { text: txt[0] }), el("div", { class: "muted", text: txt[1] }),
            el("div", { class: "meta" }, el("span", { class: "pill " + (f.fixable ? "ok" : "bad"), text: f.fixable ? t("behebbar", "fixable") : t("nicht durch Aufbereitung behebbar", "not fixable by presentation") }))));
      }),
      q.more_findings ? el("p", { class: "small", style: "font-weight:600;color:var(--navy-2)", text: t(`+ ${q.more_findings} weitere Punkte im vollständigen Bericht`, `+ ${q.more_findings} more points in the full report`) }) : null),
    improvementPanel(q.improvements),
    projectionPanel(q.projection),
    explainBox(cid, "quick"),
    el("p", { class: "disclaimer", text: q.disclaimer })), action];
}

// ------------------------------------------------------------------ plan

const PLAN_FEATURES = {
  quick: () => [
    t("Readiness-Band und Gesamtwert", "Readiness band and score"),
    t("Kennzahlen gegen Ihre Branche", "Ratios against your sector"),
    t("Die drei wichtigsten Befunde und größten Hebel", "Top three findings and biggest levers"),
    t("Fortschreibung der Kapitaldienstfähigkeit", "Projected debt service cover"),
  ],
  report: () => [
    t("Alle Befunde, nicht nur die ersten drei", "All findings, not just the first three"),
    t("Vorher/Nachher: was jede Maßnahme bringt", "Before/after: what each measure achieves"),
    t("Passender Kreditgebertyp und Förderprogramme", "Best-fitting lender type and public programmes"),
    t("Von einem Kreditanalysten geprüft und freigegeben", "Reviewed and released by a credit analyst"),
  ],
  advisor: () => [
    t("Persönliche Gespräche mit Ihrem Berater", "Personal calls with your advisor"),
    t("Abstimmung mit Ihrem Steuerberater", "Sign-off with your tax advisor"),
    t("Begleitung bis zum Bankgespräch", "Support up to the bank meeting"),
  ],
};

function wsPlanPage(ov) {
  const cid = ov.meta.case_id;
  const cur = wsPlan(ov);
  const order = ["quick", "report", "advisor"];
  const card = (key) => {
    const booked = key === "quick" || hasOrder(ov, key);
    const isCur = key === cur;
    const note = el("textarea", { placeholder: key === "advisor" ? t("Wann passt Ihnen ein Gespräch? (optional)", "When would a call suit you? (optional)") : t("Anmerkung (optional)", "Note (optional)") });
    const btn = el("button", { class: "btn " + (key === "report" ? "btn-primary" : "btn-dark"), text: t("Bestellen", "Order") });
    btn.addEventListener("click", () => guarded(btn, async () => {
      if (!confirm(key === "report" ? t(`Vollständigen Bericht für ${price("report")} verbindlich bestellen? Sie erhalten eine Rechnung.`, `Order the full report for ${price("report")}? You will receive an invoice.`)
        : t("Beratung anfragen? Wir melden uns mit einem Angebot.", "Request advisory? We'll come back with an offer."))) return;
      setOv(await api("POST", `/api/cases/${cid}/order`, { product: key, note: note.value }));
      toast(t("Vielen Dank – bestellt", "Thank you – ordered"));
      renderSmeCase(S.ov, "plan");
    }));
    return el("div", { class: "plan" + (isCur ? " current" : "") + (key === "report" ? " featured" : "") },
      isCur ? el("span", { class: "pill ok", text: t("Ihr Tarif", "Your plan") }) : key === "report" && !booked ? el("span", { class: "pill info", text: t("Empfohlen", "Recommended") }) : null,
      el("h3", { text: planName(key) }),
      el("div", { class: "price", text: price(key) }),
      el("ul", { class: "feature-list" }, PLAN_FEATURES[key]().map((f) => el("li", { text: f }))),
      booked ? el("div", { class: "booked", text: key === "quick" ? t("✓ inklusive", "✓ included") : t("✓ gebucht", "✓ booked") }) : el("div", {}, note, btn));
  };
  let submit = null;
  if (hasOrder(ov, "report") && !ov.submitted_at) {
    const missing = ov.missing_answers.unternehmen;
    const b = el("button", { class: "btn btn-primary", text: t("An Ihren Berater übermitteln", "Send to your advisor"), disabled: missing.length > 0 });
    b.addEventListener("click", () => guarded(b, async () => {
      setOv(await api("POST", `/api/cases/${cid}/submit`));
      toast(t("Übermittelt – vielen Dank!", "Submitted – thank you!"));
      renderSmeCase(S.ov, "plan");
    }));
    submit = el("div", { class: "card" },
      el("div", { class: "card-head" }, el("h3", { text: t("Bericht bestellt – jetzt übermitteln", "Report ordered – now send it") })),
      missing.length ? nextBanner("warn", t("Pflichtangaben fehlen noch", "Required answers still missing"), missing.join(" · ")) : el("p", { class: "muted", text: t("Ihr Berater prüft dann alles und erstellt den Bericht. Fehlende Unterlagen können Sie danach noch hochladen.", "Your advisor then reviews everything and prepares the report. You can still upload missing documents afterwards.") }),
      b);
  } else if (ov.submitted_at && !ov.report_released) {
    submit = nextBanner("done", t("Übermittelt", "Submitted"), t(`Am ${fdate(ov.submitted_at)}. Sie hören von uns, sobald Ihr Bericht freigegeben ist.`, `On ${fdate(ov.submitted_at)}. We'll be in touch once your report is released.`));
  }
  return [el("div", {}, submit, el("div", { class: "plans" }, order.map(card)),
    el("p", { class: "small muted", style: "margin-top:14px", text: t("Preise zzgl. USt. Keine Provision von Banken – wir werden nur von Ihnen bezahlt.", "Prices plus VAT. No commission from banks – only you pay us.") })), null];
}

// ------------------------------------------------------------------ history

function wsHistory(ov) {
  return [el("div", { class: "card" }, timeline(ov.history || [])), null];
}
