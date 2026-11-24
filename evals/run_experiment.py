"""Эксперимент ЛЗ 12: варианты A (правила), B (zero-shot), C (few-shot), D (few-shot + отказ).

    export AI_API_KEY=...            # ключ Groq (или положите в backend/.env строку AI_API_KEY=...)
    python evals/run_experiment.py   # -> evals/raw/<run_id>/  (сырые ответы, промпты, параметры, токены, ошибки)
    python evals/score.py            # -> evals/results/  (метрики, графики, ошибки) — нужен evals/gold.jsonl

Все варианты получают одни и те же сценарии и одну версию каталога (хэш data/animals.json пишется в meta).
D не делает отдельного запроса: это ответ C + детерминированная проверка ограничений и правило отказа.
"""

import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
env = ROOT / "backend/.env"
if env.exists():  # ключ кладёт сам пользователь; в git .env не попадает
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import recommender as R  # noqa: E402
import seed_animals  # noqa: E402

catalog = {a["id"]: a for a in seed_animals.catalog()}
scenarios = [json.loads(s) for s in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")]
if "--limit" in sys.argv:
    scenarios = scenarios[: int(sys.argv[sys.argv.index("--limit") + 1])]

run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_" + R.AI_MODEL.replace("/", "_").replace(":", "-")
out = ROOT / "evals/raw" / run_id
out.mkdir(parents=True)
meta = {
    "run_id": run_id,
    "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "provider_base_url": R.AI_BASE_URL,
    "model": R.AI_MODEL,
    "prompt_version": R.PROMPT_VERSION,
    "params": {
        "temperature": 0,
        "seed": 42,
        "max_tokens": 2500,
        "response_format": "json_object",
        **({"reasoning_effort": "low"} if "gpt-oss" in R.AI_MODEL else {}),
    },
    "determinism_note": "seed поддерживается провайдером в режиме best effort; детерминированность не гарантируется",
    "catalog_version": seed_animals.catalog_version(),
    "n_scenarios": len(scenarios),
    "python": platform.python_version(),
}
(out / "prompts").mkdir()
(out / "prompts/system.txt").write_text(R.SYSTEM, encoding="utf-8")
(out / "prompts/few_shot.json").write_text(json.dumps(R.FEW_SHOT, ensure_ascii=False, indent=1), encoding="utf-8")

files = {v: open(out / f"{v}.jsonl", "w", encoding="utf-8") for v in "ABCD"}
errors = []
for s in scenarios:
    cands = [catalog[i] for i in s["candidates"]]
    a = R.baseline_recommend(s["profile"], cands, s["text"])
    files["A"].write(json.dumps({"id": s["id"], **a}, ensure_ascii=False) + "\n")
    for mode, v in (("zero", "B"), ("few", "C")):
        for attempt in range(3):
            try:
                r = R.llm_recommend(s["profile"], s["text"], cands, mode=mode)
                break
            except R.AIUnavailable as e:
                errors.append({"id": s["id"], "variant": v, "attempt": attempt + 1, "error": str(e)[:400]})
                time.sleep(8 * (attempt + 1))  # лимит бесплатного тарифа: ждём и повторяем
        else:
            r = {
                "variant": v,
                "action": "error",
                "pairs": [],
                "top": [],
                "raw": "",
                "usage": {},
                "latency_s": None,
                "error": errors[-1]["error"],
            }
        files[v].write(json.dumps({"id": s["id"], **r}, ensure_ascii=False) + "\n")
        if v == "C":
            d = R.apply_refusal(r, s["profile"], s["text"], cands) if r["action"] != "error" else {**r, "variant": "D"}
            files["D"].write(json.dumps({"id": s["id"], **d}, ensure_ascii=False) + "\n")
        print(f"{s['id']} {v}: {r['action']:14} top={r['top']} {r.get('latency_s')}s", flush=True)
        time.sleep(float(os.environ.get("EVAL_PAUSE", "2.5")))  # 30 запросов/мин на бесплатном тарифе
for f in files.values():
    f.close()
meta["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
meta["api_errors"] = errors
(out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
(ROOT / "evals/raw/LATEST").write_text(run_id)
print("готово:", out, "ошибок API:", len(errors))
