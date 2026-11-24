"""Создаёт evals/labeling/0_animal_cards.xlsx — подтверждение карточек животных командой (роль приюта).
Синие значения — черновик по стандарту породы (подтвердить или исправить), жёлтые — заполнить самим."""

import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
animals = json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8"))
# порода: (размер, активность, уход, квартира, новичку)
B = {
    "Немецкая овчарка": ("Крупный", "high", "medium", "no", "no"),
    "Сибирский хаски": ("Средний", "high", "high", "no", "no"),
    "Вельш-корги пемброк": ("Средний", "medium", "medium", "yes", "yes"),
    "Золотистый ретривер": ("Крупный", "high", "medium", "unknown", "yes"),
    "Лабрадор-ретривер": ("Крупный", "high", "low", "unknown", "yes"),
    "Бигль": ("Средний", "high", "low", "yes", "unknown"),
    "Померанский шпиц": ("Маленький", "medium", "high", "yes", "yes"),
    "Бордер-колли": ("Средний", "high", "medium", "no", "no"),
    "Французский бульдог": ("Маленький", "low", "medium", "yes", "yes"),
    "Пудель": ("Средний", "medium", "high", "yes", "yes"),
    "Бернский зенненхунд": ("Крупный", "medium", "high", "no", "unknown"),
    "Джек-рассел-терьер": ("Маленький", "high", "low", "yes", "no"),
    "Кавалер-кинг-чарльз-спаниель": ("Маленький", "low", "medium", "yes", "yes"),
    "Ротвейлер": ("Крупный", "medium", "low", "no", "no"),
    "Самоедская собака": ("Крупный", "high", "high", "no", "no"),
    "Доберман": ("Крупный", "high", "low", "no", "no"),
    "Акита-ину": ("Крупный", "medium", "medium", "no", "no"),
    "Боксёр": ("Крупный", "high", "low", "no", "unknown"),
    "Сиба-ину": ("Средний", "medium", "medium", "yes", "no"),
    "Кане-корсо": ("Крупный", "medium", "low", "no", "no"),
    "Мальтийская болонка": ("Маленький", "low", "high", "yes", "yes"),
    "Американский стаффордширский терьер": ("Средний", "high", "low", "unknown", "no"),
    "Английский кокер-спаниель": ("Средний", "medium", "high", "yes", "yes"),
    "Веймаранер": ("Крупный", "high", "low", "no", "no"),
    "Такса": ("Маленький", "medium", "low", "yes", "yes"),
    "Британская короткошёрстная": ("Маленький", "low", "low", "yes", "yes"),
    "Мейн-кун": ("Средний", "medium", "medium", "yes", "yes"),
    "Шотландская прямоухая": ("Маленький", "low", "low", "yes", "yes"),
    "Персидская": ("Маленький", "low", "high", "yes", "unknown"),
    "Бенгальская": ("Маленький", "high", "low", "yes", "no"),
    "Сфинкс": ("Маленький", "medium", "high", "yes", "unknown"),
    "Рэгдолл": ("Средний", "low", "medium", "yes", "yes"),
    "Бомбейская": ("Маленький", "medium", "low", "yes", "yes"),
    "Русская голубая": ("Маленький", "medium", "low", "yes", "yes"),
    "Сиамская": ("Маленький", "high", "low", "yes", "unknown"),
    "Абиссинская": ("Маленький", "high", "low", "yes", "unknown"),
    "Норвежская лесная": ("Средний", "medium", "medium", "yes", "yes"),
    "Экзотическая короткошёрстная": ("Маленький", "low", "medium", "yes", "yes"),
    "Ориентальная короткошёрстная": ("Маленький", "high", "low", "yes", "unknown"),
    "Бирманская": ("Маленький", "low", "medium", "yes", "yes"),
    "Турецкая ангора": ("Маленький", "high", "medium", "yes", "yes"),
    "Сибирская": ("Маленький", "medium", "medium", "yes", "yes"),
    "Селкирк-рекс": ("Маленький", "medium", "medium", "yes", "yes"),
    "Девон-рекс": ("Маленький", "high", "low", "yes", "yes"),
    "Корниш-рекс": ("Маленький", "high", "low", "yes", "yes"),
    "Американская короткошёрстная": ("Маленький", "medium", "low", "yes", "yes"),
    "Бурманская": ("Маленький", "medium", "low", "yes", "yes"),
    "Манчкин": ("Маленький", "medium", "low", "yes", "yes"),
    "Тонкинская": ("Маленький", "high", "low", "yes", "yes"),
    "Египетская мау": ("Маленький", "high", "low", "yes", "unknown"),
}
wb = Workbook()
ws = wb.active
ws.title = "Карточки"
F = Font(name="Arial", size=10)
BOLD = Font(name="Arial", size=10, bold=True)
BLUE = Font(name="Arial", size=10, color="0000FF")
YEL = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="D9D2E9")
cols = [
    "id",
    "Кличка",
    "Вид",
    "Порода",
    "Возраст",
    "Город",
    "Статус",
    "Размер",
    "Активность",
    "Уход",
    "Квартира",
    "Новичку",
    "Ладит с детьми",
    "Ладит с животными",
    "Привит",
    "Стерилизован",
    "Особые потребности",
    "Подтвердил(а)",
]
ws.append(cols)
for c in ws[1]:
    c.font = BOLD
    c.fill = HEAD
    c.alignment = Alignment(wrap_text=True, vertical="center")
for a in animals:
    b = B.get(a["breed"], ("", "unknown", "unknown", "unknown", "unknown"))
    ws.append([a["id"], a["name"], a["type"], a["breed"], a["age"], a["city"], a["status"], *b, "", "", "", "", "", ""])
n = ws.max_row
for row in ws.iter_rows(min_row=2, max_row=n):
    for c in row:
        c.font = F
    for c in row[7:12]:
        c.font = BLUE
    for c in row[12:18]:
        c.fill = YEL


def dv(rng, items):
    v = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=True)
    ws.add_data_validation(v)
    v.add(rng)


dv(f"H2:H{n}", ["Маленький", "Средний", "Крупный"])
dv(f"I2:I{n}", ["low", "medium", "high"])
dv(f"J2:J{n}", ["low", "medium", "high"])
for col in "KLMNOP":
    dv(f"{col}2:{col}{n}", ["yes", "no", "unknown"])
dv(f"G2:G{n}", ["available", "reserved", "adopted", "archived"])
for col, w in zip("ABCDEFGHIJKLMNOPQR", [5, 10, 8, 26, 9, 10, 10, 11, 10, 8, 9, 9, 12, 12, 8, 10, 28, 14]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "E2"
L = wb.create_sheet("Как заполнять")
for line in [
    "Шаг 1 ЛЗ 12. Карточки животных сейчас шаблонные (у всех одинаковые размер и активность, совместимость unknown).",
    "Без подтверждённых карточек подбор и разметка теряют смысл, поэтому их заполняет команда в роли приюта.",
    "",
    "СИНИЕ ячейки (H–L) — черновик по типичным признакам породы. Проверьте и исправьте, если знаете иначе.",
    "ЖЁЛТЫЕ ячейки (M–R) — заполните сами. Если не знаете — пишите unknown: это честнее, чем угадать.",
    "Коды: low/medium/high — низкий/средний/высокий; yes/no/unknown — да/нет/неизвестно.",
    "Уход: high = ежедневное вычёсывание, особое питание, частые процедуры.",
    "Особые потребности: свободный текст (диета, лекарства, после травмы) или пусто.",
    "",
    "Пример строки: 9 | Луна | Собака | Сибирский хаски | ... | Средний | high | high | no | no | yes | unknown | yes | yes | (пусто) | Fariza",
    "",
    "После заполнения: python evals/import_animal_cards.py  — карточки попадут в backend/data/animals.json",
    "Затем: python evals/make_labeling_sheets.py  — будут созданы таблицы разметки для двух участниц.",
]:
    L.append([line])
L.column_dimensions["A"].width = 120
for r in L.iter_rows():
    for c in r:
        c.font = F
L["A1"].font = BOLD
out = ROOT / "evals/labeling/0_animal_cards.xlsx"
wb.save(out)
print(out, n - 1)
