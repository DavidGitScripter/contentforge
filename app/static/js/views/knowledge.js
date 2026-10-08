import { api } from "../api.js";
import { html, ico } from "../lib.js";

const GROUPS = [
  { id: "", label: "Alle" },
  { id: "company", label: "Unternehmen" },
  { id: "service", label: "Leistungen" },
  { id: "industry", label: "Branchen" },
];

function allFacts(kb) {
  return [
    ...kb.company_facts.map((f) => ({ ...f, group: "company", scope: "Unternehmen" })),
    ...kb.services.flatMap((s) => s.facts.map((f) => ({ ...f, group: "service", scope: s.name }))),
    ...kb.industries.flatMap((i) => i.facts.map((f) => ({ ...f, group: "industry", scope: i.name }))),
  ];
}

export default {
  title: "Wissensbasis",
  crumbs: () => [{ label: "Wissensbasis" }],

  async load() {
    return { kb: await api.knowledge() };
  },

  signature: () => "static",

  render({ kb }, { query }) {
    const b = kb.brand;
    const group = GROUPS.find((g) => g.id === (query.get("fakten") || "")) || GROUPS[0];
    const facts = allFacts(kb).filter((f) => !group.id || f.group === group.id);

    return html`
      <header class="page-head">
        <div><h1>Wissensbasis</h1>
          <p>Alle Texte stützen sich ausschließlich auf diese Fakten. Das Quality Gate prüft jede Zahl im Text gegen sie.
            Gepflegt wird die Wissensbasis versioniert in <span class="mono">knowledge/brand.yaml</span>.</p></div>
      </header>

      <div class="grid-2" style="margin-top:0">
        <section class="panel" aria-labelledby="h-brand">
          <div class="panel-head"><h2 id="h-brand">Marke</h2></div>
          <div class="panel-body"><dl class="props">
            <dt>Unternehmen</dt><dd>${b.name}</dd>
            <dt>Claim</dt><dd>${b.tagline}</dd>
            <dt>Handlungsaufruf</dt><dd>${b.cta.label}</dd>
            <dt>Domain</dt><dd class="mono">${b.domain}</dd>
          </dl></div>
        </section>
        <section class="panel" aria-labelledby="h-voice">
          <div class="panel-head"><h2 id="h-voice">Tonalität</h2></div>
          <div class="panel-body"><ul style="margin:0;padding-left:18px;display:grid;gap:6px">${b.voice.map((v) => html`<li>${v}</li>`)}</ul></div>
        </section>
      </div>

      <section class="panel table-panel" style="margin-top:16px" aria-labelledby="h-facts">
        <div class="panel-head"><div><h2 id="h-facts">Fakten</h2><p>Nur diese Aussagen und Zahlen dürfen in generierten Texten vorkommen</p></div>
          <div class="segmented" role="group" aria-label="Fakten filtern">${GROUPS.map(
            (g) => html`<a href="#/wissen${g.id ? `?fakten=${g.id}` : ""}" aria-current="${g === group}">${g.label}</a>`,
          )}</div></div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th scope="col">ID</th><th scope="col">Fakt</th><th scope="col">Gilt für</th></tr></thead>
          <tbody>${facts.map(
            (f) => html`<tr><td class="mono" style="white-space:nowrap">${f.id}</td><td>${f.text}</td><td style="white-space:nowrap">${f.scope}</td></tr>`,
          )}</tbody></table></div>
      </section>

      <div class="grid-2">
        <section class="panel table-panel" aria-labelledby="h-forbidden">
          <div class="panel-head"><div><h2 id="h-forbidden">Verbotene Formulierungen</h2><p>Treffer blockieren die Freigabe automatisch</p></div></div>
          <div class="table-wrap"><table class="table">
            <thead><tr><th scope="col">Muster</th><th scope="col">Begründung</th></tr></thead>
            <tbody>${b.forbidden_terms.map((t) => html`<tr><td class="mono">${t.pattern}</td><td>${t.reason}</td></tr>`)}</tbody></table></div>
        </section>
        <section class="panel table-panel" aria-labelledby="h-personas">
          <div class="panel-head"><div><h2 id="h-personas">Zielgruppen</h2><p>Persona und Pain Points je Branche</p></div></div>
          <div class="table-wrap"><table class="table">
            <thead><tr><th scope="col">Branche</th><th scope="col">Persona</th></tr></thead>
            <tbody>${kb.industries.map(
              (i) => html`<tr><td style="white-space:nowrap"><strong>${i.name}</strong></td>
                <td>${i.persona}<ul class="muted" style="margin:6px 0 0;padding-left:18px;font-size:12.5px">${i.pains.map((p) => html`<li>${p}</li>`)}</ul></td></tr>`,
            )}</tbody></table></div>
        </section>
      </div>

      <section class="panel table-panel" style="margin-top:16px" aria-labelledby="h-services">
        <div class="panel-head"><h2 id="h-services">Leistungen</h2></div>
        <div class="table-wrap"><table class="table">
          <thead><tr><th scope="col">Leistung</th><th scope="col">Keyword</th><th scope="col">Kurzbeschreibung</th></tr></thead>
          <tbody>${kb.services.map(
            (s) => html`<tr><td style="white-space:nowrap"><strong>${s.name}</strong></td><td style="white-space:nowrap">${s.keyword}</td><td>${s.summary}</td></tr>`,
          )}</tbody></table></div>
      </section>
      <p class="muted" style="margin-top:14px;font-size:12.5px">${ico("info", { size: 14 })} Änderungen an der Wissensbasis wirken ab dem nächsten erstellten Paket.</p>`;
  },
};
