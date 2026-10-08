import { api } from "../api.js";
import { ACTIVE, DECIDABLE, badge, fmt, html, ico } from "../lib.js";

const OPEN_FOR_BATCH = new Set(["rejected", "failed"]);

function cell(entry) {
  const r = entry.run;
  if (!r) {
    return html`<button class="cell is-empty" type="button" data-create="${entry.industry_id}|${entry.service_id}">
      <span class="cell-title">Noch nicht erstellt</span>
      <span class="cell-action">${ico("play", { size: 14 })} Paket erstellen</span>
    </button>`;
  }
  const meta = [
    r.judge_average != null ? `Bewertung ${fmt.score(r.judge_average)}` : "",
    r.revisions ? `${r.revisions} Überarb.` : "",
    r.cost_usd ? fmt.usd(r.cost_usd) : "",
  ].filter(Boolean);
  return html`<a class="cell" href="#/vorgaenge/${r.id}">
    ${badge(r.status)}
    <span class="cell-title">${r.keyword}</span>
    <span class="cell-meta">${meta.join(", ")}</span>
  </a>`;
}

export default {
  title: "Content-Planung",
  crumbs: () => [{ label: "Content-Planung" }],
  poll: (d) => (d.cells.some((c) => c.run && ACTIVE.has(c.run.status)) ? 2000 : 10000),

  async load({ app }) {
    const [matrix, stats] = await Promise.all([api.matrix(), api.stats()]);
    app.stats = stats;
    return { ...matrix, stats };
  },

  signature: (d) => JSON.stringify(d.cells.map((c) => (c.run ? c.run.id + c.run.status + c.run.updated_at : "-"))),

  render(d, { app }) {
    const byCell = new Map(d.cells.map((c) => [`${c.industry_id}|${c.service_id}`, c]));
    const count = (pred) => d.cells.filter((c) => pred(c.run)).length;
    const published = count((r) => r?.status === "published");
    const review = count((r) => r && DECIDABLE.has(r.status));
    const running = count((r) => r && ACTIVE.has(r.status));
    const openCells = d.cells.filter((c) => !c.run || OPEN_FOR_BATCH.has(c.run.status)).length;

    const head = html`<tr><th scope="col"><span class="sr-only">Branche</span></th>${d.services.map(
      (s) => html`<th scope="col">${s.name}</th>`,
    )}</tr>`;
    const rows = d.industries.map(
      (i) => html`<tr>
        <th scope="row" class="row-head">${i.name}<small>${i.persona}</small></th>
        ${d.services.map((s) => html`<td>${cell(byCell.get(`${i.id}|${s.id}`))}</td>`)}
      </tr>`,
    );

    return html`
      <header class="page-head">
        <div>
          <h1>Content-Planung</h1>
          <p>Jede Kombination aus Branche und Leistung wird zu einer Landingpage mit LinkedIn-Post und Newsletter-Teaser.
            Keyword und URL sind fest definiert, die Texte schreibt die KI auf Basis der Wissensbasis.</p>
        </div>
        <div class="actions">
          <a class="btn" href="${(app.config?.site_base_url || "/site").replace(/\/?$/, "/")}" target="_blank" rel="noopener">${ico("arrow-square-out")} Website öffnen</a>
          <button class="btn btn-primary" type="button" data-action="batch" ${openCells ? "" : "disabled"}>
            ${ico("lightning")} Offene Zellen erstellen${openCells ? ` (${openCells})` : ""}</button>
        </div>
      </header>

      <section class="panel" aria-labelledby="h-matrix">
        <div class="panel-head">
          <h2 id="h-matrix">Matrix Branche × Leistung</h2>
          <div class="coverage" aria-label="Abdeckung">
            <span><b>${published}</b> veröffentlicht</span>
            <span><b>${review}</b> in Freigabe</span>
            ${running ? html`<span class="tone-text-info"><b>${running}</b> in Bearbeitung</span>` : ""}
            <span><b>${d.cells.length - published - review - running}</b> offen</span>
          </div>
        </div>
        <div class="table-wrap"><table class="matrix"><thead>${head}</thead><tbody>${rows}</tbody></table></div>
      </section>`;
  },

  mount(root, d, { app }) {
    const onClick = async (event) => {
      const create = event.target.closest("[data-create]");
      if (create) {
        const [industry, service] = create.dataset.create.split("|");
        create.disabled = true;
        try {
          const run = await api.createRun(industry, service);
          app.toast("Paket wird erstellt", { message: run.keyword, tone: "info" });
          app.navigate(`#/vorgaenge/${run.id}`);
        } catch (error) {
          create.disabled = false;
          app.toast("Erstellen nicht möglich", { message: error.message, tone: "err" });
        }
        return;
      }
      if (event.target.closest("[data-action='batch']")) {
        const n = d.cells.filter((c) => !c.run || OPEN_FOR_BATCH.has(c.run.status)).length;
        const perPackage = d.stats.avg_cost_usd || 0.1;
        const ok = await app.confirm({
          title: `${n} Content-Pakete erstellen?`,
          body: html`<p>Für alle Zellen ohne aktuelles Paket erstellt die KI Landingpage, LinkedIn-Post und Newsletter-Teaser.
            Jedes Paket durchläuft das Quality Gate und landet danach in den Freigaben.</p>
            <p>Geschätzte Kosten: <strong>${fmt.usd(n * perPackage)}</strong> (${fmt.usd(perPackage)} je Paket, Durchschnitt bisher).</p>`,
          confirmLabel: "Pakete erstellen",
        });
        if (!ok) return;
        try {
          const res = await api.batch();
          app.toast(`${res.created.length} Pakete in Arbeit`, {
            message: res.skipped.length ? `${res.skipped.length} Zellen übersprungen, da bereits vorhanden.` : "",
            tone: "info",
          });
          app.refresh();
        } catch (error) {
          app.toast("Sammelauftrag nicht möglich", { message: error.message, tone: "err" });
        }
      }
    };
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  },
};
