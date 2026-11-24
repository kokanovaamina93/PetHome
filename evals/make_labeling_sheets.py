"""Создаёт две независимые таблицы разметки: evals/labeling/1_labeling_Fariza.xlsx и 2_labeling_Amina.xlsx.
Запускать ПОСЛЕ import_animal_cards.py: в таблицу попадают подтверждённые карточки.
Порядок пар перемешан по-разному в двух файлах, чтобы разметчицы не сверялись построчно."""

import json
import random
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/labeling"
animals = {a["id"]: a for a in json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8"))}
sc = [json.loads(s) for s in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")]
RU = {
    "preferred_type": "вид",
    "housing": "жильё",
    "kids": "дети",
    "other_pets": "другие животные",
    "time_per_day": "время в день",
    "experience": "опыт",
    "activity": "активность",
    "walks_ready": "готов гулять",
    "size_pref": "размер",
    "age_pref": "возраст",
    "allergy": "аллергия",
    "city": "город",
}
F, B = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
Y, HD = PatternFill("solid", fgColor="FFFF00"), PatternFill("solid", fgColor="D9D2E9")
WRAP = Alignment(wrap_text=True, vertical="top")


def profile_text(p):
    return "; ".join(f"{RU.get(k, k)}: {v}" for k, v in p.items()) or "анкета не заполнена"


def card(a):
    return (
        f"{a['type']}, {a['breed']}, {a['age']}, размер {a['size']}, активность {a['activity_level']}, "
        f"уход {a.get('care_level', 'unknown')}, квартира {a.get('apartment_ok', 'unknown')}, "
        f"новичку {a.get('beginner_ok', 'unknown')}, дети {a['good_with_kids']}, животные {a['good_with_pets']}"
        + (f", особые потребности: {a['special_needs']}" if a.get("special_needs") else "")
    )


def dv(ws, rng, items):
    v = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=True)
    ws.add_data_validation(v)
    v.add(rng)


def head(ws, cols, widths):
    ws.append(cols)
    for c, w in zip(ws[1], widths):
        c.font, c.fill, c.alignment = B, HD, WRAP
        ws.column_dimensions[c.column_letter].width = w
    ws.freeze_panes = "A2"


def make(name, seed):
    wb = Workbook()
    ins = wb.active
    ins.title = "Инструкция"
    for line in [
        f"Разметчица: {name}. Заполняйте САМОСТОЯТЕЛЬНО, не сверяясь со второй участницей и не спрашивая ИИ.",
        "Сценарии — тестовые (составлены командой), реальных обращений в PetHome пока нет.",
        "",
        "Лист «Сценарии» — для каждого запроса (жёлтые ячейки):",
        "  • Нужен уточняющий вопрос: yes — без доп. информации подбирать небезопасно; no — информации достаточно.",
        "  • Можно выдавать рекомендации: yes — среди кандидатов есть безопасные варианты; no — показывать никого нельзя.",
        "  • Обязательные ограничения: коротко, например «квартира; ребёнок до 6; нет времени на прогулки».",
        "  • Лучшие (необязательно): до 5 id самых подходящих по убыванию, через запятую.",
        "",
        "Лист «Пары» — для каждой пары «запрос — животное» выберите метку:",
        "  Подходит — по подтверждённым данным карточки подходит человеку;",
        "  Не подходит — нарушает требование человека или обязательное ограничение;",
        "  Недостаточно данных — важное для этого человека свойство животного неизвестно (unknown).",
        "  unknown в карточке — это НЕ «да».",
        "",
        "Пример: запрос «двое детей 3 и 5 лет», у собаки «дети unknown» → Недостаточно данных.",
        "Когда закончите — сохраните файл и передайте его (не меняйте названия листов и столбцов).",
    ]:
        ins.append([line])
    ins.column_dimensions["A"].width = 110
    for r in ins.iter_rows():
        for c in r:
            c.font = F
    ws = wb.create_sheet("Сценарии")
    head(
        ws,
        [
            "scenario_id",
            "Категория",
            "Анкета",
            "Запрос",
            "Нужен уточняющий вопрос",
            "Можно выдавать рекомендации",
            "Обязательные ограничения",
            "Лучшие (id)",
            "Комментарий",
        ],
        [10, 13, 45, 40, 12, 14, 35, 14, 25],
    )
    for s in sc:
        ws.append([s["id"], s["category"], profile_text(s["profile"]), s["text"], "", "", "", "", ""])
    n = ws.max_row
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font, c.alignment = F, WRAP
        for c in row[4:9]:
            c.fill = Y
    dv(ws, f"E2:E{n}", ["yes", "no"])
    dv(ws, f"F2:F{n}", ["yes", "no"])
    wp = wb.create_sheet("Пары")
    head(
        wp,
        ["scenario_id", "Запрос", "animal_id", "Кличка", "Карточка животного", "Метка", "Комментарий"],
        [10, 40, 9, 11, 70, 20, 25],
    )
    pairs = [(s, aid) for s in sc for aid in s["candidates"]]
    random.Random(seed).shuffle(pairs)
    for s, aid in pairs:
        a = animals[aid]
        wp.append([s["id"], f"{s['text']}  [{profile_text(s['profile'])}]", aid, a["name"], card(a), "", ""])
    n = wp.max_row
    for row in wp.iter_rows(min_row=2):
        for c in row:
            c.font, c.alignment = F, WRAP
        row[5].fill = Y
        row[6].fill = Y
    dv(wp, f"F2:F{n}", ["Подходит", "Не подходит", "Недостаточно данных"])
    path = OUT / name_file[name]
    wb.save(path)
    print(path.name, "пар:", len(pairs))


name_file = {"Fariza": "1_labeling_Fariza.xlsx", "Amina": "2_labeling_Amina.xlsx"}
make("Fariza", 1)
make("Amina", 2)
