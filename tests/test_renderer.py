"""Generierte Seiten unterscheiden sich je Branche (Farbwelt, Muster, Regulierung) und Leistung (Ablauf, Referenz)."""

from app.knowledge import build_context, load_knowledge
from app.llm.mock_client import MockLLM
from app.publishing.renderer import highlight_numbers, render_landing_page


def render(industry_id: str, service_id: str) -> str:
    kb = load_knowledge()
    ctx = build_context(kb, industry_id, service_id)
    return render_landing_page(
        MockLLM()._package(ctx, flawed=False), kb,
        industry=kb.industry(industry_id), service=kb.service(service_id),
        canonical_url="https://example.test/x/", home_url="https://example.test/",
    )


def test_industry_theme_and_regulation_differ():
    banken, fertigung = render("banken", "rag-plattform"), render("fertigung", "rag-plattform")
    assert "--accent: #1d4ed8" in banken and "pattern-lines" in banken and "DORA" in banken
    assert "--accent: #c2410c" in fertigung and "pattern-industrial" in fertigung and "EU AI Act" in fertigung


def test_service_process_and_reference_differ():
    rag, azure = render("energie", "rag-plattform"), render("energie", "azure-migration")
    assert "Evaluation mit Fachfragen" in rag and "Landing Zone" in azure
    assert "<strong>40 %</strong>" in rag and "<strong>120 Anwendungen</strong>" in azure


def test_page_is_responsive_and_accessible():
    html = render("versicherungen", "kubernetes")
    assert 'name="viewport"' in html and "@media (max-width: 600px)" in html
    assert html.count("<h1") == 1 and 'aria-label="Brotkrumen"' in html


def test_highlight_numbers_escapes_text():
    assert str(highlight_numbers("<b>um 65 %</b>")) == "&lt;b&gt;um <strong>65 %</strong>&lt;/b&gt;"
