from functools import lru_cache

from app.config import get_settings
from app.llm.base import LLMClient, LLMError, LLMResult, Usage

__all__ = ["LLMClient", "LLMError", "LLMResult", "Usage", "get_llm"]


@lru_cache
def get_llm() -> LLMClient:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(api_key=settings.anthropic_api_key, effort=settings.llm_effort)

    from app.llm.mock_client import MockLLM

    return MockLLM(latency_s=settings.mock_latency_s)
