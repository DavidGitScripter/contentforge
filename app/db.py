"""Persistenz: Runs (ein Content-Paket pro Matrix-Zelle) und Steps (Trace jedes Pipeline-Schritts)."""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import JSON, ForeignKey, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uuid.uuid4().hex[:10])
    industry_id: Mapped[str]
    service_id: Mapped[str]
    keyword: Mapped[str]
    slug: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    provider: Mapped[str]
    prompt_version: Mapped[str]

    brief: Mapped[dict | None] = mapped_column(JSON)
    package: Mapped[dict | None] = mapped_column(JSON)
    checks: Mapped[list | None] = mapped_column(JSON)
    verdict: Mapped[dict | None] = mapped_column(JSON)
    attempts: Mapped[list] = mapped_column(JSON, default=list)

    revisions: Mapped[int] = mapped_column(default=0)
    gate_passed: Mapped[bool | None]
    first_pass: Mapped[bool | None]
    judge_average: Mapped[float | None]
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    duration_ms: Mapped[int | None]

    published_url: Mapped[str | None]
    review_note: Mapped[str | None]
    error: Mapped[str | None]

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None]

    steps: Mapped[list["Step"]] = relationship(
        back_populates="run", order_by="Step.seq", cascade="all, delete-orphan"
    )
    events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="run", order_by="AuditEvent.id", cascade="all, delete-orphan"
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int]
    name: Mapped[str]  # brief | draft | checks | judge | revise | publish
    attempt: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="running")  # running | ok | failed
    model: Mapped[str | None]
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    duration_ms: Mapped[int | None]
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(default=0.0)
    summary: Mapped[str] = mapped_column(default="")

    run: Mapped[Run] = relationship(back_populates="steps")


class AuditEvent(Base):
    """Freigabe-Protokoll: wer hat wann was entschieden (Nachvollziehbarkeit, Vier-Augen-Prinzip)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    actor: Mapped[str]
    # created | gate_passed | gate_failed | failed | changes_requested | approved | published | rejected
    action: Mapped[str]
    message: Mapped[str] = mapped_column(default="")
    comment: Mapped[str | None]

    run: Mapped[Run] = relationship(back_populates="events")


def log_event(
    session: Session, run_id: str, action: str, actor: str, message: str = "", comment: str | None = None
) -> None:
    session.add(AuditEvent(run_id=run_id, action=action, actor=actor, message=message, comment=comment or None))


def record_event(run_id: str, action: str, actor: str, message: str = "", comment: str | None = None) -> None:
    """Wie log_event, aber mit eigener Transaktion (für Hintergrund-Jobs)."""
    with session_scope() as session:
        log_event(session, run_id, action, actor, message, comment)


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url.startswith("sqlite"):
        # Lokal/Tests: eine Datei, keine Installation nötig.
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    # Azure: PostgreSQL Flexible Server. pool_pre_ping erkennt Verbindungen, die Azure nach Leerlauf getrennt hat.
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI-Dependency."""
    with session_scope() as session:
        yield session


def cost_today(session: Session) -> float:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    total = session.scalar(select(func.coalesce(func.sum(Step.cost_usd), 0.0)).where(Step.started_at >= start))
    return float(total or 0.0)
