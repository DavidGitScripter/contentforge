"""Deterministisches Quality Gate – schnell, kostenlos, reproduzierbar.

Läuft vor dem LLM-Judge: Harte Fehler (errors) lösen direkt eine Revision aus, ohne Tokens für eine
Bewertung zu verbrennen. Warnungen werden angezeigt, blockieren aber nicht.

Kernidee Grounding: Jede quantitative Aussage (Prozent, Dauer, Anzahl, Jahr) muss wörtlich in einem
Fakt der Wissensbasis stehen – bei Landingpage-Abschnitten sogar in einem Fakt, den der Abschnitt
selbst zitiert. Das ist der wirksamste Schutz gegen halluzinierte Zahlen im Marketing.
"""

import re

from app.knowledge import ContentContext
from app.schemas import CheckResult, ContentPackage

_UNITS = (
    r"%|prozent|tag(?:e|en)?|woche(?:n)?|monat(?:e|en)?|jahr(?:e|en)?|stunde(?:n)?|minute(?:n)?"
    r"|euro|€|mio\.?|millionen|mrd\.?|milliarden"
)
_NUMBER = re.compile(rf"(?<![\w.,])(\d+(?:[.,]\d+)?)\s*({_UNITS})?(?![\w])", re.IGNORECASE)
_INFORMAL = re.compile(r"\b(du|dich|dir|dein\w*|euch|euer\w*)\b", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("-", " ")).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[\wäöüß]+", text.lower())


def quantitative_numbers(text: str, allowlist: set[str] | None = None) -> set[str]:
    """Zahlen, die als Tatsachenbehauptung gelten: >= 2 Stellen oder mit Einheit (%, Wochen, Euro …)."""
    found = set()
    for match in _NUMBER.finditer(text):
        number, unit = match.group(1), match.group(2)
        if (len(re.sub(r"\D", "", number)) >= 2 or unit) and number not in (allowlist or set()):
            found.add(number.replace(",", "."))
    return found


def _all_numbers(text: str) -> set[str]:
    return {m.group(1).replace(",", ".") for m in _NUMBER.finditer(text)}


def page_text(pkg: ContentPackage) -> str:
    lp = pkg.landing_page
    parts = [lp.h1, lp.intro]
    for s in lp.sections:
        parts += [s.heading, s.body]
    for f in lp.faq:
        parts += [f.question, f.answer]
    parts += [lp.cta_headline, lp.cta_text]
    return "\n".join(parts)


def channel_texts(pkg: ContentPackage) -> dict[str, str]:
    li, nl = pkg.linkedin_post, pkg.newsletter
    return {
        "Landingpage": page_text(pkg) + "\n" + pkg.landing_page.seo_title + "\n" + pkg.landing_page.meta_description,
        "LinkedIn": f"{li.hook}\n{li.body}",
        "Newsletter": f"{nl.subject}\n{nl.preheader}\n{nl.body}",
    }


def run_checks(pkg: ContentPackage, ctx: ContentContext) -> list[CheckResult]:
    results: list[CheckResult] = []

    def add(id_, category, label, passed, severity="error", detail=""):
        results.append(
            CheckResult(id=id_, category=category, label=label, passed=passed, severity=severity, detail=detail)
        )

    lp = pkg.landing_page
    kw = _norm(ctx.keyword)
    body = page_text(pkg)
    word_count = len(_words(body))

    # ------------------------------------------------------------------ SEO
    n = len(lp.seo_title)
    add("seo.title_length", "SEO", "Title-Tag 30-60 Zeichen", 30 <= n <= 60, detail=f"{n} Zeichen")
    n = len(lp.meta_description)
    add("seo.meta_length", "SEO", "Meta-Description 120-160 Zeichen", 120 <= n <= 160, detail=f"{n} Zeichen")
    add("seo.kw_title", "SEO", "Keyword im Title-Tag", kw in _norm(lp.seo_title), detail=ctx.keyword)
    add("seo.kw_h1", "SEO", "Keyword in der H1", kw in _norm(lp.h1), "warning")
    add("seo.kw_meta", "SEO", "Keyword in der Meta-Description", kw in _norm(lp.meta_description), "warning")
    first_sentence = re.split(r"(?<=[.!?])\s", lp.intro, maxsplit=1)[0]
    add("seo.kw_intro", "SEO", "Keyword im ersten Satz", kw in _norm(first_sentence), "warning")
    add(
        "seo.structure", "SEO", "Mind. 3 H2-Abschnitte", len(lp.sections) >= 3,
        detail=f"{len(lp.sections)} Abschnitte",
    )
    add("seo.faq", "SEO", "Mind. 3 FAQ (Rich Snippet)", len(lp.faq) >= 3, "warning", f"{len(lp.faq)} Fragen")
    add("seo.word_count", "SEO", "Mind. 350 Wörter Inhalt", word_count >= 350, "warning", f"{word_count} Wörter")
    occurrences = _norm(body).count(kw)
    density = occurrences * len(kw.split()) / max(word_count, 1) * 100
    add(
        "seo.kw_density", "SEO", "Keyword-Dichte 0,5-3 %", 0.5 <= density <= 3.0, "warning",
        f"{density:.1f} %, {occurrences}-mal".replace(".", ","),
    )

    # ------------------------------------------------------------------ Marke
    texts = channel_texts(pkg)
    hits = []
    for term in ctx.brand.forbidden_terms:
        for channel, text in texts.items():
            m = re.search(term.pattern, text, re.IGNORECASE)
            if m:
                hits.append(f"„{m.group(0)}“ in {channel} ({term.reason})")
    add("brand.forbidden", "Marke", "Keine verbotenen Formulierungen", not hits, detail="; ".join(hits))

    informal = sorted({m.group(0) for t in texts.values() for m in _INFORMAL.finditer(t)})
    add("brand.formal", "Marke", "Konsequente Sie-Form", not informal, detail=", ".join(informal))
    exclamations = sum(t.count("!") for t in texts.values())
    add("brand.exclamation", "Marke", "Max. 1 Ausrufezeichen", exclamations <= 1, "warning",
        f"{exclamations} gefunden" if exclamations else "keine")

    # ------------------------------------------------------------------ Grounding
    facts = ctx.facts_by_id()
    allowlist = set(ctx.brand.number_allowlist)
    cited = {fid for s in lp.sections for fid in s.fact_ids}
    unknown = sorted(cited - ctx.fact_ids)
    add(
        "grounding.fact_ids", "Grounding", "Nur zulässige Fakten zitiert", not unknown,
        detail=("Unbekannte IDs: " + ", ".join(unknown)) if unknown else f"{len(cited)} Fakten zitiert",
    )
    uncited = [s.heading for s in lp.sections if not s.fact_ids]
    add("grounding.sections_cited", "Grounding", "Jeder Abschnitt stützt sich auf Fakten", not uncited,
        "warning", "; ".join(uncited))

    ungrounded: list[str] = []
    for s in lp.sections:
        evidence = set().union(*[_all_numbers(facts[f].text) for f in s.fact_ids if f in facts])
        for num in sorted(quantitative_numbers(s.body, allowlist) - evidence):
            ungrounded.append(f"„{num}“ in Abschnitt „{s.heading}“")
    all_evidence = set().union(*[_all_numbers(f.text) for f in ctx.facts])
    rest = {
        "Intro/FAQ/CTA": "\n".join([lp.h1, lp.intro, lp.seo_title, lp.meta_description, lp.cta_headline, lp.cta_text]
                                   + [f"{f.question} {f.answer}" for f in lp.faq]),
        "LinkedIn": texts["LinkedIn"],
        "Newsletter": texts["Newsletter"],
    }
    for where, text in rest.items():
        for num in sorted(quantitative_numbers(text, allowlist) - all_evidence):
            ungrounded.append(f"„{num}“ in {where}")
    add("grounding.numbers", "Grounding", "Alle Zahlen durch Fakten belegt", not ungrounded,
        detail="; ".join(ungrounded) or "Keine unbelegten Zahlen")

    # ------------------------------------------------------------------ Kanäle
    li, nl = pkg.linkedin_post, pkg.newsletter
    li_len = len(li.hook) + len(li.body) + sum(len(h) + 2 for h in li.hashtags)
    add("channel.li_length", "Kanal", "LinkedIn-Post max. 1.300 Zeichen", li_len <= 1300, detail=f"{li_len} Zeichen")
    add("channel.li_hook", "Kanal", "LinkedIn-Hook max. 150 Zeichen", len(li.hook) <= 150, "warning",
        f"{len(li.hook)} Zeichen")
    add("channel.li_hashtags", "Kanal", "3-5 Hashtags", 3 <= len(li.hashtags) <= 5, "warning",
        f"{len(li.hashtags)} Hashtags")
    add("channel.nl_subject", "Kanal", "Betreffzeile max. 60 Zeichen", len(nl.subject) <= 60, "warning",
        f"{len(nl.subject)} Zeichen")
    add("channel.nl_preheader", "Kanal", "Preheader max. 100 Zeichen", len(nl.preheader) <= 100, "warning",
        f"{len(nl.preheader)} Zeichen")
    return results


# Blockierende Befunde als Problem formuliert (für Revision, Protokoll und Befund-Statistik)
PROBLEMS = {
    "seo.title_length": "Title-Tag mit falscher Länge",
    "seo.meta_length": "Meta-Description mit falscher Länge",
    "seo.kw_title": "Keyword fehlt im Title-Tag",
    "seo.structure": "Zu wenige Zwischenüberschriften",
    "brand.forbidden": "Verbotene Formulierung",
    "brand.formal": "Duzen statt Siezen",
    "grounding.fact_ids": "Unzulässiger Fakt zitiert",
    "grounding.numbers": "Zahl ohne Faktenbeleg",
    "channel.li_length": "LinkedIn-Post zu lang",
}


def blocking_issues(results: list[CheckResult]) -> list[str]:
    return [
        f"{PROBLEMS.get(r.id, r.label)}: {r.detail}" for r in results if not r.passed and r.severity == "error"
    ]
