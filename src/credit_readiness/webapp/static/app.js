/* Credit Readiness -- portal front end.
 *
 * Plain JavaScript, no build step, no dependencies. Every piece of text from
 * the server reaches the page through textContent, never innerHTML.
 * Permissions are enforced by the server; this file only decides what to show.
 */
"use strict";

// ------------------------------------------------------------------ basics

const S = { meta: null, me: null, cases: [], ov: null, ovCid: null, ready: false, lastRun: null };
const lang = () => (window.CRA_LANG ? window.CRA_LANG.get() : "de");
const t = (de, en) => (lang() === "en" ? en : de);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "value") node.value = v;
    else if (["checked", "disabled", "selected", "required", "hidden", "multiple"].includes(k)) node[k] = !!v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(method, url, body) {
  const opts = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (_) { /* not JSON */ }
  if (res.status === 401 && S.me && !url.startsWith("/api/auth/")) {
    S.me = null;
    go("login");
    throw new Error(t("Sitzung abgelaufen - bitte erneut anmelden", "Session expired - please log in again"));
  }
  if (!res.ok) throw new Error((data && data.error) || `Error ${res.status}`);
  return data;
}

let toastTimer = null;
function toast(msg, isError) {
  const tEl = document.getElementById("toast");
  tEl.textContent = msg;
  tEl.className = "toast" + (isError ? " error" : "");
  tEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { tEl.hidden = true; }, isError ? 7000 : 3200);
}

async function guarded(btn, fn) {
  if (btn) btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message, true); } finally { if (btn) btn.disabled = false; }
}

const nf = (v, d = 0) => (v === null || v === undefined ? "–" : Number(v).toLocaleString(lang() === "en" ? "en-GB" : "de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }));
const pct = (v, d = 1) => (v === null || v === undefined ? "–" : nf(v * 100, d) + " %");
const xf = (v) => (v === null || v === undefined ? "–" : nf(v, 2) + "x");
const eur = (v) => (v === null || v === undefined ? "–" : (lang() === "en" ? "€" + nf(v) : nf(v) + " €"));
const fdate = (iso) => { if (!iso) return ""; const d = new Date(iso); return isNaN(d) ? iso : d.toLocaleDateString(lang() === "en" ? "en-GB" : "de-DE"); };
const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((s) => s[0].toUpperCase()).join("");

function go(hash) {
  if (location.hash !== "#" + hash) location.hash = hash; else render();
}
function route() {
  const parts = location.hash.replace(/^#/, "").split("/");
  return { page: parts[0] || "", cid: parts[1] || null, part: parts[2] || null };
}

// ------------------------------------------------------------------ vocab

const ROLE = {
  berater: ["Berater", "Advisor"],
  unternehmen: ["Unternehmen", "Company"],
  steuerberater: ["Steuerberatung", "Tax advisor"],
};
const roleLabel = (r) => t(...(ROLE[r] || [r, r]));

const STAGE = {
  neu: ["Neu", "New"],
  unterlagen_angefordert: ["Unterlagen angefordert", "Documents requested"],
  unterlagen_vollstaendig: ["Unterlagen vollständig", "Documents complete"],
  diagnostik_erstellt: ["Analyse erstellt", "Analysis done"],
  massnahmen_in_umsetzung: ["Maßnahmen laufen", "Fixes in progress"],
  beim_kreditgeber: ["Beim Kreditgeber", "With lender"],
  abgeschlossen: ["Abgeschlossen", "Closed"],
};
const stageLabel = (s) => t(...(STAGE[s] || [s, s]));
const STAGE_ORDER = Object.keys(STAGE);

const SOURCE = {
  unternehmen: ["Vom Unternehmen", "From the company"],
  steuerberater: ["Von der Steuerberatung", "From the tax advisor"],
  berater: ["Holen wir ein", "We obtain this"],
};

// Plain-language explanations of the engine's findings, for clients and investors.
const FINDING = {
  R01: { de: ["Gesellschafterdarlehen zählt als Schulden", "Das Darlehen der Gesellschafter wird mangels Rangrücktritt als Fremdkapital gewertet. Mit einer Rangrücktrittserklärung zählt es für fast alle Banken als Eigenkapital – ohne frisches Geld."],
         en: ["Shareholder loan counts as debt", "Without a subordination agreement the shareholders' loan is treated as debt. With one, almost every bank counts it as equity – without any new money."] },
  R02: { de: ["Aktuelle BWA fehlt", "Die jüngste betriebswirtschaftliche Auswertung ist zu alt. Banken lesen das als schwaches Reporting. Monatliche BWA mit dem Steuerberater vereinbaren."],
         en: ["Management report out of date", "The latest management report (BWA) is too old; banks read this as weak reporting. Agree monthly reports with the tax advisor."] },
  R03: { de: ["Keine Planrechnung", "Für diesen Betrag erwarten Banken einen Blick nach vorn: Plan-GuV, Liquiditätsplan, Planbilanz für 24 Monate."],
         en: ["No financial plan", "For this amount banks expect a forward view: 24-month P&L, cash-flow and balance-sheet plan."] },
  R04: { de: ["Kontokorrent dauerhaft ausgeschöpft", "Die Kreditlinie finanziert faktisch Dauerbedarf – teuer und ein Warnsignal. Umschuldung in ein passendes Darlehen stellt die Linie als Reserve wieder her."],
         en: ["Overdraft permanently maxed out", "The credit line is funding long-term needs – expensive and a red flag. Moving it into a term loan restores the line as a reserve."] },
  R05: { de: ["Kunden zahlen spät", "Hohe Forderungen binden Liquidität. Factoring kann den Kreditbedarf senken, statt ihn zu finanzieren."],
         en: ["Customers pay late", "High receivables tie up cash. Factoring can reduce the credit need instead of financing it."] },
  R06: { de: ["Langfristiges kurzfristig finanziert", "Anlagevermögen ist teilweise über kurzfristige Kredite finanziert. Laufzeiten an die Nutzungsdauer anpassen."],
         en: ["Long-term assets on short-term money", "Fixed assets are partly funded with short-term credit. Match loan terms to the assets' life."] },
  R07: { de: ["Sicherheiten reichen nicht – Kapitaldienst schon", "Die Zahlen tragen die Rate, aber es fehlen Sicherheiten. Das lösen KfW-Programme mit Haftungsfreistellung oder die Bürgschaftsbank."],
         en: ["Collateral short – repayment capacity fine", "The numbers support the instalment but collateral is missing. KfW liability-release programmes or a guarantee bank solve this."] },
  R08: { de: ["Substanzielle Schwäche", "Verlust, schrumpfender Umsatz oder Überschuldung lassen sich nicht durch Aufbereitung beheben. Ein Antrag jetzt erzeugt eine dokumentierte Ablehnung."],
         en: ["Substantive weakness", "Losses, shrinking revenue or over-indebtedness cannot be fixed by presentation. Applying now would create a documented rejection."] },
  R09: { de: ["Steuerrückstände", "Für fast jede Bank ein K.-o.-Kriterium. Erst ausgleichen oder eine Stundungsvereinbarung vorlegen."],
         en: ["Tax arrears", "A knock-out criterion for almost every bank. Settle first or present a deferral agreement."] },
  R10: { de: ["Hoher Lagerbestand", "Ein Teil des Kreditbedarfs entsteht im Lager. Bestandsabbau senkt ihn direkt."],
         en: ["High inventory", "Part of the credit need sits in the warehouse. Reducing stock lowers it directly."] },
};
const CATEGORY = {
  "Darstellung": ["Darstellung", "Presentation"],
  "Unterlagen": ["Unterlagen", "Documentation"],
  "Produktwahl": ["Produktwahl", "Product fit"],
  "Besicherung": ["Besicherung", "Collateral"],
  "Substanzielles Kreditrisiko": ["Kreditrisiko", "Credit risk"],
};
const LENDER_EN = {
  "Hausbank (Sparkasse / Volksbank)": "Main bank (savings / cooperative bank)",
  "KfW-Programm mit Haftungsfreistellung (ueber die Hausbank)": "KfW programme with liability release (via main bank)",
  "Buergschaftsbank des Bundeslandes": "State guarantee bank",
  "Factoring-Gesellschaft": "Factoring company",
  "Leasing / Sale-and-lease-back": "Leasing / sale-and-lease-back",
  "Digitaler Mittelstandsfinanzierer": "Digital SME lender",
  "Mezzanine / Mittelstaendische Beteiligungsgesellschaft (MBG)": "Mezzanine / regional investment company (MBG)",
};
function docTitle(germanTitle) {
  if (lang() !== "en" || !S.meta) return germanTitle;
  const d = S.meta.documents.find((x) => x.title === germanTitle);
  return d ? d.title_en : germanTitle;
}
const lenderLabel = (n) => (n ? (lang() === "en" ? LENDER_EN[n] || n : n) : t("kein passender Typ", "no suitable type"));

// ------------------------------------------------------------------ shell

function logoMark() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  svg.setAttribute("class", "logo-mark");
  for (const [tag, a] of [["rect", { width: 32, height: 32, rx: 8, fill: "#0d2440" }],
    ["rect", { x: 7, y: 17, width: 4, height: 8, rx: 1.5, fill: "#6fd3b7" }],
    ["rect", { x: 14, y: 12, width: 4, height: 13, rx: 1.5, fill: "#39b894" }],
    ["rect", { x: 21, y: 7, width: 4, height: 18, rx: 1.5, fill: "#0b8f73" }]]) {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(a)) n.setAttribute(k, v);
    svg.append(n);
  }
  return svg;
}

function langToggle() {
  return el("div", { class: "lang-toggle" },
    el("button", { "data-lang": "de", class: lang() === "de" ? "active" : "", text: "DE" }),
    el("button", { "data-lang": "en", class: lang() === "en" ? "active" : "", text: "EN" }));
}

function shell(content) {
  const me = S.me;
  const logout = el("button", { class: "btn btn-ghost btn-sm", text: t("Abmelden", "Log out") });
  logout.addEventListener("click", () => guarded(logout, async () => {
    await api("POST", "/api/auth/logout");
    S.me = null; S.ov = null; S.ovCid = null;
    go("login");
  }));
  const bar = el("header", { class: "topbar" }, el("div", { class: "topbar-inner" },
    el("a", { class: "logo", href: "#home" }, logoMark(), el("span", {}, "Credit Readiness", el("small", { text: "Portal" }))),
    el("div", { class: "who" },
      el("a", { class: "small hide-sm", href: "/", text: t("Website", "Website") }),
      langToggle(),
      el("div", { class: "avatar", text: initials(me.name) }),
      el("div", {}, el("div", { class: "nm", text: me.name }), el("div", { class: "rl", text: roleLabel(me.role) })),
      logout)));
  const parts = [bar];
  if (S.meta.demo) {
    parts.push(el("div", { class: "demo-ribbon", text: t("Demo-Umgebung – alle Unternehmen und Zahlen sind fiktiv.", "Demo environment – all companies and figures are fictional.") }));
  }
  parts.push(el("main", { class: "page" }, content));
  return parts;
}

function mount(nodes) {
  const root = document.getElementById("root");
  root.className = "";
  root.replaceChildren(...[nodes].flat());
  window.scrollTo(0, 0);
}

function nextBanner(kind, title, text, action) {
  return el("div", { class: "next " + (kind || "") },
    el("div", { class: "ico", text: kind === "done" ? "✓" : kind === "warn" ? "!" : "→" }),
    el("div", { class: "txt" }, el("b", { text: title }), el("span", { text: text })),
    action || null);
}

function openModal(build) {
  const root = document.getElementById("modal-root");
  const close = () => root.replaceChildren();
  const box = el("div", { class: "modal" });
  const bg = el("div", { class: "modal-bg", onclick: (e) => { if (e.target === bg) close(); } }, box);
  build(box, close);
  root.replaceChildren(bg);
  const f = box.querySelector("input");
  if (f) f.focus();
}

// ------------------------------------------------------------------ auth

function renderAuth(mode) {
  const brand = el("div", { class: "auth-brand" },
    el("a", { class: "logo", href: "/" }, logoMark(), el("span", {}, "Credit Readiness", el("small", { text: "Advisory" }))),
    el("h2", { text: t("Wissen, woran es liegt – vor dem nächsten Kreditantrag.", "Know what's holding you back – before the next loan application.") }),
    el("ul", {},
      el("li", { text: t("Analyse Ihrer Zahlen wie das Rating-Modell Ihrer Bank", "Your numbers analysed like your bank's rating model") }),
      el("li", { text: t("Klar getrennt: was behebbar ist – und was nicht", "Clearly separated: what is fixable – and what isn't") }),
      el("li", { text: t("Ihr Steuerberater arbeitet mit, nichts ohne seine Freigabe", "Your tax advisor works with us; nothing without their approval") }),
      el("li", { text: t("Kein Rating, keine Bankprovision – unabhängig", "No rating, no bank commission – independent") })),
    el("div", { class: "foot", text: t("Richtungsweisende Einschätzung, keine Kreditzusage.", "Directional assessment, not a credit decision.") }));

  const err = el("div", { class: "form-error", hidden: true });
  const showErr = (m) => { err.textContent = m; err.hidden = false; };

  let form;
  if (mode === "register") {
    const f = {
      company: el("input", { type: "text", required: true, autocomplete: "organization" }),
      name: el("input", { type: "text", required: true, autocomplete: "name" }),
      email: el("input", { type: "email", required: true, autocomplete: "email" }),
      password: el("input", { type: "password", required: true, minlength: 8, autocomplete: "new-password" }),
      consent: el("input", { type: "checkbox" }),
    };
    const btn = el("button", { class: "btn btn-primary btn-lg", type: "submit", style: "width:100%", text: t("Konto anlegen und starten", "Create account and start") });
    form = el("form", { novalidate: true },
      el("h1", { style: "font-size:28px", text: t("Analyse starten", "Start your analysis") }),
      el("p", { class: "muted", text: t("Legen Sie ein Konto für Ihr Unternehmen an. Danach führen wir Sie Schritt für Schritt durch alles Weitere.", "Create an account for your company. We then guide you through everything, step by step.") }),
      err,
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Firmenname", "Company name") }), f.company),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Ihr Name", "Your name") }), f.name),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("E-Mail", "E-mail") }), f.email),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Passwort (mind. 8 Zeichen)", "Password (min. 8 characters)") }), f.password),
      el("label", { class: "checkbox" }, f.consent, el("span", { text: t("Ich willige in die Verarbeitung meiner Daten zum Zweck der Kreditfähigkeitsanalyse ein.", "I consent to the processing of my data for the purpose of the creditworthiness analysis.") })),
      btn);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      err.hidden = true;
      if (!f.consent.checked) return showErr(t("Bitte der Datenverarbeitung zustimmen.", "Please consent to the data processing."));
      guarded(btn, async () => {
        try {
          const res = await api("POST", "/api/auth/register", { company_name: f.company.value, name: f.name.value, email: f.email.value, password: f.password.value, consent: true });
          S.me = res.user;
          await loadCases();
          toast(t("Willkommen! Ihr Konto ist angelegt.", "Welcome! Your account is ready."));
          go(`case/${res.case_id}/company`);
        } catch (e) { showErr(e.message); }
      });
    });
  } else {
    const email = el("input", { type: "email", required: true, autocomplete: "username" });
    const pw = el("input", { type: "password", required: true, autocomplete: "current-password" });
    const btn = el("button", { class: "btn btn-dark btn-lg", type: "submit", style: "width:100%", text: t("Anmelden", "Log in") });
    form = el("form", { novalidate: true },
      el("h1", { style: "font-size:28px", text: t("Willkommen zurück", "Welcome back") }),
      el("p", { class: "muted", text: t("Melden Sie sich an, um Ihren Fall zu sehen.", "Log in to see your case.") }),
      err,
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("E-Mail", "E-mail") }), email),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Passwort", "Password") }), pw),
      btn);
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      err.hidden = true;
      guarded(btn, async () => {
        try { await login(email.value, pw.value); } catch (e) { showErr(e.message); }
      });
    });
  }

  const tabs = el("div", { class: "auth-tabs" },
    el("button", { class: mode !== "register" ? "active" : "", text: t("Anmelden", "Log in"), onclick: () => go("login") }),
    el("button", { class: mode === "register" ? "active" : "", text: t("Registrieren", "Register"), onclick: () => go("register") }));

  let demo = null;
  if (S.meta.demo && mode !== "register") {
    const colors = { berater: "#0d2440", unternehmen: "#0b8f73", steuerberater: "#6b5bd6" };
    demo = el("div", { class: "demo-box" },
      el("h4", { text: t("Demo-Zugänge", "Demo accounts") }),
      el("div", { class: "small muted", text: t(`Ein Klick meldet Sie an. Passwort: ${S.meta.demo_password}`, `One click logs you in. Password: ${S.meta.demo_password}`) }),
      S.meta.demo_accounts.map((a) => el("button", {
        class: "demo-acc", type: "button",
        onclick: (ev) => guarded(ev.currentTarget, () => login(a.email, S.meta.demo_password)),
      },
      el("div", { class: "av", style: `background:${colors[a.role]}`, text: initials(a.name) }),
      el("div", {}, el("b", { text: `${roleLabel(a.role)}: ${a.name}` }), el("span", { class: "sub", text: lang() === "en" ? a.hint_en : a.hint_de })))));
  }

  const panel = el("div", { class: "auth-panel" }, el("div", { class: "auth-card" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:22px" },
      el("a", { href: "/", class: "small", text: t("← Zur Website", "← Back to website") }), langToggle()),
    tabs, form, demo));
  mount(el("div", { class: "auth" }, brand, panel));
}

async function login(email, password) {
  S.me = await api("POST", "/api/auth/login", { email, password });
  await loadCases();
  go("home");
}

async function loadCases() {
  S.cases = await api("GET", "/api/cases");
}

// ------------------------------------------------------------------ router

async function render() {
  if (!S.ready) return;
  document.getElementById("modal-root").replaceChildren();
  const r = route();
  if (!S.me) return renderAuth(r.page === "register" ? "register" : "login");
  try {
    if (r.page === "case" && r.cid) return await renderCase(r.cid, r.part);
    return await renderHome();
  } catch (e) {
    toast(e.message, true);
  }
}

async function loadOverview(cid, force) {
  if (force || S.ovCid !== cid || !S.ov) {
    S.ov = await api("GET", `/api/cases/${cid}`);
    S.ovCid = cid;
  }
  return S.ov;
}

function setOv(ov) {
  S.ov = ov;
  S.ovCid = ov.meta.case_id;
  const c = S.cases.find((x) => x.case_id === ov.meta.case_id);
  if (c) Object.assign(c, ov.meta);
}

async function renderHome() {
  await loadCases();
  const role = S.me.role;
  if (role === "berater") return renderAdvisorHome();
  if (role === "unternehmen" && S.cases.length === 1) return go(`case/${S.cases[0].case_id}`);
  const title = role === "steuerberater" ? t("Ihre Mandate", "Your clients") : t("Ihre Fälle", "Your cases");
  const sub = role === "steuerberater"
    ? t("Mandanten, die Sie zur Kreditfähigkeitsanalyse eingeladen haben.", "Clients who invited you to their credit readiness analysis.")
    : t("Wählen Sie einen Fall.", "Choose a case.");
  const cards = S.cases.map((c) => el("button", { class: "ccard", style: "padding:20px", onclick: () => go(`case/${c.case_id}`) },
    el("div", { class: "co", style: "font-size:17px", text: c.company_name }),
    el("div", { class: "id", text: c.case_id }),
    el("div", { class: "row" }, el("span", { class: "pill info", text: stageLabel(c.stage) }),
      el("span", { class: "small", style: "color:var(--teal-2);font-weight:600", text: t("Öffnen →", "Open →") }))));
  mount(shell([
    el("div", { class: "page-head" }, el("div", {}, el("h1", { text: title }), el("div", { class: "sub", text: sub }))),
    cards.length ? el("div", { class: "grid-3" }, cards)
      : el("div", { class: "panel center muted", text: t("Noch keine Fälle. Sobald ein Mandant Sie einlädt, erscheint er hier.", "No cases yet. They appear here once a client invites you.") }),
  ]));
}

async function renderCase(cid, part) {
  const ov = await loadOverview(cid);
  if (S.me.role === "unternehmen") return renderSmeCase(ov, part);
  if (S.me.role === "steuerberater") return renderStbCase(ov, part);
  return renderAdvisorCase(ov, part);
}

// ------------------------------------------------------------------ questionnaire component

const qtext = (obj, key) => (lang() === "en" && obj[key + "_en"] ? obj[key + "_en"] : obj[key] || "");
function optLabel(q, value) {
  if (lang() !== "en" || !q.options_en) return value;
  const i = q.options.indexOf(value);
  return i >= 0 ? q.options_en[i] : value;
}
const isTrue = (v) => v === true || v === "true" || v === "ja";
const isFalse = (v) => v === false || v === "false" || v === "nein";

function displayValue(q, v) {
  if (v === null || v === undefined) return "";
  if (q.type === "money" && typeof v === "number") return v.toLocaleString("de-DE");
  return String(v);
}

let uid = 0;
function inputFor(q, value) {
  const name = `q${++uid}`;
  switch (q.type) {
    case "textarea": return el("textarea", { value: value ?? "" });
    case "bool": {
      const seg = el("div", { class: "seg", "data-kind": "bool" });
      const mk = (val, label) => {
        const on = val === "ja" ? isTrue(value) : isFalse(value);
        const lab = el("label", { class: on ? "on" : "" }, el("input", { type: "radio", name, value: val, checked: on }), label);
        lab.addEventListener("click", () => {
          seg.querySelectorAll("label").forEach((l) => l.classList.remove("on"));
          lab.classList.add("on");
        });
        return lab;
      };
      seg.append(mk("ja", t("Ja", "Yes")), mk("nein", t("Nein", "No")));
      return seg;
    }
    case "select":
      return el("select", {},
        el("option", { value: "", text: t("– bitte wählen –", "– please choose –") }),
        q.options.map((o) => el("option", { value: o, text: optLabel(q, o), selected: value === o })));
    case "date": return el("input", { type: "date", value: value ?? "" });
    case "month": return el("input", { type: "month", value: value ?? "", placeholder: "JJJJ-MM" });
    case "int": case "money": case "percent": {
      const inp = el("input", { type: "text", inputmode: "decimal", value: displayValue(q, value) });
      return q.unit ? el("div", { class: "unit-wrap" }, inp, el("span", { text: q.unit })) : inp;
    }
    default: return el("input", { type: "text", value: value ?? "" });
  }
}

function readInput(q, holder) {
  if (q.type === "bool") {
    const r = holder.querySelector("input[type=radio]:checked");
    return r ? r.value === "ja" : null;
  }
  const f = holder.querySelector("input, select, textarea");
  const v = f ? f.value.trim() : "";
  return v === "" ? null : v;
}

function questionBlock(q, value, error) {
  const holder = el("div", {}, inputFor(q, value));
  const wide = ["textarea", "list"].includes(q.type) || q.label.length > 70 || q.type === "bool";
  const node = el("div", { class: "q" + (wide ? " wide" : "") + (error ? " invalid" : "") },
    el("label", { class: "ql" }, qtext(q, "label"), q.required ? el("span", { class: "req", text: "*" }) : null),
    holder,
    qtext(q, "help") ? el("div", { class: "help", text: qtext(q, "help") }) : null,
    qtext(q, "why") ? el("div", { class: "why", text: qtext(q, "why") }) : null,
    error ? el("div", { class: "err", text: error }) : null);
  return { node, read: () => readInput(q, holder) };
}

function loanList(q, rows) {
  const wrap = el("div");
  const cards = [];
  const add = (values) => {
    const blocks = q.fields.map((f) => ({ f, b: questionBlock(f, values ? values[f.id] : null, null) }));
    const card = el("div", { class: "loan-card" },
      el("button", { class: "btn btn-danger btn-sm rm", type: "button", text: t("Entfernen", "Remove"),
        onclick: () => { card.remove(); cards.splice(cards.indexOf(entry), 1); } }),
      el("div", { class: "q-grid" }, blocks.map((x) => x.b.node)));
    const entry = { card, blocks };
    cards.push(entry);
    wrap.append(card);
  };
  (Array.isArray(rows) ? rows : []).forEach(add);
  const node = el("div", { class: "q wide" },
    el("label", { class: "ql", text: qtext(q, "label") }),
    qtext(q, "why") ? el("div", { class: "why", style: "margin:0 0 12px", text: qtext(q, "why") }) : null,
    wrap,
    el("button", { class: "btn btn-ghost btn-sm", type: "button", text: t("+ Finanzierung hinzufügen", "+ Add a loan or credit line"), onclick: () => add(null) }));
  return {
    node,
    read: () => cards.map((c) => Object.fromEntries(c.blocks.map((x) => [x.f.id, x.b.read()])))
      .filter((r) => Object.values(r).some((v) => v !== null)),
  };
}

/* Builds the form for some sections of a questionnaire. */
function qForm(aud, sectionIds, raw, errors) {
  const def = S.meta.questionnaires[aud];
  const blocks = {};
  const sections = def.sections.filter((s) => !sectionIds || sectionIds.includes(s.id));
  const node = el("div");
  for (const s of sections) {
    node.append(el("h2", { class: "sec", text: qtext(s, "title") }));
    if (qtext(s, "intro")) node.append(el("p", { class: "section-intro", text: qtext(s, "intro") }));
    const grid = el("div", { class: "q-grid" });
    for (const q of s.questions) {
      const b = q.type === "list" ? loanList(q, raw[q.id]) : questionBlock(q, raw[q.id], errors[q.id]);
      blocks[q.id] = { q, ...b };
      grid.append(b.node);
    }
    node.append(grid);
  }
  const collect = () => Object.fromEntries(Object.entries(blocks).map(([id, b]) => [id, b.read()]));
  const refresh = () => {
    const cur = Object.assign({}, raw, collect());
    for (const { q, node: n } of Object.values(blocks)) {
      if (!q.show_if) continue;
      const v = cur[q.show_if.question];
      const exp = q.show_if.equals;
      n.hidden = typeof exp === "boolean" ? !(exp ? isTrue(v) : isFalse(v)) : v !== exp;
    }
  };
  node.addEventListener("change", refresh);
  node.addEventListener("click", () => setTimeout(refresh, 0));
  refresh();
  return { node, collect: () => Object.assign({}, raw, collect()) };
}

async function saveAnswers(aud, answers) {
  const ov = await api("PUT", `/api/cases/${S.ovCid}/answers/${aud}`, answers);
  setOv(ov);
  return ov;
}

// ------------------------------------------------------------------ documents component

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => reject(new Error(t("Datei konnte nicht gelesen werden", "Could not read the file")));
    r.readAsDataURL(file);
  });
}

function docsPanel(ov, opts) {
  const defs = Object.fromEntries(S.meta.documents.map((d) => [d.id, d]));
  const groups = {};
  for (const s of ov.documents) {
    if (opts.sources && !opts.sources.includes(s.source)) continue;
    (groups[s.source] = groups[s.source] || []).push(s);
  }
  const out = el("div");
  for (const src of ["unternehmen", "steuerberater", "berater"].filter((x) => groups[x])) {
    const list = groups[src];
    const done = list.filter((s) => s.satisfied).length;
    let title = t(...SOURCE[src]);
    if (S.me.role === "unternehmen" && src === "unternehmen") title = t("Von Ihnen", "From you");
    if (S.me.role === "unternehmen" && src === "steuerberater") title = t("Von Ihrer Steuerberatung", "From your tax advisor");
    out.append(el("div", { class: "doc-group-title" }, el("h3", { style: "margin:0", text: title }),
      el("span", { class: "pill", text: `${done}/${list.length}` })));
    if (S.me.role === "unternehmen" && src === "steuerberater") {
      out.append(el("p", { class: "small muted", style: "margin-top:-4px", text: t("Diese Unterlagen fordern wir bei Ihrer Steuerberatung an, sobald Sie sie im Schritt „Steuerberater“ einladen. Sie können sie auch selbst hochladen.", "We request these from your tax advisor once you invite them in the 'Tax advisor' step. You can also upload them yourself.") }));
    }
    for (const s of list) out.append(docCard(s, defs[s.id], opts));
  }
  return out;
}

function docCard(s, def, opts) {
  const canUpload = opts.canUpload(def);
  const status = s.satisfied ? ["ok", "✓"] : s.required ? ["need", "!"] : ["opt", "–"];
  let reqText;
  if (s.required) reqText = t("erforderlich", "required") + (s.min_count > 1 ? ` · ${t("mind.", "min.")} ${s.min_count}` : "");
  else if (s.requirement === "empfohlen") reqText = t("empfohlen", "recommended");
  else if (s.requirement === "bedingt") reqText = t("nur falls zutreffend", "only if applicable");
  else reqText = t("optional", "optional");

  const files = el("div", { class: "files" }, s.files.map((f) => {
    const mine = S.me.role === "berater" || (f.meta && f.meta.uploaded_by === S.me.email);
    return el("div", { class: "file" },
      el("span", { text: "📄" }),
      el("a", { href: `/api/cases/${S.ovCid}/documents/${f.doc_id}`, text: f.filename }),
      el("span", { class: "muted small", text: `${Math.max(1, Math.round(f.size / 1024))} KB · ${fdate(f.uploaded_at)}` }),
      f.meta && f.meta.period_end ? el("span", { class: "pill", text: `${t("Stichtag", "Date")} ${fdate(f.meta.period_end)}` }) : null,
      f.meta && f.meta.account_label ? el("span", { class: "pill", text: f.meta.account_label }) : null,
      mine ? el("button", { class: "link-btn small", text: t("entfernen", "remove"), onclick: (ev) => guarded(ev.target, async () => {
        if (!confirm(t(`${f.filename} entfernen?`, `Remove ${f.filename}?`))) return;
        setOv(await api("DELETE", `/api/cases/${S.ovCid}/documents/${f.doc_id}`));
        opts.onChange();
      }) }) : null);
  }));

  let upl = null;
  if (canUpload) {
    const input = el("input", { type: "file", accept: def.formats.map((x) => "." + x).join(","), hidden: true });
    const extras = [];
    let pEnd = null, pMonths = null, acct = null;
    if (def.needs_period) {
      pEnd = el("input", { type: "date" });
      pMonths = el("input", { type: "number", min: 1, max: 12, value: 12, style: "width:80px" });
      extras.push(el("label", { class: "mini" }, t("Stichtag", "Balance date"), pEnd), el("label", { class: "mini" }, t("Monate", "Months"), pMonths));
    }
    if (def.parser === "bank_csv") {
      acct = el("input", { type: "text", placeholder: t("z. B. Geschäftskonto", "e.g. business account") });
      extras.push(el("label", { class: "mini" }, t("Konto", "Account"), acct));
    }
    const hint = el("div", { class: "hint", text: t(`Datei hierher ziehen oder auswählen (${def.formats.join(", ").toUpperCase()})`, `Drag a file here or choose one (${def.formats.join(", ").toUpperCase()})`) });
    const pick = el("button", { class: "btn btn-ghost btn-sm", type: "button", text: s.files.length && !def.multiple ? t("Ersetzen", "Replace") : t("Datei wählen", "Choose file"), onclick: () => input.click() });
    const drop = el("div", { class: "drop" }, hint, extras, pick, input);
    const collapsed = s.satisfied && !def.multiple;
    if (collapsed) drop.hidden = true;
    const upload = (file) => guarded(pick, async () => {
      if (!file) return;
      if (file.size > S.meta.max_upload_mb * 1024 * 1024) throw new Error(t("Datei zu groß", "File too large"));
      if (def.needs_period && !pEnd.value) { pEnd.focus(); throw new Error(t("Bitte zuerst den Stichtag der Saldenliste eintragen", "Please enter the balance date of the trial balance first")); }
      hint.textContent = t(`Lade ${file.name} hoch …`, `Uploading ${file.name} …`);
      const body = { doc_type: def.id, filename: file.name, content_base64: await fileToBase64(file) };
      if (pEnd) { body.period_end = pEnd.value; body.period_months = Number(pMonths.value || 12); }
      if (acct && acct.value.trim()) body.account_label = acct.value.trim();
      const res = await api("POST", `/api/cases/${S.ovCid}/documents`, body);
      setOv(res.overview);
      toast(t(`${file.name} hochgeladen`, `${file.name} uploaded`));
      opts.onChange();
    }).finally(() => { input.value = ""; });
    input.addEventListener("change", () => upload(input.files[0]));
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload(e.dataTransfer.files[0]); });
    upl = el("div", { class: "upl" },
      collapsed ? el("button", { class: "link-btn small", type: "button", text: t("Andere Datei hochladen", "Upload a different file"),
        onclick: (ev) => { drop.hidden = false; ev.currentTarget.remove(); } }) : null,
      drop);
  }

  return el("div", { class: "doc" },
    el("div", { class: "st " + status[0], text: status[1] }),
    el("div", {},
      el("div", { class: "tt" }, qtext(def, "title"), " ", def.parser ? el("span", { class: "pill ok", style: "margin-left:6px", text: t("wird automatisch ausgewertet", "read automatically") }) : null),
      el("div", { class: "ds", text: qtext(def, "description") }),
      el("div", { class: "ds", style: "color:var(--navy-2)", text: qtext(def, "why") }),
      files),
    el("div", {}, el("span", { class: "pill " + (s.satisfied ? "ok" : s.required ? "bad" : ""), text: s.satisfied ? t("liegt vor", "received") : reqText })),
    upl);
}

// ------------------------------------------------------------------ result component (client-facing)

function bandBox(band, label, cls) {
  const tone = ["A", "B"].includes(band) ? "after" : band === "C" ? "before" : band.toLowerCase();
  return el("div", { class: `band-box ${cls || tone}` },
    el("div", { class: "lbl", text: label }), el("div", { class: "val", text: band }));
}

function verdictInfo(s) {
  if (s.verdict.startsWith("nicht")) {
    return ["bad", t("Ehrliche Einschätzung: jetzt nicht beantragen", "Honest assessment: don't apply now"),
      t("Die Schwächen liegen in der wirtschaftlichen Substanz, nicht in der Darstellung. Ein Antrag jetzt würde voraussichtlich abgelehnt und spätere Anträge belasten. Wir besprechen mit Ihnen, was sich operativ ändern müsste.",
        "The weaknesses are in the business itself, not its presentation. An application now would probably be rejected and weigh on later ones. We will discuss what would need to change operationally.")];
  }
  if (s.verdict.startsWith("bereits")) {
    return ["ok", t("Bereits finanzierbar", "Already bankable"),
      t("Ihre Zahlen tragen eine Finanzierung. Der Fokus liegt auf guten Konditionen und dem richtigen Kreditgeber.", "Your numbers support financing. The focus is on good terms and the right lender.")];
  }
  return ["ok", t("Behebbar – mit den richtigen Maßnahmen", "Fixable – with the right measures"),
    t("Die Schwächen betreffen Darstellung, Unterlagen, Produktwahl oder Sicherheiten – nicht Ihr Geschäft. Mit den Maßnahmen unten verbessert sich Ihr Profil deutlich.",
      "The weaknesses concern presentation, paperwork, product choice or collateral – not your business. The measures below improve your profile significantly.")];
}

function resultView(s, cid, advisor) {
  const [tone, title, text] = verdictInfo(s);
  const k = s.key_ratios;
  const findings = s.findings.slice().sort((a, b) => (a.fixable === b.fixable ? a.weeks_to_effect - b.weeks_to_effect : a.fixable ? 1 : -1));
  return el("div", {},
    el("div", { class: "result-hero" },
      el("div", { class: "panel" },
        el("div", { class: "panel-title" }, el("h2", { text: t("Ihr Ergebnis", "Your result") }), el("span", { class: "muted small", text: fdate(s.generated_on) })),
        el("div", { class: "band-pair" },
          bandBox(s.band, t("heute", "today")),
          el("div", { class: "arrow", text: "→" }),
          bandBox(s.band_after_remediation, t("nach Maßnahmen", "after fixes"))),
        el("p", { class: "small muted", style: "margin:14px 0 0", text: t(
          `Readiness-Band A (sehr gut) bis E (substanzielle Schwäche). Indikativer Wert ${nf(s.score, 1)} → ${nf(s.score_after_remediation, 1)} von 100. Kein Rating.`,
          `Readiness band A (very good) to E (substantive weakness). Indicative score ${nf(s.score, 1)} → ${nf(s.score_after_remediation, 1)} of 100. Not a rating.`) })),
      el("div", { class: `verdict ${tone}` },
        el("h3", { text: title }), el("p", { text: text }),
        el("div", { class: "small muted", text: t("Passender Kreditgebertyp nach den Maßnahmen", "Best-fitting lender type after the fixes") }),
        el("div", { style: "font-weight:700;color:var(--navy);margin-top:2px", text: lenderLabel(s.top_lender_after) }))),
    el("div", { class: "kpis", style: "margin:18px 0" },
      kpi(t("Eigenkapitalquote", "Equity ratio"), pct(k.eigenkapitalquote), t("wirtschaftlich", "economic")),
      kpi(t("Kapitaldienstfähigkeit", "Debt service cover"), xf(k.kapitaldienstfaehigkeit_inkl_neu), t("inkl. neuer Finanzierung", "incl. new loan")),
      kpi(t("Verschuldung / EBITDA", "Net debt / EBITDA"), xf(k.dynamischer_verschuldungsgrad), t("in Jahren", "in years")),
      kpi(t("Umsatz", "Revenue"), eur(k.umsatz), `EBITDA ${eur(k.ebitda)}`)),
    el("div", { class: "panel" },
      el("div", { class: "panel-title" }, el("h2", { text: t("Was wir gefunden haben – und was zu tun ist", "What we found – and what to do") })),
      findings.length ? findings.map((f, i) => {
        const txt = FINDING[f.rule] ? FINDING[f.rule][lang()] : [f.title, ""];
        return el("div", { class: "fcard" },
          el("div", { class: "n", text: String(i + 1) }),
          el("div", {},
            el("h4", { text: txt[0] }),
            el("div", { class: "muted", text: txt[1] }),
            el("div", { class: "meta" },
              el("span", { class: "pill " + (f.fixable ? "ok" : "bad"), text: f.fixable ? t("behebbar", "fixable") : t("nicht durch Aufbereitung behebbar", "not fixable by presentation") }),
              el("span", { class: "pill", text: t(...(CATEGORY[f.category] || [f.category, f.category])) }),
              f.fixable ? el("span", { class: "pill info", text: t(`ca. ${f.weeks_to_effect} Wochen`, `approx. ${f.weeks_to_effect} weeks`) }) : null,
              f.requires_steuerberater ? el("span", { class: "pill warn", text: t("mit Steuerberater", "with tax advisor") }) : null,
              advisor ? el("span", { class: "pill", text: f.rule }) : null)));
      }) : el("p", { class: "muted", text: t("Keine wesentlichen Befunde.", "No material findings.") })),
    el("div", { class: "actions", style: "margin-top:18px" },
      el("a", { class: "btn btn-dark", href: `/api/cases/${cid}/artifacts/diagnostik.html`, target: "_blank", rel: "noopener", text: t("Vollständigen Bericht öffnen", "Open full report") }),
      el("span", { class: "small muted", style: "align-self:center", text: t("Im Bericht: Drucken → „Als PDF speichern“.", "In the report: Print → 'Save as PDF'. The report is in German, the language of the lender.") })),
    el("p", { class: "disclaimer", text: s.disclaimer }));
}

function kpi(label, value, sub) {
  return el("div", { class: "kpi" }, el("div", { class: "l", text: label }), el("div", { class: "v", text: value }), el("div", { class: "s", text: sub || "" }));
}

// ------------------------------------------------------------------ SME (company) view

const SME_STEPS = [
  { id: "company", de: "Ihr Unternehmen", en: "Your company", sub: ["Stammdaten", "Basic data"], sections: ["unternehmen"] },
  { id: "need", de: "Ihr Vorhaben", en: "Your financing need", sub: ["Betrag, Zweck, Sicherheiten", "Amount, purpose, collateral"], sections: ["vorhaben"] },
  { id: "loans", de: "Bestehende Finanzierungen", en: "Current financing", sub: ["Kredite, Kontokorrent, Gesellschafter", "Loans, overdraft, shareholders"], sections: ["finanzierungen", "gesellschafter"] },
  { id: "behaviour", de: "Reporting & Zahlungen", en: "Reporting & payments", sub: ["BWA, Zahlungsverhalten", "BWA, payment behaviour"], sections: ["verhalten"] },
  { id: "documents", de: "Unterlagen", en: "Documents", sub: ["Hochladen", "Upload"] },
  { id: "advisor", de: "Steuerberater & Einwilligung", en: "Tax advisor & consent", sub: ["Einladen, zustimmen", "Invite, consent"], sections: ["einwilligung"] },
  { id: "submit", de: "Absenden & Ergebnis", en: "Submit & result", sub: ["Übermitteln, Bericht", "Send, report"] },
];

function smeStepDone(ov, step) {
  const secs = Object.fromEntries(ov.sections.unternehmen.map((s) => [s.id, s]));
  if (step.sections) return step.sections.every((id) => secs[id] && secs[id].complete);
  if (step.id === "documents") return ov.outstanding_documents.unternehmen.length === 0;
  if (step.id === "submit") return !!ov.submitted_at;
  return false;
}

function renderSmeCase(ov, part) {
  const doneFlags = SME_STEPS.map((s) => smeStepDone(ov, s));
  let stepId = part;
  if (!SME_STEPS.some((s) => s.id === stepId)) {
    stepId = ov.report_released || ov.submitted_at ? "submit" : (SME_STEPS[doneFlags.indexOf(false)] || SME_STEPS[0]).id;
  }
  const idx = SME_STEPS.findIndex((s) => s.id === stepId);
  const step = SME_STEPS[idx];
  const doneCount = doneFlags.filter(Boolean).length;

  const stepper = el("nav", { class: "stepper" },
    el("div", { class: "progress" },
      el("div", { class: "small muted", text: t("Ihr Fortschritt", "Your progress") }),
      el("div", { style: "font-weight:700;color:var(--navy)", text: t(`${doneCount} von ${SME_STEPS.length} Schritten erledigt`, `${doneCount} of ${SME_STEPS.length} steps done`) }),
      el("div", { class: "meter" }, el("span", { style: `width:${Math.round(doneCount / SME_STEPS.length * 100)}%` }))),
    SME_STEPS.map((s, i) => el("button", {
      class: "step" + (i === idx ? " active" : "") + (doneFlags[i] ? " done" : ""),
      onclick: () => go(`case/${ov.meta.case_id}/${s.id}`),
    }, el("span", { class: "n", text: doneFlags[i] ? "✓" : String(i + 1) }),
    el("span", {}, el("div", { class: "t", text: t(s.de, s.en) }), el("div", { class: "s", text: t(...s.sub) })))));

  const prevBtn = idx > 0 ? el("button", { class: "btn btn-ghost", text: t("← Zurück", "← Back"), onclick: () => go(`case/${ov.meta.case_id}/${SME_STEPS[idx - 1].id}`) }) : el("span");
  const nextStep = SME_STEPS[idx + 1];
  let body;

  if (step.sections) {
    const form = qForm("unternehmen", step.sections, ov.raw_answers.unternehmen || {}, ov.answer_errors.unternehmen || {});
    const save = el("button", { class: "btn btn-primary", text: nextStep ? t("Speichern & weiter →", "Save & continue →") : t("Speichern", "Save") });
    save.addEventListener("click", () => guarded(save, async () => {
      const newOv = await saveAnswers("unternehmen", form.collect());
      const errs = Object.keys(newOv.answer_errors.unternehmen).filter((k) => step.sections.some((sid) => sectionHas(sid, k)));
      if (errs.length) { toast(t("Bitte die markierten Angaben prüfen", "Please check the highlighted answers"), true); return renderSmeCase(newOv, step.id); }
      toast(t("Gespeichert", "Saved"));
      go(`case/${ov.meta.case_id}/${nextStep ? nextStep.id : step.id}`);
    }));
    const extra = step.id === "advisor" ? inviteStbPanel(ov) : null;
    body = el("div", {},
      el("div", { class: "panel" },
        el("div", { class: "small muted", text: t(`Schritt ${idx + 1} von ${SME_STEPS.length}`, `Step ${idx + 1} of ${SME_STEPS.length}`) }),
        el("h1", { style: "font-size:26px;margin:4px 0 18px", text: t(step.de, step.en) }),
        form.node),
      extra,
      el("div", { class: "wizard-nav" }, prevBtn, save));
  } else if (step.id === "documents") {
    const own = ov.outstanding_documents.unternehmen.length;
    body = el("div", {},
      el("div", { class: "panel" },
        el("div", { class: "small muted", text: t(`Schritt ${idx + 1} von ${SME_STEPS.length}`, `Step ${idx + 1} of ${SME_STEPS.length}`) }),
        el("h1", { style: "font-size:26px;margin:4px 0 6px", text: t("Unterlagen", "Documents") }),
        el("p", { class: "muted", text: t("Laden Sie hoch, was Sie selbst haben. Den Rest fordern wir bei Ihrer Steuerberatung an. Nur die Saldenliste (CSV) und Kontoumsätze (CSV) werden automatisch gelesen – PDFs lesen wir selbst.", "Upload what you have yourself; we request the rest from your tax advisor. Only the trial balance (CSV) and bank statements (CSV) are read automatically – we read PDFs ourselves.") }),
        own ? nextBanner("warn", t(`Noch ${own} Unterlage(n) von Ihnen offen`, `${own} document(s) from you still missing`), ov.outstanding_documents.unternehmen.map(docTitle).join(" · ")) : nextBanner("done", t("Alle Unterlagen von Ihnen liegen vor", "All documents from you are in"), t("Danke! Weiter zum nächsten Schritt.", "Thank you! On to the next step.")),
        docsPanel(ov, { canUpload: (d) => d.source !== "berater", onChange: () => renderSmeCase(S.ov, "documents") })),
      el("div", { class: "wizard-nav" }, prevBtn, el("button", { class: "btn btn-primary", text: t("Weiter →", "Continue →"), onclick: () => go(`case/${ov.meta.case_id}/${nextStep.id}`) })));
  } else {
    body = smeSubmitStep(ov, prevBtn, idx);
  }

  mount(shell([
    el("div", { class: "page-head" },
      el("div", {},
        el("div", { class: "crumbs", text: ov.meta.case_id }),
        el("h1", { text: t(`Willkommen, ${S.me.name.split(" ")[0]}`, `Welcome, ${S.me.name.split(" ")[0]}`) }),
        el("div", { class: "sub", text: `${ov.meta.company_name} · ${smeStatusText(ov)}` }))),
    el("div", { class: "wizard" }, stepper, el("div", { class: "wizard-body" }, body)),
  ]));
}

function sectionHas(sectionId, qid) {
  const s = S.meta.questionnaires.unternehmen.sections.find((x) => x.id === sectionId);
  return s && s.questions.some((q) => q.id === qid);
}

function smeStatusText(ov) {
  if (ov.report_released) return t("Ihr Ergebnis liegt vor", "Your result is ready");
  if (ov.submitted_at) return t("Wir analysieren Ihre Unterlagen", "We are analysing your documents");
  return t("Bitte vervollständigen Sie Ihre Angaben", "Please complete your information");
}

function inviteStbPanel(ov) {
  const invited = (ov.members || {}).steuerberater || [];
  const raw = ov.raw_answers.unternehmen || {};
  const email = el("input", { type: "email", value: raw.steuerberater_email || "" });
  const name = el("input", { type: "text", value: raw.steuerberater_kanzlei || "" });
  const btn = el("button", { class: "btn btn-dark", text: t("Steuerberatung einladen", "Invite tax advisor") });
  btn.addEventListener("click", () => guarded(btn, async () => {
    const res = await api("POST", `/api/cases/${S.ovCid}/invite`, { role: "steuerberater", email: email.value, name: name.value });
    setOv(res.overview);
    showInvite(res.invite);
    renderSmeCase(S.ov, "advisor");
  }));
  return el("div", { class: "panel" },
    el("h2", { text: t("Ihre Steuerberatung einladen", "Invite your tax advisor") }),
    el("p", { class: "muted", text: t("Ihre Kanzlei bekommt einen eigenen, auf Ihren Fall beschränkten Zugang: Sie bestätigt die Buchhaltungsfakten und lädt ihre Unterlagen direkt hoch. Keine Umgliederung ohne ihre Freigabe.", "Your tax firm gets its own access, limited to your case: it confirms the accounting facts and uploads its documents directly. No reclassification without its approval.") }),
    el("div", { class: "q-grid" },
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Kanzlei", "Firm") }), name),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("E-Mail der Kanzlei", "Firm's e-mail") }), email)),
    btn,
    invited.length ? el("p", { class: "small", style: "margin-top:12px;color:var(--teal-2)", text: t(`Eingeladen: ${invited.join(", ")}`, `Invited: ${invited.join(", ")}`) }) : null);
}

function showInvite(inv) {
  openModal((box, close) => {
    box.append(el("h3", { text: t("Einladung erstellt", "Invitation created") }));
    if (inv.created) {
      box.append(
        el("p", { text: t(`Für ${inv.email} wurde ein Zugang angelegt. Einmal-Passwort:`, `An account was created for ${inv.email}. One-time password:`) }),
        el("div", { class: "secret", text: inv.temp_password }),
        el("p", { class: "small muted", style: "margin-top:10px", text: t("In der Live-Version erhält die Person stattdessen eine E-Mail mit einem Link zum Festlegen des Passworts.", "In the live version, the person receives an e-mail with a link to set their password instead.") }));
    } else {
      box.append(el("p", { text: t(`${inv.email} hat bereits ein Konto und sieht den Fall ab sofort.`, `${inv.email} already has an account and can see the case now.`) }));
    }
    box.append(el("div", { class: "foot" }, el("button", { class: "btn btn-primary", text: "OK", onclick: close })));
  });
}

function smeSubmitStep(ov, prevBtn, idx) {
  const cid = ov.meta.case_id;
  if (ov.report_released && ov.latest_summary) {
    return el("div", {},
      nextBanner("done", t("Ihr Ergebnis ist da", "Your result is ready"), t("Ihr Berater hat die Analyse geprüft und freigegeben. Nächster Schritt: Maßnahmen gemeinsam umsetzen.", "Your advisor reviewed and released the analysis. Next: implement the measures together.")),
      resultView(ov.latest_summary, cid, false));
  }
  const missing = ov.missing_answers.unternehmen;
  const outstanding = [...ov.outstanding_documents.unternehmen, ...ov.outstanding_documents.steuerberater].map(docTitle);
  if (ov.submitted_at) {
    const stages = [
      [t("Angaben übermittelt", "Information submitted"), true],
      [t("Unterlagen vollständig", "Documents complete"), ov.documents_complete],
      [t("Analyse durch Ihren Berater", "Analysis by your advisor"), false],
      [t("Ergebnis & Maßnahmenplan", "Result & action plan"), false],
    ];
    const cur = stages.findIndex((s) => !s[1]);
    return el("div", { class: "panel" },
      el("h1", { style: "font-size:26px", text: t("Vielen Dank – wir sind dran", "Thank you – we're on it") }),
      el("p", { class: "muted", text: t(`Übermittelt am ${fdate(ov.submitted_at)}. Sie hören von uns, sobald Ihr Ergebnis freigegeben ist.`, `Submitted on ${fdate(ov.submitted_at)}. We'll be in touch as soon as your result is released.`) }),
      el("ul", { class: "timeline", style: "margin-top:18px" }, stages.map((s, i) =>
        el("li", { class: s[1] ? "done" : i === cur ? "cur" : "" }, el("span", { class: "d" }), el("b", { text: s[0] })))),
      outstanding.length ? el("div", { style: "margin-top:10px" }, nextBanner("warn", t("Noch offen", "Still missing"), outstanding.join(" · "),
        el("button", { class: "btn btn-ghost btn-sm", text: t("Zu den Unterlagen", "Go to documents"), onclick: () => go(`case/${cid}/documents`) }))) : null);
  }
  const btn = el("button", { class: "btn btn-primary btn-lg", text: t("An Ihren Berater übermitteln", "Send to your advisor"), disabled: missing.length > 0 });
  btn.addEventListener("click", () => guarded(btn, async () => {
    setOv(await api("POST", `/api/cases/${cid}/submit`));
    toast(t("Übermittelt – vielen Dank!", "Submitted – thank you!"));
    renderSmeCase(S.ov, "submit");
  }));
  return el("div", {},
    el("div", { class: "panel" },
      el("div", { class: "small muted", text: t(`Schritt ${idx + 1} von ${SME_STEPS.length}`, `Step ${idx + 1} of ${SME_STEPS.length}`) }),
      el("h1", { style: "font-size:26px;margin:4px 0 6px", text: t("Prüfen & übermitteln", "Review & submit") }),
      el("p", { class: "muted", text: t("Sobald Sie übermitteln, prüft Ihr Berater die Angaben und erstellt die Analyse. Fehlende Unterlagen können Sie auch danach noch hochladen.", "Once you submit, your advisor reviews everything and prepares the analysis. You can still upload missing documents afterwards.") }),
      missing.length ? nextBanner("warn", t("Pflichtangaben fehlen noch", "Required answers are missing"), missing.join(" · "))
        : nextBanner("done", t("Alle Pflichtangaben sind vollständig", "All required answers are complete"), t("Sie können übermitteln.", "You can submit now.")),
      outstanding.length ? el("div", {}, el("h3", { text: t("Noch offene Unterlagen", "Documents still missing") }), el("ul", { class: "list-plain" }, outstanding.map((o) => el("li", { text: o })))) : null,
      el("div", { style: "margin-top:20px" }, btn)),
    el("div", { class: "wizard-nav" }, prevBtn, el("span")));
}

// ------------------------------------------------------------------ tax advisor view

function renderStbCase(ov, part) {
  const cid = ov.meta.case_id;
  const tab = ["questionnaire", "documents", "result"].includes(part) ? part : "questionnaire";
  const a = ov.answers.steuerberater;
  const outstanding = ov.outstanding_documents.steuerberater.map(docTitle);
  let banner;
  if (a.missing_required || a.answered === 0) banner = nextBanner("", t("Bitte bestätigen Sie die Buchhaltungsfakten", "Please confirm the accounting facts"), t("Rund 10 Minuten: Kontenrahmen, Abschluss, Rangrücktritt, Steuerkonto.", "About 10 minutes: chart of accounts, year-end, subordination, tax account."));
  else if (outstanding.length) banner = nextBanner("warn", t(`${outstanding.length} Unterlage(n) von Ihnen offen`, `${outstanding.length} document(s) from you still missing`), outstanding.join(" · "));
  else banner = nextBanner("done", t("Von Ihrer Seite ist alles vollständig", "Everything from your side is complete"), ov.report_released ? t("Der Bericht und die Abstimmungsvorlage liegen vor.", "The report and the sign-off sheet are available.") : t("Sobald die Analyse vorliegt, erhalten Sie die Abstimmungsvorlage.", "You'll get the sign-off sheet once the analysis is done."));

  const tabs = el("div", { class: "tabs2" }, [["questionnaire", t("Fragebogen", "Questionnaire")], ["documents", t("Unterlagen", "Documents")], ["result", t("Abstimmung & Bericht", "Sign-off & report")]]
    .map(([id, l]) => el("button", { class: id === tab ? "active" : "", text: l, onclick: () => go(`case/${cid}/${id}`) })));

  let body;
  if (tab === "questionnaire") {
    const form = qForm("steuerberater", null, ov.raw_answers.steuerberater || {}, ov.answer_errors.steuerberater || {});
    const save = el("button", { class: "btn btn-primary", text: t("Speichern", "Save") });
    save.addEventListener("click", () => guarded(save, async () => {
      const n = await saveAnswers("steuerberater", form.collect());
      toast(Object.keys(n.answer_errors.steuerberater).length ? t("Bitte markierte Angaben prüfen", "Please check highlighted answers") : t("Gespeichert", "Saved"), Object.keys(n.answer_errors.steuerberater).length > 0);
      renderStbCase(n, "questionnaire");
    }));
    body = el("div", { class: "panel" }, el("p", { class: "muted", text: qtext(S.meta.questionnaires.steuerberater, "intro") }), form.node, el("div", { class: "wizard-nav" }, el("span"), save));
  } else if (tab === "documents") {
    body = el("div", { class: "panel" }, docsPanel(ov, { sources: ["steuerberater"], canUpload: (d) => d.source === "steuerberater", onChange: () => renderStbCase(S.ov, "documents") }));
  } else {
    const links = [];
    if (ov.artifacts.includes("abstimmung_steuerberater.html")) links.push(el("a", { class: "btn btn-dark", href: `/api/cases/${cid}/artifacts/abstimmung_steuerberater.html`, target: "_blank", rel: "noopener", text: t("Abstimmungsvorlage öffnen", "Open sign-off sheet") }));
    if (ov.artifacts.includes("anforderung_steuerberater.html")) links.push(el("a", { class: "btn btn-ghost", href: `/api/cases/${cid}/artifacts/anforderung_steuerberater.html`, target: "_blank", rel: "noopener", text: t("Anforderungsschreiben", "Request letter") }));
    body = el("div", {},
      el("div", { class: "panel" },
        el("h2", { text: t("Abstimmung der Maßnahmen", "Sign-off on proposed measures") }),
        el("p", { class: "muted", text: t("Jede vorgeschlagene Umgliederung (z. B. Rangrücktritt) braucht Ihre fachliche Freigabe. Die Vorlage listet alle Punkte mit Befund, Maßnahme und Einschränkungen.", "Every proposed reclassification (e.g. subordination) needs your professional approval. The sheet lists each point with finding, measure and caveats.") }),
        links.length ? el("div", { class: "actions" }, links) : el("p", { class: "muted", text: t("Noch nicht verfügbar – entsteht mit der Analyse.", "Not available yet – created with the analysis.") })),
      ov.report_released && ov.latest_summary ? el("div", { style: "margin-top:18px" }, resultView(ov.latest_summary, cid, false)) : null);
  }

  mount(shell([
    el("div", { class: "crumbs" }, el("a", { href: "#home", text: t("← Mandate", "← Clients") })),
    el("div", { class: "page-head" }, el("div", {},
      el("h1", { text: ov.meta.company_name }),
      el("div", { class: "sub", text: `${cid} · ${stageLabel(ov.meta.stage)}` }))),
    banner, tabs, body,
  ]));
}

// ------------------------------------------------------------------ advisor view

const BOARD = [
  { de: "Neu & Unterlagen", en: "New & documents", stages: ["neu", "unterlagen_angefordert"] },
  { de: "Bereit zur Analyse", en: "Ready for analysis", stages: ["unterlagen_vollstaendig"] },
  { de: "Analyse & Maßnahmen", en: "Analysis & fixes", stages: ["diagnostik_erstellt", "massnahmen_in_umsetzung", "beim_kreditgeber"] },
  { de: "Abgeschlossen", en: "Closed", stages: ["abgeschlossen"] },
];

function renderAdvisorHome() {
  const cases = S.cases;
  const analysed = cases.filter((c) => c.summary);
  const fixable = analysed.filter((c) => c.summary.engageable).length;
  const newBtn = el("button", { class: "btn btn-primary", text: t("+ Neuer Fall", "+ New case"), onclick: newCaseModal });
  mount(shell([
    el("div", { class: "page-head" },
      el("div", {}, el("h1", { text: t("Mandate", "Engagements") }), el("div", { class: "sub", text: t("Alle Fälle im Überblick – klicken Sie auf einen Fall, um ihn zu bearbeiten.", "All cases at a glance – click a case to work on it.") })),
      newBtn),
    el("div", { class: "kpis", style: "margin-bottom:22px" },
      kpi(t("Fälle gesamt", "Total cases"), String(cases.length), ""),
      kpi(t("In Bearbeitung", "In progress"), String(cases.filter((c) => c.stage !== "abgeschlossen").length), ""),
      kpi(t("Analysen erstellt", "Analyses done"), String(analysed.length), ""),
      kpi(t("Behebbar", "Fixable"), analysed.length ? `${fixable}/${analysed.length}` : "–", t("der analysierten Fälle", "of analysed cases"))),
    el("div", { class: "board" }, BOARD.map((col) => {
      const items = cases.filter((c) => col.stages.includes(c.stage));
      return el("div", { class: "col" },
        el("div", { class: "col-h" }, el("span", { text: t(col.de, col.en) }), el("span", { class: "pill", text: String(items.length) })),
        items.map((c) => el("button", { class: "ccard", onclick: () => go(`case/${c.case_id}`) },
          el("div", { class: "co", text: c.company_name }),
          el("div", { class: "id", text: c.case_id }),
          el("div", { class: "row" },
            el("span", { class: "pill", text: stageLabel(c.stage) }),
            c.summary ? el("span", { class: `band-chip band-${c.summary.band}`, title: c.summary.verdict, text: c.summary.band }) : null),
          c.summary ? el("div", { class: "small", style: "margin-top:8px;color:" + (c.summary.engageable ? "var(--teal-2)" : c.summary.verdict.startsWith("nicht") ? "var(--red)" : "var(--muted)"),
            text: c.summary.engageable ? t(`behebbar · ${c.summary.band} → ${c.summary.band_after_remediation}`, `fixable · ${c.summary.band} → ${c.summary.band_after_remediation}`)
              : c.summary.verdict.startsWith("nicht") ? t("nicht behebbar – Absage", "not fixable – declined") : t("bereits finanzierbar", "already bankable") }) : null)));
    })),
  ]));
}

function newCaseModal() {
  openModal((box, close) => {
    const company = el("input", { type: "text" });
    const cname = el("input", { type: "text" });
    const cemail = el("input", { type: "email" });
    const btn = el("button", { class: "btn btn-primary", text: t("Fall anlegen", "Create case") });
    btn.addEventListener("click", () => guarded(btn, async () => {
      const res = await api("POST", "/api/cases", { company_name: company.value, client_name: cname.value, client_email: cemail.value });
      close();
      await loadCases();
      if (res.invite) showInvite(res.invite);
      go(`case/${res.case.case_id}`);
    }));
    box.append(
      el("h3", { text: t("Neuer Fall", "New case") }),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Firmenname", "Company name") }), company),
      el("p", { class: "small muted", text: t("Optional: Ansprechpartner des Unternehmens einladen – er füllt dann Fragebogen und Uploads selbst aus.", "Optional: invite the company's contact – they then fill in the questionnaire and uploads themselves.") }),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Name Ansprechpartner", "Contact name") }), cname),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("E-Mail Ansprechpartner", "Contact e-mail") }), cemail),
      el("div", { class: "foot" }, el("button", { class: "btn btn-ghost", text: t("Abbrechen", "Cancel"), onclick: close }), btn));
  });
}

function advisorNext(ov) {
  const cid = ov.meta.case_id;
  const s = ov.latest_summary;
  const act = (label, fn, cls) => {
    const b = el("button", { class: "btn " + (cls || "btn-primary"), text: label });
    b.addEventListener("click", () => guarded(b, fn));
    return b;
  };
  if (ov.meta.stage === "abgeschlossen") return nextBanner("done", t("Fall abgeschlossen", "Case closed"), t("Ergebnis ist im Ergebnisprotokoll festgehalten.", "The outcome is recorded in the outcome log."));
  if (ov.answers.unternehmen.missing_required > 0 && !ov.submitted_at) {
    return nextBanner("warn", t("Warten auf das Unternehmen", "Waiting for the company"),
      t(`${ov.answers.unternehmen.missing_required} Pflichtangaben im Fragebogen fehlen noch. Anforderungsschreiben erzeugen und senden.`, `${ov.answers.unternehmen.missing_required} required answers still missing. Generate and send the request letter.`),
      act(t("Anforderungsschreiben erzeugen", "Generate request letters"), async () => { setOv(await api("POST", `/api/cases/${cid}/letters`)); go(`case/${cid}/letters`); }, "btn-dark"));
  }
  if (!ov.ready_for_diagnosis) {
    return nextBanner("warn", t("Für die Analyse fehlt noch etwas", "Something is still missing for the analysis"), ov.blocking.join(" · "),
      act(t("Schreiben erzeugen", "Generate letters"), async () => { setOv(await api("POST", `/api/cases/${cid}/letters`)); go(`case/${cid}/letters`); }, "btn-dark"));
  }
  if (!s) {
    return nextBanner("", t("Bereit zur Analyse", "Ready for analysis"), t("Alle nötigen Angaben liegen vor.", "All required information is in."),
      act(t("Analyse starten", "Run analysis"), () => runAnalysis(cid)));
  }
  if (!ov.report_released) {
    return nextBanner("", t("Bericht prüfen und freigeben", "Review and release the report"), t("Das Unternehmen sieht das Ergebnis erst nach Ihrer Freigabe.", "The company sees the result only after you release it."),
      act(t("Bericht freigeben", "Release report"), async () => { setOv(await api("POST", `/api/cases/${cid}/release`, { released: true })); toast(t("Bericht freigegeben", "Report released")); renderAdvisorCase(S.ov, "analysis"); }));
  }
  return nextBanner("", t("Maßnahmen begleiten", "Support the fixes"), t("Sobald der Kreditgeber entschieden hat: Ergebnis protokollieren.", "Once the lender has decided: record the outcome."),
    act(t("Ergebnis protokollieren", "Record outcome"), async () => go(`case/${cid}/outcome`), "btn-dark"));
}

async function runAnalysis(cid) {
  const res = await api("POST", `/api/cases/${cid}/diagnose`);
  S.lastRun = res;
  setOv(res.overview);
  toast(res.ok ? t("Analyse erstellt", "Analysis complete") : t("Analyse nicht möglich", "Analysis not possible"), !res.ok);
  go(`case/${cid}/analysis`);
}

const ADV_TABS = [
  ["overview", "Überblick", "Overview"],
  ["company", "Fragebogen Unternehmen", "Company questionnaire"],
  ["taxadvisor", "Fragebogen Steuerberatung", "Tax advisor questionnaire"],
  ["documents", "Unterlagen", "Documents"],
  ["analysis", "Analyse", "Analysis"],
  ["letters", "Schreiben", "Letters"],
  ["outcome", "Ergebnis", "Outcome"],
];

function renderAdvisorCase(ov, part) {
  const cid = ov.meta.case_id;
  const tab = ADV_TABS.some(([id]) => id === part) ? part : "overview";
  const curIdx = STAGE_ORDER.indexOf(ov.meta.stage);
  const stagebar = el("div", { class: "stagebar" }, STAGE_ORDER.map((s, i) => el("span", { class: i < curIdx ? "done" : i === curIdx ? "cur" : "", text: stageLabel(s) })));
  const tabs = el("div", { class: "tabs2" }, ADV_TABS.map(([id, de, en]) => el("button", { class: id === tab ? "active" : "", text: t(de, en), onclick: () => go(`case/${cid}/${id}`) })));
  const bodies = {
    overview: advOverview, company: (o) => advQuestionnaire(o, "unternehmen"), taxadvisor: (o) => advQuestionnaire(o, "steuerberater"),
    documents: (o) => el("div", { class: "panel" }, docsPanel(o, { canUpload: () => true, onChange: () => renderAdvisorCase(S.ov, "documents") })),
    analysis: advAnalysis, letters: advLetters, outcome: advOutcome,
  };
  mount(shell([
    el("div", { class: "crumbs" }, el("a", { href: "#home", text: t("← Alle Mandate", "← All engagements") })),
    el("div", { class: "page-head" }, el("div", {}, el("h1", { text: ov.meta.company_name }), el("div", { class: "sub", text: cid }), stagebar)),
    advisorNext(ov), tabs, bodies[tab](ov),
  ]));
}

function progressLine(label, a) {
  const p = a.total ? Math.round(a.answered / a.total * 100) : 0;
  return el("div", { style: "margin-bottom:14px" },
    el("div", { style: "display:flex;justify-content:space-between;font-size:14px" }, el("span", { text: label }),
      el("span", { class: "muted", text: `${a.answered}/${a.total}` + (a.missing_required ? ` · ${a.missing_required} ${t("Pflicht offen", "required open")}` : "") })),
    el("div", { class: "meter" }, el("span", { style: `width:${p}%;background:${a.missing_required ? "#e0a100" : "var(--teal)"}` })));
}

function advOverview(ov) {
  const members = ov.members || {};
  const outstanding = [];
  for (const [src, list] of Object.entries(ov.outstanding_documents)) for (const x of list) outstanding.push(`${t(...SOURCE[src])}: ${docTitle(x)}`);
  const inviteBtn = (role, label) => el("button", { class: "btn btn-ghost btn-sm", text: label, onclick: () => inviteModal(role) });
  const s = ov.latest_summary;
  return el("div", { class: "grid-2", style: "align-items:start" },
    el("div", {},
      el("div", { class: "panel" },
        el("h2", { text: t("Stand der Unterlagen", "Status of information") }),
        progressLine(t("Fragebogen Unternehmen", "Company questionnaire"), ov.answers.unternehmen),
        progressLine(t("Fragebogen Steuerberatung", "Tax advisor questionnaire"), ov.answers.steuerberater),
        outstanding.length ? el("div", {}, el("h3", { style: "font-size:15px;margin-top:10px", text: t("Offene Unterlagen", "Missing documents") }), el("ul", { class: "list-plain small" }, outstanding.map((x) => el("li", { text: x }))))
          : el("p", { class: "small", style: "color:var(--teal-2)", text: t("Alle erforderlichen Unterlagen liegen vor.", "All required documents are in.") }),
        ov.assembly_notes.length ? el("div", {}, el("h3", { style: "font-size:15px;margin-top:10px", text: t("Hinweise zur Datenlage", "Notes on the data") }), el("ul", { class: "list-plain small" }, ov.assembly_notes.map((x) => el("li", { text: x })))) : null),
      s ? el("div", { class: "panel" },
        el("h2", { text: t("Analyse", "Analysis") }),
        el("div", { style: "display:flex;gap:14px;align-items:center" },
          el("span", { class: `band-chip band-${s.band}`, style: "width:44px;height:44px;font-size:22px", text: s.band }),
          el("span", { class: "arrow", text: "→" }),
          el("span", { class: `band-chip band-${s.band_after_remediation}`, style: "width:44px;height:44px;font-size:22px", text: s.band_after_remediation }),
          el("div", {}, el("b", { style: "color:var(--navy)", text: s.verdict }), el("div", { class: "small muted", text: `${nf(s.score, 1)} → ${nf(s.score_after_remediation, 1)} · ${ov.report_released ? t("freigegeben", "released") : t("nicht freigegeben", "not released")}` })))) : null),
    el("div", {},
      el("div", { class: "panel" },
        el("h2", { text: t("Beteiligte", "People") }),
        el("dl", { class: "kv" },
          el("dt", { text: t("Unternehmen", "Company") }), el("dd", { text: (members.unternehmen || []).join(", ") || t("– nicht eingeladen –", "– not invited –") }),
          el("dt", { text: t("Steuerberatung", "Tax advisor") }), el("dd", { text: (members.steuerberater || []).join(", ") || t("– nicht eingeladen –", "– not invited –") })),
        el("div", { class: "actions", style: "margin-top:14px" },
          inviteBtn("unternehmen", t("Unternehmen einladen", "Invite company")),
          inviteBtn("steuerberater", t("Steuerberatung einladen", "Invite tax advisor")))),
      ov.meta.advisor_note ? el("div", { class: "panel" }, el("h2", { text: t("Notiz", "Note") }), el("p", { style: "margin:0", text: ov.meta.advisor_note })) : null,
      el("div", { class: "panel" },
        el("h2", { text: t("Verlauf", "History") }),
        el("ul", { class: "timeline" }, ov.meta.stage_history.slice().reverse().map((h, i) =>
          el("li", { class: i === 0 ? "cur" : "done" }, el("span", { class: "d" }), el("b", { text: stageLabel(h.stage) }),
            el("div", { class: "small muted", text: `${fdate(h.at)}${h.note ? " · " + h.note : ""}` })))))));
}

function inviteModal(role) {
  openModal((box, close) => {
    const name = el("input", { type: "text" });
    const email = el("input", { type: "email" });
    const btn = el("button", { class: "btn btn-primary", text: t("Einladen", "Invite") });
    btn.addEventListener("click", () => guarded(btn, async () => {
      const res = await api("POST", `/api/cases/${S.ovCid}/invite`, { role, name: name.value, email: email.value });
      setOv(res.overview);
      close();
      showInvite(res.invite);
      renderAdvisorCase(S.ov, "overview");
    }));
    box.append(el("h3", { text: role === "steuerberater" ? t("Steuerberatung einladen", "Invite tax advisor") : t("Unternehmen einladen", "Invite company") }),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("Name", "Name") }), name),
      el("label", { class: "field" }, el("span", { class: "lbl", text: t("E-Mail", "E-mail") }), email),
      el("div", { class: "foot" }, el("button", { class: "btn btn-ghost", text: t("Abbrechen", "Cancel"), onclick: close }), btn));
  });
}

function advQuestionnaire(ov, aud) {
  const form = qForm(aud, null, (ov.raw_answers || {})[aud] || {}, (ov.answer_errors || {})[aud] || {});
  const save = el("button", { class: "btn btn-primary", text: t("Speichern", "Save") });
  save.addEventListener("click", () => guarded(save, async () => {
    const n = await saveAnswers(aud, form.collect());
    const errs = Object.keys(n.answer_errors[aud]).length;
    toast(errs ? t(`${errs} Angabe(n) prüfen`, `Check ${errs} answer(s)`) : t("Gespeichert", "Saved"), errs > 0);
    renderAdvisorCase(n, aud === "unternehmen" ? "company" : "taxadvisor");
  }));
  const printLink = el("a", { href: `/forms/${aud}.html`, target: "_blank", rel: "noopener", class: "small", text: t("Druckversion", "Printable version") });
  return el("div", { class: "panel" }, el("div", { class: "panel-title" }, el("p", { class: "muted", style: "margin:0", text: qtext(S.meta.questionnaires[aud], "intro") }), printLink), form.node, el("div", { class: "wizard-nav" }, el("span"), save));
}

function advAnalysis(ov) {
  const cid = ov.meta.case_id;
  const run = S.lastRun && S.lastRun.overview && S.lastRun.overview.meta.case_id === cid ? S.lastRun : null;
  const runBtn = el("button", { class: "btn btn-dark", text: ov.latest_summary ? t("Analyse neu berechnen", "Re-run analysis") : t("Analyse starten", "Run analysis") });
  runBtn.addEventListener("click", () => guarded(runBtn, () => runAnalysis(cid)));
  const parts = [el("div", { class: "actions", style: "margin-bottom:16px" }, runBtn)];
  if (run && !run.ok) parts.push(nextBanner("warn", run.stage === "validation" ? t("Daten nicht plausibel – Analyse verweigert", "Data not plausible – analysis refused") : t("Voraussetzungen fehlen", "Prerequisites missing"), run.blocking.join(" · ")));
  const s = ov.latest_summary;
  if (!s) {
    parts.push(el("div", { class: "panel muted", text: t("Noch keine Analyse vorhanden.", "No analysis yet.") }));
    return el("div", {}, parts);
  }
  const rel = el("button", { class: "btn " + (ov.report_released ? "btn-ghost" : "btn-primary"), text: ov.report_released ? t("Freigabe zurücknehmen", "Withdraw release") : t("Bericht für das Unternehmen freigeben", "Release report to the company") });
  rel.addEventListener("click", () => guarded(rel, async () => {
    setOv(await api("POST", `/api/cases/${cid}/release`, { released: !ov.report_released }));
    toast(S.ov.report_released ? t("Freigegeben", "Released") : t("Freigabe zurückgenommen", "Release withdrawn"));
    renderAdvisorCase(S.ov, "analysis");
  }));
  parts[0].append(rel,
    el("span", { class: "pill " + (ov.report_released ? "ok" : "warn"), style: "align-self:center", text: ov.report_released ? t("für das Unternehmen sichtbar", "visible to the company") : t("nur für Sie sichtbar", "visible only to you") }));
  parts.push(
    resultView(s, cid, true),
    s.warnings.length ? nextBanner("warn", t("Datenwarnungen", "Data warnings"), s.warnings.join(" · ")) : null,
    el("div", { class: "panel", style: "margin-top:18px" },
      el("div", { class: "panel-title" }, el("h2", { text: t("Vollständiger Bericht", "Full report") }),
        el("div", { class: "actions" },
          el("a", { class: "small", href: `/api/cases/${cid}/artifacts/summary.json`, target: "_blank", rel: "noopener", text: "summary.json" }),
          el("a", { class: "small", href: `/api/cases/${cid}/artifacts/case.json`, target: "_blank", rel: "noopener", text: "case.json" }),
          el("a", { class: "small", href: `/api/cases/${cid}/artifacts/diagnostik.md`, target: "_blank", rel: "noopener", text: "Markdown" }))),
      el("iframe", { class: "report-frame", src: `/api/cases/${cid}/artifacts/diagnostik.html?t=${Date.now()}`, title: "Report" })));
  return el("div", {}, parts);
}

function advLetters(ov) {
  const cid = ov.meta.case_id;
  const btn = el("button", { class: "btn btn-dark", text: t("Anforderungsschreiben (neu) erzeugen", "(Re)generate request letters") });
  btn.addEventListener("click", () => guarded(btn, async () => { setOv(await api("POST", `/api/cases/${cid}/letters`)); toast(t("Schreiben erzeugt", "Letters generated")); renderAdvisorCase(S.ov, "letters"); }));
  const LET = {
    anforderung_unternehmen: ["Unterlagenanforderung an das Unternehmen", "Document request to the company"],
    anforderung_steuerberater: ["Anfrage an die Steuerberatung", "Request to the tax advisor"],
    abstimmung_steuerberater: ["Abstimmung der Maßnahmen mit der Steuerberatung", "Sign-off of measures with the tax advisor"],
  };
  return el("div", { class: "panel" },
    el("p", { class: "muted", text: t("Die Schreiben listen immer nur, was tatsächlich noch fehlt. Nach jedem Upload neu erzeugen.", "The letters always list only what is actually still missing. Regenerate after each upload.") }),
    btn,
    el("div", { class: "table-wrap", style: "margin-top:16px" }, el("table", { class: "data" }, el("tbody", {}, Object.entries(LET).map(([key, l]) => {
      const has = ov.artifacts.includes(`${key}.html`);
      return el("tr", {}, el("td", { text: t(...l) }), el("td", {}, has
        ? el("a", { href: `/api/cases/${cid}/artifacts/${key}.html`, target: "_blank", rel: "noopener", text: t("öffnen", "open") })
        : el("span", { class: "muted", text: key === "abstimmung_steuerberater" ? t("entsteht mit der Analyse", "created with the analysis") : t("noch nicht erzeugt", "not generated yet") })));
    })))));
}

function advOutcome(ov) {
  const cid = ov.meta.case_id;
  if (!ov.latest_summary) return el("div", { class: "panel muted", text: t("Ein Ergebnis kann erst nach der Analyse protokolliert werden.", "An outcome can be recorded only after the analysis.") });
  const OUT = {
    APPROVED: ["Bewilligt", "Approved"], APPROVED_BETTER_TERMS: ["Bewilligt zu besseren Konditionen", "Approved on better terms"],
    REJECTED: ["Abgelehnt", "Rejected"], WITHDRAWN: ["Zurückgezogen", "Withdrawn"],
    ADVISED_NOT_TO_APPLY: ["Von Antrag abgeraten", "Advised not to apply"], PENDING: ["Offen", "Pending"],
  };
  const f = {
    outcome: el("select", {}, S.meta.outcomes.map((o) => el("option", { value: o, text: t(...(OUT[o] || [o, o])) }))),
    lender_type_routed: el("select", {}, el("option", { value: "", text: t("– wie empfohlen –", "– as recommended –") }), S.meta.lenders.map((l) => el("option", { value: l.key, text: lenderLabel(l.name) }))),
    facility_amount_eur: el("input", { type: "text", inputmode: "decimal" }),
    rate_pct: el("input", { type: "text", inputmode: "decimal" }),
    weeks_to_decision: el("input", { type: "text", inputmode: "numeric" }),
    remediation_applied: el("input", { type: "text", placeholder: "R01;R04" }),
    notes: el("textarea"),
  };
  const L = {
    outcome: ["Ergebnis", "Outcome"], lender_type_routed: ["Kreditgebertyp", "Lender type"], facility_amount_eur: ["Bewilligter Betrag (€)", "Amount approved (€)"],
    rate_pct: ["Zinssatz (%)", "Interest rate (%)"], weeks_to_decision: ["Wochen bis Entscheidung", "Weeks to decision"],
    remediation_applied: ["Umgesetzte Maßnahmen", "Measures implemented"], notes: ["Notizen", "Notes"],
  };
  const btn = el("button", { class: "btn btn-primary", text: t("Ergebnis protokollieren", "Record outcome") });
  btn.addEventListener("click", () => guarded(btn, async () => {
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.value.trim()]));
    const res = await api("POST", `/api/cases/${cid}/outcome`, body);
    setOv(res.overview);
    toast(t("Ergebnis protokolliert", "Outcome recorded"));
    renderAdvisorCase(S.ov, "overview");
  }));
  return el("div", { class: "panel" },
    el("p", { class: "muted", text: t("Jedes Ergebnis landet im Ergebnisprotokoll – zusammen mit dem, was die Analyse damals gesagt hat. Dieses Protokoll ist der eigentliche Wettbewerbsvorteil. „Von Antrag abgeraten“ ist ein Beratungserfolg, kein verlorener Fall.", "Every outcome goes into the outcome log – together with what the analysis said at the time. This log is the real competitive advantage. 'Advised not to apply' is a success, not a lost case.") }),
    el("div", { class: "q-grid" }, Object.entries(f).map(([k, input]) => el("label", { class: "field" + (k === "notes" ? " wide" : ""), style: k === "notes" ? "grid-column:1/-1" : "" }, el("span", { class: "lbl", text: t(...L[k]) }), input))),
    btn);
}

// ------------------------------------------------------------------ boot

async function boot() {
  try {
    S.meta = await api("GET", "/api/meta");
  } catch (e) {
    document.getElementById("root").textContent = t("Portal nicht erreichbar.", "Portal not reachable.");
    return;
  }
  try {
    S.me = (await api("GET", "/api/auth/me")).user;
    if (S.me) await loadCases();
  } catch (_) {
    S.me = null;
  }
  S.ready = true;
  window.addEventListener("hashchange", render);
  document.addEventListener("langchange", () => render());
  render();
}

boot();
