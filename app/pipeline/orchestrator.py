"""Pipeline: Brief -> Entwurf -> Quality Gate (Checks + LLM-Judge) -> Revision (max. N) -> Freigabe.

Code-gesteuerter Workflow statt autonomer Agent: Die Schritte sind bekannt, also bestimmt der Code die
Reihenfolge und das LLM nur die Inhalte. Das hält Kosten, Laufzeit und Fehlerbilder vorhersehbar.

Fordert die Freigabe Änderungen an, läuft das Feedback durch denselben Quality-Gate-Loop wie ein Erstentwurf.
"""

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.db import Run, Step, log_event, record_event, session_scope
from app.knowledge import ContentContext, build_context, load_knowledge
from app.llm import LLMResult, get_llm
from app.notify import notify
from app.pipeline.checks import blocking_issues, run_checks
from app.pipeline.prompts import (
    PROMPT_VERSION,
    brief_prompt,
    draft_prompt,
    judge_prompt,
    revise_prompt,
    system_prompt,
)
from app.schemas import CheckResult, ContentBrief, ContentPackage, JudgeVerdict

log = logging.getLogger(__name__)
R = TypeVar("R")
SYSTEM_ACTOR = "ContentForge"
Call = Callable[..., Callable[[], LLMResult]]


class StepTracer:
    """Schreibt jeden Schritt mit Dauer, Modell, Tokens und Kosten mit: Observability pro Run."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        with session_scope() as s:  # bei Überarbeitungen an bestehende Schritte anschließen
            self.seq = s.scalar(select(func.coalesce(func.max(Step.seq), 0)).where(Step.run_id == run_id))

    def _run(self, name: str, attempt: int, fn: Callable[[], Any], describe: Callable[[Any], str]) -> Any:
        self.seq += 1
        with session_scope() as s:
            step = Step(run_id=self.run_id, seq=self.seq, name=name, attempt=attempt, status="running")
            s.add(step)
            s.flush()
            step_id = step.id

        started = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            with session_scope() as s:
                step = s.get(Step, step_id)
                step.status = "failed"
                step.duration_ms = int((time.perf_counter() - started) * 1000)
                step.summary = str(exc)[:500]
            raise

        with session_scope() as s:
            step = s.get(Step, step_id)
            step.status = "ok"
            step.duration_ms = int((time.perf_counter() - started) * 1000)
            if isinstance(result, LLMResult):
                step.model = result.model
                u = result.usage
                step.input_tokens = u.input_tokens + u.cache_read_tokens + u.cache_write_tokens
                step.output_tokens = u.output_tokens
                step.cost_usd = u.cost_usd(result.model.removeprefix("mock/"))
                step.summary = describe(result.output)
                run = s.get(Run, self.run_id)
                run.cost_usd = round(run.cost_usd + step.cost_usd, 6)
            else:
                step.summary = describe(result)
        return result.output if isinstance(result, LLMResult) else result

    def llm(self, name: str, attempt: int, fn: Callable[[], LLMResult[R]], describe: Callable[[R], str]) -> R:
        return self._run(name, attempt, fn, describe)

    def local(self, name: str, attempt: int, fn: Callable[[], R], describe: Callable[[R], str]) -> R:
        return self._run(name, attempt, fn, describe)


def _update_run(run_id: str, **fields: Any) -> Run:
    with session_scope() as s:
        run = s.get(Run, run_id)
        for key, value in fields.items():
            setattr(run, key, value)
        return run


def _de(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _describe_checks(results: list[CheckResult]) -> str:
    errors = sum(1 for r in results if not r.passed and r.severity == "error")
    warnings = sum(1 for r in results if not r.passed and r.severity == "warning")
    passed = sum(1 for r in results if r.passed)
    return f"{passed} von {len(results)} bestanden, {errors} Fehler, {warnings} Warnungen"


def _prepare(run_id: str) -> tuple[Settings, ContentContext, Call]:
    settings, kb, llm = get_settings(), load_knowledge(), get_llm()
    system = system_prompt(kb)
    run = _update_run(run_id, status="running", error=None)
    ctx = build_context(kb, run.industry_id, run.service_id)

    def call(task: str, prompt: str, schema: type, model: str | None = None) -> Callable[[], LLMResult]:
        return lambda: llm.generate(
            task=task, system=system, prompt=prompt, schema=schema,
            model=model or settings.llm_model, context={"ctx": ctx},
        )

    return settings, ctx, call


def _gate_loop(
    run_id: str,
    ctx: ContentContext,
    call: Call,
    tracer: StepTracer,
    settings: Settings,
    package: ContentPackage,
    attempts: list[dict],
    feedback: str | None = None,
) -> tuple[bool, JudgeVerdict | None, int]:
    """Prüft das Paket und überarbeitet es, bis das Gate bestanden ist oder die Revisionen aufgebraucht sind.

    Mit `feedback` wird zuerst das Feedback aus der Freigabe umgesetzt. Rückgabe: (bestanden, Judge, Revisionen).
    """
    first = len(attempts)
    revisions = 0
    if feedback:
        issues = [f"Feedback aus der Freigabe (höchste Priorität): {feedback}"]
        package = tracer.llm(
            "revise", first, call("revise", revise_prompt(ctx, package, issues), ContentPackage),
            lambda p: "Feedback aus der Freigabe umgesetzt",
        )
        revisions += 1

    passed = False
    verdict: JudgeVerdict | None = None
    for i in range(settings.max_revisions + 1):
        attempt = first + i
        checks = tracer.local("checks", attempt, lambda p=package: run_checks(p, ctx), _describe_checks)
        issues = blocking_issues(checks)
        verdict = None
        if not issues:  # Judge nur, wenn die kostenlosen Checks bestanden sind
            verdict = tracer.llm(
                "judge", attempt,
                call("judge", judge_prompt(ctx, package), JudgeVerdict, settings.llm_judge_model),
                lambda v: f"Bewertung Ø {_de(v.average)}. {v.summary}",
            )
            passed = verdict.average >= settings.judge_min_avg and verdict.minimum >= settings.judge_min_single
            if not passed:
                issues = verdict.issues or ["Gesamtqualität liegt unter dem Schwellenwert"]

        attempts.append({
            "attempt": attempt,
            "passed": passed,
            "source": "feedback" if feedback and i == 0 else "pipeline",
            "blocking": issues if not passed else [],
            "warnings": [f"{c.label}: {c.detail}" for c in checks if not c.passed and c.severity == "warning"],
            "judge_average": verdict.average if verdict else None,
        })
        _update_run(
            run_id,
            package=package.model_dump(),
            checks=[c.model_dump() for c in checks],
            verdict=verdict.model_dump() if verdict else None,
            attempts=list(attempts),
        )
        if passed or i == settings.max_revisions:
            break
        package = tracer.llm(
            "revise", attempt + 1, call("revise", revise_prompt(ctx, package, issues), ContentPackage),
            lambda p, n=len(issues): f"{n} Befunde bearbeitet",
        )
        revisions += 1
    return passed, verdict, revisions


def _gate_message(passed: bool, verdict: JudgeVerdict | None, revisions: int, after_feedback: bool) -> str:
    score = f"Bewertung Ø {_de(verdict.average)}" if verdict else ""
    if after_feedback:
        extra = revisions - 1  # die erste Überarbeitung setzt das Feedback um
        more = f" nach {extra} weiteren Überarbeitung{'en' if extra > 1 else ''}" if extra > 0 else ""
        if passed:
            return f"Feedback umgesetzt, Quality Gate{more} bestanden, {score}"
        return f"Feedback umgesetzt, Quality Gate{more} nicht bestanden. Manuelle Prüfung nötig."
    if passed and revisions == 0:
        return f"Quality Gate im ersten Durchlauf bestanden, {score}"
    rev = f"{revisions} automatischen Überarbeitung{'en' if revisions > 1 else ''}"
    if passed:
        return f"Quality Gate nach {rev} bestanden, {score}"
    return f"Quality Gate nach {rev} nicht bestanden. Manuelle Prüfung nötig."


def _fail(run_id: str, exc: Exception, started: float, previous_ms: int = 0) -> Run:
    log.exception("Run %s fehlgeschlagen", run_id)
    record_event(run_id, "failed", SYSTEM_ACTOR, f"Verarbeitung abgebrochen: {str(exc)[:300]}")
    return _update_run(
        run_id, status="failed", error=str(exc)[:1000],
        duration_ms=previous_ms + int((time.perf_counter() - started) * 1000),
    )


def execute_run(run_id: str) -> None:
    started = time.perf_counter()
    settings, ctx, call = _prepare(run_id)
    tracer = StepTracer(run_id)
    try:
        brief: ContentBrief = tracer.llm(
            "brief", 0, call("brief", brief_prompt(ctx), ContentBrief),
            lambda b: f"Kernbotschaft: {b.angle}",
        )
        _update_run(run_id, brief=brief.model_dump())

        package: ContentPackage = tracer.llm(
            "draft", 0, call("draft", draft_prompt(ctx, brief), ContentPackage),
            lambda p: f"{len(p.landing_page.sections)} Abschnitte, {len(p.landing_page.faq)} FAQ, LinkedIn, Newsletter",
        )
        attempts: list[dict] = []
        passed, verdict, revisions = _gate_loop(run_id, ctx, call, tracer, settings, package, attempts)

        run = _update_run(
            run_id,
            status="awaiting_approval" if passed else "needs_review",
            gate_passed=passed,
            first_pass=passed and revisions == 0,
            revisions=revisions,
            judge_average=verdict.average if verdict else None,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        record_event(
            run_id, "gate_passed" if passed else "gate_failed", SYSTEM_ACTOR,
            _gate_message(passed, verdict, revisions, after_feedback=False),
        )
    except Exception as exc:  # Run sauber als fehlgeschlagen markieren statt still abzubrechen
        run = _fail(run_id, exc, started)
    notify(f"run.{run.status}", run)


def execute_revision(run_id: str, feedback: str) -> None:
    """Setzt Feedback aus der Freigabe um und schickt das Ergebnis erneut durch das Quality Gate."""
    started = time.perf_counter()
    with session_scope() as s:
        existing = s.get(Run, run_id)
        package = ContentPackage.model_validate(existing.package)
        attempts = list(existing.attempts or [])
        previous_revisions, previous_ms = existing.revisions, existing.duration_ms or 0
    settings, ctx, call = _prepare(run_id)
    tracer = StepTracer(run_id)
    try:
        passed, verdict, revisions = _gate_loop(
            run_id, ctx, call, tracer, settings, package, attempts, feedback=feedback
        )
        run = _update_run(
            run_id,
            status="awaiting_approval" if passed else "needs_review",
            gate_passed=passed,
            revisions=previous_revisions + revisions,
            judge_average=verdict.average if verdict else None,
            duration_ms=previous_ms + int((time.perf_counter() - started) * 1000),
        )
        record_event(
            run_id, "gate_passed" if passed else "gate_failed", SYSTEM_ACTOR,
            _gate_message(passed, verdict, revisions, after_feedback=True),
        )
    except Exception as exc:
        run = _fail(run_id, exc, started, previous_ms)
    notify(f"run.{run.status}", run)


def new_run(industry_id: str, service_id: str, actor: str = "API", note: str = "Einzelauftrag") -> Run:
    kb = load_knowledge()
    ctx = build_context(kb, industry_id, service_id)
    with session_scope() as s:
        run = Run(
            industry_id=industry_id,
            service_id=service_id,
            keyword=ctx.keyword,
            slug=ctx.slug,
            provider=get_llm().provider,
            prompt_version=PROMPT_VERSION,
            attempts=[],
        )
        s.add(run)
        s.flush()
        log_event(s, run.id, "created", actor, note)
        return run
