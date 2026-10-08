"""Veröffentlichung nach menschlicher Freigabe: Seite rendern, hochladen, Index + Sitemap neu erzeugen."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Run, utcnow
from app.knowledge import load_knowledge
from app.publishing.publishers import get_publisher
from app.publishing.renderer import render_index, render_landing_page, render_robots, render_sitemap
from app.schemas import ContentPackage

HTML = "text/html; charset=utf-8"


def page_url(slug: str) -> str:
    return f"{get_settings().site_base_url.rstrip('/')}/{slug}/"


def render_run(run: Run, *, preview: bool = False) -> str:
    kb = load_knowledge()
    return render_landing_page(
        ContentPackage.model_validate(run.package),
        kb,
        industry=kb.industry(run.industry_id),
        service=kb.service(run.service_id),
        canonical_url=page_url(run.slug),
        home_url=get_settings().site_base_url.rstrip("/") + "/",
        preview=preview,
    )


def publish_run(session: Session, run: Run) -> str:
    publisher = get_publisher()
    publisher.put(f"{run.slug}/index.html", render_run(run), HTML)
    run.status = "published"
    run.published_url = page_url(run.slug)
    run.published_at = utcnow()
    session.flush()
    rebuild_site_index(session)
    return run.published_url


def republish_all(session: Session) -> int:
    """Alle aktuell veröffentlichten Seiten mit dem aktuellen Template neu erzeugen (z. B. nach Design-Änderungen)."""
    latest: dict[str, Run] = {}
    for run in session.scalars(select(Run).where(Run.status == "published").order_by(Run.published_at.desc())):
        latest.setdefault(run.slug, run)
    publisher = get_publisher()
    for run in latest.values():
        publisher.put(f"{run.slug}/index.html", render_run(run), HTML)
    rebuild_site_index(session)
    return len(latest)


def rebuild_site_index(session: Session) -> None:
    """Index, sitemap.xml und robots.txt aus der DB als Single Source of Truth neu erzeugen."""
    settings, kb = get_settings(), load_knowledge()
    base = settings.site_base_url.rstrip("/")
    runs = session.scalars(
        select(Run).where(Run.status == "published").order_by(Run.published_at.desc())
    ).all()
    latest: dict[str, Run] = {}
    for run in runs:  # pro Slug nur die neueste Version
        latest.setdefault(run.slug, run)

    pages = [
        {
            "url": page_url(r.slug),
            "title": r.package["landing_page"]["h1"],
            "description": r.package["landing_page"]["meta_description"],
            "industry_id": r.industry_id,
            "service": kb.service(r.service_id).name,
            "service_icon": kb.service(r.service_id).icon,
        }
        for r in sorted(latest.values(), key=lambda r: (r.industry_id, r.service_id))
    ]
    publisher = get_publisher()
    publisher.put("index.html", render_index(pages, kb, base + "/"), HTML)
    publisher.put(
        "sitemap.xml",
        render_sitemap([(base + "/", utcnow())] + [(page_url(r.slug), r.published_at) for r in latest.values()]),
        "application/xml",
    )
    publisher.put("robots.txt", render_robots(base), "text/plain")
    publisher.put("404.html", render_index([], kb, base + "/", "Diese Seite existiert nicht (mehr)."), HTML)
