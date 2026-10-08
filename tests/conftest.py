import os
import tempfile
from pathlib import Path

# Vor dem ersten App-Import setzen: Mock-LLM, synchrone Runs, isolierte DB und Site.
_tmp = Path(tempfile.mkdtemp(prefix="contentforge-test-"))
os.environ.update({
    "LLM_PROVIDER": "mock",
    "MOCK_LATENCY_S": "0",
    "INLINE_RUNS": "true",
    # TEST_DATABASE_URL=postgresql+psycopg://... prüft dieselben Tests gegen PostgreSQL (wie in Azure).
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp / 'test.db'}",
    "SITE_DIR": str(_tmp / "site"),
    "SITE_BASE_URL": "http://testserver/site",
    "PUBLISHER": "local",
    "N8N_WEBHOOK_URL": "",
    "API_KEY": "",
    "DAILY_BUDGET_USD": "100",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.knowledge import build_context, load_knowledge  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.db import Base, get_engine
    from app.main import app

    Base.metadata.drop_all(get_engine())  # leere DB auch bei wiederverwendetem PostgreSQL

    with TestClient(app) as c:
        yield c


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def kb():
    return load_knowledge()


@pytest.fixture
def ctx(kb):
    return build_context(kb, "banken", "rag-plattform")
