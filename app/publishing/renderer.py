"""Rendert statische, SEO-fertige Seiten: Meta-Tags, Canonical, Open Graph, JSON-LD (Service + FAQPage)."""

import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from app.knowledge import Industry, KnowledgeBase, Service, slugify
from app.publishing.icons import icon
from app.schemas import ContentPackage

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.globals["icon"] = icon
_env.filters["numbers"] = lambda text: highlight_numbers(text)


def _json_ld(pkg: ContentPackage, kb: KnowledgeBase, service: Service, industry: Industry, url: str) -> list[dict]:
    lp = pkg.landing_page
    org = {"@type": "Organization", "name": kb.brand.name, "url": f"https://{kb.brand.domain}"}
    return [
        {
            "@context": "https://schema.org",
            "@type": "Service",
            "name": lp.h1,
            "serviceType": service.name,
            "audience": {"@type": "BusinessAudience", "name": industry.name},
            "description": lp.meta_description,
            "provider": org,
            "areaServed": "DE",
            "url": url,
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": f.question, "acceptedAnswer": {"@type": "Answer", "text": f.answer}}
                for f in lp.faq
            ],
        },
    ]


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?(?:\s?(?:%|Prozent|Tage?n?|Wochen?|Monate?n?|Jahre?n?|Anwendungen))?")


def highlight_numbers(text: str) -> Markup:
    """Zahlen eines Fakts hervorheben (Text wird vorher escaped)."""
    return Markup(_NUMBER.sub(lambda m: f"<strong>{m.group(0)}</strong>", str(escape(text))))


def render_landing_page(
    pkg: ContentPackage,
    kb: KnowledgeBase,
    *,
    industry: Industry,
    service: Service,
    canonical_url: str,
    home_url: str,
    preview: bool = False,
) -> str:
    """Eine Seite pro Matrix-Zelle. Farbwelt und Muster kommen aus der Branche, Ablauf und Referenz aus der
    Leistung. Nur die Texte sind generiert, der Aufbau bleibt deterministisch und prüfbar."""
    facts = {f.id: f for f in kb.all_facts()}
    return _env.get_template("landing_page.html.j2").render(
        page=pkg.landing_page,
        brand=kb.brand,
        industry=industry,
        service=service,
        reference=service.reference_fact(),
        regulation_fact=facts.get(industry.regulation_fact),
        start_fact=facts.get("F-ORG-3"),
        anchor=slugify,
        canonical_url=canonical_url,
        home_url=home_url,
        json_ld=_json_ld(pkg, kb, service, industry, canonical_url),
        preview=preview,
        year=datetime.now().year,
    )


def render_index(
    pages: list[dict], kb: KnowledgeBase, home_url: str, empty_message: str = "Noch keine Seiten veröffentlicht."
) -> str:
    groups = [
        {"industry": i, "pages": [p for p in pages if p["industry_id"] == i.id]}
        for i in kb.industries
    ]
    return _env.get_template("index.html.j2").render(
        groups=[g for g in groups if g["pages"]], brand=kb.brand, home_url=home_url,
        empty_message=empty_message, year=datetime.now().year,
    )


def render_sitemap(urls: list[tuple[str, datetime]]) -> str:
    entries = "\n".join(
        f"  <url><loc>{xml_escape(url)}</loc><lastmod>{ts.date().isoformat()}</lastmod></url>" for url, ts in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def render_robots(base_url: str) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n"
