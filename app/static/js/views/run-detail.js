import { api } from "../api.js";
import { ACTIVE, CRITERIA, DECIDABLE, EVENT, STEP, badge, fmt, html, ico, raw } from "../lib.js";

const TABS = [
  { id: "inhalte", label: "Inhalte" },
  { id: "gate", label: "Quality Gate" },
  { id: "verarbeitung", label: "Verarbeitung" },
  { id: "briefing", label: "Briefing" },
  { id: "protokoll", label: "Protokoll" },
];
const PIPELINE = ["brief", "draft", "checks", "judge"];
const drafts = new Map(); // Kommentarentwürfe je Vorgang überleben Aktualisierungen
const view = { content: "page", preview: "desktop" };

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const lastEvent = (run, action) => [...run.events].reverse().find((e) => e.action === action);

// --------------------------------------------------------------------------- Tabs: Inhalte

function contentTab(run, app) {
  if (!run.package) {
    return ACTIVE.has(run.status)
      ? html`<p class="muted" style="margin-bottom:14px">Die KI erstellt gerade das Content-Paket.</p>
          <span class="skeleton" style="width:60%"></span><span class="skeleton"></span><span class="skeleton block" style="height:360px;margin-top:16px"></span>`
      : html`<div class="empty"><p>Für diesen Vorgang liegt kein Content vor.</p></div>`;
  }
  const p = run.package;
  const lp = p.landing_page;
  const channels = [
    { id: "page", label: "Landingpage", icon: "file-text" },
    { id: "linkedin", label: "LinkedIn-Post", icon: "linkedin-logo" },
    { id: "newsletter", label: "Newsletter", icon: "envelope-simple" },
  ];
  const switcher = html`<div class="segmented" role="group" aria-label="Kanal">${channels.map(
    (c) => html`<button type="button" data-content="${c.id}" aria-pressed="${view.content === c.id}">${ico(c.icon, { size: 15 })}${c.label}</button>`,
  )}</div>`;
  const base = (app.config?.site_base_url || "").replace(/\/$/, "");

  if (view.content === "linkedin") {
    const li = p.linkedin_post;
    const brand = app.config?.brand_name || "Unternehmen";
    const length = li.hook.length + li.body.length;
    return html`${switcher}
      <div class="channel-card" style="margin-top:16px">
        <div class="channel-head"><div class="org-logo" aria-hidden="true">${(app.config?.brand_short || "UN").slice(0, 2).toUpperCase()}</div>
          <div><strong>${brand}</strong><div class="muted" style="font-size:12px">Unternehmensseite, Entwurf</div></div></div>
        <div class="channel-body"><span class="hook">${li.hook}</span>\n\n${li.body}
          <div class="hashtags">${li.hashtags.map((h) => `#${h.replace(/^#/, "")}`).join(" ")}</div></div>
      </div>
      <p class="char-count">${fmt.int(length)} Zeichen, Grenze 1.300</p>`;
  }

  if (view.content === "newsletter") {
    const nl = p.newsletter;
    return html`${switcher}
      <div class="channel-card" style="margin-top:16px">
        <div class="mail-head"><div class="subject">${nl.subject}</div><div class="pre">${nl.preheader}</div></div>
        <div class="channel-body" style="padding-top:14px">${nl.body}</div>
      </div>
      <p class="char-count">Betreff ${nl.subject.length} Zeichen, Vorschautext ${nl.preheader.length} Zeichen</p>`;
  }

  return html`${switcher}
    <h3 style="margin:18px 0 8px">Suchergebnis-Vorschau</h3>
    <div class="serp" aria-label="Vorschau im Suchergebnis">
      <div class="url">${base}/${run.slug}/</div>
      <div class="title">${lp.seo_title}</div>
      <div class="desc">${lp.meta_description}</div>
    </div>
    <div class="preview-bar">
      <h3>Seitenvorschau</h3>
      <div class="actions">
        <div class="segmented" role="group" aria-label="Ansicht">
          <button type="button" data-preview="desktop" aria-pressed="${view.preview === "desktop"}">Desktop</button>
          <button type="button" data-preview="mobile" aria-pressed="${view.preview === "mobile"}">Mobil</button>
        </div>
        <a class="btn btn-sm" href="/api/runs/${run.id}/preview" target="_blank" rel="noopener">${ico("arrow-square-out", { size: 14 })} Neuer Tab</a>
      </div>
    </div>
    <div class="preview-stage ${view.preview === "mobile" ? "is-mobile" : ""}">
      <div class="browser-bar" aria-hidden="true"><span class="dots"><i></i><i></i><i></i></span>
        <span class="url">${base}/${run.slug}/</span><span class="dim" data-dim></span></div>
      <div class="viewport">
        <iframe title="Vorschau der Landingpage" src="/api/runs/${run.id}/preview?v=${encodeURIComponent(run.updated_at)}"></iframe>
      </div>
    </div>
    <p class="muted" style="margin-top:8px;font-size:12.5px">So erscheint die Seite nach der Freigabe. Die Vorschau ist für Suchmaschinen gesperrt (noindex).</p>`;
}

// --------------------------------------------------------------------------- Tabs: Quality Gate

function gateTab(run) {
  if (!run.checks) {
    return html`<div class="empty"><div class="empty-icon">${ico("shield-check", { size: 22 })}</div>
      <p>Die Prüfung startet, sobald der Entwurf vorliegt.</p></div>`;
  }
  const attempts = run.attempts.map((a, i) => {
    const title = a.passed
      ? `Durchlauf ${i + 1}: bestanden${a.judge_average != null ? `, Bewertung ${fmt.score(a.judge_average)}` : ""}`
      : `Durchlauf ${i + 1}: ${plural(a.blocking.length, "Befund", "Befunde")}${i < run.attempts.length - 1 ? ", überarbeitet" : ""}`;
    return html`<li class="attempt ${a.passed ? "is-pass" : "is-fail"}">
      ${ico(a.passed ? "check-circle" : "warning", { size: 18 })}
      <div><div class="attempt-title">${title}</div>
        ${a.source === "feedback" ? html`<div class="muted" style="font-size:12.5px">Nach Feedback aus der Freigabe</div>` : ""}
        ${a.blocking.length ? html`<ul>${a.blocking.map((b) => html`<li>${b}</li>`)}</ul>` : ""}
      </div></li>`;
  });

  const groups = {};
  run.checks.forEach((c) => (groups[c.category] ||= []).push(c));
  const result = (c) =>
    c.passed
      ? html`<span class="state-ok">${ico("check-circle", { size: 16 })} Erfüllt</span>`
      : c.severity === "error"
        ? html`<span class="state-err">${ico("x-circle", { size: 16 })} Nicht erfüllt</span>`
        : html`<span class="state-warn">${ico("warning", { size: 16 })} Hinweis</span>`;
  const checkRows = Object.entries(groups).map(
    ([category, list]) => html`
      <tr class="group-row"><td colspan="3">${category}: ${list.filter((c) => c.passed).length} von ${list.length} erfüllt</td></tr>
      ${list.map((c) => html`<tr><td>${c.label}</td><td>${result(c)}</td><td class="muted">${c.detail}</td></tr>`)}`,
  );

  const v = run.verdict;
  const judge = v
    ? html`<h3 style="margin:24px 0 10px">Qualitätsbewertung durch das Sprachmodell</h3>
        <div class="table-wrap"><table class="table"><thead><tr><th scope="col">Kriterium</th><th scope="col" class="num">Bewertung</th></tr></thead>
          <tbody>${Object.entries(v.scores).map(
            ([key, value]) => html`<tr><td>${CRITERIA[key] || key}</td><td class="num"><span class="score">${value} <small>von 5</small></span></td></tr>`,
          )}</tbody></table></div>
        <p style="margin-top:12px">${v.summary}</p>
        ${v.issues.length ? html`<h3 style="margin:16px 0 6px">Verbesserungsvorschläge</h3><ul style="margin:0;padding-left:18px">${v.issues.map((i) => html`<li>${i}</li>`)}</ul>` : ""}`
    : "";

  return html`
    <h3 style="margin-bottom:10px">Durchläufe</h3>
    <ol class="attempts">${attempts}</ol>
    <h3 style="margin:24px 0 10px">Regelprüfung im letzten Durchlauf</h3>
    <div class="table-wrap"><table class="table">
      <thead><tr><th scope="col">Prüfung</th><th scope="col">Ergebnis</th><th scope="col">Detail</th></tr></thead>
      <tbody>${checkRows}</tbody></table></div>
    ${judge}`;
}

// --------------------------------------------------------------------------- Tabs: Verarbeitung, Briefing, Protokoll

function processingTab(run) {
  if (!run.steps.length) return html`<div class="empty"><p>Der Vorgang wartet auf einen freien Verarbeitungsplatz.</p></div>`;
  const totalTokens = run.steps.reduce((sum, s) => sum + s.input_tokens + s.output_tokens, 0);
  const rows = run.steps.map((s) => {
    const state =
      s.status === "failed"
        ? html`<span class="state-err">${ico("x-circle", { size: 16 })}</span>`
        : s.status === "running"
          ? html`<span class="tone-text-info">${ico("circle-notch", { size: 16, className: "spin" })}</span>`
          : html`<span class="state-ok">${ico("check-circle", { size: 16 })}</span>`;
    return html`<tr>
      <td class="num muted">${s.seq}</td>
      <td><span style="display:inline-flex;gap:8px;align-items:center">${state}<strong>${STEP[s.name] || s.name}</strong></span>
        <span class="row-sub">${s.summary}</span></td>
      <td class="mono">${s.model ? s.model.replace("mock/", "Demo: ") : html`<span class="muted">lokal</span>`}</td>
      <td class="num">${s.input_tokens ? `${fmt.int(s.input_tokens)} / ${fmt.int(s.output_tokens)}` : raw('<span class="nil">-</span>')}</td>
      <td class="num">${s.cost_usd ? fmt.usd(s.cost_usd) : raw('<span class="nil">-</span>')}</td>
      <td class="num">${fmt.duration(s.duration_ms)}</td>
    </tr>`;
  });
  return html`<div class="table-wrap"><table class="table">
      <thead><tr><th scope="col" class="num">#</th><th scope="col">Schritt</th><th scope="col">Modell</th>
        <th scope="col" class="num">Tokens ein / aus</th><th scope="col" class="num">Kosten</th><th scope="col" class="num">Dauer</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <p class="muted" style="margin-top:12px;font-size:12.5px">Gesamt: ${fmt.usd(run.cost_usd)} für ${fmt.int(totalTokens)} Tokens,
      Prompt-Version <span class="mono">${run.prompt_version}</span>, Anbieter ${run.provider === "mock" ? "Demo-Modus" : "Anthropic Claude"}.</p>`;
}

function briefingTab(run) {
  const b = run.brief;
  if (!b) return html`<div class="empty"><p>Das Briefing wird als erster Schritt erstellt.</p></div>`;
  return html`<dl class="props">
    <dt>Haupt-Keyword</dt><dd><strong>${run.keyword}</strong></dd>
    <dt>Weitere Keywords</dt><dd>${b.secondary_keywords.join(", ")}</dd>
    <dt>Suchintention</dt><dd>${b.search_intent}</dd>
    <dt>Kernbotschaft</dt><dd>${b.angle}</dd>
    <dt>Gliederung</dt><dd><ol style="margin:0;padding-left:18px">${b.outline.map((o) => html`<li>${o}</li>`)}</ol></dd>
  </dl>`;
}

function protocolTab(run) {
  if (!run.events.length) return html`<div class="empty"><p>Für diesen Vorgang gibt es noch keine Protokolleinträge.</p></div>`;
  return html`<ol class="timeline">${run.events.map((e) => {
    const meta = EVENT[e.action] || { label: e.action, icon: "info", tone: "neutral" };
    return html`<li>
      <span class="dot tone-${meta.tone}">${ico(meta.icon, { size: 15 })}</span>
      <div>
        <div class="event-title">${meta.label}</div>
        <div class="event-meta">${e.actor}, ${fmt.dateTime(e.created_at)}</div>
        ${e.message && e.message !== meta.label ? html`<div class="event-msg">${e.message}</div>` : ""}
        ${e.comment ? html`<blockquote>${e.comment}</blockquote>` : ""}
      </div></li>`;
  })}</ol>`;
}

// --------------------------------------------------------------------------- Entscheidungspanel

function decisionPanel(run, app) {
  if (ACTIVE.has(run.status)) {
    const done = new Set(run.steps.filter((s) => s.status === "ok").map((s) => s.name));
    const currentStep = [...run.steps].reverse().find((s) => s.status === "running");
    return html`<section class="panel decision" aria-labelledby="h-decision">
      <div class="panel-head"><h2 id="h-decision">In Bearbeitung</h2></div>
      <div class="panel-body">
        <p>${currentStep ? `Aktueller Schritt: ${STEP[currentStep.name]}.` : "Wartet auf einen freien Verarbeitungsplatz."}
          Die Ansicht aktualisiert sich automatisch.</p>
        <ol class="progress-steps">${PIPELINE.map((name) => {
          const isDone = done.has(name);
          const isNow = currentStep?.name === name;
          return html`<li class="${isDone ? "state-ok" : isNow ? "tone-text-info" : "muted"}">
            ${ico(isDone ? "check-circle" : isNow ? "circle-notch" : "clock", { size: 16, className: isNow ? "spin" : "" })}
            ${STEP[name]}</li>`;
        })}</ol>
      </div></section>`;
  }

  if (run.status === "published") {
    const approved = lastEvent(run, "approved");
    return html`<section class="panel decision" aria-labelledby="h-decision">
      <div class="panel-head"><h2 id="h-decision">Veröffentlicht</h2>${badge("published")}</div>
      <div class="panel-body">
        <dl class="decision-facts">
          <div><dt>Veröffentlicht</dt><dd>${fmt.dateTime(run.published_at)}</dd></div>
          <div><dt>Freigegeben von</dt><dd>${approved?.actor || "unbekannt"}</dd></div>
          <div><dt>Bewertung</dt><dd>${fmt.score(run.judge_average)} von 5</dd></div>
        </dl>
        ${approved?.comment ? html`<blockquote class="notice tone-neutral" style="margin:0">${approved.comment}</blockquote>` : ""}
        <div class="decision-actions">
          <a class="btn btn-primary" href="${run.published_url}" target="_blank" rel="noopener">${ico("arrow-square-out")} Live-Seite öffnen</a>
          <button class="btn" type="button" data-action="regenerate">${ico("arrow-clockwise")} Neue Version erstellen</button>
        </div>
      </div></section>`;
  }

  if (run.status === "rejected" || run.status === "failed") {
    const rejected = run.status === "rejected";
    const reason = rejected ? lastEvent(run, "rejected")?.comment : run.error;
    return html`<section class="panel decision" aria-labelledby="h-decision">
      <div class="panel-head"><h2 id="h-decision">${rejected ? "Abgelehnt" : "Verarbeitung fehlgeschlagen"}</h2>${badge(run.status)}</div>
      <div class="panel-body">
        ${reason ? html`<div class="notice ${rejected ? "tone-neutral" : "tone-err"}">${ico(rejected ? "prohibit" : "warning-circle")}<div>${reason}</div></div>` : ""}
        <div class="decision-actions">
          <button class="btn btn-primary" type="button" data-action="regenerate">${ico("arrow-clockwise")} ${rejected ? "Neu erstellen" : "Erneut versuchen"}</button>
        </div>
      </div></section>`;
  }

  // Entscheidung offen
  const exception = run.status === "needs_review";
  const actor = app.actor();
  return html`<section class="panel decision" aria-labelledby="h-decision">
    <div class="panel-head"><div><h2 id="h-decision">Entscheidung</h2><p>Vier-Augen-Prinzip</p></div>${badge(run.status)}</div>
    <div class="panel-body">
      <dl class="decision-facts">
        <div><dt>Quality Gate</dt><dd>${run.gate_passed ? html`<span class="state-ok">${ico("check-circle", { size: 16 })} bestanden</span>` : html`<span class="state-warn">${ico("warning", { size: 16 })} nicht bestanden</span>`}</dd></div>
        <div><dt>Bewertung</dt><dd>${run.judge_average != null ? html`${fmt.score(run.judge_average)} von 5` : raw('<span class="nil">-</span>')}</dd></div>
        <div><dt>Überarbeitungen</dt><dd>${fmt.int(run.revisions)}</dd></div>
        <div><dt>Kosten bisher</dt><dd>${fmt.usd(run.cost_usd)}</dd></div>
      </dl>
      ${exception ? html`<div class="notice tone-warn" style="margin-bottom:16px">${ico("warning")}
        <div><strong>Befunde nach ${plural(run.revisions, "Überarbeitung", "Überarbeitungen")} offen</strong>
        Veröffentlichen ist nur als begründete Ausnahme möglich. Details im Tab Quality Gate.</div></div>` : ""}
      <form data-decision novalidate>
        <div class="field">
          <label for="d-reviewer">Prüfer:in</label>
          <input class="input" id="d-reviewer" name="reviewer" value="${actor}" autocomplete="name" required aria-describedby="d-reviewer-err">
          <span class="error" id="d-reviewer-err" hidden></span>
        </div>
        <div class="field">
          <label for="d-comment">Kommentar</label>
          <textarea class="textarea" id="d-comment" name="comment" rows="4" aria-describedby="d-comment-hint d-comment-err"
            placeholder="z. B. Einstieg stärker auf die Pain Points der Zielgruppe ausrichten">${drafts.get(run.id) || ""}</textarea>
          <span class="hint" id="d-comment-hint">Pflicht bei Änderungswunsch, Ablehnung und Ausnahme. Wird im Protokoll gespeichert.</span>
          <span class="error" id="d-comment-err" hidden></span>
        </div>
        <div class="decision-actions">
          <button class="btn ${exception ? "btn-warn" : "btn-primary"} btn-block" type="button" data-decide="approve">
            ${ico(exception ? "warning" : "check")} ${exception ? "Als Ausnahme veröffentlichen" : "Freigeben und veröffentlichen"}</button>
          <div class="split">
            <button class="btn" type="button" data-decide="changes">${ico("pencil-simple-line")} Änderungen</button>
            <button class="btn btn-danger" type="button" data-decide="reject">${ico("prohibit")} Ablehnen</button>
          </div>
        </div>
        <p class="muted" style="margin-top:12px;font-size:12px">„Änderungen“ schickt Ihren Kommentar an die KI. Sie überarbeitet das Paket und prüft es erneut.</p>
      </form>
    </div></section>`;
}

// --------------------------------------------------------------------------- View

export default {
  title: (d) => d.run.keyword,
  crumbs: (d) => [{ label: "Vorgänge", href: "#/vorgaenge" }, { label: d.run.keyword }],
  poll: (d) => (ACTIVE.has(d.run.status) ? 1500 : 8000),

  async load({ params }) {
    return { run: await api.run(params[0]) };
  },

  signature: ({ run: r }) => [r.id, r.status, r.updated_at, r.steps.map((s) => s.status).join(""), r.events.length].join("|"),

  render({ run }, { app, query }) {
    const tab = TABS.find((t) => t.id === query.get("tab")) || TABS[0];
    const counts = { protokoll: run.events.length, verarbeitung: run.steps.length };
    const tabs = html`<nav class="tabs" aria-label="Bereiche des Vorgangs">${TABS.map(
      (t) => html`<a href="#/vorgaenge/${run.id}${t === TABS[0] ? "" : `?tab=${t.id}`}" aria-current="${t === tab ? "page" : "false"}">${t.label}${
        counts[t.id] ? html`<span class="tab-count">${counts[t.id]}</span>` : ""
      }</a>`,
    )}</nav>`;
    const body = {
      inhalte: () => contentTab(run, app),
      gate: () => gateTab(run),
      verarbeitung: () => processingTab(run),
      briefing: () => briefingTab(run),
      protokoll: () => protocolTab(run),
    }[tab.id]();

    return html`
      <header class="page-head">
        <div>
          <div class="title-row"><h1>${run.keyword}</h1>${badge(run.status)}</div>
          <div class="meta-row">
            <span>Branche <strong>${app.industry(run.industry_id)}</strong></span>
            <span>Leistung <strong>${app.service(run.service_id)}</strong></span>
            <span>URL <strong class="mono">/${run.slug}/</strong></span>
            <span>Erstellt <strong>${fmt.dateTime(run.created_at)}</strong></span>
            <span>Vorgang <strong class="mono">${run.id}</strong></span>
          </div>
        </div>
        <div class="actions">
          ${run.package ? html`<a class="btn" href="/api/runs/${run.id}/preview" target="_blank" rel="noopener">${ico("eye")} Vorschau</a>` : ""}
          ${!ACTIVE.has(run.status) && DECIDABLE.has(run.status) ? html`<button class="btn" type="button" data-action="regenerate">${ico("arrow-clockwise")} Neu erstellen</button>` : ""}
        </div>
      </header>
      <div class="detail-grid">
        <section class="panel" aria-labelledby="h-tab">${tabs}<div class="panel-body"><h2 class="sr-only" id="h-tab">${tab.label}</h2>${body}</div></section>
        ${decisionPanel(run, app)}
      </div>`;
  },

  mount(root, { run }, { app }) {
    const cleanups = [];
    const stage = root.querySelector(".preview-stage");
    if (stage) {
      const iframe = stage.querySelector("iframe");
      const viewport = stage.querySelector(".viewport");
      const dim = stage.querySelector("[data-dim]");
      const layout = () => {
        const mobile = view.preview === "mobile";
        stage.classList.toggle("is-mobile", mobile);
        if (mobile) {
          // Smartphone-Rahmen: 390 px Inhaltsbreite wie ein aktuelles iPhone, 1:1 ohne Skalierung
          // 410 px inkl. 2 x 10 px Rahmen = 390 px sichtbare Seitenbreite
          Object.assign(iframe.style, { width: "410px", height: `${viewport.clientHeight - 40}px`, transform: "none" });
        } else {
          // Desktop: Seite wird in 1280 px gerendert und auf die verfügbare Breite verkleinert
          const scale = Math.min(1, viewport.clientWidth / 1280);
          Object.assign(iframe.style, { width: "1280px", height: `${viewport.clientHeight / scale}px`, transform: `scale(${scale})` });
          dim.textContent = `1280 px, ${Math.round(scale * 100)} %`;
        }
      };
      const observer = new ResizeObserver(layout);
      observer.observe(stage);
      layout();
      cleanups.push(() => observer.disconnect());
      stage.dataset.layout = "ready";
      stage._layout = layout;
    }

    const form = root.querySelector("[data-decision]");
    const showError = (id, message) => {
      const el = root.querySelector(`#${id}-err`);
      const input = root.querySelector(`#${id}`);
      el.hidden = !message;
      el.innerHTML = message ? html`${ico("warning-circle", { size: 14 })}<span>${message}</span>` : "";
      input.classList.toggle("is-invalid", Boolean(message));
      input.setAttribute("aria-invalid", message ? "true" : "false");
      if (message) input.focus();
    };

    const decide = async (kind, button) => {
      const reviewer = form.reviewer.value.trim();
      const comment = form.comment.value.trim();
      showError("d-reviewer", "");
      showError("d-comment", "");
      if (!reviewer) return showError("d-reviewer", "Bitte geben Sie Ihren Namen für das Protokoll an.");
      const exception = run.status === "needs_review";
      const needsComment = kind !== "approve" || exception;
      if (needsComment && comment.length < 3) {
        const msg = {
          approve: "Eine Ausnahme braucht eine Begründung.",
          changes: "Beschreiben Sie, was die KI ändern soll.",
          reject: "Bitte begründen Sie die Ablehnung.",
        }[kind];
        return showError("d-comment", msg);
      }
      app.setActor(reviewer);

      if (kind === "approve") {
        const base = (app.config?.site_base_url || "").replace(/\/$/, "");
        const ok = await app.confirm(
          exception
            ? {
                title: "Trotz Befunden veröffentlichen?",
                body: html`<p>Das Quality Gate ist nicht bestanden. Die Seite geht mit Ihrer Begründung als Ausnahme live:</p>
                  <p><strong>${base}/${run.slug}/</strong></p>`,
                confirmLabel: "Als Ausnahme veröffentlichen",
                tone: "warn",
                focusCancel: true,
              }
            : {
                title: "Seite veröffentlichen?",
                body: html`<p>Die Landingpage geht unter <strong>${base}/${run.slug}/</strong> live. Übersicht und sitemap.xml werden aktualisiert.</p>`,
                confirmLabel: "Veröffentlichen",
              },
        );
        if (!ok) return;
      }
      if (kind === "reject") {
        const ok = await app.confirm({
          title: "Paket ablehnen?",
          body: html`<p>Der Vorgang wird geschlossen und nicht veröffentlicht. Eine neue Version können Sie jederzeit erstellen.</p>`,
          confirmLabel: "Ablehnen",
          tone: "danger",
          focusCancel: true,
        });
        if (!ok) return;
      }

      const buttons = form.querySelectorAll("button");
      buttons.forEach((b) => (b.disabled = true));
      button.setAttribute("aria-busy", "true");
      try {
        if (kind === "approve") {
          const res = await api.approve(run.id, { reviewer, comment, override: exception });
          app.toast("Veröffentlicht", { message: res.published_url });
        } else if (kind === "changes") {
          await api.requestChanges(run.id, { reviewer, feedback: comment });
          app.toast("Überarbeitung gestartet", { message: "Die KI setzt Ihren Kommentar um und prüft erneut.", tone: "info" });
        } else {
          await api.reject(run.id, { reviewer, reason: comment });
          app.toast("Paket abgelehnt", { tone: "info" });
        }
        drafts.delete(run.id);
        app.refreshShell();
        app.refresh();
      } catch (error) {
        buttons.forEach((b) => (b.disabled = false));
        button.removeAttribute("aria-busy");
        app.toast("Aktion fehlgeschlagen", { message: error.message, tone: "err" });
      }
    };

    const onClick = async (event) => {
      const content = event.target.closest("[data-content]");
      if (content) {
        view.content = content.dataset.content;
        app.refresh();
        return;
      }
      const preview = event.target.closest("[data-preview]");
      if (preview && stage) {
        view.preview = preview.dataset.preview;
        root.querySelectorAll("[data-preview]").forEach((b) => b.setAttribute("aria-pressed", String(b === preview)));
        stage._layout();
        return;
      }
      const decideBtn = event.target.closest("[data-decide]");
      if (decideBtn) {
        decide(decideBtn.dataset.decide, decideBtn);
        return;
      }
      const regen = event.target.closest("[data-action='regenerate']");
      if (regen) {
        regen.disabled = true;
        try {
          const next = await api.createRun(run.industry_id, run.service_id);
          app.toast("Neue Version wird erstellt", { message: next.keyword, tone: "info" });
          app.navigate(`#/vorgaenge/${next.id}`);
        } catch (error) {
          regen.disabled = false;
          app.toast("Erstellen nicht möglich", { message: error.message, tone: "err" });
        }
      }
    };
    root.addEventListener("click", onClick);
    cleanups.push(() => root.removeEventListener("click", onClick));

    if (form) {
      const onInput = (event) => {
        if (event.target.name === "comment") drafts.set(run.id, event.target.value);
      };
      form.addEventListener("input", onInput);
    }
    return () => cleanups.forEach((fn) => fn());
  },
};
