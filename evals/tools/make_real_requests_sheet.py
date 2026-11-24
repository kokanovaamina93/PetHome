"""Создаёт evals/labeling/4_real_requests.xlsx — шаблон для сбора реальных обращений (задание 4 методички)."""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[2]
F, B = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
Y, H = PatternFill("solid", fgColor="FFFF00"), PatternFill("solid", fgColor="D9D2E9")
wb = Workbook()
ins = wb.active
ins.title = "Как собирать"
for line in [
    "Реальные обращения для независимой проверки ИИ-подбора PetHome (10–15 штук).",
    "",
    "Кого спросить: одногруппников, знакомых, родственников — людей, которые могли бы взять животное из приюта.",
    "Что попросить: «Напиши одним–тремя предложениями, какое животное ты хотел(а) бы взять и в каких условиях живёшь».",
    "Записывайте ответ ДОСЛОВНО, своими словами человека, с его ошибками и смесью языков. Не улучшайте текст и не придумывайте.",
    "",
    "Обезличивание: никаких имён, фамилий, телефонов, адресов, ников. Возраст детей и город — можно.",
    "Согласие: спросите, можно ли использовать фразу в учебном проекте; без «да» строку не добавляйте.",
    "Анкета необязательна: заполните, только если человек сам это сказал. Если не сказал — оставьте пусто (это нормально).",
    "",
    "Пример строки: r-01 | «Живу в общаге, хочу котика, но соседка боится кошек» | жильё: квартира | одногруппник | 25.11.2026 | да | Fariza",
    "",
    "Потом: python evals/import_real_requests.py, затем python evals/make_labeling_sheets.py --set real",
    "Эти обращения размечаете вы вдвоём ВРУЧНУЮ и независимо — это и будет независимая проверка (задания 4 и 5).",
]:
    ins.append([line])
ins.column_dimensions["A"].width = 125
for r in ins.iter_rows():
    for c in r:
        c.font = F
ins["A1"].font = B
ws = wb.create_sheet("Обращения")
cols = ["id", "Обращение (дословно)", "Вид (если сказал)", "Жильё", "Дети", "Другие животные", "Время в день", "Опыт",
        "Готов гулять", "Источник", "Дата", "Согласие", "Кто собрал"]
ws.append(cols)
for c in ws[1]:
    c.font, c.fill, c.alignment = B, H, Alignment(wrap_text=True)
for i in range(1, 16):
    ws.append([f"r-{i:02d}"] + [""] * (len(cols) - 1))
for row in ws.iter_rows(min_row=2):
    for c in row:
        c.font = F
    for c in row[1:]:
        c.fill = Y
for col, w in zip("ABCDEFGHIJKLM", [6, 60, 10, 12, 12, 14, 13, 12, 11, 14, 11, 10, 12]):
    ws.column_dimensions[col].width = w


def dv(rng, items):
    v = DataValidation(type="list", formula1='"' + ",".join(items) + '"', allow_blank=True)
    ws.add_data_validation(v)
    v.add(rng)


dv("C2:C16", ["кошка", "собака", "не важно"])
dv("D2:D16", ["квартира", "частный дом"])
dv("E2:E16", ["нет", "до 6 лет", "старше 6 лет"])
dv("F2:F16", ["нет", "есть кошка", "есть собака"])
dv("G2:G16", ["меньше часа", "1–3 часа", "больше 3 часов"])
dv("H2:H16", ["нет опыта", "немного", "большой"])
dv("I2:I16", ["да", "нет"])
dv("J2:J16", ["одногруппник", "знакомый", "родственник", "другое"])
dv("L2:L16", ["да"])
out = ROOT / "evals/labeling/4_real_requests.xlsx"
wb.save(out)
print(out)
