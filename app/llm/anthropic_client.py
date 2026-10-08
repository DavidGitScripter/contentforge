"""Claude über das offizielle Anthropic SDK – Structured Outputs, Prompt Caching, Refusal-Fallback."""

from typing import Any

import anthropic

from app.llm.base import LLMError, LLMResult, T, Usage

FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5")


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, api_key: str | None, effort: str = "medium") -> None:
        # Ohne expliziten Key greift das SDK auf ANTHROPIC_API_KEY bzw. ein `ant auth login`-Profil zurück.
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=3, timeout=180.0)
        self._effort = effort

    def generate(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        schema: type[T],
        model: str,
        context: dict[str, Any] | None = None,
    ) -> LLMResult[T]:
        options: dict[str, Any] = {}
        if not model.startswith("claude-haiku"):  # Haiku 4.5 unterstützt kein `effort`
            options["output_config"] = {"effort": self._effort}
        if model.startswith(FALLBACK_MODELS):
            # Lehnt das Modell eine Anfrage ab, übernimmt serverseitig ein Fallback-Modell.
            options["betas"] = ["server-side-fallback-2026-07-01"]
            options["fallbacks"] = "default"
        try:
            response = self._client.beta.messages.parse(
                model=model,
                max_tokens=16000,
                # System-Prompt (Marke + Faktenbasis) ist für alle Runs identisch -> Prompt Caching.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                **options,
            )
        except anthropic.RateLimitError as exc:
            raise LLMError(f"Rate-Limit erreicht ({task}) – später erneut versuchen") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMError("Ungültiger oder fehlender ANTHROPIC_API_KEY") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Claude-API-Fehler {exc.status_code} ({task}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"Keine Verbindung zur Claude-API ({task})") from exc

        if response.stop_reason == "refusal":
            raise LLMError(f"Anfrage abgelehnt ({task})")
        if response.stop_reason == "max_tokens":
            raise LLMError(f"Antwort abgeschnitten – max_tokens erreicht ({task})")
        if response.parsed_output is None:
            raise LLMError(f"Antwort entsprach nicht dem Schema {schema.__name__} ({task})")

        u = response.usage
        usage = Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
        )
        return LLMResult(output=response.parsed_output, model=response.model, usage=usage)
