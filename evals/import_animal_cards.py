"""Переносит подтверждённые карточки из evals/labeling/0_animal_cards.xlsx в backend/data/animals.json.
    python evals/import_animal_cards.py
Потом на сервере: cd backend && python seed_animals.py  (обновит базу по id)."""

import json
import sys
from pathlib import Path
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backend/data/animals.json"
COLS = {
    "Размер": "size",
    "Активность": "activity_level",
    "Уход": "care_level",
    "Квартира": "apartment_ok",
    "Новичку": "beginner_ok",
    "Ладит с детьми": "good_with_kids",
    "Ладит с животными": "good_with_pets",
    "Привит": "vaccinated",
    "Стерилизован": "sterilized",
    "Особые потребности": "special_needs",
    "Город": "city",
    "Статус": "status",
}
OK = {
    "size": {"Маленький", "Средний", "Крупный"},
    "activity_level": {"low", "medium", "high"},
    "care_level": {"low", "medium", "high"},
}
YN = {"yes", "no", "unknown"}
ws = load_workbook(ROOT / "evals/labeling/0_animal_cards.xlsx").active
head = [c.value for c in ws[1]]
animals = {a["id"]: a for a in json.loads(DATA.read_text(encoding="utf-8"))}
errors, empty = [], 0
for row in ws.iter_rows(min_row=2, values_only=True):
    r = dict(zip(head, row))
    a = animals.get(r["id"])
    if a is None:
        errors.append(f"id {r['id']} нет в каталоге")
        continue
    for ru, key in COLS.items():
        v = r.get(ru)
        v = "" if v is None else str(v).strip()
        if key in OK and v not in OK[key]:
            errors.append(f"id {r['id']}: {ru}='{v}'")
        elif key in ("apartment_ok", "beginner_ok", "good_with_kids", "good_with_pets", "vaccinated", "sterilized"):
            if v == "":
                empty += 1
                v = "unknown"
            elif v not in YN:
                errors.append(f"id {r['id']}: {ru}='{v}'")
        a[key] = v
    a["card_confirmed_by"] = str(r.get("Подтвердил(а)") or "")
if errors:
    sys.exit("Исправьте ячейки:\n  " + "\n  ".join(errors))
DATA.write_text(json.dumps(list(animals.values()), ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Обновлено карточек: {len(animals)}; пустых yes/no-полей (записаны как unknown): {empty}")
