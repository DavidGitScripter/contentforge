import { api } from "../api.js";
import { fmt, html, ico, prettyModel } from "../lib.js";

const onOff = (on, yes, no) =>
  on ? html`<span class="state-ok">${ico("check-circle", { size: 16 })} ${yes}</span>` : html`<span class="muted">${no}</span>`;

export default {
  title: "System",
  crumbs: () => [{ label: "System" }],
  poll: 10000,

  async load({ app }) {
    const [config, stats] = await Promise.all([api.config(), api.stats()]);
    Object.assign(app, { config, stats });
    return { config, stats };
  },

  signature: (d) => JSON.stringify(d),

  render({ config: c, stats: s }, { app }) {
    const used = c.daily_budget_usd ? Math.min(1, c.cost_today_usd / c.daily_budget_usd) : 0;
    const demo = c.provider !== "anthropic";
    return html`
      <header class="page-head">
        <div><h1>System</h1>
          <p>Konfiguration dieser Installation. Die Werte kommen aus Umgebungsvariablen (lokal <span class="mono">.env</span>,
            in Azure die Container App) und ändern sich erst nach einem Neustart.</p></div>
      </header>

      <section class="panel" aria-labelledby="h-profile">
        <div class="panel-head"><div><h2 id="h-profile">Ihr Profil</h2><p>Name, mit dem Ihre Entscheidungen im Protokoll erscheinen (nur in diesem Browser gespeichert)</p></div></div>
        <form class="panel-body" data-profile style="display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap">
          <div class="field" style="flex:1 1 260px"><label for="p-name">Anzeigename</label>
            <input class="input" id="p-name" name="name" value="${app.actor()}" autocomplete="name" placeholder="Vor- und Nachname"></div>
          <button class="btn btn-primary" type="submit">Speichern</button>
        </form>
      </section>

      <div class="grid-2">
        <section class="panel" aria-labelledby="h-ai">
          <div class="panel-head"><h2 id="h-ai">KI-Modelle</h2>${demo ? html`<span class="badge tone-neutral">Demo-Modus</span>` : html`<span class="badge tone-ok">Produktiv</span>`}</div>
          <div class="panel-body"><dl class="props">
            <dt>Anbieter</dt><dd>${demo ? "Demo (offline, deterministisch, ohne API-Kosten)" : "Anthropic Claude API"}</dd>
            <dt>Textmodell</dt><dd>${prettyModel(c.model)}</dd>
            <dt>Bewertungsmodell</dt><dd>${prettyModel(c.judge_model)}</dd>
            <dt>Denktiefe (effort)</dt><dd>${c.effort}</dd>
            <dt>Prompt-Version</dt><dd class="mono">${c.prompt_version}</dd>
          </dl></div>
        </section>

        <section class="panel" aria-labelledby="h-gate">
          <div class="panel-head"><h2 id="h-gate">Quality Gate</h2></div>
          <div class="panel-body"><dl class="props">
            <dt>Mindestbewertung</dt><dd>Durchschnitt ab ${fmt.score(c.judge_min_avg)}, kein Kriterium unter ${c.judge_min_single}</dd>
            <dt>Überarbeitungen</dt><dd>höchstens ${c.max_revisions} automatisch, danach manuelle Prüfung</dd>
            <dt>Regelprüfung</dt><dd>SEO, Markenregeln, Faktenbelege, Kanalvorgaben</dd>
            <dt>Bisher abgefangen</dt><dd>${fmt.int(s.issues_caught)} Befunde vor der Freigabe</dd>
          </dl></div>
        </section>

        <section class="panel" aria-labelledby="h-cost">
          <div class="panel-head"><h2 id="h-cost">Kosten und Betrieb</h2></div>
          <div class="panel-body"><dl class="props">
            <dt>Tagesbudget</dt><dd>${fmt.usd(c.daily_budget_usd)}, danach blockiert die Kostenbremse neue Pakete</dd>
            <dt>Heute verbraucht</dt><dd>${fmt.usd(c.cost_today_usd)} (${fmt.pct(used)})</dd>
            <dt>Gesamtkosten</dt><dd>${fmt.usd(s.cost_total_usd)} für ${fmt.int(s.runs_total)} Vorgänge</dd>
            <dt>Parallele Verarbeitung</dt><dd>${c.max_concurrent_runs} Pakete gleichzeitig</dd>
            <dt>Datenbank</dt><dd>${c.database}</dd>
            <dt>Version</dt><dd><code>${c.version.slice(0, 12)}</code></dd>
          </dl></div>
        </section>

        <section class="panel" aria-labelledby="h-integrations">
          <div class="panel-head"><h2 id="h-integrations">Veröffentlichung und Integrationen</h2></div>
          <div class="panel-body"><dl class="props">
            <dt>Ziel</dt><dd>${c.publisher === "azure_blob" ? "Azure Blob Storage (Static Website)" : "Lokaler Webserver"}</dd>
            <dt>Website</dt><dd><a href="${c.site_base_url.replace(/\/?$/, "/")}" target="_blank" rel="noopener">${c.site_base_url}</a></dd>
            <dt>n8n-Benachrichtigungen</dt><dd>${onOff(c.n8n_connected, "verbunden", "nicht verbunden")}</dd>
            <dt>API-Schutz</dt><dd>${onOff(c.auth_required, "aktiv (X-API-Key)", "aus, nur für lokale Demo geeignet")}</dd>
          </dl></div>
        </section>
      </div>`;
  },

  mount(root, d, { app }) {
    const form = root.querySelector("[data-profile]");
    const onSubmit = (event) => {
      event.preventDefault();
      const name = form.name.value.trim();
      app.setActor(name);
      app.toast(name ? `Gespeichert: ${name}` : "Anzeigename entfernt", { tone: "ok" });
    };
    form.addEventListener("submit", onSubmit);
    if (location.hash.includes("profil")) form.name.focus();
    return () => form.removeEventListener("submit", onSubmit);
  },
};
