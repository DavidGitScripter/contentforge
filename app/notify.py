"""Event-Webhook an n8n (z. B. Teams-Benachrichtigung zur Freigabe). Fehler blockieren die Pipeline nie."""

import logging

import httpx

from app.config import get_settings
from app.db import Run

log = logging.getLogger(__name__)


def notify(event: str, run: Run) -> None:
    settings = get_settings()
    if not settings.n8n_webhook_url:
        return
    payload = {
        "event": event,
        "run_id": run.id,
        "keyword": run.keyword,
        "status": run.status,
        "gate_passed": run.gate_passed,
        "revisions": run.revisions,
        "judge_average": run.judge_average,
        "cost_usd": round(run.cost_usd, 4),
        "published_url": run.published_url,
        "error": run.error,
        "dashboard_url": f"{settings.dashboard_base_url.rstrip('/')}/#/vorgaenge/{run.id}",
        "preview_url": f"{settings.dashboard_base_url}/api/runs/{run.id}/preview",
    }
    try:
        httpx.post(settings.n8n_webhook_url, json=payload, timeout=5.0).raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("n8n-Webhook fehlgeschlagen (%s): %s", event, exc)
