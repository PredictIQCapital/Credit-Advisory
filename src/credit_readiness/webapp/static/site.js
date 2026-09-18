/* Shared by all pages: language switch (remembered per browser). */
"use strict";
(function () {
  function initialLang() {
    try {
      const saved = localStorage.getItem("cra_lang");
      if (saved === "de" || saved === "en") return saved;
    } catch (_) { /* storage blocked */ }
    return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
  }
  function setLang(lang) {
    document.documentElement.setAttribute("data-lang", lang);
    document.documentElement.lang = lang;
    try { localStorage.setItem("cra_lang", lang); } catch (_) { /* ignore */ }
    document.querySelectorAll(".lang-toggle button").forEach((b) => {
      b.classList.toggle("active", b.dataset.lang === lang);
    });
    document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
  }
  window.CRA_LANG = { get: () => document.documentElement.getAttribute("data-lang") || "de", set: setLang };
  // Loaded in <head>, so the right language is set before the first paint;
  // the toggle buttons exist only once the body has been parsed.
  setLang(initialLang());
  document.addEventListener("DOMContentLoaded", () => setLang(window.CRA_LANG.get()));
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest(".lang-toggle button");
    if (b) setLang(b.dataset.lang);
  });
})();
