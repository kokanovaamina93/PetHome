"""Создаёт evals/results/cost-model.xlsx с рабочими формулами (ЛЗ 12, задания 12–13).

Токены берутся из последнего прогона (evals/raw/LATEST, вариант C = промпт сайта).
Если прогона на Groq ещё нет — подставляются предварительные значения (помечены в файле).
    python evals/cost_model.py
"""

import json
import statistics
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/results"
OUT.mkdir(parents=True, exist_ok=True)

tok_in, tok_out, tok_src = 3078, 305, "ПРЕДВАРИТЕЛЬНО: пробный прогон qwen2.5:3b (4 сценария). Заменится после прогона на Groq"
latest = ROOT / "evals/raw/LATEST"
if latest.exists():
    run = latest.read_text().strip()
    usage = [json.loads(s)["usage"] for s in open(ROOT / "evals/raw" / run / "C.jsonl", encoding="utf-8")]
    usage = [u for u in usage if u.get("prompt_tokens")]
    if usage:
        tok_in = round(statistics.mean(u["prompt_tokens"] for u in usage))
        tok_out = round(statistics.mean(u["completion_tokens"] for u in usage))
        tok_src = f"Фактическое среднее usage из прогона {run}, вариант C, {len(usage)} запросов"

AR = "Arial"
F, B = Font(name=AR, size=10), Font(name=AR, size=10, bold=True)
BLUE, GREEN = Font(name=AR, size=10, color="0000FF"), Font(name=AR, size=10, color="008000")
H1 = Font(name=AR, size=13, bold=True)
YEL, HEAD = PatternFill("solid", fgColor="FFFF00"), PatternFill("solid", fgColor="D9D2E9")
USD, KZT, INT = '"$"#,##0.0000', '#,##0" ₸"', "#,##0"

wb = Workbook()
# ---------------------------------------------------------------- 1. Допущения
ws = wb.active
ws.title = "Допущения"
rows = [
    ("Параметр", "Значение", "Источник / комментарий"),
    ("Модель", "openai/gpt-oss-20b (Groq)", "https://console.groq.com/docs/models — проверено 24.11.2026"),
    ("Тариф: вход, $ за 1 млн токенов", 0.075, "https://console.groq.com/docs/models — 24.11.2026"),
    ("Тариф: выход, $ за 1 млн токенов", 0.30, "https://console.groq.com/docs/models — 24.11.2026"),
    ("Средние входные токены на запрос", tok_in, tok_src),
    ("Средние выходные токены на запрос", tok_out, tok_src + " (включая токены рассуждений)"),
    ("Курс USD/KZT", 455.12, "Национальный банк РК, официальный курс на 24.11.2026 (nationalbank.kz)"),
    ("Сессий подбора в день (прогноз)", 30, "Допущение команды: исторических данных нет"),
    ("Запросов к модели на сессию", 1.5, "Допущение: анкета + в среднем 0,5 уточнения в чате"),
    ("Дней в месяце", 30, ""),
    ("Бесплатный тариф Groq: запросов/мин", 30, "https://console.groq.com/docs/rate-limits — 24.11.2026"),
    ("Бесплатный тариф Groq: запросов/сутки", 1000, "там же"),
    ("Бесплатный тариф Groq: токенов/мин", 8000, "там же; один запрос ≈ входные+выходные токены"),
    ("Бесплатный тариф Groq: токенов/сутки", 200000, "там же"),
]
for r in rows:
    ws.append(r)
for c in ws[1]:
    c.font, c.fill = B, HEAD
for r in range(2, ws.max_row + 1):
    ws.cell(r, 1).font = F
    ws.cell(r, 3).font = F
    ws.cell(r, 2).font = BLUE
    ws.cell(r, 2).fill = YEL
ws["B3"].number_format = ws["B4"].number_format = '"$"0.000'
ws["B7"].number_format = "0.00"
ws.column_dimensions["A"].width = 40
ws.column_dimensions["B"].width = 26
ws.column_dimensions["C"].width = 95
ws["B5"].comment = Comment(tok_src, "PetHome")
ws.append([])
ws.append(["Жёлтые ячейки — входные данные, остальные листы считаются формулами."])
ws.cell(ws.max_row, 1).font = Font(name=AR, size=10, italic=True)

A = "Допущения!"
# ---------------------------------------------------------------- 2. Стоимость API
c = wb.create_sheet("Стоимость API")
c["A1"] = "Стоимость облачного API"
c["A1"].font = H1
c.append([])
c.append(["Показатель", "Текущий поток", "Рост ×10", "Формула"])
for x in c[3]:
    x.font, x.fill = B, HEAD
lines = [
    ("Запросов в месяц", f"={A}B8*{A}B9*{A}B10", f"=B4*10", "сессии/день × запросов на сессию × дней"),
    ("Входных токенов в месяц", f"=B4*{A}B5", f"=C4*{A}B5", "запросы × средние входные токены"),
    ("Выходных токенов в месяц", f"=B4*{A}B6", f"=C4*{A}B6", "запросы × средние выходные токены"),
    ("Стоимость одного запроса, $", f"={A}B5/1000000*{A}B3+{A}B6/1000000*{A}B4", "=B7", "вход/1e6×тариф + выход/1e6×тариф"),
    ("Стоимость API в месяц, $", f"=B5/1000000*{A}B3+B6/1000000*{A}B4", f"=C5/1000000*{A}B3+C6/1000000*{A}B4",
     "(входные/1e6 × тариф входа) + (выходные/1e6 × тариф выхода)"),
    ("Стоимость API в месяц, ₸", f"=B8*{A}B7", f"=C8*{A}B7", "× курс НБРК"),
    ("Стоимость API в год, $", "=B8*12", "=C8*12", "× 12"),
    ("Стоимость API в год, ₸", "=B10*" + A + "B7", "=C10*" + A + "B7", "× курс"),
    ("Запросов в сутки", "=B4/" + A + "B10", "=C4/" + A + "B10", "для сравнения с лимитом бесплатного тарифа"),
    ("Токенов в сутки", f"=(B5+B6)/{A}B10", f"=(C5+C6)/{A}B10", ""),
    ("Укладывается в бесплатный тариф Groq?", f'=IF(AND(B12<={A}B12,B13<={A}B14),"да","нет")',
     f'=IF(AND(C12<={A}B12,C13<={A}B14),"да","нет")', "сравнение с лимитами RPD и TPD"),
]
for r in lines:
    c.append(list(r))
for r in range(4, c.max_row + 1):
    for col in "ABD":
        c[f"{col}{r}"].font = F
    for col in "BC":
        c[f"{col}{r}"].font = GREEN if A in str(c[f"{col}{r}"].value) else F
for r, fmt in {4: INT, 5: INT, 6: INT, 7: '"$"0.000000', 8: '"$"#,##0.00', 9: KZT, 10: '"$"#,##0.00', 11: KZT,
               12: "#,##0.0", 13: INT}.items():
    c[f"B{r}"].number_format = c[f"C{r}"].number_format = fmt
c.column_dimensions["A"].width = 42
c.column_dimensions["B"].width = 18
c.column_dimensions["C"].width = 18
c.column_dimensions["D"].width = 60

# ---------------------------------------------------------------- 3. Инфраструктура
inf = wb.create_sheet("Инфраструктура")
inf["A1"] = "Расходы на инфраструктуру (в месяц)"
inf["A1"].font = H1
inf.append([])
inf.append(["Статья", "Валюта", "Цена", "В долларах", "В тенге", "Источник (проверено 24.11.2026)"])
for x in inf[3]:
    x.font, x.fill = B, HEAD
items = [
    ("Render Web Service Free (сейчас; засыпает через 15 мин)", "USD", 0, "https://render.com/pricing, https://render.com/docs/free"),
    ("Render Web Service Starter, 512 МБ (без засыпания)", "USD", 7, "https://render.com/pricing"),
    ("Render Postgres Basic-256mb (Free удаляется через 30 дней)", "USD", 6, "https://render.com/pricing"),
    ("Vercel Hobby (фронтенд)", "USD", 0, "https://vercel.com/pricing"),
    ("CPU-сервер Hetzner CPX42: 8 vCPU, 16 ГБ — открытая 7B-модель", "EUR", 59.49, "https://www.hetzner.com/cloud/regular-performance"),
    ("GPU-сервер Hetzner GEX45: RTX PRO 4000, 24 ГБ VRAM", "EUR", 214, "https://www.hetzner.com/dedicated-rootserver/matrix-gpu/"),
    ("GPU-сервер: разовая установка (setup fee)", "EUR", 209, "там же; разово, в месячную сумму не входит"),
    ("Курс EUR/USD", "", 1.16, "Допущение: средний рыночный курс ноября 2026"),
    ("Сопровождение своего сервера, часов в месяц", "", 4, "Допущение: обновления, мониторинг, резервные копии"),
    ("Стоимость часа сопровождения, $", "USD", 10, "Допущение: студенческая ставка"),
]
for i, (name, cur, price, src) in enumerate(items, start=4):
    inf.append([name, cur, price, None, None, src])
    inf[f"C{i}"].font = BLUE
    inf[f"C{i}"].fill = YEL
    if cur == "USD":
        inf[f"D{i}"] = f"=C{i}"
    elif cur == "EUR":
        inf[f"D{i}"] = f"=C{i}*$C$11"
    if cur:
        inf[f"E{i}"] = f"=D{i}*{A}$B$7"
for r in range(4, inf.max_row + 1):
    for col in "ABF":
        inf[f"{col}{r}"].font = F
    inf[f"D{r}"].number_format = '"$"#,##0.00'
    inf[f"E{r}"].number_format = KZT
r0 = inf.max_row + 2
for k, (label, formula) in enumerate([
    ("Итого: текущая схема (Render Starter + Postgres + Vercel), $/мес", "=D5+D6+D7"),
    ("Свой CPU-сервер + сопровождение, $/мес", "=D8+C12*C13"),
    ("Свой GPU-сервер + сопровождение, $/мес", "=D9+C12*C13"),
]):
    inf.cell(r0 + k, 1, label)
    inf.cell(r0 + k, 4, formula)
    inf.cell(r0 + k, 5, f"=D{r0 + k}*{A}B7")
for r in range(r0, r0 + 3):
    inf[f"A{r}"].font = B
    inf[f"D{r}"].font = inf[f"E{r}"].font = B
    inf[f"D{r}"].number_format = '"$"#,##0.00'
    inf[f"E{r}"].number_format = KZT
inf.column_dimensions["A"].width = 62
inf.column_dimensions["B"].width = 8
inf.column_dimensions["C"].width = 10
inf.column_dimensions["D"].width = 13
inf.column_dimensions["E"].width = 14
inf.column_dimensions["F"].width = 60
CPU, GPU = f"Инфраструктура!D{r0 + 1}", f"Инфраструктура!D{r0 + 2}"

# ---------------------------------------------------------------- 4. Безубыточность
be = wb.create_sheet("Безубыточность")
be["A1"] = "Точка безубыточности собственного сервера"
be["A1"].font = H1
be["A3"], be["B3"] = "Стоимость одного запроса к API, $", "='Стоимость API'!B7"
be["A4"], be["B4"] = "Переменные затраты своего сервера на запрос, $", 0
be["C4"] = "Электричество и износ включены в аренду — переменные затраты ≈ 0"
be["A5"], be["B5"] = "Своё: CPU-сервер, $/мес", "=" + CPU
be["A6"], be["B6"] = "Своё: GPU-сервер, $/мес", "=" + GPU
be["A7"], be["B7"] = "Точка безубыточности CPU, запросов/мес", "=B5/(B3-B4)"
be["A8"], be["B8"] = "Точка безубыточности GPU, запросов/мес", "=B6/(B3-B4)"
be["A9"], be["B9"] = "Текущий поток, запросов/мес", "='Стоимость API'!B4"
be["A10"], be["B10"] = "Во сколько раз точка CPU больше текущего потока", "=B7/B9"
be["A11"], be["B11"] = "Во сколько раз точка GPU больше текущего потока", "=B8/B9"
be["A12"], be["B12"] = "Пропускная способность CPU-сервера, запросов/мес", "=30*24*3600/B13"
be["A13"], be["B13"] = "Секунд CPU на один запрос 7B-модели (оценка)", 20
be["C13"] = "Оценка: ~3 000 входных токенов на 8 vCPU; не замерено на этом сервере"
be["A14"], be["B14"] = "CPU-сервер физически успевает до точки безубыточности?", '=IF(B12>=B7,"да","нет")'
be["B4"].font = be["B13"].font = BLUE
be["B4"].fill = be["B13"].fill = YEL
fmts = {3: '"$"0.000000', 4: '"$"0.000000', 5: '"$"#,##0.00', 6: '"$"#,##0.00', 7: INT, 8: INT, 9: INT,
        10: "#,##0", 11: "#,##0", 12: INT}
for r in range(3, 15):
    be[f"A{r}"].font = F
    be[f"C{r}"].font = F
    if be[f"B{r}"].font != BLUE:
        be[f"B{r}"].font = F
    if r in fmts:
        be[f"B{r}"].number_format = fmts[r]
be["A16"] = "Запросов в месяц"
be["B16"], be["C16"], be["D16"] = "API, $/мес", "Свой CPU, $/мес", "Свой GPU, $/мес"
for x in be[16][:4]:
    x.font, x.fill = B, HEAD
vols = [1_000, 10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 3_000_000]
for i, v in enumerate(vols, start=17):
    be[f"A{i}"] = v
    be[f"B{i}"] = f"=A{i}*$B$3"
    be[f"C{i}"] = f"=$B$5+A{i}*$B$4"
    be[f"D{i}"] = f"=$B$6+A{i}*$B$4"
    be[f"A{i}"].number_format = INT
    for col in "BCD":
        be[f"{col}{i}"].number_format = '"$"#,##0'
        be[f"{col}{i}"].font = F
    be[f"A{i}"].font = F
ch = LineChart()
ch.title = "API против собственного сервера"
ch.y_axis.title = "$ в месяц"
ch.x_axis.title = "запросов в месяц"
ch.add_data(Reference(be, min_col=2, min_row=16, max_col=4, max_row=16 + len(vols)), titles_from_data=True)
ch.set_categories(Reference(be, min_col=1, min_row=17, max_row=16 + len(vols)))
ch.height, ch.width = 8, 16
ch.roundedCorners = False
ch.legend.overlay = False
ch.title.overlay = False
ch.x_axis.title.overlay = False
ch.y_axis.title.overlay = False
ch.x_axis.delete = False
ch.y_axis.delete = False
be.add_chart(ch, "F3")
be.column_dimensions["A"].width = 52
be.column_dimensions["B"].width = 16
be.column_dimensions["C"].width = 16
be.column_dimensions["D"].width = 16

out = OUT / "cost-model.xlsx"
wb.save(out)
print(out, "| токены:", tok_in, tok_out, "|", tok_src)
