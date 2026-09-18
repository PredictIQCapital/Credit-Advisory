/* Credit Readiness Portal -- front end.
 *
 * Plain JavaScript, no build step, no dependencies. All text reaches the DOM
 * through textContent, never innerHTML, so client-supplied names and answers
 * cannot inject markup.
 */
"use strict";

const state = {
  meta: null,
  cases: [],
  cid: null,
  tab: "uebersicht",
  overview: null,
  lastRun: null,
};

const TABS = [
  ["uebersicht", "Uebersicht"],
  ["unternehmen", "Fragebogen Unternehmen"],
  ["steuerberater", "Fragebogen Steuerberater"],
  ["unterlagen", "Unterlagen"],
  ["diagnostik", "Diagnostik"],
  ["schreiben", "Schreiben"],
  ["ergebnis", "Ergebnis"],
];

const REQ_LABEL = { pflicht: "Pflicht", empfohlen: "empfohlen", bedingt: "bedingt", optional: "optional" };

// ------------------------------------------------------------------ helpers

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (k === "value") node.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected" || k === "required") node[k] = !!v;
    else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (_) { /* non-JSON */ }
  if (!res.ok) throw new Error((data && data.error) || `Fehler ${res.status}`);
  return data;
}

let toastTimer = null;
function toast(msg, isError) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (isError ? " error" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, isError ? 7000 : 3500);
}

async function guarded(button, fn) {
  if (button) button.disabled = true;
  try { await fn(); }
  catch (e) { toast(e.message, true); }
  finally { if (button) button.disabled = false; }
}

const fmtPct = (v) => (v === null || v === undefined ? "n/a" : (v * 100).toFixed(1).replace(".", ",") + " %");
const fmtX = (v) => (v === null || v === undefined ? "n/a" : v.toFixed(2).replace(".", ",") + "x");
const fmtEur = (v) => (v === null || v === undefined ? "n/a" :
  Math.round(v).toLocaleString("de-DE") + " EUR");
const fmtDate = (iso) => { try { return new Date(iso).toLocaleString("de-DE"); } catch (_) { return iso; } };
const caseUrl = (suffix) => `/api/cases/${state.cid}${suffix || ""}`;

function callout(kind, title, items) {
  if (!items || !items.length) return null;
  return el("div", { class: `callout ${kind}` },
    el("strong", { text: title }),
    el("ul", {}, items.map((i) => el("li", { text: i }))));
}

// ------------------------------------------------------------------ routing

function setHash() {
  const h = state.cid ? `#${state.cid}/${state.tab}` : "";
  if (location.hash !== h) history.replaceState(null, "", h || location.pathname);
}

function readHash() {
  const m = location.hash.match(/^#(CRA-\d{4}-\d{4})(?:\/([a-z]+))?/);
  if (!m) return null;
  return { cid: m[1], tab: TABS.some(([t]) => t === m[2]) ? m[2] : "uebersicht" };
}

// ------------------------------------------------------------------ sidebar

async function loadCases() {
  state.cases = await api("GET", "/api/cases");
  renderCaseList();
}

function stageLabel(id) {
  const s = state.meta.stages.find((x) => x.id === id);
  return s ? s.label : id;
}

function renderCaseList() {
  const ul = document.getElementById("case-list");
  ul.replaceChildren();
  if (!state.cases.length) {
    ul.append(el("li", { class: "muted small", text: "Noch keine Faelle." }));
    return;
  }
  for (const c of state.cases) {
    ul.append(el("li", {
      class: c.case_id === state.cid ? "active" : "",
      onclick: () => openCase(c.case_id, "uebersicht"),
    },
    el("div", { class: "cl-name", text: c.company_name }),
    el("div", { class: "cl-sub", text: `${c.case_id} - ${stageLabel(c.stage)}` })));
  }
}

// ------------------------------------------------------------------ case view

async function openCase(cid, tab) {
  state.cid = cid;
  state.tab = tab || "uebersicht";
  state.lastRun = null;
  try {
    state.overview = await api("GET", caseUrl());
  } catch (e) {
    toast(e.message, true);
    state.cid = null;
    setHash();
    return;
  }
  setHash();
  renderCaseList();
  renderCase();
}

function applyOverview(ov) {
  state.overview = ov;
  const c = state.cases.find((x) => x.case_id === ov.meta.case_id);
  if (c) Object.assign(c, ov.meta);
  renderCaseList();
}

function renderCase() {
  const ov = state.overview;
  const main = document.getElementById("main");
  const tabs = el("nav", { class: "tabs" }, TABS.map(([id, label]) =>
    el("button", {
      class: id === state.tab ? "active" : "",
      text: label,
      onclick: () => { state.tab = id; setHash(); renderCase(); },
    })));
  const head = el("div", { class: "case-head" },
    el("div", {},
      el("h1", { text: ov.meta.company_name }),
      el("div", { class: "muted" }, `${ov.meta.case_id} - angelegt ${fmtDate(ov.meta.created_at)}`)),
    el("span", { class: "badge", text: ov.stage_label }));

  const renderers = {
    uebersicht: renderOverview,
    unternehmen: () => renderQuestionnaire("unternehmen"),
    steuerberater: () => renderQuestionnaire("steuerberater"),
    unterlagen: renderDocuments,
    diagnostik: renderDiagnostik,
    schreiben: renderLetters,
    ergebnis: renderOutcome,
  };
  main.replaceChildren(head, tabs, renderers[state.tab]());
}

// ------------------------------------------------------------------ overview tab

function renderOverview() {
  const ov = state.overview;
  const a = ov.answers;
  const open = Object.values(ov.outstanding_documents).reduce((n, l) => n + l.length, 0);
  const s = ov.latest_summary;

  const cards = el("div", { class: "cards" },
    card("Fragebogen Unternehmen", `${a.unternehmen.answered}/${a.unternehmen.total}`,
      a.unternehmen.missing_required ? `${a.unternehmen.missing_required} Pflichtangaben fehlen` : "Pflichtangaben vollstaendig"),
    card("Fragebogen Steuerberater", `${a.steuerberater.answered}/${a.steuerberater.total}`,
      a.steuerberater.answered === 0 ? "noch nicht beantwortet" :
        a.steuerberater.missing_required ? `${a.steuerberater.missing_required} Pflichtangaben fehlen` : "vollstaendig"),
    card("Unterlagen offen", String(open), open ? "erforderliche Unterlagen fehlen" : "alle erforderlichen liegen vor"),
    card("Diagnostik", s ? `Band ${s.band}` : "-",
      s ? `${s.score} -> ${s.score_after_remediation} (Band ${s.band_after_remediation})` :
        ov.ready_for_diagnosis ? "bereit zur Erstellung" : "noch nicht moeglich"));

  const stageSel = el("select", {}, state.meta.stages.map((st) =>
    el("option", { value: st.id, text: st.label, selected: st.id === ov.meta.stage })));
  const note = el("input", { type: "text", placeholder: "Notiz (optional)" });
  const stageBtn = el("button", { class: "secondary small", text: "Phase setzen" });
  stageBtn.addEventListener("click", () => guarded(stageBtn, async () => {
    applyOverview(await api("POST", caseUrl("/stage"), { stage: stageSel.value, note: note.value }));
    toast("Phase aktualisiert");
    renderCase();
  }));

  const outstanding = [];
  for (const [src, titles] of Object.entries(ov.outstanding_documents)) {
    for (const t of titles) outstanding.push(`${state.meta.source_labels[src]}: ${t}`);
  }
  const missing = [
    ...ov.missing_answers.unternehmen.map((m) => `Unternehmen: ${m}`),
    ...ov.missing_answers.steuerberater.map((m) => `Steuerberater: ${m}`),
  ];

  let summaryBlock = null;
  if (s) {
    summaryBlock = el("div", {},
      el("h2", { text: "Letzte Diagnostik" }),
      el("p", {}, el("span", { class: "band", text: `Band ${s.band}` }),
        ` - ${s.band_interpretation}. Einordnung: `, el("strong", { text: s.verdict }), "."),
      el("p", { class: "muted", text: `Erstellt am ${s.generated_on}. Nach Massnahmen: Band ${s.band_after_remediation} (${s.score_after_remediation}). ` +
        `Kreditgebertyp nach Massnahmen: ${s.top_lender_after || "keiner geeignet"}.` }));
  }

  return el("div", {},
    cards,
    el("h2", { text: "Phase" }),
    el("div", { class: "stage-row" }, stageSel, note, stageBtn),
    ov.ready_for_diagnosis
      ? el("div", { class: "callout ok" }, "Alle fuer die Diagnostik noetigen Angaben liegen vor.")
      : callout("bad", "Diagnostik noch nicht moeglich:", ov.blocking),
    callout("warn", "Erforderliche Unterlagen fehlen:", outstanding),
    callout("warn", "Pflichtangaben fehlen:", missing),
    callout("info", "Hinweise zur Datenlage:", ov.assembly_notes),
    summaryBlock,
    el("h2", { text: "Verlauf" }),
    el("table", { class: "simple" },
      el("thead", {}, el("tr", {}, el("th", { text: "Phase" }), el("th", { text: "Zeitpunkt" }), el("th", { text: "Notiz" }))),
      el("tbody", {}, ov.meta.stage_history.slice().reverse().map((h) =>
        el("tr", {}, el("td", { text: stageLabel(h.stage) }), el("td", { text: fmtDate(h.at) }), el("td", { text: h.note || "" }))))));
}

function card(label, value, sub) {
  return el("div", { class: "card" },
    el("div", { class: "label", text: label }),
    el("div", { class: "value", text: value }),
    el("div", { class: "sub", text: sub }));
}

// ------------------------------------------------------------------ questionnaire tab

function isTrue(v) { return v === true || v === "true" || v === "ja"; }
function isFalse(v) { return v === false || v === "false" || v === "nein"; }

function inputFor(q, value, onChange) {
  const name = `q_${q.id}_${Math.random().toString(36).slice(2, 8)}`;
  switch (q.type) {
    case "textarea":
      return el("textarea", { value: value ?? "", oninput: onChange });
    case "bool": {
      const mk = (val, label) => el("label", {},
        el("input", { type: "radio", name, value: val, checked: val === "ja" ? isTrue(value) : val === "nein" ? isFalse(value) : (value === null || value === undefined || value === ""), onchange: onChange }),
        ` ${label}`);
      return el("div", { class: "bool-group", "data-bool": "1" }, mk("ja", "ja"), mk("nein", "nein"), mk("", "keine Angabe"));
    }
    case "select":
      return el("select", { onchange: onChange },
        el("option", { value: "", text: "- bitte waehlen -" }),
        q.options.map((o) => el("option", { value: o, text: o, selected: value === o })));
    case "date":
      return el("input", { type: "date", value: value ?? "", onchange: onChange });
    case "month":
      return el("input", { type: "month", value: value ?? "", placeholder: "JJJJ-MM", onchange: onChange });
    case "int": case "money": case "percent": {
      const input = el("input", { type: "text", inputmode: "decimal", value: value ?? "", oninput: onChange });
      return q.unit ? el("div", { class: "unit-wrap" }, input, el("span", { text: q.unit })) : input;
    }
    default:
      return el("input", { type: "text", value: value ?? "", oninput: onChange });
  }
}

function readInput(q, container) {
  if (q.type === "bool") {
    const r = container.querySelector("input[type=radio]:checked");
    if (!r || r.value === "") return null;
    return r.value === "ja";
  }
  const field = container.querySelector("input, select, textarea");
  const v = field ? field.value.trim() : "";
  return v === "" ? null : v;
}

function renderQuestionnaire(aud) {
  const ov = state.overview;
  const def = state.meta.questionnaires[aud];
  const raw = JSON.parse(JSON.stringify(ov.raw_answers[aud] || {}));
  const errors = ov.answer_errors[aud] || {};
  const blocks = {};          // qid -> {q, node, read}

  const refreshVisibility = () => {
    const current = collect();
    for (const { q, node } of Object.values(blocks)) {
      if (!q.show_if) continue;
      const v = current[q.show_if.question];
      const exp = q.show_if.equals;
      node.hidden = typeof exp === "boolean" ? !(exp ? isTrue(v) : isFalse(v)) : v !== exp;
    }
  };

  function collect() {
    const out = {};
    for (const [qid, b] of Object.entries(blocks)) out[qid] = b.read();
    return out;
  }

  const sections = def.sections.map((s) => el("section", { class: "q-section" },
    el("h2", { text: s.title }),
    s.intro ? el("p", { class: "muted", text: s.intro }) : null,
    s.questions.map((q) => {
      let node;
      if (q.type === "list") {
        node = listQuestion(q, raw[q.id]);
        blocks[q.id] = { q, node, read: node._read };
      } else {
        const holder = el("div", {}, inputFor(q, raw[q.id], refreshVisibility));
        node = el("div", { class: "q" + (errors[q.id] ? " invalid" : "") },
          el("label", {}, q.label, q.required ? el("span", { class: "req", text: "*" }) : null),
          holder,
          q.help ? el("div", { class: "help", text: q.help }) : null,
          q.why ? el("div", { class: "why", text: `Warum wir fragen: ${q.why}` }) : null,
          errors[q.id] ? el("div", { class: "err", text: errors[q.id] }) : null);
        blocks[q.id] = { q, node, read: () => readInput(q, holder) };
      }
      return node;
    })));

  const status = el("span", { class: "muted small" });
  const a = ov.answers[aud];
  status.textContent = `${a.answered} von ${a.total} Fragen beantwortet` +
    (a.missing_required ? `, ${a.missing_required} Pflichtangaben offen` : "");

  const save = el("button", { text: "Speichern" });
  save.addEventListener("click", () => guarded(save, async () => {
    const answers = collect();
    // Keep keys the form does not show (e.g. an imported "_hinweis") untouched.
    const merged = Object.assign({}, raw, answers);
    applyOverview(await api("PUT", caseUrl(`/answers/${aud}`), merged));
    const e = Object.keys(state.overview.answer_errors[aud]).length;
    toast(e ? `Gespeichert - ${e} Eingabe(n) pruefen` : "Gespeichert", e > 0);
    renderCase();
  }));

  const fileInput = el("input", { type: "file", accept: ".json", hidden: true });
  fileInput.addEventListener("change", () => guarded(null, async () => {
    const f = fileInput.files[0];
    if (!f) return;
    const data = JSON.parse(await f.text());
    applyOverview(await api("PUT", caseUrl(`/answers/${aud}`), data));
    toast("Antworten importiert");
    renderCase();
  }));
  const importBtn = el("button", { class: "secondary", text: "JSON importieren",
    onclick: () => fileInput.click() });

  const wrap = el("div", {},
    el("p", { class: "muted", text: def.intro }),
    el("p", { class: "small" }, "Druckversion: ",
      el("a", { href: `/forms/${aud}.html`, target: "_blank", rel: "noopener", text: "Fragebogen oeffnen" })),
    Object.keys(errors).length ? callout("bad", "Bitte pruefen:", Object.entries(errors).map(([k, v]) => {
      const q = blocks[k] ? blocks[k].q : null;
      return `${q ? q.label : k}: ${v}`;
    })) : null,
    sections,
    el("div", { class: "sticky-save" }, save, importBtn, fileInput, status));
  refreshVisibility();
  return wrap;
}

function listQuestion(q, rows) {
  rows = Array.isArray(rows) && rows.length ? rows : [];
  const tbody = el("tbody");
  const addRow = (values) => {
    const cells = q.fields.map((f) => {
      const holder = el("div", {}, inputFor(f, values ? values[f.id] : null, () => {}));
      holder._q = f;
      return holder;
    });
    const tr = el("tr", {}, cells.map((c) => el("td", {}, c)),
      el("td", {}, el("button", { class: "danger", text: "x", title: "Zeile entfernen",
        onclick: () => tr.remove() })));
    tr._cells = cells;
    tbody.append(tr);
  };
  rows.forEach((r) => addRow(r));
  const node = el("div", { class: "q" },
    el("label", { text: q.label }),
    q.why ? el("div", { class: "why", text: `Warum wir fragen: ${q.why}` }) : null,
    el("div", { class: "list-wrap" },
      el("table", { class: "list-table" },
        el("thead", {}, el("tr", {}, q.fields.map((f) =>
          el("th", {}, f.label, f.required ? el("span", { class: "req", text: "*" }) : null,
            f.unit ? el("span", { class: "muted", text: ` (${f.unit})` }) : null)), el("th"))),
        tbody)),
    el("button", { class: "secondary small", text: "+ Zeile hinzufuegen", onclick: () => addRow(null) }));
  node._read = () => [...tbody.children].map((tr) => {
    const row = {};
    for (const c of tr._cells) row[c._q.id] = readInput(c._q, c);
    return row;
  }).filter((row) => Object.values(row).some((v) => v !== null));
  return node;
}

// ------------------------------------------------------------------ documents tab

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = () => reject(new Error("Datei konnte nicht gelesen werden"));
    r.readAsDataURL(file);
  });
}

function renderDocuments() {
  const ov = state.overview;
  const defs = Object.fromEntries(state.meta.documents.map((d) => [d.id, d]));
  const groups = {};
  for (const s of ov.documents) (groups[s.source] = groups[s.source] || []).push(s);

  const out = [el("p", { class: "muted" },
    "Automatisch ausgewertet werden nur die DATEV-Summen- und Saldenliste (CSV) und Kontoumsaetze (CSV). ",
    "PDF-Unterlagen werden abgelegt und von Ihnen gelesen - aus einem PDF wird nie automatisch eine Zahl uebernommen. ",
    `Maximal ${state.meta.max_upload_mb} MB pro Datei.`)];

  for (const [src, list] of Object.entries(groups)) {
    out.push(el("h2", { text: `Von: ${state.meta.source_labels[src]}` }));
    for (const s of list) out.push(documentCard(s, defs[s.id]));
  }
  return el("div", {}, out);
}

function documentCard(s, def) {
  let badge;
  if (s.satisfied) badge = el("span", { class: "badge ok", text: "liegt vor" });
  else if (s.required) badge = el("span", { class: "badge bad", text: "fehlt" });
  else badge = el("span", { class: "badge", text: "offen" });

  const req = s.required ? `erforderlich${s.min_count > 1 ? ` (mind. ${s.min_count})` : ""}` :
    REQ_LABEL[s.requirement] + (s.requirement === "bedingt" ? `: ${s.condition_text}` : "");

  const files = el("ul", { class: "doc-files" }, s.files.map((f) => el("li", {},
    el("a", { href: caseUrl(`/documents/${f.doc_id}`), text: f.filename }),
    el("span", { class: "muted", text: `${(f.size / 1024).toFixed(0)} KB, ${fmtDate(f.uploaded_at)}` }),
    f.meta && f.meta.period_end ? el("span", { class: "badge", text: `Stichtag ${f.meta.period_end}, ${f.meta.period_months || 12} Mon.` }) : null,
    f.meta && f.meta.account_label ? el("span", { class: "badge", text: f.meta.account_label }) : null,
    el("button", { class: "danger", text: "entfernen", onclick: (ev) => guarded(ev.target, async () => {
      if (!confirm(`${f.filename} entfernen?`)) return;
      applyOverview(await api("DELETE", caseUrl(`/documents/${f.doc_id}`)));
      renderCase();
    }) }))));

  const fileInput = el("input", { type: "file", accept: def.formats.map((x) => "." + x).join(",") });
  const extra = [];
  let periodEnd, periodMonths, accountLabel;
  if (def.needs_period) {
    periodEnd = el("input", { type: "date" });
    periodMonths = el("input", { type: "number", min: 1, max: 12, value: 12, style: "width:80px" });
    extra.push(el("label", { class: "field" }, "Stichtag", periodEnd),
      el("label", { class: "field" }, "Monate", periodMonths));
  }
  if (def.parser === "bank_csv") {
    accountLabel = el("input", { type: "text", placeholder: "z. B. Kontokorrent Sparkasse" });
    extra.push(el("label", { class: "field" }, "Kontobezeichnung", accountLabel));
  }
  const up = el("button", { class: "small", text: s.files.length && !def.multiple ? "Ersetzen" : "Hochladen" });
  up.addEventListener("click", () => guarded(up, async () => {
    const f = fileInput.files[0];
    if (!f) throw new Error("Bitte zuerst eine Datei waehlen");
    if (f.size > state.meta.max_upload_mb * 1024 * 1024) throw new Error("Datei zu gross");
    if (def.needs_period && !periodEnd.value) throw new Error("Bitte den Stichtag der SuSa angeben");
    const body = {
      doc_type: def.id,
      filename: f.name,
      content_base64: await fileToBase64(f),
    };
    if (periodEnd) { body.period_end = periodEnd.value; body.period_months = Number(periodMonths.value || 12); }
    if (accountLabel && accountLabel.value.trim()) body.account_label = accountLabel.value.trim();
    const res = await api("POST", caseUrl("/documents"), body);
    applyOverview(res.overview);
    toast(`${f.name} hochgeladen`);
    renderCase();
  }));

  return el("div", { class: "doc" },
    el("div", { class: "doc-head" },
      el("span", { class: "doc-title", text: def.title }),
      el("span", {}, badge, " ", el("span", { class: "badge", text: req }),
        def.parser ? el("span", { class: "badge ok", text: "wird ausgewertet", style: "margin-left:4px" }) : null)),
    el("div", { class: "desc", text: def.description }),
    el("div", { class: "desc", text: `Warum: ${def.why}` }),
    files,
    el("div", { class: "upload-row" }, fileInput, extra, up));
}

// ------------------------------------------------------------------ diagnostic tab

function renderDiagnostik() {
  const ov = state.overview;
  const run = state.lastRun;
  const btn = el("button", { text: ov.latest_summary ? "Diagnostik neu erstellen" : "Diagnostik erstellen" });
  btn.addEventListener("click", () => guarded(btn, async () => {
    const res = await api("POST", caseUrl("/diagnose"));
    state.lastRun = res;
    applyOverview(res.overview);
    toast(res.ok ? "Diagnostik erstellt" : "Diagnostik nicht moeglich", !res.ok);
    renderCase();
  }));

  const parts = [el("div", { class: "stage-row" }, btn,
    el("span", { class: "muted small", text: "Liest SuSa, Kontoumsaetze und beide Frageboegen neu ein." }))];

  if (run && !run.ok) {
    parts.push(callout("bad", run.stage === "validation"
      ? "Die Daten sind nicht plausibel - die Diagnostik wird verweigert:"
      : "Es fehlen Voraussetzungen:", run.blocking));
  } else if (!ov.latest_summary && !ov.ready_for_diagnosis) {
    parts.push(callout("bad", "Noch nicht moeglich:", ov.blocking));
  }

  const s = ov.latest_summary;
  if (s) {
    const k = s.key_ratios;
    parts.push(
      el("div", { class: "cards", style: "margin-top:14px" },
        card("Readiness-Band", s.band, s.band_interpretation),
        card("Indikativer Wert", String(s.score), `nach Massnahmen ${s.score_after_remediation} (Band ${s.band_after_remediation})`),
        card("Einordnung", s.engageable ? "behebbar" : s.verdict.startsWith("bereits") ? "finanzierbar" : "nicht behebbar", s.verdict),
        card("Kreditgebertyp", s.top_lender_after ? "passend" : "-", s.top_lender_after || "kein geeigneter Typ")),
      el("div", { class: "cards", style: "margin-top:12px" },
        card("EK-Quote (wirtsch.)", fmtPct(k.eigenkapitalquote), ""),
        card("DSCR inkl. neu", fmtX(k.kapitaldienstfaehigkeit_inkl_neu), ""),
        card("Nettoverschuldung / EBITDA", fmtX(k.dynamischer_verschuldungsgrad), ""),
        card("Umsatz", fmtEur(k.umsatz), `EBITDA ${fmtEur(k.ebitda)}`)),
      callout("warn", "Datenwarnungen:", s.warnings),
      el("div", { class: "links" },
        el("a", { href: caseUrl("/artifacts/diagnostik.html"), target: "_blank", rel: "noopener", text: "Bericht in neuem Fenster (drucken / als PDF speichern)" }),
        el("a", { href: caseUrl("/artifacts/diagnostik.md"), target: "_blank", rel: "noopener", text: "Markdown" }),
        el("a", { href: caseUrl("/artifacts/summary.json"), target: "_blank", rel: "noopener", text: "Zusammenfassung (JSON)" }),
        el("a", { href: caseUrl("/artifacts/case.json"), target: "_blank", rel: "noopener", text: "Falldaten (JSON)" }),
        el("a", { href: caseUrl("/artifacts/abstimmung_steuerberater.html"), target: "_blank", rel: "noopener", text: "Abstimmung mit Steuerberater" })),
      el("iframe", { class: "report-frame", src: caseUrl(`/artifacts/diagnostik.html?t=${Date.now()}`), title: "Diagnostik-Bericht" }));
  }
  return el("div", {}, parts);
}

// ------------------------------------------------------------------ letters tab

function renderLetters() {
  const ov = state.overview;
  const btn = el("button", { text: "Anforderungsschreiben (neu) erzeugen" });
  btn.addEventListener("click", () => guarded(btn, async () => {
    applyOverview(await api("POST", caseUrl("/letters")));
    toast("Schreiben erzeugt");
    renderCase();
  }));
  const rows = Object.entries(state.meta.letters).map(([key, label]) => {
    const has = ov.artifacts.includes(`${key}.html`);
    return el("tr", {},
      el("td", { text: label }),
      el("td", {}, has
        ? el("span", {},
          el("a", { href: caseUrl(`/artifacts/${key}.html`), target: "_blank", rel: "noopener", text: "oeffnen" }), " | ",
          el("a", { href: caseUrl(`/artifacts/${key}.md`), target: "_blank", rel: "noopener", text: "Markdown" }))
        : el("span", { class: "muted", text: key === "abstimmung_steuerberater" ? "entsteht mit der Diagnostik" : "noch nicht erzeugt" })));
  });
  return el("div", {},
    el("p", { class: "muted", text: "Die Schreiben listen immer den aktuellen Stand: nach jedem Upload neu erzeugen, dann stehen nur noch die tatsaechlich fehlenden Unterlagen darin." }),
    btn,
    el("table", { class: "simple", style: "margin-top:14px" },
      el("thead", {}, el("tr", {}, el("th", { text: "Schreiben" }), el("th", { text: "" }))),
      el("tbody", {}, rows)),
    el("p", { class: "small muted", text: "Versand bitte ueber einen sicheren Kanal, nicht per ungeschuetzter E-Mail." }));
}

// ------------------------------------------------------------------ outcome tab

function renderOutcome() {
  const ov = state.overview;
  if (!ov.latest_summary) {
    return el("div", { class: "callout info" }, "Ein Ergebnis kann erst nach einer Diagnostik protokolliert werden.");
  }
  const f = {
    outcome: el("select", {}, state.meta.outcomes.map((o) => el("option", { value: o, text: o }))),
    lender_type_routed: el("select", {}, el("option", { value: "", text: "- wie empfohlen -" }),
      state.meta.lenders.map((l) => el("option", { value: l.key, text: l.name }))),
    remediation_applied: el("input", { type: "text", placeholder: "z. B. R01;R04" }),
    facility_amount_eur: el("input", { type: "text", inputmode: "decimal" }),
    rate_pct: el("input", { type: "text", inputmode: "decimal" }),
    weeks_to_decision: el("input", { type: "text", inputmode: "numeric" }),
    notes: el("textarea"),
  };
  const labels = {
    outcome: "Ergebnis", lender_type_routed: "Kreditgebertyp", remediation_applied: "Umgesetzte Massnahmen",
    facility_amount_eur: "Bewilligter Betrag (EUR)", rate_pct: "Zinssatz (%)", weeks_to_decision: "Wochen bis Entscheidung",
    notes: "Notizen",
  };
  const btn = el("button", { text: "Ergebnis protokollieren" });
  btn.addEventListener("click", () => guarded(btn, async () => {
    const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.value.trim()]));
    const res = await api("POST", caseUrl("/outcome"), body);
    applyOverview(res.overview);
    toast("Ergebnis protokolliert");
    renderCase();
  }));
  return el("div", {},
    el("p", { class: "muted" },
      "Jedes Ergebnis wird im Ergebnisprotokoll (outcome_log.csv) festgehalten - zusammen mit dem, was die Diagnostik damals gesagt hat. ",
      "Dieses Protokoll ist laut Blueprint der eigentliche Wettbewerbsvorteil. ",
      "ADVISED_NOT_TO_APPLY ist ein Beratungserfolg, kein verlorener Fall."),
    el("div", { class: "form-grid" }, Object.entries(f).map(([k, input]) =>
      el("div", { class: "field" }, el("label", { text: labels[k] }), input))),
    el("div", { style: "margin-top:14px" }, btn));
}

// ------------------------------------------------------------------ boot

async function boot() {
  try {
    state.meta = await api("GET", "/api/meta");
    await loadCases();
  } catch (e) {
    toast(`Portal nicht erreichbar: ${e.message}`, true);
    return;
  }
  document.getElementById("new-case-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const input = document.getElementById("new-case-name");
    guarded(ev.submitter, async () => {
      const meta = await api("POST", "/api/cases", { company_name: input.value });
      input.value = "";
      await loadCases();
      await openCase(meta.case_id, "unternehmen");
      toast(`Fall ${meta.case_id} angelegt`);
    });
  });
  window.addEventListener("hashchange", () => {
    const h = readHash();
    if (h && (h.cid !== state.cid || h.tab !== state.tab)) openCase(h.cid, h.tab);
  });
  const h = readHash();
  if (h) openCase(h.cid, h.tab);
}

boot();
