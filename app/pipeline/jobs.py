"""Ausführung im Hintergrund: begrenzter Thread-Pool = eingebautes Concurrency-Limit gegen Rate-Limits."""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache

from sqlalchemy import select

from app.config import get_settings
from app.db import Run, session_scope
from app.pipeline.orchestrator import execute_revision, execute_run

log = logging.getLogger(__name__)


@lru_cache
def _executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=get_settings().max_concurrent_runs, thread_name_prefix="pipeline")


def _safe_execute(fn: Callable[..., None], run_id: str, *args: str) -> None:
    """Letzte Verteidigungslinie: Kein Run darf wegen einer Exception dauerhaft auf "running" hängen bleiben."""
    try:
        fn(run_id, *args)
    except Exception as exc:
        log.exception("Run %s abgebrochen", run_id)
        with session_scope() as s:
            run = s.get(Run, run_id)
            if run and run.status in ("queued", "running"):
                run.status = "failed"
                run.error = f"Interner Fehler: {exc}"[:1000]


def _submit(fn: Callable[..., None], run_id: str, *args: str) -> Future | None:
    if get_settings().inline_runs:
        _safe_execute(fn, run_id, *args)
        return None
    return _executor().submit(_safe_execute, fn, run_id, *args)


def submit(run_id: str) -> Future | None:
    return _submit(execute_run, run_id)


def submit_revision(run_id: str, feedback: str) -> Future | None:
    return _submit(execute_revision, run_id, feedback)


def recover_interrupted_runs() -> int:
    """Beim Start: Runs, die durch einen Neustart unterbrochen wurden, sauber als fehlgeschlagen markieren."""
    with session_scope() as s:
        stuck = s.scalars(select(Run).where(Run.status.in_(["queued", "running"]))).all()
        for run in stuck:
            run.status = "failed"
            run.error = "Durch Neustart des Servers unterbrochen. Bitte neu generieren."
        if stuck:
            log.warning("%d unterbrochene Runs als fehlgeschlagen markiert", len(stuck))
        return len(stuck)
