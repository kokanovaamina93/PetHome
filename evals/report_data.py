"""Собирает все цифры ЛЗ 12 в docs/lab12/report_data.json — единый источник для Word-отчёта и GitHub Wiki.

    python evals/report_data.py [run_id]
Читает: evals/results/<run>/metrics.json, per_category.csv, errors.csv; evals/results/agreement.json;
evals/gold.jsonl; evals/scenarios.jsonl; evals/error_analysis.json (ручной разбор); evals/results/cost-model.xlsx
(значения после пересчёта LibreOffice).
"""

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
run = sys.argv[1] if len(sys.argv) > 1 else (ROOT / "evals/raw/LATEST").read_text().strip()
RES = ROOT / "evals/results" / run
RAW = ROOT / "evals/raw" / run

metrics = json.loads((RES / "metrics.json").read_text(encoding="utf-8"))
agreement = json.loads((ROOT / "evals/results/agreement.json").read_text(encoding="utf-8"))
gold = [json.loads(x) for x in open(ROOT / "evals/gold.jsonl", encoding="utf-8")]
scen = [json.loads(x) for x in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")]
errors = list(csv.DictReader(open(RES / "errors.csv", encoding="utf-8-sig")))
per_cat = list(csv.DictReader(open(RES / "per_category.csv", encoding="utf-8-sig")))
analysis_path = ROOT / "evals/error_analysis.json"
analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else {}


def usage(v):
    rows = [json.loads(x) for x in open(RAW / f"{v}.jsonl", encoding="utf-8")]
    u = [r["usage"] for r in rows if r.get("usage")]
    return {
        "n": len(u),
        "prompt_avg": round(statistics.mean(x["prompt_tokens"] for x in u)) if u else None,
        "completion_avg": round(statistics.mean(x["completion_tokens"] for x in u)) if u else None,
        "reasoning_avg": round(statistics.mean((x.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) for x in u))
        if u
        else None,
        "fingerprints": len({r.get("system_fingerprint") for r in rows if r.get("system_fingerprint")}),
    }


cost = {}
cm = ROOT / "evals/results/cost-model.xlsx"
if cm.exists():
    wb = load_workbook(cm, data_only=True)
    api, be, inf = wb["Стоимость API"], wb["Безубыточность"], wb["Инфраструктура"]
    cost = {
        "per_request_usd": api["B7"].value,
        "requests_month": [api["B4"].value, api["C4"].value],
        "tokens_in_month": [api["B5"].value, api["C5"].value],
        "tokens_out_month": [api["B6"].value, api["C6"].value],
        "month_usd": [api["B8"].value, api["C8"].value],
        "month_kzt": [api["B9"].value, api["C9"].value],
        "year_usd": [api["B10"].value, api["C10"].value],
        "year_kzt": [api["B11"].value, api["C11"].value],
        "free_tier_ok": [api["B14"].value, api["C14"].value],
        "cpu_server_usd": be["B5"].value,
        "gpu_server_usd": be["B6"].value,
        "breakeven_cpu": be["B7"].value,
        "breakeven_gpu": be["B8"].value,
        "times_cpu": be["B10"].value,
        "times_gpu": be["B11"].value,
        "cpu_capacity": be["B12"].value,
        "cpu_can_reach": be["B14"].value,
        "infra_current_usd": inf["D15"].value,
        "tokens_source": wb["Допущения"]["C5"].value,
        "tokens_in": wb["Допущения"]["B5"].value,
        "tokens_out": wb["Допущения"]["B6"].value,
        "usd_kzt": wb["Допущения"]["B7"].value,
    }
    if cost["per_request_usd"] is None:
        sys.exit("cost-model.xlsx не пересчитан: запустите recalc (LibreOffice) после evals/cost_model.py")

gold_v2 = {}
v2dir = ROOT / "evals/results" / f"{run}__gold_v2"
if (v2dir / "metrics.json").exists():
    g2 = [json.loads(x) for x in open(ROOT / "evals/gold_v2.jsonl", encoding="utf-8")]
    gold_v2 = {
        "results": json.loads((v2dir / "metrics.json").read_text(encoding="utf-8"))["results"],
        "agreement": json.loads((ROOT / "evals/results/agreement_v2.json").read_text(encoding="utf-8")),
        "counts": dict(Counter(v for g in g2 for v in g["pairs"].values())),
        "clarify": dict(Counter(g["clarify"] for g in g2)),
        "allowed": dict(Counter(g["allowed"] for g in g2)),
    }

data = {
    "gold_v2": gold_v2,
    "run_id": run,
    "meta": metrics["meta"],
    "results": metrics["results"],
    "agreement": agreement,
    "gold_counts": dict(Counter(v for g in gold for v in g["pairs"].values())),
    "gold_clarify": dict(Counter(g["clarify"] for g in gold)),
    "gold_allowed": dict(Counter(g["allowed"] for g in gold)),
    "categories": dict(Counter(s["category"] for s in scen)),
    "hard": dict(Counter(s["hard"] for s in scen if s["hard"])),
    "per_category": per_cat,
    "errors": errors,
    "analysis": analysis,
    "usage": {v: usage(v) for v in ("B", "C")},
    "cost": cost,
    "n_animals": len(json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8"))),
    "images": {
        "quality": f"evals/results/{run}/quality.png",
        "latency": f"evals/results/{run}/latency.png",
        "errors": f"evals/results/{run}/errors.png",
        "confusion_A": f"evals/results/{run}/confusion_A.png",
        "confusion_D": f"evals/results/{run}/confusion_D.png",
        "confusion_D2": f"evals/results/{run}/confusion_D2.png",
        "cost_chart": "evals/results/cost_chart.png",
        "screen_reco": "docs/lab12/img/recommendations.jpg",
        "screen_chat": "docs/lab12/img/chat_clarify.jpg",
        "screen_handoff": "docs/lab12/img/handoff.jpg",
    },
}
out = ROOT / "docs/lab12/report_data.json"
out.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
print(out)
