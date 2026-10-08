import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import get_settings
from app.db import init_db, session_scope
from app.pipeline.jobs import recover_interrupted_runs
from app.publishing.service import republish_all

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    recover_interrupted_runs()
    if settings.publisher == "local":
        with session_scope() as session:
            republish_all(session)  # lokale Website immer im aktuellen Design
    yield


app = FastAPI(
    title="ContentForge",
    description="KI-Content-Pipeline für Programmatic SEO & B2B-Marketing",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)

if settings.publisher == "local":
    settings.site_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/site", StaticFiles(directory=settings.site_dir, html=True), name="site")

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="dashboard")
