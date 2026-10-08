from types import SimpleNamespace

from app.config import KEY_VAULT_SECRETS, Settings, load_key_vault_secrets


class FakeSecretClient:
    def __init__(self, secrets: dict[str, str]) -> None:
        self.secrets = secrets
        self.requested: list[str] = []

    def get_secret(self, name: str) -> SimpleNamespace:
        self.requested.append(name)
        return SimpleNamespace(value=self.secrets[name])


def test_key_vault_secrets_map_to_settings_fields():
    client = FakeSecretClient({
        "anthropic-api-key": "sk-test",
        "app-api-key": "app-test",
        "database-url": "postgresql+psycopg://u:p@host:5432/db",
    })

    values = load_key_vault_secrets("https://kv-test.vault.azure.net/", client=client)

    assert sorted(client.requested) == sorted(KEY_VAULT_SECRETS)
    assert values == {
        "anthropic_api_key": "sk-test",
        "api_key": "app-test",
        "database_url": "postgresql+psycopg://u:p@host:5432/db",
    }
    # Jedes Ziel muss ein echtes Settings-Feld sein, sonst ginge der Wert stillschweigend verloren
    assert set(values) <= set(Settings.model_fields)
