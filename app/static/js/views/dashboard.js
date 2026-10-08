import { api } from "../api.js";
import { ACTIVE, DECIDABLE, EVENT, badge, fmt, html, ico, prettyModel, when } from "../lib.js";

const MAX_ROWS = 6;

export function eventItem(e, { withKeyword = true } = {}) {
  const meta = EVENT[e.action] || { label: e.action, icon: "info", tone: "neutral" };
  const comment = e.comment ? `: „${e.comment.length > 70 ? `${e.comment.slice(0, 70).trim()}…` : e.comment}“` : "";
  return html`<li>
    <span class="tone-text-${meta.tone}">${ico(meta.icon, { size: 18 })}</span>
    <div>
      <div><strong>${meta.label}</strong>${
        withKeyword ? html` <a href="#/vorgaenge/${e.run_id}">${e.keyword}</a>` : ""
      }</div>
      <div class="who">${e.actor}${comment}</div>
    </div>
    ${when(e.created_at)}
  </li>`;
}

function approvalsTable(open, app) {
  if (!open.length) {
    return html`<div class="empty">
      <div class="empty-icon">${ico("tray", { size: 22 })}</div>
      <h2>Keine offenen Freigaben</h2>
      <p>Sobald die KI ein Content-Paket erstellt und geprüft hat, erscheint es hier zur Entscheidung.</p>
    </div>`;
  }
  const rows = open.slice(0, MAX_ROWS).map(
    (r) => html`<tr class="is-link" data-href="#/vorgaenge/${r.id}">
      <td><a class="row-title" href="#/vorgaenge/${r.id}">${r.keyword}</a><span class="row-sub">${app.industry(r.industry_id)}</span></td>
      <td>${badge(r.status)}</td>
      <td class="num hide-sm">${fmt.score(r.judge_average)}</td>
      <td>${when(r.created_at)}</td>
    </tr>`,
  );
  return html`<div class="table-wrap"><table class="table">
    <thead><tr><th scope="col">Vorgang</th><th scope="col">Status</th><th scope="col" class="num hide-sm">Bewertung</th><th scope="col">Eingang</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

export default {
  title: "Übersicht",
  crumbs: () => [{ label: "Übersicht" }],
  poll: (d) => (d.active.length ? 2500 : 8000),

  async load({ app }) {
    const [stats, runs, events] = await Promise.all([api.stats(), api.runs(500), api.events(8)]);
    app.stats = stats;
    const open = runs.filter((r) => DECIDABLE.has(r.status)).sort((a, b) => a.created_at.localeCompare(b.created_at));
    return { stats, open, active: runs.filter((r) => ACTIVE.has(r.status)), events };
  },

  signature: (d) =>
    JSON.stringify([d.stats, d.open.map((r) => r.id + r.status), d.active.length, d.events.map((e) => e.id), Math.floor(Date.now() / 60000)]),

  render(d, { app }) {
    const s = d.stats;
    const c = app.config || {};
    const total = app.meta.industries.length * app.meta.services.length;
    const needsReview = d.open.filter((r) => r.status === "needs_review").length;
    const budgetUsed = c.daily_budget_usd ? Math.min(1, s.cost_today_usd / c.daily_budget_usd) : 0;

    return html`
      <header class="page-head">
        <div>
          <h1>Übersicht</h1>
          <p>Stand der Content-Pipeline für ${c.brand_name || "Ihr Unternehmen"}.</p>
        </div>
        <div class="actions">
          <a class="btn" href="#/planung">${ico("grid-four")} Content-Planung</a>
          <a class="btn btn-primary" href="#/freigaben">${ico("tray")} Freigaben prüfen</a>
        </div>
      </header>

      <dl class="summary" aria-label="Kennzahlen">
        <div><dt>Veröffentlichte Seiten</dt><dd>${fmt.int(s.published)} <small>von ${total}</small></dd><dd class="sub">Abdeckung der Content-Matrix</dd></div>
        <div><dt>Offene Freigaben</dt><dd>${fmt.int(s.awaiting_review)}</dd><dd class="sub">${
          needsReview ? `${needsReview} mit offenen Befunden` : "Alle ohne offene Befunde"
        }</dd></div>
        <div><dt>Quality Gate bestanden</dt><dd>${fmt.pct(s.gate_pass_rate)}</dd><dd class="sub">${fmt.pct(s.first_pass_rate)} ohne Überarbeitung</dd></div>
        <div><dt>Kosten je Paket</dt><dd>${fmt.usd(s.avg_cost_usd)}</dd><dd class="sub">Durchschnitt, ${fmt.duration(s.avg_duration_ms)} Laufzeit</dd></div>
        <div><dt>Kosten heute</dt><dd>${fmt.usd(s.cost_today_usd)} <small>von ${fmt.usd(c.daily_budget_usd)}</small></dd>
          <dd class="sub"><div class="meter-light" role="meter" aria-label="Tagesbudget verbraucht" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(budgetUsed * 100)}"><span style="width:${(budgetUsed * 100).toFixed(1)}%"></span></div></dd></div>
      </dl>

      ${
        d.active.length
          ? html`<div class="notice tone-info" style="margin-top:16px">${ico("circle-notch", { className: "spin" })}
              <div><strong>${d.active.length === 1 ? "1 Content-Paket wird erstellt" : `${d.active.length} Content-Pakete werden erstellt`}</strong>
              Die Übersicht aktualisiert sich automatisch. <a href="#/vorgaenge?status=running">Laufende Vorgänge anzeigen</a></div></div>`
          : ""
      }

      <div class="grid-2 wide-left">
        <section class="panel table-panel" aria-labelledby="h-open">
          <div class="panel-head"><div><h2 id="h-open">Offene Freigaben</h2><p>Älteste zuerst</p></div>
            <a class="btn btn-ghost btn-sm" href="#/freigaben">Alle anzeigen ${ico("caret-right", { size: 14 })}</a></div>
          ${approvalsTable(d.open, app)}
          ${d.open.length > MAX_ROWS ? html`<div class="panel-foot"><a href="#/freigaben">${d.open.length - MAX_ROWS} weitere Freigaben</a></div>` : ""}
        </section>

        <section class="panel" aria-labelledby="h-feed">
          <div class="panel-head"><div><h2 id="h-feed">Letzte Aktivitäten</h2><p>Aus dem Freigabe-Protokoll</p></div></div>
          ${
            d.events.length
              ? html`<ul class="feed">${d.events.map((e) => eventItem(e))}</ul>`
              : html`<div class="empty"><p>Noch keine Aktivitäten.</p></div>`
          }
        </section>
      </div>

      <div class="grid-2">
        <section class="panel table-panel" aria-labelledby="h-findings">
          <div class="panel-head"><div><h2 id="h-findings">Häufigste Befunde</h2><p>Vom Quality Gate abgefangen, bevor Inhalte zur Freigabe kamen</p></div></div>
          ${
            s.top_findings.length
              ? html`<div class="table-wrap"><table class="table"><thead><tr><th scope="col">Befund</th><th scope="col" class="num">Anzahl</th></tr></thead>
                  <tbody>${s.top_findings.map((f) => html`<tr><td>${f.label}</td><td class="num">${fmt.int(f.count)}</td></tr>`)}</tbody></table></div>`
              : html`<div class="empty"><p>Noch keine Befunde. Das Quality Gate hat bisher alle Erstentwürfe durchgelassen.</p></div>`
          }
        </section>

        <section class="panel" aria-labelledby="h-system">
          <div class="panel-head"><div><h2 id="h-system">Systemstatus</h2><p>Konfiguration dieser Installation</p></div>
            <a class="btn btn-ghost btn-sm" href="#/system">Details ${ico("caret-right", { size: 14 })}</a></div>
          <div class="panel-body">
            <dl class="props">
              <dt>Textmodell</dt><dd>${c.provider === "anthropic" ? prettyModel(c.model) : "Demo-Modus (offline, ohne API-Kosten)"}</dd>
              <dt>Quality Gate</dt><dd>Bewertung ab ${fmt.score(c.judge_min_avg)}, höchstens ${c.max_revisions} Überarbeitungen</dd>
              <dt>Veröffentlichung</dt><dd>${c.publisher === "azure_blob" ? "Azure Static Website" : "Lokaler Webserver"}</dd>
              <dt>Benachrichtigungen</dt><dd>${c.n8n_connected ? html`<span class="state-ok">${ico("check-circle")} n8n verbunden</span>` : html`<span class="muted">n8n nicht verbunden</span>`}</dd>
              <dt>Prompt-Version</dt><dd class="mono">${c.prompt_version}</dd>
            </dl>
          </div>
        </section>
      </div>`;
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
