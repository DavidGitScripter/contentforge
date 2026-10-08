"""Versionierte Prompts. Die Version wird an jedem Run gespeichert – Ergebnisse bleiben vergleichbar,
wenn Prompts weiterentwickelt werden (Grundlage für Evals/A-B-Vergleiche)."""

from app.knowledge import ContentContext, KnowledgeBase
from app.schemas import ContentBrief, ContentPackage

PROMPT_VERSION = "2026-09.4"


def system_prompt(kb: KnowledgeBase) -> str:
    """Stabil für alle Runs (Marke + komplette Faktenbasis) -> ideal für Prompt Caching."""
    b = kb.brand
    voice = "\n".join(f"- {v}" for v in b.voice)
    forbidden = "\n".join(f"- /{t.pattern}/ – {t.reason}" for t in b.forbidden_terms)
    facts = "\n".join(f"[{f.id}] {f.text}" for f in kb.all_facts())
    return f"""Du bist Senior Content Strategist für B2B-Technologiemarketing bei {b.name} ({b.city}).
Du schreibst deutschsprachige Inhalte für IT-Entscheider:innen im Mittelstand und in regulierten Branchen.

# Markenstimme
{voice}

# Verbotene Formulierungen (Regex, Groß-/Kleinschreibung egal)
{forbidden}

# Faktenbasis – einzige zulässige Quelle für Tatsachenbehauptungen
{facts}

# Regeln für Fakten (nicht verhandelbar)
1. Aussagen über {b.short_name}, Projekte, Ergebnisse oder Regulierung nur, wenn ein Fakt sie belegt.
2. Jede Zahl (Prozent, Dauer, Anzahl, Datum) muss wörtlich aus einem Fakt stammen. Bei Landingpage-
   Abschnitten muss dieser Fakt in `fact_ids` desselben Abschnitts stehen.
3. Verwende nur Fakt-IDs, die in der Aufgabe als zulässig genannt werden.
4. Erfinde keine Kunden, Zertifizierungen, Auszeichnungen, Preise oder Zitate.
5. Referenzprojekte bleiben als Demo-Referenz erkennbar."""


def _context_block(ctx: ContentContext) -> str:
    pains = "\n".join(f"- {p}" for p in ctx.industry.pains)
    return f"""Haupt-Keyword: {ctx.keyword}
URL: /{ctx.slug}/
Leistung: {ctx.service.name} – {ctx.service.summary}
Branche: {ctx.industry.name}
Persona: {ctx.industry.persona}
Pain Points der Persona:
{pains}
Zulässige Fakt-IDs: {", ".join(sorted(ctx.fact_ids))}"""


def brief_prompt(ctx: ContentContext) -> str:
    return f"""Erstelle ein Content-Briefing für eine SEO-Landingpage.

{_context_block(ctx)}

Das Briefing soll die Suchintention der Persona treffen und eine klare Kernbotschaft festlegen.
Die Gliederung soll von der Problemlage der Persona zum konkreten Vorgehen führen."""


def draft_prompt(ctx: ContentContext, brief: ContentBrief) -> str:
    return f"""Erstelle ein Content-Paket (Landingpage, LinkedIn-Post, Newsletter-Teaser) auf Basis des Briefings.

{_context_block(ctx)}

Briefing:
{brief.model_dump_json(indent=2)}

Anforderungen Landingpage:
- seo_title 30–60 Zeichen, enthält das Haupt-Keyword wörtlich; H1 enthält das Haupt-Keyword.
- meta_description 120–155 Zeichen mit Haupt-Keyword und Nutzenversprechen.
- intro: 2–3 Sätze, Haupt-Keyword wörtlich im ersten Satz.
- 4–5 sections (60–110 Wörter je Abschnitt) entlang der Gliederung, jeweils mit fact_ids.
- Die Seite zeigt Pain Points der Branche, den Projektablauf, die Demo-Referenz und die FAQ bereits als
  feste Bausteine. Wiederhole sie in den sections nicht als Aufzählung, sondern erkläre Lösung, Nutzen,
  Sicherheit und Betrieb aus Sicht der Persona.
- 3–4 FAQ, die echte Einwände der Persona beantworten.
- Haupt-Keyword insgesamt 3–5-mal natürlich verwenden, sekundäre Keywords einstreuen.
- cta_headline + cta_text führen zu: „{ctx.brand.cta.label}“.

Anforderungen LinkedIn: Hook max. 150 Zeichen, Body max. 1.100 Zeichen in kurzen Absätzen,
3–5 Hashtags ohne #. Newsletter: Betreff max. 60 Zeichen, Preheader max. 100 Zeichen, Body 80–150 Wörter."""


def judge_prompt(ctx: ContentContext, package: ContentPackage) -> str:
    return f"""Du bist kritische:r Marketing-Lead und entscheidest, ob dieses Content-Paket veröffentlicht wird.

{_context_block(ctx)}

Content-Paket:
{package.model_dump_json(indent=2)}

Bewerte jedes Kriterium von 1 (unbrauchbar) bis 5 (publikationsreif, keine Änderung nötig).
Vergib 5 nur, wenn du den Text ohne Änderungen freigeben würdest. Formale Regeln (Längen, Zahlen,
verbotene Begriffe) wurden bereits automatisch geprüft – konzentriere dich auf Wirkung und Qualität.
Nenne in `issues` nur konkrete, umsetzbare Verbesserungen (max. 5)."""


def revise_prompt(ctx: ContentContext, package: ContentPackage, issues: list[str]) -> str:
    issue_list = "\n".join(f"- {i}" for i in issues)
    return f"""Überarbeite das Content-Paket. Behebe ALLE folgenden Probleme vollständig und ändere
darüber hinaus so wenig wie möglich.

Probleme:
{issue_list}

{_context_block(ctx)}

Aktuelles Content-Paket:
{package.model_dump_json(indent=2)}"""
