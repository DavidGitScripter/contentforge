"""Der echte Claude-Client gegen einen lokalen Fake-Server: prüft Request-Aufbau und Response-Handling ohne API-Key."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.llm import LLMError
from app.llm.anthropic_client import AnthropicLLM
from app.schemas import ContentBrief

BRIEF = {
    "secondary_keywords": ["RAG Banken", "KI-Wissensplattform"],
    "search_intent": "Umsetzungspartner finden",
    "angle": "Wissen schneller finden",
    "outline": ["Ausgangslage", "Lösung", "Vorgehen"],
}


@pytest.fixture
def fake_api(monkeypatch):
    state = {"requests": [], "stop_reason": "end_turn"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append({"path": self.path, "headers": dict(self.headers), "body": body})
            payload = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": json.dumps(BRIEF)}],
                "stop_reason": state["stop_reason"],
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 3000,
                },
            }
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    yield state
    server.shutdown()


def generate(model="claude-opus-5"):
    llm = AnthropicLLM(api_key="test-key", effort="medium")
    return llm.generate(task="brief", system="SYSTEM", prompt="PROMPT", schema=ContentBrief, model=model)


def test_request_uses_structured_output_caching_and_fallback(fake_api):
    result = generate()

    assert isinstance(result.output, ContentBrief)
    assert result.output.outline == BRIEF["outline"]
    req = fake_api["requests"][0]
    body = req["body"]
    assert req["path"].startswith("/v1/messages")
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["effort"] == "medium"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req["headers"]["anthropic-beta"]
    # 1000 In + 3000 Cache-Read (10 %) + 200 Out bei Opus-5-Preisen
    assert result.usage.cost_usd("claude-opus-5") == pytest.approx((1000 * 5 + 3000 * 0.5 + 200 * 25) / 1e6)


def test_haiku_judge_gets_no_effort_and_no_fallback(fake_api):
    generate(model="claude-haiku-4-5")
    body = fake_api["requests"][0]["body"]
    assert "effort" not in body.get("output_config", {})
    assert "fallbacks" not in body


def test_refusal_raises_llm_error(fake_api):
    fake_api["stop_reason"] = "refusal"
    with pytest.raises(LLMError, match="abgelehnt"):
        generate()
