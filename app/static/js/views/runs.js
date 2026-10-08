import { api } from "../api.js";
import { ACTIVE, STATUS, badge, debounce, fmt, html, ico, raw, when } from "../lib.js";

const COLUMNS = [
  { key: "keyword", label: "Vorgang" },
  { key: "service", label: "Leistung", secondary: true },
  { key: "status", label: "Status" },
  { key: "judge", label: "Bewertung", num: true, secondary: true },
  { key: "revisions", label: "Überarb.", num: true, secondary: true },
  { key: "cost", label: "Kosten", num: true, secondary: true },
  { key: "duration", label: "Dauer", num: true, secondary: true },
  { key: "created", label: "Erstellt" },
];

const SORTERS = {
  keyword: (r) => r.keyword.toLowerCase(),
  service: (r) => r.service_id,
  status: (r) => STATUS[r.status]?.label || r.status,
  judge: (r) => r.judge_average ?? -1,
  revisions: (r) => r.revisions,
  cost: (r) => r.cost_usd,
  duration: (r) => r.duration_ms ?? -1,
  created: (r) => r.created_at,
};

function readFilters(query) {
  return {
    q: query.get("q") || "",
    status: query.get("status") || "",
    branche: query.get("branche") || "",
    leistung: query.get("leistung") || "",
    sort: SORTERS[query.get("sort")] ? query.get("sort") : "created",
    dir: query.get("dir") === "asc" ? "asc" : "desc",
  };
}

function applyFilters(runs, f) {
  const q = f.q.toLowerCase();
  const rows = runs.filter(
    (r) =>
      (!q || r.keyword.toLowerCase().includes(q) || r.id.includes(q)) &&
      (!f.status || r.status === f.status || (f.status === "running" && ACTIVE.has(r.status))) &&
      (!f.branche || r.industry_id === f.branche) &&
      (!f.leistung || r.service_id === f.leistung),
  );
  const key = SORTERS[f.sort];
  const sign = f.dir === "asc" ? 1 : -1;
  return rows.sort((a, b) => (key(a) > key(b) ? sign : key(a) < key(b) ? -sign : 0));
}

function bodyRows(rows, app) {
  if (!rows.length) {
    return html`<tr><td colspan="${COLUMNS.length}"><div class="empty">
      <div class="empty-icon">${ico("funnel-simple", { size: 22 })}</div>
      <h2>Keine Vorgänge gefunden</h2><p>Für diese Filter gibt es keine Einträge.</p>
      <button class="btn" type="button" data-action="reset">Filter zurücksetzen</button></div></td></tr>`;
  }
  return rows.map(
    (r) => html`<tr class="is-link" data-href="#/vorgaenge/${r.id}">
      <td><a class="row-title" href="#/vorgaenge/${r.id}">${r.keyword}</a><span class="row-sub">${app.industry(r.industry_id)}</span></td>
      <td class="hide-sm">${app.service(r.service_id)}</td>
      <td>${badge(r.status)}</td>
      <td class="num hide-sm">${fmt.score(r.judge_average)}</td>
      <td class="num hide-sm">${fmt.int(r.revisions)}</td>
      <td class="num hide-sm">${fmt.usd(r.cost_usd)}</td>
      <td class="num hide-sm">${fmt.duration(r.duration_ms)}</td>
      <td>${when(r.created_at)}</td>
    </tr>`,
  );
}

function headRow(f) {
  return COLUMNS.map((c) => {
    const sorted = f.sort === c.key;
    const aria = sorted ? (f.dir === "asc" ? "ascending" : "descending") : null;
    const glyph = sorted ? (f.dir === "asc" ? "caret-up" : "caret-down") : "caret-up-down";
    const cls = [c.num ? "num" : "", c.secondary ? "hide-sm" : ""].join(" ").trim();
    return html`<th scope="col" class="${cls}" ${aria ? raw(`aria-sort="${aria}"`) : ""}>
      <button class="th-sort" type="button" data-sort="${c.key}">${c.label}${ico(glyph, { size: 12 })}</button></th>`;
  });
}

const options = (items, selected) =>
  items.map((o) => html`<option value="${o.value}" ${o.value === selected ? "selected" : ""}>${o.label}</option>`);

export default {
  title: "Vorgänge",
  crumbs: () => [{ label: "Vorgänge" }],
  poll: (d) => (d.runs.some((r) => ACTIVE.has(r.status)) ? 2500 : 10000),

  async load() {
    return { runs: await api.runs(500) };
  },

  signature: (d) => JSON.stringify(d.runs.map((r) => r.id + r.status + r.updated_at)),

  render(d, { app, query }) {
    const f = readFilters(query);
    const rows = applyFilters([...d.runs], f);
    const statusOptions = [
      { value: "", label: "Alle Status" },
      { value: "running", label: "In Bearbeitung" },
      ...Object.entries(STATUS)
        .filter(([key]) => !ACTIVE.has(key))
        .map(([value, s]) => ({ value, label: s.label })),
    ];

    return html`
      <header class="page-head">
        <div><h1>Vorgänge</h1><p>Alle Content-Pakete mit Status, Qualitätsbewertung, Kosten und Laufzeit.</p></div>
        <div class="actions"><a class="btn" href="#/planung">${ico("grid-four")} Neues Paket in der Planung</a></div>
      </header>
      <section class="panel table-panel" aria-label="Vorgänge">
        <form class="toolbar" data-filters>
          <div class="field grow"><label for="f-q">Suche</label>
            <input class="input" id="f-q" name="q" type="search" value="${f.q}" placeholder="Keyword oder Vorgangs-ID" autocomplete="off"></div>
          <div class="field"><label for="f-status">Status</label>
            <select class="select" id="f-status" name="status">${options(statusOptions, f.status)}</select></div>
          <div class="field"><label for="f-branche">Branche</label>
            <select class="select" id="f-branche" name="branche">${options(
              [{ value: "", label: "Alle Branchen" }, ...app.meta.industries.map((i) => ({ value: i.id, label: i.name }))],
              f.branche,
            )}</select></div>
          <div class="field"><label for="f-leistung">Leistung</label>
            <select class="select" id="f-leistung" name="leistung">${options(
              [{ value: "", label: "Alle Leistungen" }, ...app.meta.services.map((s) => ({ value: s.id, label: s.name }))],
              f.leistung,
            )}</select></div>
          <span class="count" data-count>${rows.length} von ${d.runs.length}</span>
        </form>
        <div class="table-wrap"><table class="table">
          <thead><tr data-head>${headRow(f)}</tr></thead>
          <tbody data-body>${bodyRows(rows, app)}</tbody>
        </table></div>
      </section>`;
  },

  mount(root, d, { app, query }) {
    const f = readFilters(query);
    const form = root.querySelector("[data-filters]");

    const apply = () => {
      const rows = applyFilters([...d.runs], f);
      root.querySelector("[data-body]").innerHTML = html`${bodyRows(rows, app)}`;
      root.querySelector("[data-head]").innerHTML = html`${headRow(f)}`;
      root.querySelector("[data-count]").textContent = `${rows.length} von ${d.runs.length}`;
      const params = new URLSearchParams();
      Object.entries(f).forEach(([k, v]) => {
        if (v && !(k === "sort" && v === "created") && !(k === "dir" && v === "desc")) params.set(k, v);
      });
      const qs = params.toString();
      history.replaceState(null, "", `#/vorgaenge${qs ? `?${qs}` : ""}`);
    };

    const onInput = debounce((event) => {
      f[event.target.name] = event.target.value.trim();
      apply();
    }, 180);
    const onChange = (event) => {
      if (event.target.matches("select")) {
        f[event.target.name] = event.target.value;
        apply();
      }
    };
    const onClick = (event) => {
      const sort = event.target.closest("[data-sort]");
      if (sort) {
        const key = sort.dataset.sort;
        f.dir = f.sort === key && f.dir === "desc" ? "asc" : "desc";
        f.sort = key;
        apply();
        root.querySelector(`[data-sort="${key}"]`)?.focus();
        return;
      }
      if (event.target.closest("[data-action='reset']")) {
        Object.assign(f, { q: "", status: "", branche: "", leistung: "" });
        form.reset();
        form.querySelectorAll("input, select").forEach((el) => (el.value = ""));
        apply();
        return;
      }
      const row = event.target.closest("tr[data-href]");
      if (row && !event.target.closest("a, button")) location.hash = row.dataset.href;
    };

    form.addEventListener("input", (event) => event.target.name === "q" && onInput(event));
    form.addEventListener("change", onChange);
    form.addEventListener("submit", (event) => event.preventDefault());
    root.addEventListener("click", onClick);
    return () => root.removeEventListener("click", onClick);
  },
};
