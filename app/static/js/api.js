// API-Client: Anzeigename als X-Actor (Protokoll), optionaler API-Key, verständliche Fehlermeldungen.
import { storage } from "./lib.js";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let requestApiKey = async () => null;
export const onApiKeyRequired = (handler) => {
  requestApiKey = handler;
};

function describe(status, detail) {
  if (Array.isArray(detail)) return "Eingabe unvollständig. Bitte die markierten Felder prüfen.";
  if (typeof detail === "string" && detail) return detail;
  if (status >= 500) return "Serverfehler. Bitte später erneut versuchen.";
  return `Anfrage fehlgeschlagen (HTTP ${status}).`;
}

export async function request(path, { method = "GET", body, retried = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const key = storage.get("apiKey");
  if (key) headers["X-API-Key"] = key;
  const actor = storage.get("actor");
  if (actor && method !== "GET") headers["X-Actor"] = encodeURIComponent(actor);

  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Keine Verbindung zum Server.");
  }
  if (res.status === 401 && !retried) {
    const entered = await requestApiKey();
    if (entered) {
      storage.set("apiKey", entered);
      return request(path, { method, body, retried: true });
    }
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, describe(res.status, data.detail));
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  config: () => request("/api/config"),
  stats: () => request("/api/stats"),
  matrix: () => request("/api/matrix"),
  knowledge: () => request("/api/knowledge"),
  runs: (limit = 500) => request(`/api/runs?limit=${limit}`),
  run: (id) => request(`/api/runs/${encodeURIComponent(id)}`),
  events: (limit = 12) => request(`/api/events?limit=${limit}`),
  createRun: (industry_id, service_id) => request("/api/runs", { method: "POST", body: { industry_id, service_id } }),
  batch: () => request("/api/runs/batch", { method: "POST", body: { skip_existing: true } }),
  approve: (id, body) => request(`/api/runs/${id}/approve`, { method: "POST", body }),
  reject: (id, body) => request(`/api/runs/${id}/reject`, { method: "POST", body }),
  requestChanges: (id, body) => request(`/api/runs/${id}/request-changes`, { method: "POST", body }),
};
