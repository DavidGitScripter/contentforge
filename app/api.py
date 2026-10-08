"""REST-API für Dashboard und n8n."""

import secrets
import threading
from collections import Counter
from itertools import product
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import AuditEvent, Run, cost_today, get_session, log_event
from app.knowledge import load_knowledge
from app.notify import notify
from app.pipeline import jobs
from app.pipeline.orchestrator import new_run
from app.pipeline.prompts import PROMPT_VERSION
from app.publishing.service import page_url, publish_run, render_run
from app.schemas import (
    ApproveRequest,
    BatchCreate,
    ChangeRequest,
    EventOut,
    FeedEvent,
    RejectRequest,
    RunCreate,
    RunDetail,
    RunOut,
    StepOut,
)

router = APIRouter(prefix="/api")
OPEN_STATUSES = {"queued", "running", "awaiting_approval", "needs_review"}
DECIDABLE = ("awaiting_approval", "needs_review")
# Entscheidungen (freigeben, ablehnen, Änderungen) strikt nacheinander: Zwei gleichzeitige Klicks dürfen
# nie doppelt veröffentlichen. Reicht für eine Instanz; bei mehreren Replicas: Row-Lock in PostgreSQL.
_DECISION_LOCK = threading.Lock()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if expected and not secrets.compare_digest(x_api_key or "", expected):
        raise HTTPException(401, "Ungültiger oder fehlender X-API-Key")


def actor_name(x_actor: str | None = Header(default=None)) -> str:
    """Wer eine Aktion auslöst: Dashboard sendet den Anzeigenamen, n8n/Skripte erscheinen als "API"."""
    return unquote(x_actor or "").strip()[:80] or "API"


def _to_out(run: Run) -> RunOut:
    out = RunOut.model_validate(run, from_attributes=True)
    # Links immer aus der aktuellen Konfiguration (Port, Azure-Endpunkt), nicht aus dem Veröffentlichungszeitpunkt
    return out.model_copy(update={"published_url": page_url(run.slug)}) if run.published_url else out


def _to_detail(run: Run) -> RunDetail:
    return RunDetail(
        **_to_out(run).model_dump(),
        brief=run.brief,
        package=run.package,
        checks=run.checks,
        verdict=run.verdict,
        attempts=run.attempts or [],
        steps=[StepOut.model_validate(s, from_attributes=True) for s in run.steps],
        events=[EventOut.model_validate(e, from_attributes=True) for e in run.events],
    )


def _get_run(session: Session, run_id: str) -> Run:
    run = session.get(Run, run_id)
    if not run:
        raise HTTPException(404, f"Vorgang {run_id} nicht gefunden")
    return run


def _ensure_decidable(run: Run, verb: str) -> None:
    if run.status not in DECIDABLE:
        raise HTTPException(409, f"Vorgang im Status '{run.status}' kann nicht {verb} werden")


def _ensure_budget(session: Session) -> None:
    budget = get_settings().daily_budget_usd
    spent = cost_today(session)
    if spent >= budget:
        raise HTTPException(429, f"Tagesbudget erreicht ({spent:.2f} von {budget:.2f} USD). Kostenbremse aktiv.")


def _validate_cell(industry_id: str, service_id: str) -> None:
    kb = load_knowledge()
    if industry_id not in {i.id for i in kb.industries}:
        raise HTTPException(422, f"Unbekannte Branche: {industry_id}")
    if service_id not in {s.id for s in kb.services}:
        raise HTTPException(422, f"Unbekannte Leistung: {service_id}")


def _latest_runs(session: Session) -> dict[tuple[str, str], Run]:
    latest: dict[tuple[str, str], Run] = {}
    for run in session.scalars(select(Run).order_by(desc(Run.created_at))):
        latest.setdefault((run.industry_id, run.service_id), run)
    return latest


# --------------------------------------------------------------------------- Lesen


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/config")
def config(session: Session = Depends(get_session)) -> dict:
    s, kb = get_settings(), load_knowledge()
    return {
        "brand_name": kb.brand.name,
        "brand_short": kb.brand.short_name,
        "provider": s.llm_provider,
        "model": s.llm_model,
        "judge_model": s.llm_judge_model,
        "effort": s.llm_effort,
        "max_revisions": s.max_revisions,
        "judge_min_avg": s.judge_min_avg,
        "judge_min_single": s.judge_min_single,
        "max_concurrent_runs": s.max_concurrent_runs,
        "prompt_version": PROMPT_VERSION,
        "publisher": s.publisher,
        "site_base_url": s.site_base_url,
        "daily_budget_usd": s.daily_budget_usd,
        "cost_today_usd": round(cost_today(session), 4),
        "auth_required": bool(s.api_key),
        "n8n_connected": bool(s.n8n_webhook_url),
        "version": s.app_version,
        "database": "PostgreSQL" if s.database_url.startswith("postgresql") else "SQLite",
    }


@router.get("/knowledge")
def knowledge() -> dict:
    """Wissensbasis (read-only): Grundlage aller Texte und aller Faktenprüfungen."""
    return load_knowledge().model_dump()


@router.get("/matrix")
def matrix(session: Session = Depends(get_session)) -> dict:
    kb = load_knowledge()
    latest = _latest_runs(session)
    cells = []
    for industry, service in product(kb.industries, kb.services):
        run = latest.get((industry.id, service.id))
        cells.append({
            "industry_id": industry.id,
            "service_id": service.id,
            "run": _to_out(run).model_dump(mode="json") if run else None,
        })
    return {
        "industries": [{"id": i.id, "name": i.name, "persona": i.persona} for i in kb.industries],
        "services": [{"id": s.id, "name": s.name} for s in kb.services],
        "cells": cells,
    }


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    runs = session.scalars(select(Run)).all()
    finished = [r for r in runs if r.gate_passed is not None]
    n = len(finished) or 1
    findings = Counter(
        issue.split(":")[0].strip()
        for r in finished
        for a in r.attempts or []
        if not a.get("passed")
        for issue in a.get("blocking", [])
    )
    return {
        "runs_total": len(runs),
        "published": len({r.slug for r in runs if r.status == "published"}),
        "awaiting_review": sum(r.status in DECIDABLE for r in runs),
        "in_progress": sum(r.status in ("queued", "running") for r in runs),
        "failed": sum(r.status == "failed" for r in runs),
        "gate_pass_rate": round(sum(bool(r.gate_passed) for r in finished) / n, 3) if finished else None,
        "first_pass_rate": round(sum(bool(r.first_pass) for r in finished) / n, 3) if finished else None,
        "avg_revisions": round(sum(r.revisions for r in finished) / n, 2) if finished else None,
        "avg_cost_usd": round(sum(r.cost_usd for r in finished) / n, 4) if finished else None,
        "avg_duration_ms": int(sum(r.duration_ms or 0 for r in finished) / n) if finished else None,
        "issues_caught": sum(findings.values()),
        "top_findings": [{"label": label, "count": count} for label, count in findings.most_common(6)],
        "cost_total_usd": round(sum(r.cost_usd for r in runs), 4),
        "cost_today_usd": round(cost_today(session), 4),
    }


@router.get("/events", response_model=list[FeedEvent])
def events(limit: int = Query(20, le=100), session: Session = Depends(get_session)) -> list[FeedEvent]:
    query = select(AuditEvent, Run.keyword).join(Run)
    rows = session.execute(query.order_by(desc(AuditEvent.created_at), desc(AuditEvent.id)).limit(limit)).all()
    return [
        FeedEvent(**EventOut.model_validate(event, from_attributes=True).model_dump(), keyword=keyword)
        for event, keyword in rows
    ]


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    status: str | None = None, limit: int = Query(50, le=500), session: Session = Depends(get_session)
) -> list[RunOut]:
    query = select(Run).order_by(desc(Run.created_at)).limit(limit)
    if status:
        query = query.where(Run.status == status)
    return [_to_out(r) for r in session.scalars(query)]


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: str, session: Session = Depends(get_session)) -> RunDetail:
    return _to_detail(_get_run(session, run_id))


@router.get("/runs/{run_id}/preview", response_class=HTMLResponse)
def preview_run(run_id: str, session: Session = Depends(get_session)) -> HTMLResponse:
    run = _get_run(session, run_id)
    if not run.package:
        raise HTTPException(409, "Für diesen Vorgang existiert noch kein Content")
    return HTMLResponse(render_run(run, preview=True))


# --------------------------------------------------------------------------- Schreiben


@router.post("/runs", status_code=202, response_model=RunOut, dependencies=[Depends(require_api_key)])
def create_run(body: RunCreate, actor: str = Depends(actor_name), session: Session = Depends(get_session)) -> RunOut:
    _validate_cell(body.industry_id, body.service_id)
    _ensure_budget(session)
    run = new_run(body.industry_id, body.service_id, actor=actor)
    jobs.submit(run.id)
    return _to_out(session.get(Run, run.id) or run)


@router.post("/runs/batch", status_code=202, dependencies=[Depends(require_api_key)])
def create_batch(
    body: BatchCreate, actor: str = Depends(actor_name), session: Session = Depends(get_session)
) -> dict:
    kb = load_knowledge()
    industries = body.industry_ids or [i.id for i in kb.industries]
    services = body.service_ids or [s.id for s in kb.services]
    latest = _latest_runs(session)
    _ensure_budget(session)

    created, skipped = [], []
    for industry_id, service_id in product(industries, services):
        _validate_cell(industry_id, service_id)
        existing = latest.get((industry_id, service_id))
        if body.skip_existing and existing and existing.status in OPEN_STATUSES | {"published"}:
            skipped.append(existing.slug)
            continue
        run = new_run(industry_id, service_id, actor=actor, note="Sammelauftrag")
        jobs.submit(run.id)
        created.append({"run_id": run.id, "keyword": run.keyword})
    return {"created": created, "skipped": skipped}


@router.post("/runs/{run_id}/approve", response_model=RunOut, dependencies=[Depends(require_api_key)])
def approve_run(run_id: str, body: ApproveRequest, session: Session = Depends(get_session)) -> RunOut:
    with _DECISION_LOCK:
        run = _get_run(session, run_id)
        _ensure_decidable(run, "freigegeben")
        if run.status == "needs_review":
            if not body.override:
                raise HTTPException(409, "Quality Gate nicht bestanden. Freigabe nur als begründete Ausnahme.")
            if len(body.comment) < 3:
                raise HTTPException(422, "Eine Freigabe trotz Befunden braucht eine Begründung im Kommentar.")
        run.review_note = f"Freigegeben von {body.reviewer}" + (" (Ausnahme)" if body.override else "")
        log_event(
            session, run.id, "approved", body.reviewer,
            "Freigegeben trotz offener Befunde (Ausnahme)" if body.override else "Freigegeben", body.comment,
        )
        url = publish_run(session, run)
        log_event(session, run.id, "published", "ContentForge", f"Veröffentlicht unter {url}")
        session.commit()  # innerhalb der Sperre: der nächste Request sieht bereits "published"
    notify("run.published", run)
    return _to_out(run)


@router.post("/runs/{run_id}/reject", response_model=RunOut, dependencies=[Depends(require_api_key)])
def reject_run(run_id: str, body: RejectRequest, session: Session = Depends(get_session)) -> RunOut:
    with _DECISION_LOCK:
        run = _get_run(session, run_id)
        _ensure_decidable(run, "abgelehnt")
        run.status = "rejected"
        run.review_note = f"Abgelehnt von {body.reviewer}: {body.reason}"
        log_event(session, run.id, "rejected", body.reviewer, "Abgelehnt", body.reason)
        session.commit()
    notify("run.rejected", run)
    return _to_out(run)


@router.post("/runs/{run_id}/request-changes", status_code=202, response_model=RunOut,
             dependencies=[Depends(require_api_key)])
def request_changes(run_id: str, body: ChangeRequest, session: Session = Depends(get_session)) -> RunOut:
    """Feedback aus der Freigabe: Die KI überarbeitet das Paket, danach läuft erneut das Quality Gate."""
    with _DECISION_LOCK:
        run = _get_run(session, run_id)
        _ensure_decidable(run, "überarbeitet")
        _ensure_budget(session)
        run.status = "queued"
        run.review_note = f"Änderungen angefordert von {body.reviewer}"
        log_event(session, run.id, "changes_requested", body.reviewer, "Änderungen angefordert", body.feedback)
        session.commit()  # Status sichtbar machen, bevor der Job startet
    jobs.submit_revision(run.id, body.feedback)
    session.refresh(run)
    return _to_out(run)
