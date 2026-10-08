"""Zentrale Konfiguration – alles über Umgebungsvariablen (12-Factor), lokal via .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM -------------------------------------------------------------
    llm_provider: Literal["mock", "anthropic"] = "mock"
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5"
    llm_judge_model: str = "claude-opus-5"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    mock_latency_s: float = 0.7

    # --- Pipeline / Quality Gate ------------------------------------------
    max_revisions: int = 2
    judge_min_avg: float = 4.0
    judge_min_single: int = 3
    max_concurrent_runs: int = 3
    daily_budget_usd: float = 5.0
    inline_runs: bool = False  # Tests/Evals: Pipeline synchron statt im Thread-Pool

    # --- Daten & Wissen ---------------------------------------------------
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'contentforge.db'}"
    knowledge_path: Path = BASE_DIR / "knowledge" / "brand.yaml"

    # --- Publishing -------------------------------------------------------
    publisher: Literal["local", "azure_blob"] = "local"
    site_dir: Path = BASE_DIR / "site"
    site_base_url: str = "http://localhost:8000/site"
    azure_storage_account_url: str | None = None  # https://<account>.blob.core.windows.net

    # --- Integration & Sicherheit -----------------------------------------
    n8n_webhook_url: str | None = None
    dashboard_base_url: str = "http://localhost:8000"
    api_key: str | None = None  # wenn gesetzt: schreibende Endpunkte brauchen X-API-Key
    app_version: str = "lokal"  # im Image gesetzt (Docker build-arg = Commit-SHA aus GitHub Actions)

    # --- Azure Key Vault ---------------------------------------------------
    azure_key_vault_url: str | None = None  # gesetzt (nur in Azure): Secrets beim Start aus dem Key Vault laden


# Secret-Name im Key Vault -> Feld in Settings
KEY_VAULT_SECRETS = {
    "anthropic-api-key": "anthropic_api_key",
    "app-api-key": "api_key",
    "database-url": "database_url",
}


def load_key_vault_secrets(vault_url: str, client=None) -> dict[str, str]:
    """Liest die Secrets per Managed Identity (DefaultAzureCredential) – kein Passwort in Code, Image oder Umgebung.

    Container Apps "Express" unterstützt keine Key-Vault-Referenzen in der App-Konfiguration, deshalb holt die App
    die Werte beim Start selbst. Lokal funktioniert derselbe Code mit dem `az login` der Entwickler:in.
    """
    if client is None:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    return {field: client.get_secret(name).value for name, field in KEY_VAULT_SECRETS.items()}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.azure_key_vault_url:
        settings = settings.model_copy(update=load_key_vault_secrets(settings.azure_key_vault_url))
    return settings
