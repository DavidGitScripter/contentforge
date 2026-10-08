import json
import re


def create(client, industry="versicherungen", service="rag-plattform"):
    res = client.post("/api/runs", json={"industry_id": industry, "service_id": service})
    assert res.status_code == 202, res.text
    return res.json()


def test_create_run_and_fetch_detail(client):
    run = create(client)
    detail = client.get(f"/api/runs/{run['id']}").json()
    assert detail["status"] == "awaiting_approval"
    assert detail["package"]["landing_page"]["sections"]
    assert detail["steps"][0]["name"] == "brief"


def test_preview_is_noindex_and_has_structured_data(client):
    run = create(client, "fertigung", "rag-plattform")
    html = client.get(f"/api/runs/{run['id']}/preview").text
    assert 'name="robots" content="noindex' in html
    blocks = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)]
    assert {b["@type"] for b in blocks} == {"Service", "FAQPage"}


def test_approve_publishes_page_and_updates_sitemap(client, settings):
    run = create(client, "energie", "kubernetes")
    res = client.post(f"/api/runs/{run['id']}/approve", json={"reviewer": "test"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "published"
    assert (settings.site_dir / run["slug"] / "index.html").exists()
    assert body["published_url"] in (settings.site_dir / "sitemap.xml").read_text()
    assert client.get(f"/site/{run['slug']}/").status_code == 200


def test_needs_review_requires_override(client, monkeypatch):
    from app.llm.mock_client import MockLLM
    from app.schemas import JudgeScores, JudgeVerdict

    weak = JudgeVerdict(scores=JudgeScores(persona_fit=2, clarity=3, brand_voice=3, persuasiveness=2),
                        issues=["Zu generisch"], summary="Schwach.")
    monkeypatch.setattr(MockLLM, "_verdict", lambda self, ctx: weak)
    run = create(client, "fertigung", "workflow-automatisierung")
    assert client.get(f"/api/runs/{run['id']}").json()["status"] == "needs_review"
    assert client.post(f"/api/runs/{run['id']}/approve", json={}).status_code == 409
    # Ausnahme nur mit Begründung
    assert client.post(f"/api/runs/{run['id']}/approve", json={"override": True}).status_code == 422
    res = client.post(
        f"/api/runs/{run['id']}/approve",
        json={"override": True, "comment": "Manuell geprüft, Tonalität passt", "reviewer": "L. Brandl"},
    )
    assert res.status_code == 200
    events = client.get(f"/api/runs/{run['id']}").json()["events"]
    approved = next(e for e in events if e["action"] == "approved")
    assert approved["actor"] == "L. Brandl" and "Ausnahme" in approved["message"]


def test_reject_requires_reason(client):
    run = create(client, "banken", "kubernetes")
    assert client.post(f"/api/runs/{run['id']}/reject", json={"reason": "  "}).status_code == 422
    res = client.post(f"/api/runs/{run['id']}/reject", json={"reason": "Tonalität"})
    assert res.json()["status"] == "rejected"
    assert client.post(f"/api/runs/{run['id']}/approve", json={}).status_code == 409


def test_request_changes_runs_feedback_through_quality_gate(client):
    run = create(client, "energie", "workflow-automatisierung")
    before = client.get(f"/api/runs/{run['id']}").json()
    assert client.post(f"/api/runs/{run['id']}/request-changes", json={"feedback": "x"}).status_code == 422

    res = client.post(
        f"/api/runs/{run['id']}/request-changes",
        json={"feedback": "Stärker auf KRITIS-Nachweise eingehen", "reviewer": "M. Huber"},
    )
    assert res.status_code == 202
    after = client.get(f"/api/runs/{run['id']}").json()
    assert after["status"] == "awaiting_approval"
    assert after["revisions"] == before["revisions"] + 1
    assert after["attempts"][-1]["source"] == "feedback"
    new_steps = after["steps"][len(before["steps"]):]
    assert [s["name"] for s in new_steps][:2] == ["revise", "checks"]
    assert [e["action"] for e in after["events"]][-2:] == ["changes_requested", "gate_passed"]
    assert after["events"][-2]["comment"] == "Stärker auf KRITIS-Nachweise eingehen"


def test_actor_header_is_recorded(client):
    res = client.post("/api/runs", json={"industry_id": "fertigung", "service_id": "kubernetes"},
                      headers={"X-Actor": "J%C3%BCrgen%20Wei%C3%9F"})  # URL-kodiert wie vom Dashboard
    events = client.get(f"/api/runs/{res.json()['id']}").json()["events"]
    assert events[0]["action"] == "created" and events[0]["actor"] == "Jürgen Weiß"


def test_activity_feed_and_knowledge(client):
    feed = client.get("/api/events?limit=5").json()
    assert 0 < len(feed) <= 5 and {"keyword", "actor", "action"} <= feed[0].keys()
    kb = client.get("/api/knowledge").json()
    assert {"brand", "services", "industries", "company_facts"} <= kb.keys()


def test_unknown_cell_is_rejected(client):
    res = client.post("/api/runs", json={"industry_id": "raumfahrt", "service_id": "rag-plattform"})
    assert res.status_code == 422


def test_budget_guard_blocks_new_runs(client, monkeypatch, settings):
    create(client, "banken", "azure-migration")
    monkeypatch.setattr(settings, "daily_budget_usd", 0.0)
    res = client.post("/api/runs", json={"industry_id": "banken", "service_id": "azure-migration"})
    assert res.status_code == 429


def test_api_key_protects_write_endpoints(client, monkeypatch, settings):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    payload = {"industry_id": "banken", "service_id": "rag-plattform"}
    assert client.post("/api/runs", json=payload).status_code == 401
    assert client.post("/api/runs", json=payload, headers={"X-API-Key": "s3cret"}).status_code == 202
    assert client.get("/api/stats").status_code == 200  # Lesen bleibt offen


def test_batch_skips_existing_cells(client):
    res = client.post("/api/runs/batch", json={"industry_ids": ["versicherungen"], "skip_existing": True}).json()
    keywords = {c["keyword"] for c in res["created"]}
    assert "RAG-Plattform für Versicherer" not in keywords  # existiert bereits aus anderem Test
    assert "rag-plattform-fuer-versicherer" in res["skipped"]


def test_stats_and_matrix(client):
    stats = client.get("/api/stats").json()
    assert stats["runs_total"] > 0 and stats["issues_caught"] >= 0
    assert all({"label", "count"} <= f.keys() for f in stats["top_findings"])
    matrix = client.get("/api/matrix").json()
    assert len(matrix["cells"]) == len(matrix["industries"]) * len(matrix["services"])


def test_concurrent_approvals_publish_only_once(client):
    from concurrent.futures import ThreadPoolExecutor

    run = create(client, "banken", "workflow-automatisierung")
    url = f"/api/runs/{run['id']}/approve"
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = sorted(pool.map(lambda _: client.post(url, json={"reviewer": "Test"}).status_code, range(4)))
    assert codes == [200, 409, 409, 409]
    events = client.get(f"/api/runs/{run['id']}").json()["events"]
    assert sum(e["action"] == "published" for e in events) == 1
