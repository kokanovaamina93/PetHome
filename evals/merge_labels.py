"""Сверка двух независимых разметок и сборка эталона.

python evals/merge_labels.py           -> согласие, Cohen's kappa, evals/labeling/3_disputes.xlsx
(разобрать спорные случаи, заполнить «Согласованное решение» и «Как согласовано»)
python evals/merge_labels.py --write   -> evals/gold.jsonl  (эталон для score.py)
"""

import json
import sys
from collections import Counter
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

ROOT = Path(__file__).resolve().parents[1]
L = ROOT / "evals/labeling"
CODE = {"Подходит": "suitable", "Не подходит": "unsuitable", "Недостаточно данных": "insufficient"}
RU = {v: k for k, v in CODE.items()}
YN = {"да": "yes", "нет": "no", "yes": "yes", "no": "no"}
SCEN = {json.loads(x)["id"]: json.loads(x) for x in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")}
ANIMALS = {a["id"]: a for a in json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8"))}


def norm_decision(kind, value):
    v = str(value).strip()
    if kind == "пара":
        return CODE.get(v, v if v in RU else "")
    return YN.get(v.lower(), "")


def read(path):
    wb = load_workbook(path, data_only=True)
    pairs = {}
    for r in wb["Пары"].iter_rows(min_row=2, values_only=True):
        if r[0]:
            pairs[(r[0], int(r[2]))] = CODE.get(str(r[5] or "").strip(), "")
    scen = {}
    for r in wb["Сценарии"].iter_rows(min_row=2, values_only=True):
        if r[0]:
            scen[r[0]] = {
                "clarify": str(r[4] or "").strip(),
                "allowed": str(r[5] or "").strip(),
                "constraints": str(r[6] or "").strip(),
                "best": str(r[7] or "").strip(),
            }
    return pairs, scen


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n**2
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


pa, sa = read(L / "1_labeling_Fariza.xlsx")
pb, sb = read(L / "2_labeling_Amina.xlsx")
empty = [k for k in pa if not pa[k] or not pb.get(k)] + [
    k for k in sa if not sa[k]["clarify"] or not sa[k]["allowed"] or not sb[k]["clarify"] or not sb[k]["allowed"]
]
if empty:
    sys.exit(f"Не заполнено ячеек: {len(empty)} (например {empty[:3]})")
keys = sorted(pa)
po, k = kappa([pa[x] for x in keys], [pb[x] for x in keys])
pc, kc = kappa([sa[s]["clarify"] for s in sa], [sb[s]["clarify"] for s in sa])
pr, kr = kappa([sa[s]["allowed"] for s in sa], [sb[s]["allowed"] for s in sa])
report = {
    "pairs": len(keys),
    "pairs_agreement": round(po, 3),
    "pairs_kappa": round(k, 3),
    "clarify_agreement": round(pc, 3),
    "clarify_kappa": round(kc, 3),
    "allowed_agreement": round(pr, 3),
    "allowed_kappa": round(kr, 3),
}
print(json.dumps(report, ensure_ascii=False, indent=1))
(ROOT / "evals/results").mkdir(exist_ok=True)
(ROOT / "evals/results/agreement.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

disp_path = L / "3_disputes.xlsx"
if "--write" not in sys.argv:
    from openpyxl.styles import Alignment
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Спорные"
    ws.append(["Тип", "scenario_id", "animal_id", "Запрос и анкета", "Карточка животного / вопрос", "Fariza", "Amina",
               "Согласованное решение", "Как согласовано (кто, когда, почему)"])
    QTXT = {"clarify": "Нужен уточняющий вопрос?", "allowed": "Можно выдавать рекомендации?"}
    for x in keys:
        if pa[x] != pb[x]:
            sc_, an = SCEN[x[0]], ANIMALS[x[1]]
            card = (f"{an['name']}: {an['type']}, {an['breed']}, размер {an['size']}, активность {an['activity_level']}, "
                    f"уход {an.get('care_level')}, квартира {an.get('apartment_ok')}, новичку {an.get('beginner_ok')}, "
                    f"дети {an['good_with_kids']}, животные {an['good_with_pets']}")
            ws.append(["пара", x[0], x[1], f"{sc_['text']} | {sc_['profile']}", card, RU[pa[x]], RU[pb[x]], "", ""])
    for sid in sorted(sa):
        for fld in ("clarify", "allowed"):
            if sa[sid][fld] != sb[sid][fld]:
                sc_ = SCEN[sid]
                ws.append([fld, sid, "", f"{sc_['text']} | {sc_['profile']}", QTXT[fld],
                           "да" if sa[sid][fld] == "yes" else "нет", "да" if sb[sid][fld] == "yes" else "нет", "", ""])
    n = ws.max_row
    for row in ws.iter_rows():
        for c in row:
            c.font = Font(name="Arial", size=10, bold=c.row == 1)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        if row[0].row > 1:
            row[7].fill = row[8].fill = PatternFill("solid", fgColor="FFFF00")
    for col, w in zip("ABCDEFGHI", [8, 10, 9, 48, 48, 18, 18, 22, 40]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "D2"
    dv = DataValidation(type="list", formula1='"Подходит,Не подходит,Недостаточно данных,да,нет"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"H2:H{n}")
    help_ = wb.create_sheet("Как согласовать")
    for line in ["Спорные случаи — где Fariza и Amina ответили по-разному.",
                 "Обсудите каждый случай вдвоём (или с ответственным представителем проекта) и выберите решение в колонке H.",
                 "Для пар: Подходит / Не подходит / Недостаточно данных. Для вопросов: да / нет.",
                 "В колонке I честно опишите, кто и как согласовал, например: «Fariza и Amina, обсуждение 25.11, у собаки apartment_ok=no».",
                 "Заказчика (приюта) в проекте нет — не пишите, что согласовал заказчик, если этого не было."]:
        help_.append([line])
    help_.column_dimensions["A"].width = 120
    wb.save(disp_path)
    print(f"Спорных строк: {ws.max_row - 1} -> {disp_path.name}. Метки: suitable / unsuitable / insufficient, yes / no")
    sys.exit(0)

resolved = {}
if disp_path.exists():
    for r in load_workbook(disp_path, data_only=True).active.iter_rows(min_row=2, values_only=True):
        if r[0]:
            dec = norm_decision(r[0], r[7])
            if not dec or not r[8]:
                sys.exit(f"Спорный случай без решения или без описания согласования: {r[:3]}")
            resolved[(r[0], r[1], r[2] or "")] = dec
with open(ROOT / "evals/gold.jsonl", "w", encoding="utf-8") as f:
    for s in sorted(sa):
        pairs = {}
        for (sid, aid), lab in pa.items():
            if sid == s:
                pairs[aid] = lab if lab == pb[(sid, aid)] else resolved[("пара", sid, aid)]
        g = {}
        for fld in ("clarify", "allowed"):
            g[fld] = sa[s][fld] if sa[s][fld] == sb[s][fld] else resolved[(fld, s, "")]
        best = [int(x) for x in sa[s]["best"].replace(";", ",").split(",") if x.strip().isdigit()]
        f.write(
            json.dumps(
                {
                    "id": s,
                    "pairs": {str(k): v for k, v in pairs.items()},
                    **g,
                    "best": best[:5],
                    "constraints_a": sa[s]["constraints"],
                    "constraints_b": sb[s]["constraints"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
print("gold.jsonl записан")
