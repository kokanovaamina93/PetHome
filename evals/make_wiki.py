"""Генерирует страницы GitHub Wiki в docs/wiki/ из тех же источников, что и Word-отчёт.
    python evals/make_wiki.py
Публикация: git clone https://github.com/kokanovaamina93/PetHome.wiki.git && cp docs/wiki/*.md PetHome.wiki/ && push."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/wiki"
OUT.mkdir(parents=True, exist_ok=True)
D = json.loads((ROOT / "docs/lab12/report_data.json").read_text(encoding="utf-8"))
RAW = "https://github.com/kokanovaamina93/PetHome/blob/lab12-ai-recommender/"
run = D["run_id"]
read = lambda p: (ROOT / p).read_text(encoding="utf-8")  # noqa: E731
img = lambda rel, alt: f"![{alt}]({RAW}{rel}?raw=true)"  # noqa: E731
f3 = lambda x: "—" if x is None else f"{x:.3f}".replace(".", ",")  # noqa: E731
R, A, an, C = D["results"], D["agreement"], D["analysis"], D["cost"]
NAV = ("**ЛЗ 12 — ИИ-подбор питомца:** [Обзор](ЛЗ-12-Обзор) · [Карточка функции](ЛЗ-12-Карточка-функции) · "
       "[Eval-набор](ЛЗ-12-Eval-набор) · [Замер и ошибки](ЛЗ-12-Замер-и-ошибки) · [Стоимость](ЛЗ-12-Стоимость) · "
       "[Риски](ЛЗ-12-Риски) · [ADR-002](ЛЗ-12-ADR-002) · [Самопроверка](ЛЗ-12-Самопроверка)\n\n---\n\n")
V = {"A": "A. Правила", "B": "B. Zero-shot", "C": "C. Few-shot", "D": "D. Few-shot + отказ v1", "D2": "D2. Отказ v2 (повторная проверка)"}
pages = {}
pages["ЛЗ-12-Обзор"] = f"""# ЛЗ 12. План ИИ-функции: evals, стоимость, риски

Функция: **интеллектуальный подбор питомца** на PetHome — анкета, ИИ-чат и персональные рекомендации (одна функция).
Модель: `{D['meta']['model']}` через Groq. Замер {D['meta']['started_utc'][:10]}, коммит `{D['meta']['git_commit']}`.

| Итог | Значение |
|---|---|
| Baseline (18 правил) | macro F1 {f3(R['A']['macro_f1'])}, NDCG@5 {f3(R['A']['ndcg_at_5'])} |
| Итоговый гибрид D2 | macro F1 {f3(R['D2']['macro_f1'])}, NDCG@5 {f3(R['D2']['ndcg_at_5'])}, нарушений {R['D2']['violations']}/{R['D2']['recommended_items']} |
| Стоимость | ${C['per_request_usd']:.6f} за запрос, ≈ {C['month_kzt'][0]:.0f} ₸/мес, ×10 — ≈ {C['month_kzt'][1]:.0f} ₸/мес |
| Решение (ADR-002) | **Отложено**: критерий приёмки не выполнен |

Отчёт Word: `docs/lab12/ЛЗ_12_PetHome_План_ИИ_функции.docx`. Код: `backend/recommender.py`, `src/matcher.jsx`, `evals/`.

{img(D['images']['screen_reco'], 'Рекомендации')}
"""
pages["ЛЗ-12-Карточка-функции"] = read("docs/lab12/01-feature-card.md")
pages["ЛЗ-12-Eval-набор"] = (
    "# Набор для оценки\n\n"
    f"36 тестовых сценариев × 10 животных из базы = 360 пар. Категории: {', '.join(f'{k} — {v}' for k, v in D['categories'].items())}. "
    f"Сложных — {sum(D['hard'].values())}. Эталон: подходит {D['gold_counts']['suitable']}, не подходит {D['gold_counts']['unsuitable']}, "
    f"недостаточно данных {D['gold_counts']['insufficient']}.\n\n"
    + read("evals/LABELING.md").replace("# Как получены эталонные метки (фактическое описание)", "## Как получены эталонные метки")
    + f"\n\n| Что сравнивали | Совпадение | Cohen's kappa |\n|---|---|---|\n| Пары | {A['pairs_agreement']:.1%} | {f3(A['pairs_kappa'])} |\n"
    f"| Можно выдавать рекомендации | {A['allowed_agreement']:.1%} | {f3(A['allowed_kappa'])} |\n| Нужен уточняющий вопрос | {A['clarify_agreement']:.1%} | {f3(A['clarify_kappa'])} |\n\n"
    "Правила расчёта метрик: `evals/METRICS.md`. Baseline: `evals/BASELINE_RULES.md`.\n"
)
rows = "\n".join(
    f"| {V[k]} | {f3(R[k]['accuracy'])} | **{f3(R[k]['macro_f1'])}** | {f3(R[k]['precision_at_5'])} | {f3(R[k]['recall_at_5'])} | "
    f"{f3(R[k]['ndcg_at_5'])} | {R[k]['violations']}/{R[k]['recommended_items']} | {R[k]['correct_refusal']} |"
    for k in V if k in R)
cls = "\n".join(
    f"| {name} | " + " | ".join(f3(R[k]["per_class"][c]["f1"]) for k in V if k in R) + " |"
    for c, name in (("suitable", "Подходит"), ("unsuitable", "Не подходит"), ("insufficient", "Недостаточно данных")))
cases = "\n".join(f"| {c['id']} | {c['request']} | {c['type']} | {c['cause']} | {c['fix']} | {c['retest']} |" for c in an["cases"])
pages["ЛЗ-12-Замер-и-ошибки"] = f"""# Замер качества и разбор ошибок

Провайдер Groq, модель `{D['meta']['model']}`, temperature 0, seed 42 (best effort), промпт `{D['meta']['prompt_version']}`.
Сырые ответы: `evals/raw/{run}/`. Выполнено 31 из 36 сценариев, 5 — суточный лимит API (засчитаны как «нет ответа»).

| Вариант | Accuracy | Macro F1 | P@5 | R@5 | NDCG@5 | Нарушения | Верный отказ |
|---|---|---|---|---|---|---|---|
{rows}

| F1 по классам | {' | '.join(V[k] for k in V if k in R)} |
|---|{'---|' * len([k for k in V if k in R])}
{cls}

{img(D['images']['quality'], 'Качество')}

{img(D['images']['confusion_D2'], 'Матрица ошибок D2')}

## Разбор ошибок

{an['intro']}

| ID | Запрос | Тип | Причина | Исправление | Повторная проверка |
|---|---|---|---|---|---|
{cases}

## Правило отказа
{an['refusal']}

## Итог
{an['conclusion']}
"""
pages["ЛЗ-12-Стоимость"] = f"""# Стоимость эксплуатации

Токены — счётчик провайдера: {C['tokens_in']} входных и {C['tokens_out']} выходных на запрос. Тариф Groq gpt-oss-20b: $0,075 / $0,30 за 1 млн
(console.groq.com/docs/models, 24.11.2026). Курс {C['usd_kzt']} ₸/$ (НБРК, 24.11.2026). Формулы: `evals/results/cost-model.xlsx`.

| Показатель | Прогноз | Рост ×10 |
|---|---|---|
| Запросов в месяц | {C['requests_month'][0]:,} | {C['requests_month'][1]:,} |
| В месяц | ${C['month_usd'][0]:.2f} ≈ {C['month_kzt'][0]:.0f} ₸ | ${C['month_usd'][1]:.2f} ≈ {C['month_kzt'][1]:.0f} ₸ |
| В год | ${C['year_usd'][0]:.2f} ≈ {C['year_kzt'][0]:.0f} ₸ | ${C['year_usd'][1]:.2f} ≈ {C['year_kzt'][1]:.0f} ₸ |
| Бесплатный тариф Groq | {C['free_tier_ok'][0]} | {C['free_tier_ok'][1]} |

Свой CPU-сервер ≈ ${C['cpu_server_usd']:.0f}/мес — точка безубыточности {C['breakeven_cpu']:,.0f} запросов/мес (×{C['times_cpu']:.0f}); GPU ≈ ${C['gpu_server_usd']:.0f}/мес —
{C['breakeven_gpu']:,.0f} (×{C['times_gpu']:.0f}). Для PetHome недостижимо: спор «свой сервер или API» — про данные, а не про деньги.

{img(D['images']['cost_chart'], 'API против своего сервера')}
"""
pages["ЛЗ-12-Риски"] = read("docs/lab12/05-risk-card.md")
pages["ЛЗ-12-ADR-002"] = read("docs/lab12/06-adr-002.md")
pages["ЛЗ-12-Самопроверка"] = read("docs/lab12/07-self-check.md")
for name, body in pages.items():
    (OUT / f"{name}.md").write_text(NAV + body, encoding="utf-8")
print("страниц:", len(pages), "->", OUT)
