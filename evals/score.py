"""Метрики ЛЗ 12 по эталону людей (evals/gold.jsonl) и последнему прогону (evals/raw/LATEST).

    python evals/score.py [run_id] [--gold path]

Правила расчёта зафиксированы ДО прогона — см. evals/METRICS.md.
Результат: evals/results/<run_id>/ — summary.md, metrics.json, per_class.csv, per_category.csv,
errors.csv, confusion_*.png, quality.png, latency.png, errors.png, explanations_review.xlsx
"""

import csv
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import recommender as R  # noqa: E402
import seed_animals  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
gold_path = Path(sys.argv[sys.argv.index("--gold") + 1]) if "--gold" in sys.argv else ROOT / "evals/gold.jsonl"
if "--gold" in sys.argv:
    args = [a for a in args if a != str(gold_path)]
run_id = args[0] if args else (ROOT / "evals/raw/LATEST").read_text().strip()
RAW = ROOT / "evals/raw" / run_id
OUT = ROOT / "evals/results" / run_id
OUT.mkdir(parents=True, exist_ok=True)
meta = json.loads((RAW / "meta.json").read_text(encoding="utf-8"))
catalog = {a["id"]: a for a in seed_animals.catalog()}
if meta["catalog_version"] != seed_animals.catalog_version():
    sys.exit("Каталог изменился после прогона — сравнение некорректно, перезапустите run_experiment.py")
_sf = ROOT / "evals" / meta.get("scenarios_file", "scenarios.jsonl")
scen = {json.loads(s)["id"]: json.loads(s) for s in open(_sf, encoding="utf-8")}
gold = {json.loads(s)["id"]: json.loads(s) for s in open(gold_path, encoding="utf-8")}
VARIANTS = {"A": "A. Правила (baseline)", "B": "B. Zero-shot", "C": "C. Few-shot", "D": "D. Few-shot + отказ"}
if (RAW / "D2.jsonl").exists():
    VARIANTS["D2"] = "D2. Отказ v2 (повторная проверка)"
if (RAW / "D3.jsonl").exists():
    VARIANTS["D3"] = "D3. Отказ v3 + ранжирование правилами (повторная проверка)"
pred = {v: {json.loads(s)["id"]: json.loads(s) for s in open(RAW / f"{v}.jsonl", encoding="utf-8")} for v in VARIANTS}
CL = list(R.LABELS)


def cls_metrics(t, p):
    n = len(t)
    per = {}
    for c in CL:
        tp = sum(a == c and b == c for a, b in zip(t, p))
        fp = sum(a != c and b == c for a, b in zip(t, p))
        fn = sum(a == c and b != c for a, b in zip(t, p))
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        per[c] = {"precision": pr, "recall": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0, "support": tp + fn}
    return {
        "accuracy": sum(a == b for a, b in zip(t, p)) / n,
        "macro_precision": statistics.mean(per[c]["precision"] for c in CL),
        "macro_recall": statistics.mean(per[c]["recall"] for c in CL),
        "macro_f1": statistics.mean(per[c]["f1"] for c in CL),
        "per_class": per,
    }


def dcg(gains):
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def rank_metrics(g, top):
    rel = {int(k) for k, v in g["pairs"].items() if v == "suitable"}
    gain = {int(k): (2 if int(k) in g["best"] else 1) for k in rel}
    top = top[:5]
    if not rel:
        return None
    if not top:
        return {"p5": 0.0, "r5": 0.0, "ndcg5": 0.0}
    hits = sum(i in rel for i in top)
    ideal = dcg(sorted(gain.values(), reverse=True)[:5])
    return {"p5": hits / len(top), "r5": hits / min(5, len(rel)), "ndcg5": dcg([gain.get(i, 0) for i in top]) / ideal}


results, errors_rows = {}, []
for v in VARIANTS:
    t, p, ranks, viol, recs, lat, explain_bad, explain_total = [], [], [], 0, 0, [], 0, 0
    refusal_ok, refusal_n, clar_ok, api_err, parse_err = 0, 0, 0, 0, 0
    per_cat = {}
    for sid, g in gold.items():
        r = pred[v][sid]
        labs = {str(x["animal_id"]): x["label"] for x in r.get("pairs", [])}
        for aid, gl in g["pairs"].items():
            t.append(gl)
            p.append(labs.get(aid, "missing"))
        if r.get("action") == "error":
            api_err += 1
        elif v != "A" and not r.get("parse_ok", True):
            parse_err += 1
        top = r.get("top", [])
        recs += len(top)
        bad = [i for i in top if g["pairs"].get(str(i)) == "unsuitable"]
        viol += len(bad)
        if r.get("latency_s") is not None:
            lat.append(float(r["latency_s"]))
        for x in r.get("pairs", []):
            if x["animal_id"] in top:
                explain_total += 1
                explain_bad += bool(R.explanation_errors(x.get("reason", ""), catalog[x["animal_id"]]))
        clar_ok += (r.get("action") == "clarify") == (g["clarify"] == "yes")
        if g["allowed"] == "no":
            refusal_n += 1
            refusal_ok += not top
        m = rank_metrics(g, top) if g["allowed"] == "yes" else None
        if m:
            ranks.append(m)
            per_cat.setdefault(scen[sid]["category"], []).append({**m, "viol": len(bad)})
        # строка разбора ошибок
        kinds = []
        if bad:
            kinds.append("нарушение ограничения")
        if g["allowed"] == "no" and top:
            kinds.append("рекомендация при отсутствии безопасных")
        if g["allowed"] == "yes" and not top and r.get("action") != "error":
            kinds.append("лишний отказ")
        if g["clarify"] == "yes" and r.get("action") != "clarify":
            kinds.append("не задан уточняющий вопрос")
        if r.get("action") == "error":
            kinds.append("ошибка API")
        wrong_pairs = sum(labs.get(a, "missing") != gl for a, gl in g["pairs"].items())
        if kinds or wrong_pairs >= 3:
            errors_rows.append(
                {
                    "variant": v,
                    "id": sid,
                    "category": scen[sid]["category"],
                    "hard": scen[sid]["hard"] or "",
                    "request": scen[sid]["text"],
                    "gold": f"подходят {[int(k) for k, x in g['pairs'].items() if x == 'suitable']}; уточнить={g['clarify']}; можно={g['allowed']}",
                    "answer": f"action={r.get('action')}; top={top}; неверных пар={wrong_pairs}/10",
                    "error_type": "; ".join(kinds) or "ошибки классификации пар",
                    "cause": "",
                    "fix": "",
                    "retest": "",
                }
            )
    cm = {a: {b: 0 for b in CL + ["missing"]} for a in CL}
    for a, b in zip(t, p):
        cm[a][b if b in cm[a] else "missing"] += 1
    res = cls_metrics(t, p)
    res.update(
        {
            "precision_at_5": statistics.mean(x["p5"] for x in ranks) if ranks else None,
            "recall_at_5": statistics.mean(x["r5"] for x in ranks) if ranks else None,
            "ndcg_at_5": statistics.mean(x["ndcg5"] for x in ranks) if ranks else None,
            "violation_rate": viol / recs if recs else 0.0,
            "violations": viol,
            "recommended_items": recs,
            "explanation_error_rate": explain_bad / explain_total if explain_total else None,
            "correct_refusal": f"{refusal_ok}/{refusal_n}",
            "clarify_accuracy": clar_ok / len(gold),
            "latency_mean_s": statistics.mean(lat) if lat else None,
            "latency_p95_s": sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else None,
            "api_errors": api_err,
            "parse_errors": parse_err,
            "confusion": cm,
            "per_category": {
                c: {
                    "p5": statistics.mean(x["p5"] for x in xs),
                    "ndcg5": statistics.mean(x["ndcg5"] for x in xs),
                    "violations": sum(x["viol"] for x in xs),
                    "n": len(xs),
                }
                for c, xs in per_cat.items()
            },
        }
    )
    results[v] = res

(OUT / "metrics.json").write_text(
    json.dumps(
        {"meta": meta, "gold": str(gold_path.name), "results": results}, ensure_ascii=False, indent=1, default=float
    ),
    encoding="utf-8",
)
with open(OUT / "errors.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(errors_rows[0]) if errors_rows else ["variant"])
    w.writeheader()
    w.writerows(errors_rows)
with open(OUT / "per_class.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["variant", "class", "precision", "recall", "f1", "support"])
    for v, r in results.items():
        for c in CL:
            pc = r["per_class"][c]
            w.writerow([v, c, round(pc["precision"], 3), round(pc["recall"], 3), round(pc["f1"], 3), pc["support"]])
cats = sorted({c for r in results.values() for c in r["per_category"]})
with open(OUT / "per_category.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["category"] + [f"{v}_{m}" for v in VARIANTS for m in ("P@5", "NDCG@5", "violations")])
    for c in cats:
        row = [c]
        for v in VARIANTS:
            x = results[v]["per_category"].get(c)
            row += [round(x["p5"], 3), round(x["ndcg5"], 3), x["violations"]] if x else ["", "", ""]
        w.writerow(row)

# ---------- графики
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

COL = ["#9AA0A6", "#7C6FD6", "#4B3FB5", "#2E7D5B", "#C2620C", "#B8336A"]
plt.rcParams.update({"font.family": "Arial", "font.size": 10})
ms = [
    ("macro_f1", "Macro F1"),
    ("accuracy", "Accuracy"),
    ("precision_at_5", "Precision@5"),
    ("recall_at_5", "Recall@5"),
    ("ndcg_at_5", "NDCG@5"),
]
fig, ax = plt.subplots(figsize=(9, 4))
w = 0.8 / len(VARIANTS)
for i, v in enumerate(VARIANTS):
    vals = [results[v][k] or 0 for k, _ in ms]
    bars = ax.bar([j + (i - (len(VARIANTS) - 1) / 2) * w for j in range(len(ms))], vals, w, label=VARIANTS[v], color=COL[i])
    ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=1)
ax.set_xticks(range(len(ms)), [n for _, n in ms])
ax.set_ylim(0, 1.12)
ax.set_title("Качество подбора: четыре варианта")
ax.legend(ncol=len(VARIANTS), fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "quality.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(6, 3.2))
vals = [results[v]["latency_mean_s"] or 0 for v in VARIANTS]
bars = ax.bar([VARIANTS[v] for v in VARIANTS], vals, color=COL)
ax.bar_label(bars, fmt="%.2f с", fontsize=8)
ax.set_ylabel("секунд на сценарий")
ax.set_title("Среднее время ответа")
ax.spines[["top", "right"]].set_visible(False)
plt.xticks(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "latency.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 3.4))
kinds = [("violations", "Нарушения ограничений"), ("api_errors", "Ошибки API"), ("parse_errors", "Неразобранный ответ")]
for i, v in enumerate(VARIANTS):
    vals = [results[v][k] for k, _ in kinds]
    bars = ax.bar([j + (i - (len(VARIANTS) - 1) / 2) * w for j in range(len(kinds))], vals, w, label=VARIANTS[v], color=COL[i])
    ax.bar_label(bars, fontsize=7)
ax.set_xticks(range(len(kinds)), [n for _, n in kinds])
ax.set_title("Ошибки по вариантам (шт.)")
ax.legend(fontsize=8, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(OUT / "errors.png", dpi=180)
plt.close(fig)

for v in VARIANTS:
    cm = results[v]["confusion"]
    cols = CL + ["missing"]
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    data = [[cm[a][b] for b in cols] for a in CL]
    ax.imshow(data, cmap="Purples")
    for i, row in enumerate(data):
        for j, x in enumerate(row):
            ax.text(j, i, x, ha="center", va="center", color="white" if x > max(map(max, data)) / 2 else "black")
    ax.set_xticks(range(len(cols)), ["Подходит", "Не подходит", "Нет данных", "Нет ответа"], fontsize=8)
    ax.set_yticks(range(len(CL)), ["Подходит", "Не подходит", "Нет данных"], fontsize=8)
    ax.set_xlabel("Ответ варианта")
    ax.set_ylabel("Эталон")
    ax.set_title(VARIANTS[v], fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / f"confusion_{v}.png", dpi=180)
    plt.close(fig)

# ---------- лист для ручной проверки объяснений (вариант D)
from openpyxl import Workbook  # noqa: E402

wb = Workbook()
ws = wb.active
ws.title = "Объяснения D"
ws.append(
    [
        "scenario_id",
        "Запрос",
        "animal_id",
        "Кличка",
        "Объяснение модели",
        "Авто-проверка",
        "Оценка человека (верно/частично/неверно)",
    ]
)
for sid in gold:
    r = pred["D"][sid]
    for x in r.get("pairs", []):
        if x["animal_id"] in r.get("top", []):
            a = catalog[x["animal_id"]]
            ws.append(
                [
                    sid,
                    scen[sid]["text"],
                    a["id"],
                    a["name"],
                    x.get("reason", ""),
                    "; ".join(R.explanation_errors(x.get("reason", ""), a)) or "ок",
                    "",
                ]
            )
wb.save(OUT / "explanations_review.xlsx")

# ---------- сводка
f3 = lambda x: "—" if x is None else f"{x:.3f}"  # noqa: E731
L = [
    f"# Результаты {run_id}",
    "",
    f"Модель: `{meta['model']}` · промпт `{meta['prompt_version']}` · каталог `{meta['catalog_version']}` · "
    f"{meta['started_utc']} UTC · temperature 0, seed 42",
    "",
    "| Вариант | Accuracy | Macro P | Macro R | Macro F1 | P@5 | R@5 | NDCG@5 | Нарушения | Ошибки объясн. | Верный отказ | Уточнение | Время, с |",
    "|---|" + "---|" * 12,
]
for v, r in results.items():
    L.append(
        f"| {VARIANTS[v]} | {f3(r['accuracy'])} | {f3(r['macro_precision'])} | {f3(r['macro_recall'])} | **{f3(r['macro_f1'])}** | "
        f"{f3(r['precision_at_5'])} | {f3(r['recall_at_5'])} | {f3(r['ndcg_at_5'])} | {r['violations']}/{r['recommended_items']} | "
        f"{f3(r['explanation_error_rate'])} | {r['correct_refusal']} | {f3(r['clarify_accuracy'])} | {f3(r['latency_mean_s'])} |"
    )
L += ["", "## F1 по классам", "", "| Класс | " + " | ".join(VARIANTS.values()) + " |", "|---|" + "---|" * len(VARIANTS)]
for c in CL:
    L.append(
        f"| {R.LABELS_RU[c]} ({results['A']['per_class'][c]['support']}) | "
        + " | ".join(f3(results[v]["per_class"][c]["f1"]) for v in VARIANTS)
        + " |"
    )
best = max([v for v in VARIANTS if v != "A"], key=lambda v: results[v]["macro_f1"])
L.append("")
for v in [x for x in VARIANTS if x in ("D", "D2", "D3")]:
    win = all(results[v]["per_class"][c]["f1"] > results["A"]["per_class"][c]["f1"] for c in CL)
    L.append(f"{VARIANTS[v]} лучше baseline по F1 каждого класса: **{'да' if win else 'НЕТ'}**.")
L.append(f"Лучший ИИ-вариант по macro F1: {VARIANTS[best]}.")
(OUT / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
