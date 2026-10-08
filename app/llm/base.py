"""Provider-neutrales Interface: Die Pipeline kennt nur `LLMClient.generate()`.

Dadurch lassen sich Claude, ein Mock (Offline-Demo, Tests, CI) oder später ein Router wie LiteLLM
austauschen, ohne die Pipeline anzufassen.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# USD pro 1 Mio. Tokens (Stand 2026-09). Cache-Reads = 10 %, Cache-Writes = 125 % des Input-Preises.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost_usd(self, model: str) -> float:
        price_in, price_out = PRICES_USD_PER_MTOK.get(model, PRICES_USD_PER_MTOK["claude-opus-5"])
        cost = (
            self.input_tokens * price_in
            + self.cache_write_tokens * price_in * 1.25
            + self.cache_read_tokens * price_in * 0.10
            + self.output_tokens * price_out
        ) / 1_000_000
        return round(cost, 6)


@dataclass
class LLMResult[T]:
    output: T
    model: str
    usage: Usage = field(default_factory=Usage)


class LLMError(RuntimeError):
    """Fachlicher Fehler des Modells (Refusal, abgeschnittene Antwort, ungültiges Schema)."""


class LLMClient(Protocol):
    provider: str

    def generate(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        schema: type[T],
        model: str,
        context: dict[str, Any] | None = None,
    ) -> LLMResult[T]: ...
