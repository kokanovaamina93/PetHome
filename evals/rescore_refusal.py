"""Пересчитывает вариант D по СОХРАНЁННЫМ ответам модели (C.jsonl) с другой версией правила отказа.
Новых запросов к API нет. Результат — evals/raw/<run>/D2.jsonl (refusal-v2) или D3.jsonl (refusal-v3).
Правила берутся той версии, что указана в RULES_VERSION (для прогона v1 — rules-v1).
Это повторная проверка на наборе разработки, а не независимая оценка: правило изменено после разбора ошибок.
    python evals/rescore_refusal.py [run_id] [--version refusal-v2]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import recommender as R  # noqa: E402
import seed_animals  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.startswith("refusal-")]
version = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else "refusal-v2"
name = {"refusal-v2": "D2", "refusal-v3": "D3"}.get(version, "D2")
run = args[0] if args else (ROOT / "evals/raw/LATEST").read_text().strip()
raw = ROOT / "evals/raw" / run
cat = {a["id"]: a for a in seed_animals.catalog()}
sc = {json.loads(x)["id"]: json.loads(x) for x in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")}
n = 0
with open(raw / f"{name}.jsonl", "w", encoding="utf-8") as f:
    for line in open(raw / "C.jsonl", encoding="utf-8"):
        r = json.loads(line)
        s = sc[r["id"]]
        if r.get("action") == "error":
            d = {**r, "variant": name}
        else:
            d = R.apply_refusal(r, s["profile"], s["text"], [cat[i] for i in s["candidates"]], version=version)
            d["variant"] = name
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
        n += 1
print(f"{name} ({version}, {R.RULES_VERSION}) пересчитан по {n} сохранённым ответам C -> {raw / (name + '.jsonl')}")
