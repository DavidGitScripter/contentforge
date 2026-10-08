"""Ziele für veröffentlichte Seiten: lokales Verzeichnis (Dev) oder Azure Blob Storage Static Website (Prod)."""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class Publisher(Protocol):
    def put(self, path: str, content: str, content_type: str) -> None: ...


class LocalPublisher:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, path: str, content: str, content_type: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class AzureBlobPublisher:
    """Schreibt in den `$web`-Container. Auth über Managed Identity (DefaultAzureCredential) – kein Key im Code."""

    def __init__(self, account_url: str, container: str = "$web") -> None:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        service = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
        self._container = service.get_container_client(container)

    def put(self, path: str, content: str, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        self._container.upload_blob(
            name=path,
            data=content.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type, cache_control="public, max-age=300"),
        )


@lru_cache
def get_publisher() -> Publisher:
    settings = get_settings()
    if settings.publisher == "azure_blob":
        if not settings.azure_storage_account_url:
            raise RuntimeError("PUBLISHER=azure_blob erfordert AZURE_STORAGE_ACCOUNT_URL")
        return AzureBlobPublisher(settings.azure_storage_account_url)
    return LocalPublisher(settings.site_dir)
