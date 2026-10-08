"""Deterministischer Mock-Provider: Demo ohne API-Key/Internet, reproduzierbare Tests und CI-Evals.

Bewusst eingebaut: Bei etwa der Hälfte der Matrix-Zellen enthält der erste Entwurf typische
LLM-Fehler (Garantieversprechen, erfundene Prozentzahl). So ist im Demo sichtbar, wie das
Quality Gate sie erkennt und die Revision sie behebt.
"""

import hashlib
import time
from typing import Any

from app.knowledge import ContentContext, Fact
from app.llm.base import LLMError, LLMResult, T, Usage
from app.schemas import (
    ContentBrief,
    ContentPackage,
    FaqItem,
    JudgeScores,
    JudgeVerdict,
    LandingPage,
    LinkedInPost,
    Newsletter,
    Section,
)

_GOALS = {
    "rag-plattform": "verteiltes Wissen schnell und nachvollziehbar zugänglich zu machen",
    "azure-migration": "bestehende Anwendungen planbar und kontrolliert in die Cloud zu überführen",
    "kubernetes": "neue Services schneller und nach einheitlichen Standards bereitzustellen",
    "workflow-automatisierung": "wiederkehrende Abläufe zu entlasten, ohne die Kontrolle abzugeben",
}
_BENEFITS = {
    "rag-plattform": "Für Ihre Fachbereiche bedeutet das: weniger Suchen, weniger Rückfragen und Antworten, "
    "deren Herkunft sich jederzeit prüfen lässt.",
    "azure-migration": "Für Ihre IT bedeutet das: eine Zielumgebung, die dokumentiert, wiederholbar und "
    "kontrolliert aufgebaut ist, statt einer Migration nach Bauchgefühl.",
    "kubernetes": "Für Ihre Entwicklungsteams bedeutet das: weniger Wartezeit auf Infrastruktur, einheitliche "
    "Standards und Deployments, die sich jederzeit nachvollziehen lassen.",
    "workflow-automatisierung": "Für Ihre Fachbereiche bedeutet das: weniger Routinearbeit, weniger "
    "Medienbrüche und mehr Zeit für Fälle, die wirklich eine Entscheidung brauchen.",
}
_HEADLINES = {
    "rag-plattform": "Antworten mit Quellenangabe",
    "azure-migration": "planbar in die Cloud",
    "kubernetes": "neue Services in kürzerer Zeit",
    "workflow-automatisierung": "Routine automatisieren, Kontrolle behalten",
}
_SERVICE_TAGS = {
    "rag-plattform": "RAG",
    "azure-migration": "CloudMigration",
    "kubernetes": "Kubernetes",
    "workflow-automatisierung": "Automatisierung",
}
_INDUSTRY_TAGS = {
    "fertigung": "Fertigung",
    "energie": "Energiewirtschaft",
    "banken": "Banking",
    "versicherungen": "Versicherung",
}
_REGULATION_FAQ = {
    "banken": ("Welche Rolle spielt DORA für das Projekt?", "F-BK-1"),
    "versicherungen": ("Welche Rolle spielt DORA für das Projekt?", "F-VS-1"),
    "energie": ("Was bedeutet KRITIS für die Umsetzung?", "F-EN-1"),
    "fertigung": ("Was bedeutet der EU AI Act für KI-Projekte?", "F-REG-1"),
}


def _stable_hash(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def _fit(text: str, lo: int, hi: int, filler: str) -> str:
    """Kürzt an Wortgrenzen auf <= hi Zeichen bzw. ergänzt bis >= lo Zeichen."""
    if len(text) < lo:
        text = f"{text} {filler}"
    while len(text) > hi:
        text = text.rsplit(" ", 1)[0].rstrip(",;:–-") + "."
        text = text.replace("..", ".")
    return text


def _meta_description(keyword: str, summary: str) -> str:
    """Erste Variante, die ohne Kürzen in 120–155 Zeichen passt."""
    core = summary.split(" – ")[0].rstrip(".")
    candidates = [
        f"{keyword}: {summary}",
        f"{keyword}: {core}. Vom Proof of Concept bis in den Betrieb.",
        f"{keyword}: {core}. Schrittweise, messbar, beherrschbar.",
        f"{keyword}: {core}.",
    ]
    for text in candidates:
        if 120 <= len(text) <= 155:
            return text
    return _fit(candidates[-1], 120, 155, "Jetzt kostenloses Erstgespräch vereinbaren.")


class MockLLM:
    provider = "mock"

    def __init__(self, latency_s: float = 0.0) -> None:
        self._latency_s = latency_s

    def generate(
        self,
        *,
        task: str,
        system: str,
        prompt: str,
        schema: type[T],
        model: str,
        context: dict[str, Any] | None = None,
    ) -> LLMResult[T]:
        if not context or "ctx" not in context:
            raise LLMError("MockLLM benötigt den ContentContext im Parameter `context`")
        ctx: ContentContext = context["ctx"]
        builders = {
            "brief": lambda: self._brief(ctx),
            "draft": lambda: self._package(ctx, flawed=self.draft_is_flawed(ctx)),
            "revise": lambda: self._package(ctx, flawed=False),
            "judge": lambda: self._verdict(ctx),
        }
        output = builders[task]()
        if not isinstance(output, schema):
            raise LLMError(f"Mock liefert {type(output).__name__}, erwartet {schema.__name__}")

        time.sleep(self._latency_s)
        # Token-Schätzung (~4 Zeichen/Token), damit das Kosten-Tracking auch im Demo realistisch wirkt.
        usage = Usage(
            input_tokens=(len(system) + len(prompt)) // 4,
            output_tokens=len(output.model_dump_json()) // 4,
        )
        return LLMResult(output=output, model=f"mock/{model}", usage=usage)

    @staticmethod
    def draft_is_flawed(ctx: ContentContext) -> bool:
        return _stable_hash(ctx.slug) % 2 == 0

    # ------------------------------------------------------------------ Builder

    def _brief(self, ctx: ContentContext) -> ContentBrief:
        s, i = ctx.service, ctx.industry
        return ContentBrief(
            secondary_keywords=[
                f"{s.name} {i.keyword}",
                f"{s.keyword} Beratung",
                f"{s.keyword} Mittelstand",
                f"{s.keyword} Azure",
                f"{i.name} Digitalisierung",
            ],
            search_intent=(
                f"{i.persona} sucht einen Umsetzungspartner und will Aufwand, Risiken und Vorgehen verstehen."
            ),
            angle=(
                f"Eine {ctx.keyword} löst konkrete Alltagsprobleme – schrittweise, messbar und im eigenen "
                "Betrieb beherrschbar."
            ),
            outline=[
                "Was sich in der Branche verändert",
                f"So funktioniert eine {s.keyword}",
                "Qualität, Sicherheit und Kontrolle",
                "Betrieb und Verantwortung",
            ],
        )

    def _package(self, ctx: ContentContext, *, flawed: bool) -> ContentPackage:
        facts = ctx.facts_by_id()
        s, i, b = ctx.service, ctx.industry, ctx.brand
        sf: list[Fact] = s.facts
        kw = ctx.keyword

        intro = (
            f"Eine {kw} hilft Ihnen, {_GOALS.get(s.id, 'Prozesse zu verbessern')}. {s.summary} "
            "Hier erfahren Sie, wie der Einstieg gelingt und worauf es im laufenden Betrieb ankommt."
        )
        if flawed:
            intro += " Der Projekterfolg ist dabei garantiert."

        sections = [
            Section(
                heading="Was sich in der Branche verändert",
                body=(
                    f"Als {i.persona} bewerten Sie neue Technologie danach, ob sie im Alltag trägt und sich "
                    f"sauber in die bestehende Landschaft einfügt. {i.facts[0].text} Daraus entsteht Druck, "
                    "Abläufe zu vereinfachen und Wissen verlässlich verfügbar zu machen, ohne neue Insellösungen "
                    "zu schaffen oder die Anforderungen an Sicherheit und Nachweisführung aus dem Blick zu verlieren."
                ),
                fact_ids=[i.facts[0].id],
            ),
            Section(
                heading=f"So funktioniert eine {s.keyword}",
                body=(
                    f"{sf[0].text} {sf[1].text} {_BENEFITS.get(s.id, _BENEFITS['rag-plattform'])}"
                ),
                fact_ids=[sf[0].id, sf[1].id],
            ),
            Section(
                heading="Qualität, Sicherheit und Kontrolle",
                body=(
                    f"{sf[2].text} {facts['F-ORG-5'].text} {i.facts[1].text} Architektur, Berechtigungen "
                    "und Betriebsprozesse stimmen wir deshalb früh mit Ihrer IT-Sicherheit ab."
                ),
                fact_ids=[sf[2].id, "F-ORG-5", i.facts[1].id],
            ),
            Section(
                heading="Betrieb und Verantwortung",
                body=(
                    f"Eine {kw} ist erst dann ein Erfolg, wenn Ihr Team sie selbst sicher betreiben kann. "
                    f"{facts['F-ORG-2'].text} {facts['F-ORG-4'].text} Dokumentation, Monitoring und "
                    "Zuständigkeiten legen wir deshalb von Beginn an gemeinsam fest, damit Wissen im Haus bleibt "
                    "und Sie über jeden nächsten Ausbauschritt auf Basis messbarer Ergebnisse entscheiden."
                ),
                fact_ids=["F-ORG-2", "F-ORG-4"],
            ),
        ]

        reg_question, reg_fact = _REGULATION_FAQ.get(i.id, _REGULATION_FAQ["fertigung"])
        faq = [
            FaqItem(
                question=f"Wie gelingt der Einstieg in eine {s.keyword}?",
                answer=f"{facts['F-ORG-3'].text} Erst wenn diese Kriterien erreicht sind, folgt der Rollout.",
            ),
            FaqItem(
                question="Wo werden unsere Daten verarbeitet?",
                answer=f"{facts['F-ORG-5'].text} Die Zielarchitektur wird gemeinsam mit Ihrer IT abgestimmt.",
            ),
            FaqItem(
                question="Können wir die Lösung später selbst betreiben?",
                answer=f"Ja. {facts['F-ORG-4'].text}",
            ),
            FaqItem(
                question=reg_question,
                answer=(
                    f"{facts[reg_fact].text} Architektur und Betriebsprozesse werden so dokumentiert, "
                    "dass sie in Ihr bestehendes Risikomanagement einfließen können."
                ),
            ),
        ]

        seo_title = f"{kw} | {b.short_name}"
        if len(seo_title) > 60:
            seo_title = kw
        landing = LandingPage(
            seo_title=seo_title,
            meta_description=_meta_description(kw, s.summary),
            h1=f"{kw}: {_HEADLINES.get(s.id, 'vom Proof of Concept in den Betrieb')}",
            intro=intro,
            sections=sections,
            faq=faq,
            cta_headline="Lassen Sie uns über Ihren Anwendungsfall sprechen",
            cta_text=(
                f"In einem kostenlosen Erstgespräch klären wir, ob eine {s.keyword} zu Ihrer Ausgangslage "
                "passt und wie ein Proof of Concept aussehen kann."
            ),
        )

        linkedin_body = (
            f"{i.facts[0].text}\n\n{sf[0].text}\n\n{sf[3].text}\n\n"
            f"Unser Ansatz: {facts['F-ORG-3'].text}\n\n"
            f"Wie das für {i.name} konkret aussieht, zeigen wir auf unserer neuen Seite zur {kw}."
        )
        if flawed:
            linkedin_body += " Unsere Kunden sparen im Schnitt 73 % Zeit."
        linkedin = LinkedInPost(
            hook=f"{i.pains[0]}? Das muss nicht so bleiben.",
            body=linkedin_body,
            hashtags=[_SERVICE_TAGS.get(s.id, "Cloud"), _INDUSTRY_TAGS.get(i.id, "Mittelstand"), "KI", "Azure"],
        )

        newsletter = Newsletter(
            subject=f"{s.keyword}: so starten {i.keyword}",
            preheader="Vom Proof of Concept in den Betrieb – ein Leitfaden für Ihre IT.",
            body=(
                f"Guten Tag,\n\n{i.facts[0].text} Eine {s.keyword} setzt genau dort an. {sf[0].text}\n\n"
                f"{sf[3].text} Wichtig ist uns dabei ein schrittweises Vorgehen: {facts['F-ORG-3'].text}\n\n"
                f"Alle Details, typische Fragen und den Ablauf finden Sie auf unserer neuen Seite zur {kw}.\n\n"
                f"Viele Grüße\nIhr Team von {b.short_name}"
            ),
        )
        return ContentPackage(landing_page=landing, linkedin_post=linkedin, newsletter=newsletter)

    def _verdict(self, ctx: ContentContext) -> JudgeVerdict:
        h = _stable_hash(ctx.slug + "judge")
        scores = JudgeScores(persona_fit=4 + h % 2, clarity=4 + (h >> 1) % 2, brand_voice=5, persuasiveness=4)
        return JudgeVerdict(
            scores=scores,
            issues=["Im LinkedIn-Post könnte die Frage am Ende stärker zur Interaktion einladen."],
            summary="Publikationsreif; kleinere stilistische Optimierungen möglich.",
        )
