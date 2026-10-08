"""Erzeugt einen realistischen Demo-Arbeitsstand (Mock-Modus, kostenlos).

    python -m scripts.seed_demo            # ergänzt die bestehende Datenbank
    python -m scripts.seed_demo --reset    # löscht lokale Demo-Daten (data/, site/) und baut neu auf

Alle Aktionen laufen über die echte REST-API (inkl. Quality Gate, Protokoll, Veröffentlichung).
Danach werden die Zeitstempel über die letzten Tage verteilt, damit Übersicht und Protokoll lebendig wirken.
"""

import argparse
import os
import shutil
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Szenario: (Branche, Leistung, Aktion, Prüfer:in, Kommentar)
SCENARIO = [
    ("banken", "rag-plattform", "approve", "Katharina Vogt", "Freigegeben. Quellenangaben und DORA-Bezug passen."),
    ("banken", "azure-migration", "approve", "Katharina Vogt", ""),
    ("fertigung", "rag-plattform", "approve", "Stefan Huber", "Passt für die Messe-Kampagne im November."),
    ("energie", "workflow-automatisierung", "approve", "Stefan Huber", ""),
    ("versicherungen", "kubernetes", "approve", "Katharina Vogt", "Freigabe nach Abstimmung mit dem Vertrieb."),
    ("versicherungen", "rag-plattform", "changes", "Miriam Lindner",
     "Bitte die Schadenbearbeitung als Einstieg nutzen und den Newsletter kürzer fassen."),
    ("energie", "rag-plattform", "changes", "Stefan Huber",
     "KRITIS-Anforderungen im zweiten Abschnitt konkreter machen."),
    ("fertigung", "kubernetes", "reject", "Miriam Lindner",
     "Thema passt aktuell nicht zur Fertigungskampagne, bitte im Q1 neu aufsetzen."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="lokale Demo-Daten löschen und neu aufbauen")
    args = parser.parse_args()

    os.environ.update({"INLINE_RUNS": "true", "MOCK_LATENCY_S": "0.25", "N8N_WEBHOOK_URL": ""})
    os.environ.setdefault("LLM_PROVIDER", "mock")
    if os.environ["LLM_PROVIDER"] != "mock":
        print("Abbruch: Das Seed-Skript läuft nur im Mock-Modus (LLM_PROVIDER=mock), um API-Kosten zu vermeiden.")
        return 1

    from app.config import get_settings

    settings = get_settings()
    if args.reset:
        db_file = Path(settings.database_url.removeprefix("sqlite:///"))
        for path in (db_file, settings.site_dir):
            if ROOT not in path.resolve().parents:
                print(f"Abbruch: {path} liegt außerhalb des Projekts, wird nicht gelöscht.")
                return 1
        db_file.unlink(missing_ok=True)
        shutil.rmtree(settings.site_dir, ignore_errors=True)
        print("Lokale Demo-Daten gelöscht.")

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.db import AuditEvent, Run, Step, session_scope, utcnow
    from app.main import app

    with TestClient(app) as client:
        actor = {"X-Actor": "n8n%20Wochenplanung"}
        created = client.post("/api/runs/batch", json={"skip_existing": True}, headers=actor)
        created.raise_for_status()
        print(f"{len(created.json()['created'])} Pakete erstellt.")

        runs = {(r["industry_id"], r["service_id"]): r for r in client.get("/api/runs?limit=500").json()}
        for industry, service, action, reviewer, comment in SCENARIO:
            run = runs.get((industry, service))
            if not run or run["status"] not in ("awaiting_approval", "needs_review"):
                continue
            body = {"reviewer": reviewer}
            if action == "approve":
                path, body = "approve", {**body, "comment": comment}
            elif action == "changes":
                path, body = "request-changes", {**body, "feedback": comment}
            else:
                path, body = "reject", {**body, "reason": comment}
            client.post(f"/api/runs/{run['id']}/{path}", json=body).raise_for_status()
            print(f"  {action:8} {run['keyword']}")

    # Zeitstempel verteilen: Erstellung über die letzten Tage, Entscheidungen einige Stunden danach.
    decisions = {"approved", "published", "rejected", "changes_requested"}
    with session_scope() as s:
        all_runs = s.scalars(select(Run).order_by(Run.created_at)).all()
        now = utcnow()
        for i, run in enumerate(all_runs):
            target = timedelta(hours=70 - i * 4.3, minutes=(i * 17) % 50)
            shift = max(target - (now - run.created_at), timedelta(0))
            decided_shift = max(shift - timedelta(hours=1 + i % 5, minutes=(i * 7) % 60), timedelta(0))
            run.created_at -= shift
            for step in s.scalars(select(Step).where(Step.run_id == run.id)):
                step.started_at -= shift
            decided = False
            events = s.scalars(select(AuditEvent).where(AuditEvent.run_id == run.id).order_by(AuditEvent.id))
            for event in events:
                decided = decided or event.action in decisions
                event.created_at -= decided_shift if decided else shift
            run.updated_at -= decided_shift if decided else shift
            if run.published_at:
                run.published_at -= decided_shift

    with TestClient(app) as client:  # Index und Sitemap mit den neuen Zeitstempeln
        stats = client.get("/api/stats").json()
    from app.publishing.service import republish_all

    with session_scope() as s:
        republish_all(s)
    print(
        f"Fertig: {stats['published']} veröffentlicht, {stats['awaiting_review']} offen, "
        f"{stats['runs_total']} Vorgänge."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
