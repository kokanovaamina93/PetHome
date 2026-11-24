"""Переносит собранные реальные обращения из evals/labeling/4_real_requests.xlsx в evals/scenarios_real.jsonl.
Кандидаты (10 животных) выбираются тем же детерминированным правилом, что и для тестовых сценариев (только по виду).
    python evals/import_real_requests.py"""
import json
import random
import re
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import recommender as R  # noqa: E402

animals = [a for a in json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8")) if a["status"] == "available"]
cats = sorted(a["id"] for a in animals if a["type"] == "Кошка")
dogs = sorted(a["id"] for a in animals if a["type"] == "Собака")
MAP = {
    "Вид (если сказал)": ("preferred_type", {"кошка": "cat", "собака": "dog", "не важно": "any"}),
    "Жильё": ("housing", {"квартира": "apartment", "частный дом": "house"}),
    "Дети": ("kids", {"нет": "none", "до 6 лет": "under6", "старше 6 лет": "over6"}),
    "Другие животные": ("other_pets", {"нет": "none", "есть кошка": "cat", "есть собака": "dog"}),
    "Время в день": ("time_per_day", {"меньше часа": "low", "1–3 часа": "medium", "больше 3 часов": "high"}),
    "Опыт": ("experience", {"нет опыта": "none", "немного": "some", "большой": "experienced"}),
    "Готов гулять": ("walks_ready", {"да": "yes", "нет": "no"}),
}
PII = re.compile(r"(?:\+?\d[\s\-()]*){7,}\d|[\w.+-]+@[\w-]+\.[\w.]+")
ws = load_workbook(ROOT / "evals/labeling/4_real_requests.xlsx", data_only=True)["Обращения"]
head = [c.value for c in ws[1]]
out, skipped = [], []
for n, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=1):
    r = dict(zip(head, row))
    text = str(r.get("Обращение (дословно)") or "").strip()
    if not text:
        continue
    if str(r.get("Согласие") or "").strip().lower() != "да":
        skipped.append(f"{r['id']}: нет согласия")
        continue
    if PII.search(text):
        sys.exit(f"{r['id']}: в тексте телефон или e-mail — удалите перед импортом")
    prof = {}
    for col, (key, m) in MAP.items():
        v = str(r.get(col) or "").strip().lower()
        if v in m:
            prof[key] = m[v]
    want = prof.get("preferred_type") or R._type_from_text(text)
    rng = random.Random(1000 + n)
    cand = rng.sample(cats, 10) if want == "cat" else rng.sample(dogs, 10) if want == "dog" else rng.sample(cats, 5) + rng.sample(dogs, 5)
    out.append({"id": r["id"], "category": "real", "hard": None, "source": "real_request",
                "collected": {"source": r.get("Источник"), "date": str(r.get("Дата") or ""), "by": r.get("Кто собрал")},
                "profile": prof, "text": text, "candidates": sorted(cand)})
with open(ROOT / "evals/scenarios_real.jsonl", "w", encoding="utf-8") as f:
    for x in out:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")
print(f"импортировано {len(out)} обращений", "| пропущено:", skipped or "—")
