import { api } from "../api.js";
import { fmt, html, ico } from "../lib.js";

export default {
  title: "Veröffentlicht",
  crumbs: () => [{ label: "Veröffentlicht" }],
  poll: 15000,

  async load() {
    const runs = await api.runs(500);
    const latest = new Map();
    runs
      .filter((r) => r.status === "published")
      .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""))
      .forEach((r) => latest.has(r.slug) || latest.set(r.slug, r));
    return { pages: [...latest.values()] };
  },

  signature: (d) => JSON.stringify(d.pages.map((r) => r.id + r.published_at)),

  render(d, { app }) {
    const base = (app.config?.site_base_url || "/site").replace(/\/$/, "");
    const reviewer = (r) => (r.review_note || "").replace(/^Freigegeben von /, "").replace(/ \(Ausnahme\)$/, "") || "unbekannt";
    const table = d.pages.length
      ? html`<div class="table-wrap"><table class="table">
          <thead><tr><th scope="col">Seite</th><th scope="col">Leistung</th><th scope="col">Veröffentlicht</th>
            <th scope="col">Freigegeben von</th><th scope="col" class="num">Bewertung</th><th scope="col"><span class="sr-only">Aktionen</span></th></tr></thead>
          <tbody>${d.pages.map(
            (r) => html`<tr>
              <td><a class="row-title" href="${r.published_url}" target="_blank" rel="noopener">${r.keyword}</a>
                <span class="row-sub mono">/${r.slug}/</span></td>
              <td>${app.service(r.service_id)}<span class="row-sub">${app.industry(r.industry_id)}</span></td>
              <td>${fmt.dateTime(r.published_at)}</td>
              <td>${reviewer(r)}${/\(Ausnahme\)$/.test(r.review_note || "") ? html` <span class="badge tone-warn">Ausnahme</span>` : ""}</td>
              <td class="num">${fmt.score(r.judge_average)}</td>
              <td class="num"><div class="actions" style="justify-content:flex-end">
                <a class="btn btn-sm" href="#/vorgaenge/${r.id}">Vorgang</a>
                <a class="btn btn-sm" href="${r.published_url}" target="_blank" rel="noopener">${ico("arrow-square-out", { size: 14 })} Öffnen</a>
              </div></td>
            </tr>`,
          )}</tbody></table></div>`
      : html`<div class="empty">
          <div class="empty-icon">${ico("globe-simple", { size: 22 })}</div>
          <h2>Noch keine Seite veröffentlicht</h2>
          <p>Seiten gehen erst nach einer Freigabe live. Offene Pakete finden Sie in den Freigaben.</p>
          <a class="btn btn-primary" href="#/freigaben">${ico("tray")} Zu den Freigaben</a>
        </div>`;

    return html`
      <header class="page-head">
        <div><h1>Veröffentlichte Seiten</h1>
          <p>Live-Seiten der Programmatic-SEO-Website. Übersichtsseite und sitemap.xml werden bei jeder Freigabe neu erzeugt.</p></div>
        <div class="actions">
          <a class="btn" href="${base}/sitemap.xml" target="_blank" rel="noopener">${ico("tree-structure")} sitemap.xml</a>
          <a class="btn btn-primary" href="${base}/" target="_blank" rel="noopener">${ico("arrow-square-out")} Website öffnen</a>
        </div>
      </header>
      <section class="panel table-panel" aria-label="Veröffentlichte Seiten">${table}</section>`;
  },
};
