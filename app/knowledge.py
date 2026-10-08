"""Wissensbasis: Marke, Leistungen, Branchen und die Fakten, auf die sich Content stützen darf.

Programmatic SEO = Matrix aus Branche x Leistung. Keyword und URL werden deterministisch aus der
Matrix abgeleitet – generativ ist nur der Text. So bleibt die Seitenstruktur planbar und auditierbar.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.config import get_settings


class Fact(BaseModel):
    id: str
    text: str


class ForbiddenTerm(BaseModel):
    pattern: str
    reason: str


class CallToAction(BaseModel):
    label: str
    url: str


class Brand(BaseModel):
    name: str
    short_name: str
    domain: str
    city: str
    tagline: str
    primary_color: str
    cta: CallToAction
    voice: list[str]
    forbidden_terms: list[ForbiddenTerm]
    number_allowlist: list[str] = []


class ProcessStep(BaseModel):
    title: str
    text: str


class Theme(BaseModel):
    """Erscheinungsbild der generierten Seiten je Branche (Farbwelt + Hero-Muster)."""

    pattern: str = "lines"  # industrial | grid | lines | waves
    accent: str = "#0369a1"
    dark: str = "#0f1a2c"
    soft: str = "#f0f9ff"


class Service(BaseModel):
    id: str
    name: str
    keyword: str
    summary: str
    icon: str = "check-circle"
    process: list[ProcessStep] = []
    facts: list[Fact]

    def reference_fact(self) -> Fact | None:
        return next((f for f in self.facts if "Referenz" in f.text), None)


class Industry(BaseModel):
    id: str
    name: str
    keyword: str
    persona: str
    pains: list[str]
    icon: str = "users-three"
    regulation: str = ""
    regulation_fact: str = ""
    theme: Theme = Theme()
    facts: list[Fact]


class KnowledgeBase(BaseModel):
    brand: Brand
    company_facts: list[Fact]
    services: list[Service]
    industries: list[Industry]

    def service(self, service_id: str) -> Service:
        return next(s for s in self.services if s.id == service_id)

    def industry(self, industry_id: str) -> Industry:
        return next(i for i in self.industries if i.id == industry_id)

    def all_facts(self) -> list[Fact]:
        facts = list(self.company_facts)
        for s in self.services:
            facts += s.facts
        for i in self.industries:
            facts += i.facts
        return facts


@dataclass(frozen=True)
class ContentContext:
    """Alles, was die Pipeline für eine Zelle der Matrix braucht."""

    brand: Brand
    industry: Industry
    service: Service
    keyword: str
    slug: str
    facts: list[Fact]  # zulässige Fakten für genau diese Seite

    @property
    def fact_ids(self) -> set[str]:
        return {f.id for f in self.facts}

    def facts_by_id(self) -> dict[str, Fact]:
        return {f.id: f for f in self.facts}


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slugify(text: str) -> str:
    text = text.lower().translate(_UMLAUTS)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


@lru_cache
def load_knowledge(path: Path | None = None) -> KnowledgeBase:
    path = path or get_settings().knowledge_path
    with open(path, encoding="utf-8") as f:
        return KnowledgeBase.model_validate(yaml.safe_load(f))


def build_context(kb: KnowledgeBase, industry_id: str, service_id: str) -> ContentContext:
    industry = kb.industry(industry_id)
    service = kb.service(service_id)
    keyword = f"{service.keyword} für {industry.keyword}"
    return ContentContext(
        brand=kb.brand,
        industry=industry,
        service=service,
        keyword=keyword,
        slug=slugify(keyword),
        facts=[*kb.company_facts, *service.facts, *industry.facts],
    )
