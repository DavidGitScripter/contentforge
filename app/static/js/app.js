// App-Shell: Router (Hash-basiert, deep-linkbar), Navigation, Polling, Dialoge, Toasts.
import { api, onApiKeyRequired } from "./api.js";
import { debounce, html, ico, initials, prettyModel, storage } from "./lib.js";
import approvals from "./views/approvals.js";
import dashboard from "./views/dashboard.js";
import knowledge from "./views/knowledge.js";
import pages from "./views/pages.js";
import planning from "./views/planning.js";
import runDetail from "./views/run-detail.js";
import runs from "./views/runs.js";
import system from "./views/system.js";

const $ = (selector) => document.querySelector(selector);
const main = $("#main");

const NAV = [
  { id: "uebersicht", href: "#/", label: "Übersicht", icon: "squares-four" },
  { id: "planung", href: "#/planung", label: "Content-Planung", icon: "grid-four" },
  { id: "freigaben", href: "#/freigaben", label: "Freigaben", icon: "tray", count: "awaiting_review" },
  { id: "vorgaenge", href: "#/vorgaenge", label: "Vorgänge", icon: "list-bullets" },
  { id: "seiten", href: "#/seiten", label: "Veröffentlicht", icon: "globe-simple" },
  null,
  { id: "wissen", href: "#/wissen", label: "Wissensbasis", icon: "books" },
  { id: "system", href: "#/system", label: "System", icon: "gear-six" },
];

const ROUTES = [
  { pattern: /^\/$/, view: dashboard, nav: "uebersicht" },
  { pattern: /^\/planung$/, view: planning, nav: "planung" },
  { pattern: /^\/freigaben$/, view: approvals, nav: "freigaben" },
  { pattern: /^\/vorgaenge$/, view: runs, nav: "vorgaenge" },
  { pattern: /^\/vorgaenge\/([\w-]+)$/, view: runDetail, nav: "vorgaenge" },
  { pattern: /^\/seiten$/, view: pages, nav: "seiten" },
  { pattern: /^\/wissen$/, view: knowledge, nav: "wissen" },
  { pattern: /^\/system$/, view: system, nav: "system" },
];

// --------------------------------------------------------------------------- Globaler Zustand

export const app = {
  config: null,
  stats: null,
  meta: { industries: [], services: [] },
  navigate(hash) {
    if (location.hash === hash) render({ reason: "refresh" });
    else location.hash = hash;
  },
  setQuery(params) {
    const { path, query } = parseHash();
    Object.entries(params).forEach(([key, value]) => (value ? query.set(key, value) : query.delete(key)));
    const qs = query.toString();
    history.replaceState(null, "", `#${path}${qs ? `?${qs}` : ""}`);
    render({ reason: "query" });
  },
  industry: (id) => app.meta.industries.find((i) => i.id === id)?.name || id,
  service: (id) => app.meta.services.find((s) => s.id === id)?.name || id,
  actor: () => storage.get("actor"),
  setActor(name) {
    storage.set("actor", name.trim());
    renderUser();
  },
  refresh: () => render({ reason: "refresh" }),
  refreshShell,
  toast,
  confirm,
  prompt: promptDialog,
};

// --------------------------------------------------------------------------- Router

let current = { key: null, route: null, data: null, signature: "", cleanup: null, loadedAt: 0 };
let renderToken = 0;

function parseHash() {
  const value = location.hash.slice(1) || "/";
  const [path, qs = ""] = value.split("?");
  return { path: path || "/", query: new URLSearchParams(qs) };
}

function match(path) {
  for (const route of ROUTES) {
    const m = path.match(route.pattern);
    if (m) return { route, params: m.slice(1) };
  }
  return null;
}

const skeleton = () => html`
  <div class="page-head"><div style="width:min(420px,70%)"><span class="skeleton" style="height:24px"></span><span class="skeleton"></span></div></div>
  <span class="skeleton block"></span><span class="skeleton block" style="height:320px;margin-top:16px"></span>`;

function renderError(error) {
  main.innerHTML = html`
    <section class="panel"><div class="empty">
      <div class="empty-icon">${ico("warning-circle", { size: 22 })}</div>
      <h2>Daten konnten nicht geladen werden</h2>
      <p>${error.message || "Unbekannter Fehler"}</p>
      <button class="btn" type="button" data-shell="retry">${ico("arrow-clockwise")} Erneut versuchen</button>
    </div></section>`;
}

async function render({ reason = "navigate" } = {}) {
  const { path, query } = parseHash();
  const found = match(path);
  if (!found) {
    location.replace("#/");
    return;
  }
  const { route, params } = found;
  const key = `${path}`;
  const sameRoute = current.key === key;
  const ctx = { params, query, app };
  const token = ++renderToken;

  if (!sameRoute) {
    current.cleanup?.();
    current = { key, route, data: null, signature: "", cleanup: null, loadedAt: 0 };
    main.innerHTML = skeleton();
    updateNav(route.nav);
    closeMenu();
  }

  let data;
  try {
    data = await route.view.load(ctx);
  } catch (error) {
    if (token === renderToken) renderError(error);
    return;
  }
  if (token !== renderToken) return;

  const signature = route.view.signature ? route.view.signature(data, ctx) : JSON.stringify(data);
  const needsPaint = !sameRoute || reason !== "poll" || signature !== current.signature;
  current.data = data;
  current.loadedAt = Date.now();
  if (!needsPaint) return;

  if (reason === "poll" && isEditing()) return; // Eingaben nie durch Polling überschreiben
  current.signature = signature;
  current.cleanup?.();
  main.innerHTML = route.view.render(data, ctx);
  current.cleanup = route.view.mount?.(main, data, ctx) || null;

  const title = typeof route.view.title === "function" ? route.view.title(data, ctx) : route.view.title;
  document.title = `${title} | ContentForge`;
  renderBreadcrumb(route.view.crumbs ? route.view.crumbs(data, ctx) : [{ label: title }]);

  if (!sameRoute) {
    window.scrollTo(0, 0);
    if (reason === "navigate") main.focus({ preventScroll: true });
  }
}

function isEditing() {
  const el = document.activeElement;
  return el && main.contains(el) && el.matches("input, textarea, select");
}

// --------------------------------------------------------------------------- Shell: Navigation, Kopfzeile, Umgebung

function renderNav() {
  const items = NAV.map((item) =>
    item === null
      ? html`<li role="presentation"><div class="nav-sep"></div></li>`
      : html`<li><a href="${item.href}" data-nav="${item.id}">${ico(item.icon, { size: 19 })}<span class="nav-label">${item.label}</span>${
          item.count ? html`<span class="nav-count" data-count="${item.count}" hidden></span>` : ""
        }</a></li>`,
  );
  $("#nav").innerHTML = html`<ul class="nav">${items}</ul>`;
  $("#menu-btn").innerHTML = ico("list", { size: 20 });
  $("#search-form").insertAdjacentHTML("afterbegin", String(ico("magnifying-glass", { size: 16 })));
}

function updateNav(active) {
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function renderBreadcrumb(crumbs) {
  const items = crumbs.map((crumb, i) => {
    const last = i === crumbs.length - 1;
    const sep = i > 0 ? ico("caret-right", { size: 12 }) : "";
    return last
      ? html`<li>${sep}<span aria-current="page">${crumb.label}</span></li>`
      : html`<li>${sep}<a href="${crumb.href}">${crumb.label}</a></li>`;
  });
  $("#breadcrumb").innerHTML = html`<ol>${items}</ol>`;
}

function renderEnv() {
  const c = app.config;
  if (!c) return;
  const used = c.daily_budget_usd ? Math.min(1, c.cost_today_usd / c.daily_budget_usd) : 0;
  const usd = (v) => new Intl.NumberFormat("de-DE", { style: "currency", currency: "USD" }).format(v);
  $("#sidebar-env").innerHTML = html`
    <div class="env-row"><span>KI-Modell</span><strong>${c.provider === "anthropic" ? prettyModel(c.model) : "Demo (offline)"}</strong></div>
    <div class="env-row"><span>Veröffentlichung</span><strong>${c.publisher === "azure_blob" ? "Azure" : "Lokal"}</strong></div>
    <div>
      <div class="env-row"><span>Budget heute</span><strong>${usd(c.cost_today_usd)} von ${usd(c.daily_budget_usd)}</strong></div>
      <div class="meter ${used > 0.8 ? "is-high" : ""}" role="meter" aria-label="Tagesbudget verbraucht"
           aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(used * 100)}"><span style="width:${(used * 100).toFixed(1)}%"></span></div>
    </div>`;
}

function renderCounts() {
  const stats = app.stats;
  if (!stats) return;
  document.querySelectorAll("[data-count]").forEach((el) => {
    const value = stats[el.dataset.count] || 0;
    el.textContent = value;
    el.hidden = value === 0;
    el.setAttribute("aria-label", `${value} offen`);
  });
}

function renderUser() {
  const name = app.actor();
  $("#user-chip").innerHTML = html`<span class="avatar" aria-hidden="true">${name ? initials(name) : ico("user-circle", { size: 18 })}</span><span class="user-name">${name || "Namen festlegen"}</span>`;
  $("#user-chip").setAttribute("aria-label", name ? `Angemeldet als ${name}, Einstellungen öffnen` : "Anzeigenamen festlegen");
}

async function refreshShell() {
  try {
    const [config, stats] = await Promise.all([api.config(), api.stats()]);
    app.config = config;
    app.stats = stats;
    renderEnv();
    renderCounts();
  } catch {
    /* Shell-Daten sind nicht kritisch; nächster Versuch beim nächsten Intervall */
  }
}

// --------------------------------------------------------------------------- Mobile Navigation

function openMenu() {
  $("#sidebar").classList.add("is-open");
  $("#scrim").classList.add("is-open");
  $("#menu-btn").setAttribute("aria-expanded", "true");
}

function closeMenu() {
  $("#sidebar").classList.remove("is-open");
  $("#scrim").classList.remove("is-open");
  $("#menu-btn").setAttribute("aria-expanded", "false");
}

// --------------------------------------------------------------------------- Toasts

const TOAST_ICON = { ok: "check-circle", err: "warning-circle", info: "info" };

function toast(title, { message = "", tone = "ok", timeout = 5000 } = {}) {
  const el = document.createElement("div");
  el.className = `toast tone-${tone}`;
  el.setAttribute("role", tone === "err" ? "alert" : "status");
  el.innerHTML = html`${ico(TOAST_ICON[tone] || "info", { size: 18 })}<div><strong>${title}</strong>${message ? html`<span>${message}</span>` : ""}</div>
    <button class="icon-btn" type="button" aria-label="Meldung schließen">${ico("x", { size: 14 })}</button>`;
  el.querySelector("button").addEventListener("click", () => el.remove());
  $("#toasts").append(el);
  if (timeout) setTimeout(() => el.remove(), tone === "err" ? timeout * 2 : timeout);
}

// --------------------------------------------------------------------------- Dialoge (nativ, fokussicher)

let dialogListeners = null;

function openDialog({ title, body, confirmLabel, tone = "primary", field = null, focusCancel = false }) {
  const dialog = $("#dialog");
  const btnClass = tone === "danger" ? "btn btn-danger" : tone === "warn" ? "btn btn-warn" : "btn btn-primary";
  dialog.innerHTML = html`
    <form method="dialog" novalidate>
      <div class="dialog-head"><h2 id="dialog-title">${title}</h2></div>
      <div class="dialog-body">${body}${
        field
          ? html`<div class="field"><label for="dialog-input">${field.label}</label>
              <input class="input" id="dialog-input" name="value" type="${field.type || "text"}" autocomplete="${field.autocomplete || "off"}" value="${field.value || ""}" required>
              ${field.hint ? html`<span class="hint">${field.hint}</span>` : ""}</div>`
          : ""
      }</div>
      <div class="dialog-foot">
        <button class="btn" value="cancel" type="submit" formnovalidate ${focusCancel ? "autofocus" : ""}>Abbrechen</button>
        <button class="${btnClass}" value="confirm" type="submit">${confirmLabel}</button>
      </div>
    </form>`;
  dialog.setAttribute("aria-labelledby", "dialog-title");
  const form = dialog.querySelector("form");
  const input = dialog.querySelector("#dialog-input");
  dialogListeners?.abort(); // Listener eines vorherigen Dialogs dürfen nie eine alte Aktion bestätigen
  const listeners = new AbortController();
  dialogListeners = listeners;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok) => {
      if (settled) return;
      settled = true;
      listeners.abort();
      if (dialog.open) dialog.close();
      resolve(field ? (ok ? input.value.trim() || null : null) : ok);
    };
    // "submit" feuert synchron beim Klick; "close"/"cancel" (Esc) sind die Rückfallebene.
    const opts = { signal: listeners.signal };
    form.addEventListener(
      "submit",
      (event) => {
        const ok = event.submitter?.value === "confirm";
        if (ok && field && !input.value.trim()) {
          event.preventDefault();
          input.focus();
          return;
        }
        finish(ok);
      },
      opts,
    );
    dialog.addEventListener("cancel", () => finish(false), opts);
    dialog.addEventListener("close", () => finish(dialog.returnValue === "confirm"), opts);
    dialog.returnValue = "";
    dialog.showModal();
    if (field && !focusCancel) input.focus();
  });
}

function confirm(options) {
  return openDialog(options);
}

function promptDialog(options) {
  return openDialog(options);
}

onApiKeyRequired(() =>
  promptDialog({
    title: "API-Schlüssel erforderlich",
    body: html`<p>Diese Installation schützt schreibende Aktionen mit einem API-Schlüssel. Er wird nur in diesem Browser gespeichert.</p>`,
    confirmLabel: "Speichern",
    field: { label: "API-Schlüssel", type: "password", autocomplete: "current-password" },
  }),
);

// --------------------------------------------------------------------------- Start

function bindShell() {
  window.addEventListener("hashchange", () => render({ reason: "navigate" }));
  $("#menu-btn").addEventListener("click", () =>
    $("#sidebar").classList.contains("is-open") ? closeMenu() : openMenu(),
  );
  $("#scrim").addEventListener("click", closeMenu);
  $("#search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const q = $("#search").value.trim();
    app.navigate(`#/vorgaenge${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  });
  document.addEventListener("keydown", (event) => {
    const typing = event.target.matches?.("input, textarea, select, [contenteditable]");
    if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      $("#search").focus();
    }
    if (event.key === "Escape" && $("#sidebar").classList.contains("is-open")) closeMenu();
  });
  main.addEventListener("click", (event) => {
    if (event.target.closest("[data-shell='retry']")) render({ reason: "refresh" });
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick(true);
  });
}

let lastShell = 0;
async function tick(force = false) {
  if (document.hidden) return;
  const now = Date.now();
  if (force || now - lastShell > 5000) {
    lastShell = now;
    refreshShell();
  }
  const view = current.route?.view;
  if (!view?.poll || !current.data) return;
  const interval = typeof view.poll === "function" ? view.poll(current.data) : view.poll;
  if (force || now - current.loadedAt > interval) render({ reason: "poll" });
}

async function start() {
  renderNav();
  renderUser();
  bindShell();
  try {
    const [config, stats, matrix] = await Promise.all([api.config(), api.stats(), api.matrix()]);
    Object.assign(app, { config, stats });
    app.meta = { industries: matrix.industries, services: matrix.services };
    renderEnv();
    renderCounts();
  } catch (error) {
    renderError(error);
  }
  await render({ reason: "initial" });
  setInterval(tick, 1000);
}

// Suchfeld mit aktueller Route synchron halten (z. B. nach Deep-Link auf #/vorgaenge?q=...)
window.addEventListener(
  "hashchange",
  debounce(() => {
    const { path, query } = parseHash();
    if (path === "/vorgaenge") $("#search").value = query.get("q") || "";
  }, 50),
);

start();
