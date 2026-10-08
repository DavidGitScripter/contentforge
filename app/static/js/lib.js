// Kleine Hilfsbibliothek: sicheres HTML-Templating, deutsche Formatierung, Status-Vokabular.
import { icon } from "./icons.js";

// --------------------------------------------------------------------------- HTML

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export class Html {
  constructor(value) {
    this.value = value;
  }
  toString() {
    return this.value;
  }
}

export const raw = (value) => new Html(String(value));

function stringify(value) {
  if (value == null || value === false) return "";
  if (value instanceof Html) return value.value;
  if (Array.isArray(value)) return value.map(stringify).join("");
  return String(value).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

/** Tagged Template: Werte werden escaped, verschachtelte html``-Ergebnisse und raw() nicht. */
export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((value, i) => {
    out += stringify(value) + strings[i + 1];
  });
  return new Html(out);
}

export const ico = (name, options) => raw(icon(name, options));

// --------------------------------------------------------------------------- Speicher (pro Browser)

export const storage = {
  get(key) {
    try {
      return localStorage.getItem(`contentforge.${key}`) || "";
    } catch {
      return "";
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`contentforge.${key}`, value);
    } catch {
      /* privater Modus: dann eben nur für diese Sitzung */
    }
  },
};

// --------------------------------------------------------------------------- Formatierung (de-DE)

const toDate = (value) => (value instanceof Date ? value : new Date(/Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`));
const nfCache = new Map();
const nf = (options) => {
  const key = JSON.stringify(options);
  if (!nfCache.has(key)) nfCache.set(key, new Intl.NumberFormat("de-DE", options));
  return nfCache.get(key);
};
const dateTimeFmt = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" });
const dateFmt = new Intl.DateTimeFormat("de-DE", { dateStyle: "medium" });
const timeFmt = new Intl.DateTimeFormat("de-DE", { timeStyle: "short" });
const relFmt = new Intl.RelativeTimeFormat("de", { numeric: "auto", style: "short" });

export const NIL = raw('<span class="nil" aria-label="keine Angabe">-</span>');

export const fmt = {
  usd(value) {
    if (value == null) return NIL;
    const digits = value !== 0 && Math.abs(value) < 0.01 ? 3 : 2;
    return nf({ style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: digits }).format(value);
  },
  pct(value) {
    return value == null ? NIL : nf({ style: "percent", maximumFractionDigits: 0 }).format(value);
  },
  num(value, digits = 0) {
    return value == null ? NIL : nf({ minimumFractionDigits: 0, maximumFractionDigits: digits }).format(value);
  },
  score(value) {
    return value == null ? NIL : nf({ minimumFractionDigits: 1, maximumFractionDigits: 2 }).format(value);
  },
  int(value) {
    return value == null ? NIL : nf({ maximumFractionDigits: 0 }).format(value);
  },
  duration(ms) {
    if (ms == null) return NIL;
    if (ms < 1000) return `${fmt.int(ms)} ms`;
    const s = ms / 1000;
    if (s < 60) return `${nf({ maximumFractionDigits: 1 }).format(s)} s`;
    return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
  },
  dateTime: (value) => (value ? dateTimeFmt.format(toDate(value)) : NIL),
  date: (value) => (value ? dateFmt.format(toDate(value)) : NIL),
  time: (value) => (value ? timeFmt.format(toDate(value)) : NIL),
  relative(value) {
    if (!value) return NIL;
    const seconds = (toDate(value).getTime() - Date.now()) / 1000;
    const abs = Math.abs(seconds);
    if (abs < 45) return "gerade eben";
    if (abs < 3600) return relFmt.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return relFmt.format(Math.round(seconds / 3600), "hour");
    return relFmt.format(Math.round(seconds / 86400), "day");
  },
};

/** Zeitstempel mit vollem Datum als Tooltip. */
export const when = (value) =>
  value ? html`<time datetime="${toDate(value).toISOString()}" title="${fmt.dateTime(value)}">${fmt.relative(value)}</time>` : NIL;

// --------------------------------------------------------------------------- Fachliches Vokabular

export const STATUS = {
  queued: { label: "Wartet", tone: "info", busy: true },
  running: { label: "In Bearbeitung", tone: "info", busy: true },
  awaiting_approval: { label: "Freigabe offen", tone: "accent" },
  needs_review: { label: "Prüfung nötig", tone: "warn" },
  published: { label: "Veröffentlicht", tone: "ok" },
  rejected: { label: "Abgelehnt", tone: "neutral" },
  failed: { label: "Fehlgeschlagen", tone: "err" },
};
export const ACTIVE = new Set(["queued", "running"]);
export const DECIDABLE = new Set(["awaiting_approval", "needs_review"]);

export function badge(status) {
  const s = STATUS[status] || { label: status, tone: "neutral" };
  return html`<span class="badge tone-${s.tone}">${s.busy ? ico("circle-notch", { size: 12, className: "spin" }) : ""}${s.label}</span>`;
}

export const STEP = {
  brief: "Briefing",
  draft: "Entwurf",
  checks: "Regelprüfung",
  judge: "Qualitätsbewertung",
  revise: "Überarbeitung",
};

export const EVENT = {
  created: { label: "Vorgang angelegt", icon: "file-text", tone: "neutral" },
  gate_passed: { label: "Quality Gate bestanden", icon: "shield-check", tone: "ok" },
  gate_failed: { label: "Quality Gate nicht bestanden", icon: "warning", tone: "warn" },
  failed: { label: "Verarbeitung fehlgeschlagen", icon: "warning-circle", tone: "err" },
  changes_requested: { label: "Änderungen angefordert", icon: "pencil-simple-line", tone: "accent" },
  approved: { label: "Freigegeben", icon: "check-circle", tone: "ok" },
  published: { label: "Veröffentlicht", icon: "globe-simple", tone: "ok" },
  rejected: { label: "Abgelehnt", icon: "prohibit", tone: "err" },
};

export const CRITERIA = {
  persona_fit: "Passung zur Zielgruppe",
  clarity: "Verständlichkeit",
  brand_voice: "Markenstimme",
  persuasiveness: "Überzeugungskraft",
};

export const initials = (name) =>
  (name || "")
    .split(/[\s.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("") || "?";

/** "claude-opus-5-5" -> "Claude Opus 5.5" */
export function prettyModel(id = "") {
  return id
    .replace(/(\d)-(\d)/g, "$1.$2")
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function debounce(fn, ms = 200) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
