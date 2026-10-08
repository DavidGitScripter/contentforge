"""Eval über die Content-Matrix: Wie zuverlässig liefert die Pipeline publikationsreifen Content?

    python -m evals.run_eval                                   # Mock, alle 16 Zellen (kostenlos, CI)
    python -m evals.run_eval --provider anthropic --limit 4    # echte Claude-Calls (kostet Geld!)
    python -m evals.run_eval --min-pass-rate 1.0               # Exit-Code 1, wenn Gate-Quote darunter liegt

Metriken: Gate-Quote, First-Pass-Quote, Ø Revisionen, Ø Judge-Score, Kosten, Laufzeit und welche
Regeln in Erstentwürfen am häufigsten anschlagen (-> Hinweise, wo Prompts nachgeschärft werden sollten).
"""

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from itertools import product
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", choices=["mock", "anthropic"], default="mock")
    p.add_argument("--limit", type=int, default=None, help="Nur die ersten N Zellen der Matrix")
    p.add_argument("--min-pass-rate", type=float, default=None)
    p.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="contentforge-eval-"))
    os.environ.update({
        "LLM_PROVIDER": args.provider,
        "MOCK_LATENCY_S": "0",
        "INLINE_RUNS": "true",
        "DATABASE_URL": f"sqlite:///{tmp / 'eval.db'}",
        "SITE_DIR": str(tmp / "site"),
        "N8N_WEBHOOK_URL": "",
    })

    # Import erst nach dem Setzen der Umgebung (Settings werden beim ersten Zugriff gelesen).
    from app.db import Run, init_db, session_scope
    from app.knowledge import load_knowledge
    from app.pipeline.orchestrator import execute_run, new_run
    from app.pipeline.prompts import PROMPT_VERSION

    init_db()
    kb = load_knowledge()
    cells = list(product([i.id for i in kb.industries], [s.id for s in kb.services]))[: args.limit]

    rows, first_draft_rules = [], Counter()
    for industry_id, service_id in cells:
        run = new_run(industry_id, service_id)
        execute_run(run.id)
        with session_scope() as s:
            run = s.get(Run, run.id)
            first = (run.attempts or [{}])[0]
            for issue in first.get("blocking", []):
                first_draft_rules[issue.split(":")[0]] += 1
            rows.append({
                "keyword": run.keyword,
                "status": run.status,
                "gate_passed": bool(run.gate_passed),
                "first_pass": bool(run.first_pass),
                "revisions": run.revisions,
                "judge": run.judge_average,
                "cost_usd": round(run.cost_usd, 4),
                "duration_s": round((run.duration_ms or 0) / 1000, 1),
                "error": run.error,
            })
        print(f"  {rows[-1]['status']:18} {run.keyword}", flush=True)

    n = len(rows)
    judged = [r["judge"] for r in rows if r["judge"] is not None]
    summary = {
        "provider": args.provider,
        "prompt_version": PROMPT_VERSION,
        "cells": n,
        "gate_pass_rate": round(sum(r["gate_passed"] for r in rows) / n, 3),
        "first_pass_rate": round(sum(r["first_pass"] for r in rows) / n, 3),
        "avg_revisions": round(sum(r["revisions"] for r in rows) / n, 2),
        "avg_judge": round(sum(judged) / len(judged), 2) if judged else None,
        "failed": sum(r["status"] == "failed" for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
        "avg_cost_usd": round(sum(r["cost_usd"] for r in rows) / n, 4),
        "avg_duration_s": round(sum(r["duration_s"] for r in rows) / n, 1),
        "first_draft_issues": dict(first_draft_rules.most_common()),
    }

    report = [
        f"# Eval-Report – {datetime.now():%Y-%m-%d %H:%M} ({args.provider}, Prompt {PROMPT_VERSION})",
        "",
        "| Metrik | Wert |",
        "|---|---|",
        f"| Zellen | {n} |",
        f"| Gate bestanden | {summary['gate_pass_rate']:.0%} |",
        f"| First-Pass (ohne Revision) | {summary['first_pass_rate']:.0%} |",
        f"| Ø Revisionen | {summary['avg_revisions']} |",
        f"| Ø Judge-Score | {summary['avg_judge']} |",
        f"| Kosten gesamt / Ø pro Paket | ${summary['total_cost_usd']} / ${summary['avg_cost_usd']} |",
        f"| Ø Laufzeit | {summary['avg_duration_s']} s |",
        "",
        "## Häufigste Probleme in Erstentwürfen",
        "",
        *([f"- {rule}: {count}x" for rule, count in first_draft_rules.most_common()] or ["- keine"]),
        "",
        "## Zellen",
        "",
        "| Keyword | Status | Rev. | Judge | Kosten |",
        "|---|---|---|---|---|",
        *[f"| {r['keyword']} | {r['status']} | {r['revisions']} | {r['judge']} | ${r['cost_usd']} |" for r in rows],
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}-{args.provider}"
    result = {"summary": summary, "rows": rows}
    (args.out / f"{stamp}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    (args.out / f"{stamp}.md").write_text("\n".join(report) + "\n")
    print("\n" + "\n".join(report[: report.index("## Zellen")]))
    print(f"\nReport: {args.out / stamp}.md")

    if args.min_pass_rate is not None and summary["gate_pass_rate"] < args.min_pass_rate:
        print(f"FEHLER: Gate-Quote {summary['gate_pass_rate']:.0%} < {args.min_pass_rate:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
