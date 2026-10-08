from app.db import Run, session_scope
from app.llm import LLMError
from app.llm.mock_client import MockLLM
from app.pipeline.orchestrator import execute_run, new_run
from app.schemas import JudgeScores, JudgeVerdict


def run_cell(industry: str, service: str) -> Run:
    run = new_run(industry, service)
    execute_run(run.id)
    with session_scope() as s:
        run = s.get(Run, run.id)
        _ = run.steps  # Relationship laden, solange die Session offen ist
        return run


def test_flawed_draft_is_revised_and_passes(client, ctx):
    assert MockLLM.draft_is_flawed(ctx)
    run = run_cell("banken", "rag-plattform")
    assert run.status == "awaiting_approval"
    assert run.revisions == 1 and run.first_pass is False and run.gate_passed is True
    assert len(run.attempts[0]["blocking"]) == 2
    assert [s.name for s in run.steps] == ["brief", "draft", "checks", "revise", "checks", "judge"]
    assert run.cost_usd > 0


def test_clean_draft_passes_first_time(client):
    run = run_cell("banken", "workflow-automatisierung")
    assert run.status == "awaiting_approval"
    assert run.first_pass is True and run.revisions == 0
    # Judge läuft nur, wenn die kostenlosen Checks bestanden sind
    assert [s.name for s in run.steps] == ["brief", "draft", "checks", "judge"]


def test_low_judge_score_ends_in_needs_review(client, monkeypatch, settings):
    weak = JudgeVerdict(
        scores=JudgeScores(persona_fit=3, clarity=3, brand_voice=4, persuasiveness=2),
        issues=["Nutzen für die Persona bleibt abstrakt"],
        summary="Nicht publikationsreif.",
    )
    monkeypatch.setattr(MockLLM, "_verdict", lambda self, ctx: weak)
    run = run_cell("energie", "azure-migration")
    assert run.status == "needs_review"
    assert run.gate_passed is False
    assert run.revisions == settings.max_revisions


def test_llm_error_marks_run_failed(client, monkeypatch):
    def boom(self, **kwargs):
        raise LLMError("Rate-Limit erreicht")

    monkeypatch.setattr(MockLLM, "generate", boom)
    run = run_cell("fertigung", "kubernetes")
    assert run.status == "failed"
    assert "Rate-Limit" in run.error
    assert run.steps[-1].status == "failed"
