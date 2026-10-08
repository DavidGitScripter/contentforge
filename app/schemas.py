"""Typisierte Verträge zwischen Pipeline und LLM (Structured Outputs) sowie für die REST-API.

Die LLM-Schemas werden per `messages.parse(output_format=...)` erzwungen – Claude liefert garantiert
valides JSON in genau dieser Form, kein fragiles Parsen von Freitext.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

# --------------------------------------------------------------------------- LLM-Outputs


class ContentBrief(BaseModel):
    secondary_keywords: list[str] = Field(description="4-6 verwandte Suchbegriffe")
    search_intent: str = Field(description="Suchintention der Persona in einem Satz")
    angle: str = Field(description="Kernbotschaft der Seite in einem Satz")
    outline: list[str] = Field(description="4-5 H2-Zwischenüberschriften in sinnvoller Reihenfolge")


class Section(BaseModel):
    heading: str = Field(description="H2-Zwischenüberschrift")
    body: str = Field(description="Fließtext, 60-110 Wörter")
    fact_ids: list[str] = Field(description="IDs aller Fakten, auf die sich dieser Abschnitt stützt")


class FaqItem(BaseModel):
    question: str
    answer: str


class LandingPage(BaseModel):
    seo_title: str = Field(description="30-60 Zeichen, enthält das Haupt-Keyword")
    meta_description: str = Field(description="120-155 Zeichen, enthält das Haupt-Keyword")
    h1: str
    intro: str = Field(description="2-3 Sätze, Haupt-Keyword im ersten Satz")
    sections: list[Section]
    faq: list[FaqItem]
    cta_headline: str
    cta_text: str


class LinkedInPost(BaseModel):
    hook: str = Field(description="Erste Zeile, max. 150 Zeichen")
    body: str = Field(description="Max. 1100 Zeichen, kurze Absätze")
    hashtags: list[str] = Field(description="3-5 Hashtags ohne #")


class Newsletter(BaseModel):
    subject: str = Field(description="Max. 60 Zeichen")
    preheader: str = Field(description="Max. 100 Zeichen")
    body: str = Field(description="80-150 Wörter")


class ContentPackage(BaseModel):
    landing_page: LandingPage
    linkedin_post: LinkedInPost
    newsletter: Newsletter


class JudgeScores(BaseModel):
    persona_fit: int = Field(description="1-5: Trifft der Text Probleme und Sprache der Persona?")
    clarity: int = Field(description="1-5: Verständlich, konkret, gut strukturiert?")
    brand_voice: int = Field(description="1-5: Entspricht der Text den Markenregeln?")
    persuasiveness: int = Field(description="1-5: Führt der Text überzeugend zum Call-to-Action?")


class JudgeVerdict(BaseModel):
    scores: JudgeScores
    issues: list[str] = Field(description="Max. 5 konkrete, umsetzbare Verbesserungen")
    summary: str = Field(description="Gesamturteil in einem Satz")

    @property
    def average(self) -> float:
        s = self.scores
        return round((s.persona_fit + s.clarity + s.brand_voice + s.persuasiveness) / 4, 2)

    @property
    def minimum(self) -> int:
        s = self.scores
        return min(s.persona_fit, s.clarity, s.brand_voice, s.persuasiveness)


# --------------------------------------------------------------------------- Quality Gate


class CheckResult(BaseModel):
    id: str
    category: Literal["SEO", "Marke", "Grounding", "Kanal"]
    label: str
    passed: bool
    severity: Literal["error", "warning"]
    detail: str = ""


# --------------------------------------------------------------------------- API

RunStatus = Literal[
    "queued", "running", "awaiting_approval", "needs_review", "published", "rejected", "failed"
]


class RunCreate(BaseModel):
    industry_id: str
    service_id: str


class BatchCreate(BaseModel):
    industry_ids: list[str] | None = None
    service_ids: list[str] | None = None
    skip_existing: bool = Field(True, description="Zellen mit veröffentlichter oder offener Seite überspringen")


Reviewer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
RequiredComment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]


class ApproveRequest(BaseModel):
    reviewer: Reviewer = "Dashboard"
    comment: Comment = ""
    override: bool = Field(False, description="Veröffentlichen, obwohl das Quality Gate nicht bestanden wurde")


class RejectRequest(BaseModel):
    reviewer: Reviewer = "Dashboard"
    reason: RequiredComment


class ChangeRequest(BaseModel):
    reviewer: Reviewer = "Dashboard"
    feedback: RequiredComment = Field(description="Was soll die KI in der Überarbeitung ändern?")


class StepOut(BaseModel):
    seq: int
    name: str
    attempt: int
    status: str
    model: str | None
    duration_ms: int | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    summary: str


class RunOut(BaseModel):
    id: str
    industry_id: str
    service_id: str
    keyword: str
    slug: str
    status: RunStatus
    provider: str
    prompt_version: str
    revisions: int
    gate_passed: bool | None
    first_pass: bool | None
    judge_average: float | None
    cost_usd: float
    duration_ms: int | None
    published_url: str | None
    published_at: datetime | None
    review_note: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class EventOut(BaseModel):
    id: int
    run_id: str
    created_at: datetime
    actor: str
    action: str
    message: str
    comment: str | None


class FeedEvent(EventOut):
    keyword: str


class RunDetail(RunOut):
    brief: dict | None
    package: dict | None
    checks: list[dict] | None
    verdict: dict | None
    attempts: list[dict]
    steps: list[StepOut]
    events: list[EventOut]
