"""Guardrail-Tests: Das Quality Gate muss typische LLM-Fehler zuverlässig finden – und sauberen Content durchlassen."""

from itertools import product

import pytest

from app.knowledge import build_context, load_knowledge
from app.llm.mock_client import MockLLM
from app.pipeline.checks import blocking_issues, quantitative_numbers, run_checks

KB = load_knowledge()
CELLS = list(product([i.id for i in KB.industries], [s.id for s in KB.services]))


def failed(results, check_id):
    return next(r for r in results if r.id == check_id).passed is False


@pytest.mark.parametrize(("industry", "service"), CELLS)
def test_clean_content_passes_all_blocking_checks(industry, service):
    ctx = build_context(KB, industry, service)
    pkg = MockLLM()._package(ctx, flawed=False)
    results = run_checks(pkg, ctx)
    assert blocking_issues(results) == []
    assert all(r.passed for r in results), [r for r in results if not r.passed]


def test_flawed_draft_is_caught(ctx):
    pkg = MockLLM()._package(ctx, flawed=True)
    results = run_checks(pkg, ctx)
    assert failed(results, "brand.forbidden")
    assert failed(results, "grounding.numbers")
    assert len(blocking_issues(results)) == 2


def test_number_must_be_backed_by_facts_cited_in_same_section(ctx):
    pkg = MockLLM()._package(ctx, flawed=False)
    section = pkg.landing_page.sections[1]
    # "40 %" existiert in F-RAG-4 – dieser Abschnitt zitiert F-RAG-4 aber nicht.
    assert "F-RAG-4" not in section.fact_ids
    section.body += " Die Recherchezeit sinkt um 40 %."
    results = run_checks(pkg, ctx)
    assert failed(results, "grounding.numbers")
    assert "40" in next(r for r in results if r.id == "grounding.numbers").detail


def test_unknown_fact_id_is_rejected(ctx):
    pkg = MockLLM()._package(ctx, flawed=False)
    pkg.landing_page.sections[0].fact_ids.append("F-AZ-4")  # Fakt einer anderen Leistung
    assert failed(run_checks(pkg, ctx), "grounding.fact_ids")


def test_informal_address_is_rejected(ctx):
    pkg = MockLLM()._package(ctx, flawed=False)
    pkg.linkedin_post.body += " Was denkst du?"
    assert failed(run_checks(pkg, ctx), "brand.formal")


def test_seo_title_length_and_keyword(ctx):
    pkg = MockLLM()._package(ctx, flawed=False)
    pkg.landing_page.seo_title = "Wissensmanagement neu gedacht für moderne Unternehmen und Teams"
    results = run_checks(pkg, ctx)
    assert failed(results, "seo.title_length")
    assert failed(results, "seo.kw_title")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In 3 Schritten zum Ergebnis", set()),  # einstellige Zahl ohne Einheit = Struktur, kein Claim
        ("Nach 3 Wochen live", {"3"}),  # Einheit macht es zur Tatsachenbehauptung
        ("Spart 25 % Zeit und 1,5 Mio. Euro", {"25", "1.5"}),
        ("Integriert mit Microsoft 365", set()),  # Allowlist für Produktnamen
        ("Seit dem 17. Januar 2025", {"17", "2025"}),
    ],
)
def test_quantitative_number_detection(text, expected):
    assert quantitative_numbers(text, allowlist={"365"}) == expected
