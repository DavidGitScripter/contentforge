import { api } from "../api.js";
import { DECIDABLE, badge, fmt, html, ico, when } from "../lib.js";

const FILTERS = [
  { id: "", label: "Alle offenen", test: () => true },
  { id: "bestanden", label: "Gate bestanden", test: (r) => r.status === "awaiting_approval" },
  { id: "befunde", label: "Mit Befunden", test: (r) => r.status === "needs_review" },
];

export default {
  title: "Freigaben",
  crumbs: () => [{ label: "Freigaben" }],
  poll: 5000,

  async load() {
    const runs = await api.runs(500);
    return {
      open: runs.filter((r) => DECIDABLE.has(r.status)).sort((a, b) => a.created_at.localeCompare(b.created_at)),
    };
  },

  signature: (d) => JSON.stringify([d.open.map((r) => r.id + r.status + r.updated_at), Math.floor(Date.now() / 60000)]),

  render(d, { app, query }) {
    const active = FILTERS.find((f) => f.id === (query.get("filter") || "")) || FILTERS[0];
    const rows = d.open.filter(active.test);

    const segmented = html`<div class="segmented" role="group" aria-label="Filter">${FILTERS.map(
      (f) => html`<a href="#/freigaben${f.id ? `?filter=${f.id}` : ""}" aria-current="${f === active}">${f.label}
        <span class="count-pill">${d.open.filter(f.test).length}</span></a>`,
    )}</div>`;

    const table = rows.length
      ? html`<div class="table-wrap"><table class="table">
          <thead><tr>
            <th scope="col">Vorgang</th><th scope="col" class="hide-sm">Leistung</th><th scope="col">Status</th>
            <th scope="col" class="num hide-sm">Bewertung</th><th scope="col" class="num hide-sm">Überarb.</th>
            <th scope="col" class="num hide-sm">Kosten</th><th scope="col" class="hide-sm">Eingang</th><th scope="col"><span class="sr-only">Aktion</span></th>
          </tr></thead>
          <tbody>${rows.map(
            (r) => html`<tr class="is-link" data-href="#/vorgaenge/${r.id}">
              <td><a class="row-title" href="#/vorgaenge/${r.id}">${r.keyword}</a><span class="row-sub">${app.industry(r.industry_id)}</span></td>
              <td class="hide-sm">${app.service(r.service_id)}</td>
              <td>${badge(r.status)}</td>
              <td class="num hide-sm">${fmt.score(r.judge_average)}</td>
              <td class="num hide-sm">${fmt.int(r.revisions)}</td>
              <td class="num hide-sm">${fmt.usd(r.cost_usd)}</td>
              <td class="hide-sm">${when(r.created_at)}</td>
              <td class="num"><a class="btn btn-sm" href="#/vorgaenge/${r.id}">Prüfen</a></td>
            </tr>`,
          )}</tbody></table></div>`
      : html`<div class="empty">
          <div class="empty-icon">${ico("tray", { size: 22 })}</div>
          <h2>${d.open.length ? "Keine Einträge für diesen Filter" : "Keine offenen Freigaben"}</h2>
          <p>${
            d.open.length
              ? "Wechseln Sie den Filter, um die übrigen offenen Freigaben zu sehen."
              : "Neue Inhalte entstehen in der Content-Planung. Sobald die KI ein Paket erstellt und geprüft hat, erscheint es hier."
          }</p>
          ${d.open.length ? "" : html`<a class="btn btn-primary" href="#/planung">${ico("grid-four")} Zur Content-Planung</a>`}
        </div>`;

    return html`
      <header class="page-head">
        <div>
          <h1>Freigaben</h1>
          <p>Vier-Augen-Prinzip: Kein Inhalt wird ohne menschliche Freigabe veröffentlicht.
            Jede Entscheidung wird mit Name und Kommentar im Protokoll festgehalten.</p>
        </div>
      </header>
      <section class="panel table-panel" aria-label="Offene Freigaben">
        <div class="toolbar">${segmented}<span class="count">${rows.length} von ${d.open.length}</span></div>
        ${table}
      </section>`;
  },

  mount(root) {
    const onClick = (event) => {
      const row = event.target.closest("tr[data-href]");
      if (row && !event.target.closest("a, button")) location.hash = row.dataset.href;
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  },
};
