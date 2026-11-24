"""Интеллектуальный подбор питомца PetHome (ЛЗ 12).

Одна функция, четыре варианта, один и тот же код для сайта и для evals:
  A  baseline_recommend()          — 18 правил, без ИИ
  B  llm_recommend(mode="zero")    — облачная модель, инструкция без примеров
  C  llm_recommend(mode="few")     — та же модель + 3 демонстрационных примера
  D  safe_recommend()              — C + проверка обязательных ограничений и правило отказа

Правило отказа (D) НЕ использует «уверенность», которую называет модель: оно опирается
на полноту анкеты и на проверяемые поля карточки животного.

Провайдер — любой OpenAI-совместимый API (Groq в продакшене):
  AI_BASE_URL=https://api.groq.com/openai/v1  AI_MODEL=openai/gpt-oss-20b  AI_API_KEY=...
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

# reco-v1 — замер 24.11 (сохранён дословно); reco-v3 — 25.11, после разбора ошибок (см. evals/error_analysis.json)
PROMPT_VERSION = os.environ.get("PROMPT_VERSION", "reco-v3")
# rules-v1 — 18 правил замера 24.11; rules-v2 — плюс R19 «собака при нехватке времени»
RULES_VERSION = os.environ.get("RULES_VERSION", "rules-v2")
# v1 — замер 24.11; v2 (25.11, после разбора ошибок): при неполной анкете пары, не исключённые правилами,
# получают «недостаточно данных» — о человеке слишком мало сведений, чтобы судить о совместимости
# refusal-v3 (25.11): v2 + порядок рекомендаций по баллам правил R15–R18 среди всех проверенных «подходит»
REFUSAL_VERSION = os.environ.get("REFUSAL_VERSION", "refusal-v3")
LABELS = ("suitable", "unsuitable", "insufficient")
LABELS_RU = {"suitable": "Подходит", "unsuitable": "Не подходит", "insufficient": "Недостаточно данных"}
TOP_K = 5



def _load_env_file() -> str:
    """Читает backend/.env или файл из PETHOME_ENV_FILE (KEY=VALUE). Уже заданные переменные не перезаписывает.
    Возвращает путь к прочитанному файлу (без значений) — для диагностики."""
    from pathlib import Path

    path = Path(os.environ.get("PETHOME_ENV_FILE") or Path(__file__).resolve().parent / ".env").expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip().removeprefix("export ").strip(), v.strip().strip("'\""))
    return str(path)


ENV_FILE_LOADED = _load_env_file()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
# AI_API_KEY — основное имя; GROQ_API_KEY принимаем как синоним (так его часто называют на Render)
AI_API_KEY = os.environ.get("AI_API_KEY") or os.environ.get("GROQ_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-oss-20b")
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", "25"))

# ============================================================ анкета
PROFILE_FIELDS = {
    "city": "город",
    "preferred_type": "cat | dog | any",
    "housing": "apartment | house",
    "experience": "none | some | experienced",
    "time_per_day": "low (<1 ч) | medium (1–3 ч) | high (>3 ч)",
    "kids": "none | under6 | over6",
    "other_pets": "none | cat | dog",
    "activity": "low | medium | high",
    "walks_ready": "yes | no",
    "size_pref": "small | medium | large | any",
    "age_pref": "young | adult | senior | any",
    "allergy": "yes | no",
}
# без этих полей безопасный подбор невозможен (используется правилом отказа D)
REQUIRED_FIELDS = ("housing", "kids", "other_pets", "time_per_day", "experience")


def clean_profile(p: dict | None) -> dict:
    p = dict(p or {})
    return {k: (str(p[k]).strip().lower() if p.get(k) not in (None, "") else None) for k in PROFILE_FIELDS}


# ============================================================ карточка животного
_SIZE = {
    "маленький": "small",
    "small": "small",
    "средний": "medium",
    "medium": "medium",
    "крупный": "large",
    "большой": "large",
    "large": "large",
}
_TYPE = {"кошка": "cat", "кот": "cat", "cat": "cat", "собака": "dog", "пёс": "dog", "dog": "dog"}
_YN = {"yes": "yes", "да": "yes", "true": "yes", "no": "no", "нет": "no", "false": "no"}


def _age_years(text: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)", text or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v / 12 if "мес" in (text or "") else v


def norm_animal(a: dict) -> dict:
    """Приводим карточку к единому виду. Неизвестное остаётся 'unknown' — не додумываем."""
    g = lambda k: (a.get(k) or "").strip().lower()  # noqa: E731
    age = _age_years(a.get("age", ""))
    return {
        "id": a["id"],
        "name": a.get("name", ""),
        "type": _TYPE.get(g("type"), "other"),
        "breed": a.get("breed", ""),
        "age_years": age,
        "age_group": "young"
        if age is not None and age < 2
        else "senior"
        if age is not None and age >= 8
        else "adult"
        if age is not None
        else "unknown",
        "city": a.get("city", ""),
        "status": g("status") or "available",
        "size": _SIZE.get(g("size"), "unknown"),
        "activity": g("activity_level") if g("activity_level") in ("low", "medium", "high") else "unknown",
        "temperament": a.get("temperament", ""),
        "good_with_kids": _YN.get(g("good_with_kids"), "unknown"),
        "good_with_pets": _YN.get(g("good_with_pets"), "unknown"),
        "apartment_ok": _YN.get(g("apartment_ok"), "unknown"),
        "beginner_ok": _YN.get(g("beginner_ok"), "unknown"),
        "care_level": g("care_level") if g("care_level") in ("low", "medium", "high") else "unknown",
        "special_needs": (a.get("special_needs") or "").strip(),
        "vaccinated": _YN.get(g("vaccinated"), "unknown"),
    }


# ============================================================ A. baseline: 18 правил
# Жёсткие правила (нарушение -> «не подходит»)
def _hard_violations(p: dict, a: dict) -> list[str]:
    v = []
    if a["status"] != "available":
        v.append("R1: животное недоступно")
    if p["preferred_type"] in ("cat", "dog") and a["type"] != p["preferred_type"]:
        v.append("R2: другой вид животного")
    if p["city"] and a["city"] and p["city"] != a["city"].lower():
        v.append("R3: другой город")
    if p["kids"] in ("under6", "over6") and a["good_with_kids"] == "no":
        v.append("R4: не ладит с детьми")
    if p["other_pets"] in ("cat", "dog") and a["good_with_pets"] == "no":
        v.append("R5: не ладит с другими животными")
    if p["housing"] == "apartment" and (
        a["apartment_ok"] == "no" or (a["size"] == "large" and a["apartment_ok"] != "yes")
    ):
        v.append("R6: не подходит для квартиры")
    if p["walks_ready"] == "no" and a["type"] == "dog":
        v.append("R7: собаке нужны ежедневные прогулки")
    if p["experience"] == "none" and a["beginner_ok"] == "no":
        v.append("R8: нужен опытный владелец")
    if p["time_per_day"] == "low" and a["care_level"] == "high":
        v.append("R9: сложный уход при недостатке времени")
    if p["activity"] == "low" and a["activity"] == "high" and a["type"] == "dog":
        v.append("R10: очень активная собака для спокойного образа жизни")
    if (RULES_VERSION != "rules-v1" and p["time_per_day"] == "low" and a["type"] == "dog"
            and not (a["activity"] == "low" and a["care_level"] == "low")):
        v.append("R19: собаке нужно больше часа в день, а времени мало")
    return v


# медицинские особые потребности (особенности ухода вроде «вычёсывание» сюда не относятся)
_MEDICAL = re.compile(r"лечен|лекарств|таблет|инъекц|диет|травм|хрон|операц|инвалид|слеп|глух|болезн|аллерг|диабет", re.I)


# Правила неопределённости (нет подтверждённых данных -> «недостаточно данных»)
def _uncertain(p: dict, a: dict) -> list[str]:
    u = []
    if p["kids"] == "under6" and a["good_with_kids"] == "unknown":
        u.append("R11: нет данных о совместимости с маленькими детьми")
    if p["other_pets"] in ("cat", "dog") and a["good_with_pets"] == "unknown":
        u.append("R12: нет данных о совместимости с другими животными")
    if _MEDICAL.search(a["special_needs"]) and p["experience"] in (None, "none"):
        u.append("R13: медицинские особые потребности требуют консультации")
    if p["allergy"] == "yes":
        u.append("R14: аллергия — нужна встреча с животным до решения")
    return u


def _score(p: dict, a: dict, text: str) -> float:
    s = 0.0
    order = {"low": 0, "medium": 1, "high": 2}
    if p["activity"] in order and a["activity"] in order:  # R15 активность
        s += 2 - abs(order[p["activity"]] - order[a["activity"]])
    if p["size_pref"] not in (None, "any") and a["size"] == p["size_pref"]:  # R16 размер
        s += 1
    if p["age_pref"] not in (None, "any") and a["age_group"] == p["age_pref"]:  # R17 возраст
        s += 1
    t = (text or "").lower()
    if a["breed"] and a["breed"].lower()[:5] in t:  # R18 порода/характер из свободного текста
        s += 2
    if ("спокой" in t and "спокой" in a["temperament"].lower()) or (
        "актив" in t and "актив" in a["temperament"].lower()
    ):
        s += 1
    if p["time_per_day"] == "high" and a["care_level"] == "high":
        s += 0.5
    return s


_CAT_RX = re.compile(r"\bкош\w*|\bкот(?:ик\w*|ёнк\w*|енк\w*|ят\w*|ы|а|у|е|ом)?\b|\bкотёнок\b|\bкотенок\b|мысық|\bcats?\b|"
                     r"мейн-кун|сфинкс|британ|шотланд|персидск")
_DOG_RX = re.compile(r"\bсобак\w*|\bсобачк\w*|\bп[её]с\b|\bпсин\w*|\bщен\w*|\bит\b|\bитті\w*|\bdogs?\b|хаски|овчарк|"
                     r"лабрадор|ретривер|корги|шпиц|терьер|бигл|пудел|такс[аеуы]\b|доберман|ротвейлер|самоед")


_OWNED_RX = re.compile(r"(?:уже\s+)?есть\s+(?:\w+\s+){0,2}?(?:кош\w*|кот\w*|собак\w*|п[её]с\w*)|"
                       r"(?:мысық|ит)\s+(?:та|те)\s+бар|(?:кошк\w*|кот\w*|собак\w*)\s+уже\s+есть")


def _type_from_text(text: str) -> str | None:
    t = (text or "").lower()
    if RULES_VERSION == "rules-v1":  # как в замере 24.11 (с найденным дефектом: «кот» в «который», «ит» в глаголах)
        cat, dog = bool(re.search(r"кош|кот|мысық|cat", t)), bool(re.search(r"собак|пёс|пес|щен|ит\b|dog", t))
    else:
        # животные, которые у человека уже есть, — не то, что он хочет взять
        t = _OWNED_RX.sub(" ", t)
        cat, dog = bool(_CAT_RX.search(t)), bool(_DOG_RX.search(t))
    return "cat" if cat and not dog else "dog" if dog and not cat else None


# Явные сведения из свободного текста (чат). Анкета важнее: текст заполняет только пустые поля.
_TEXT_FACTS = [
    ("housing", "apartment", r"квартир|пәтер|apartment|однушк|студи[июя]"),
    ("housing", "house", r"частн\w* дом|сво[йё]м? дом|в доме|дом за городом|дом с |үйім|үй бар|house"),
    ("kids", "none", r"детей нет|без детей|нет детей"),
    ("kids", "under6", r"малыш|младен|кішкентай|\b[1-5]\s*(год|года|лет)\b|годовал"),
    ("kids", "over6", r"школьн|подрост|\b([6-9]|1[0-7])\s*(год|года|лет)\b|сын|доч|дет[иейя]|ребён|ребен|бала"),
    ("other_pets", "none", r"других животных нет|нет (других )?животных"),
    ("other_pets", "cat", r"есть (ещё |уже )?(кошка|кот)\b|уже есть кот|мысық та бар|дома (уже )?(есть )?кот"),
    ("other_pets", "dog", r"есть (ещё |уже )?(одна )?(собака|пёс|пес)|ит те бар|взрослая собака"),
    ("time_per_day", "low", r"мало времени|допоздна|по 1[0-2] час|командировк|почти нет|никого нет дома"),
    ("time_per_day", "high", r"работаю из дома|много (свободного )?времени|пенсионер|учусь онлайн|весь день дома"),
    ("experience", "none", r"нет опыта|опыта нет|никогда не было|первый питомец|первый в жизни|впервые|не было (собак|кошек)"),
    ("experience", "some", r"есть опыт|опыт с|был[аи]? (кошка|собака|кот)|раньше (была|был)|(была|был) раньше|жил[аи]? (кошка|собака|кот)"),
    ("walks_ready", "no", r"гулять не смогу|не смогу гулять|не могу гулять"),
    ("walks_ready", "yes", r"гуляю|гулять (утром|дважды|два раза)|серуендеймін|могу гулять"),
]
_TEXT_FACTS_RX = [(f, v, re.compile(rx, re.I)) for f, v, rx in _TEXT_FACTS]


def profile_with_text(profile: dict | None, text: str = "") -> dict:
    p = clean_profile(profile)
    for field, value, rx in _TEXT_FACTS_RX:
        if not p[field] and rx.search(text or ""):
            p[field] = value
    if not p["preferred_type"]:
        p["preferred_type"] = _type_from_text(text)
    return p


def classify_pair_rules(profile: dict, animal: dict, text: str = "") -> tuple[str, list[str]]:
    p = profile_with_text(profile, text)
    a = norm_animal(animal)
    hv = _hard_violations(p, a)
    if hv:
        return "unsuitable", hv
    un = _uncertain(p, a)
    return ("insufficient", un) if un else ("suitable", [])


def baseline_recommend(profile: dict, animals: list[dict], text: str = "") -> dict:
    t0 = time.perf_counter()
    pairs, scored = [], []
    for animal in animals:
        label, why = classify_pair_rules(profile, animal, text)
        pairs.append({"animal_id": animal["id"], "label": label, "reason": "; ".join(why) or "все правила выполнены"})
        if label == "suitable":
            scored.append((_score(profile_with_text(profile, text), norm_animal(animal), text), -animal["id"], animal["id"]))
    top = [i for *_, i in sorted(scored, reverse=True)[:TOP_K]]
    return {
        "variant": "A",
        "action": "recommend" if top else "no_safe_match",
        "top": top,
        "pairs": pairs,
        "question": None,
        "latency_s": round(time.perf_counter() - t0, 5),
        "usage": {},
        "source": "rules",
    }


# ============================================================ B / C. облачная модель
SYSTEM = """Ты — помощник платформы PetHome, которая помогает людям выбрать животное из приюта.
Тебе дают анкету человека, его свободный запрос и список животных-кандидатов (только они существуют).
Задача:
1. Для КАЖДОГО кандидата поставь метку:
   suitable — подходит по всем подтверждённым данным;
   unsuitable — нарушает требование человека или очевидное ограничение (дети, другие животные, жильё, время, прогулки, опыт, вид);
   insufficient — нет подтверждённых данных о важном для этого человека свойстве (значение unknown), решить нельзя.
2. Выбери до 5 лучших подходящих (top) по убыванию соответствия, только из suitable.
3. action: recommend — есть подходящие; clarify — в анкете не хватает важной информации и нужно задать вопрос;
   no_safe_match — безопасных вариантов нет.
Правила: не придумывай свойства животных, которых нет в карточке; unknown — это не «да».
Ты ничего не одобряешь и не решаешь: итоговое решение принимает сотрудник приюта.
Запрос может быть на русском, казахском или смеси языков.
Ответь ТОЛЬКО JSON:
{"action":"recommend|clarify|no_safe_match","question":"вопрос или null",
 "pairs":[{"animal_id":1,"label":"suitable|unsuitable|insufficient","reason":"коротко, по-русски"}],
 "top":[1,2]}"""

# Примеры few-shot: вымышленные животные (id 9xxx) и сценарии, которых нет в eval-наборе.
_EX_ANIMALS_1 = [
    {
        "id": 9001,
        "type": "dog",
        "breed": "Лабрадор",
        "size": "large",
        "activity": "high",
        "good_with_kids": "yes",
        "good_with_pets": "yes",
        "apartment_ok": "unknown",
        "beginner_ok": "yes",
        "care_level": "medium",
        "age_group": "adult",
    },
    {
        "id": 9002,
        "type": "dog",
        "breed": "Мопс",
        "size": "small",
        "activity": "low",
        "good_with_kids": "yes",
        "good_with_pets": "unknown",
        "apartment_ok": "yes",
        "beginner_ok": "yes",
        "care_level": "low",
        "age_group": "adult",
    },
    {
        "id": 9003,
        "type": "cat",
        "breed": "Метис",
        "size": "small",
        "activity": "medium",
        "good_with_kids": "no",
        "good_with_pets": "yes",
        "apartment_ok": "yes",
        "beginner_ok": "yes",
        "care_level": "low",
        "age_group": "young",
    },
]
FEW_SHOT = [
    (
        {
            "profile": {
                "preferred_type": "dog",
                "housing": "apartment",
                "kids": "over6",
                "other_pets": "none",
                "time_per_day": "medium",
                "experience": "none",
                "activity": "low",
                "walks_ready": "yes",
            },
            "text": "Хотим спокойную собаку в квартиру, ребёнку 9 лет",
            "candidates": _EX_ANIMALS_1,
        },
        {
            "action": "recommend",
            "question": None,
            "top": [9002],
            "pairs": [
                {
                    "animal_id": 9001,
                    "label": "unsuitable",
                    "reason": "крупная и очень активная, нет подтверждения, что подходит для квартиры",
                },
                {
                    "animal_id": 9002,
                    "label": "suitable",
                    "reason": "маленькая спокойная собака, ладит с детьми, подходит для квартиры",
                },
                {"animal_id": 9003, "label": "unsuitable", "reason": "человек ищет собаку, а это кошка"},
            ],
        },
    ),
    (
        {
            "profile": {"preferred_type": "any", "kids": "under6", "other_pets": "cat"},
            "text": "хочу питомца",
            "candidates": _EX_ANIMALS_1,
        },
        {
            "action": "clarify",
            "question": "Вы живёте в квартире или в доме и сколько времени в день готовы уделять питомцу?",
            "top": [],
            "pairs": [
                {"animal_id": 9001, "label": "insufficient", "reason": "неизвестно жильё и время человека"},
                {"animal_id": 9002, "label": "insufficient", "reason": "нет данных, ладит ли с кошками"},
                {"animal_id": 9003, "label": "unsuitable", "reason": "не ладит с детьми, а в семье ребёнок до 6 лет"},
            ],
        },
    ),
    (
        {
            "profile": {
                "preferred_type": "cat",
                "housing": "apartment",
                "kids": "under6",
                "other_pets": "none",
                "time_per_day": "low",
                "experience": "none",
            },
            "text": "Мысық керек, үйде кішкентай бала бар",
            "candidates": _EX_ANIMALS_1,
        },
        {
            "action": "no_safe_match",
            "question": None,
            "top": [],
            "pairs": [
                {"animal_id": 9001, "label": "unsuitable", "reason": "нужна кошка, а это собака"},
                {"animal_id": 9002, "label": "unsuitable", "reason": "нужна кошка, а это собака"},
                {
                    "animal_id": 9003,
                    "label": "unsuitable",
                    "reason": "кошка не ладит с детьми, а в семье маленький ребёнок",
                },
            ],
        },
    ),
]

SYSTEM_V3 = """Ты — помощник платформы PetHome, которая помогает людям выбрать животное из приюта.
Тебе дают анкету человека, его свободный запрос и список животных-кандидатов (существуют только они).
Для КАЖДОГО кандидата из списка поставь ровно одну метку (пропускать кандидатов нельзя):
- suitable — по подтверждённым данным карточки животное подходит человеку;
- unsuitable — нарушено ОБЯЗАТЕЛЬНОЕ ограничение человека: другой вид; ребёнок в семье, а животное не ладит с детьми (no);
  есть другое животное, а это не ладит с животными (no); квартира, а apartment_ok = no; нет опыта, а beginner_ok = no;
  человек не готов гулять, а это собака; мало времени, а уход сложный или собака активная; просит конкретную породу — другая порода;
- insufficient — по важному для ЭТОГО человека вопросу данных нет: свойство животного unknown ИЛИ человек не сообщил
  о себе главного (жильё, дети, другие животные, время, опыт), ИЛИ нужное свойство вообще не описано в карточке
  (гипоаллергенность, выносливость для спорта, безопасный выгул).
Важно:
- Разница в активности на один уровень (low/medium или medium/high) — НЕ причина для unsuitable: учти её только в порядке top.
- apartment_ok касается только квартиры. Для частного дома это поле не ограничение.
- Не применяй ограничение, которого у человека нет (нет других животных — совместимость с животными не важна; нет детей — не важна совместимость с детьми).
- unknown — это не «да». Не придумывай свойств, которых нет в карточке.
top — до 5 лучших из suitable по убыванию соответствия. action: recommend — есть suitable; clarify — о человеке не хватает
главного; no_safe_match — безопасных вариантов нет. Ты ничего не одобряешь: решение принимает сотрудник приюта.
Запрос может быть на русском, казахском или смеси. reason — коротко по-русски, со ссылкой на конкретное поле."""

_EX_ANIMALS_3 = [
    {"id": 9101, "type": "dog", "breed": "Бигль", "size": "medium", "activity": "high", "good_with_kids": "yes",
     "good_with_pets": "no", "apartment_ok": "yes", "beginner_ok": "yes", "care_level": "low", "age_group": "adult"},
    {"id": 9102, "type": "dog", "breed": "Ши-тцу", "size": "small", "activity": "medium", "good_with_kids": "yes",
     "good_with_pets": "yes", "apartment_ok": "yes", "beginner_ok": "yes", "care_level": "medium", "age_group": "adult"},
    {"id": 9103, "type": "dog", "breed": "Аляскинский маламут", "size": "large", "activity": "high", "good_with_kids": "yes",
     "good_with_pets": "unknown", "apartment_ok": "no", "beginner_ok": "no", "care_level": "high", "age_group": "young"},
    {"id": 9104, "type": "cat", "breed": "Метис", "size": "small", "activity": "low", "good_with_kids": "unknown",
     "good_with_pets": "yes", "apartment_ok": "yes", "beginner_ok": "yes", "care_level": "low", "age_group": "senior"},
]
FEW_SHOT_V3 = [
    (
        {"profile": {"preferred_type": "dog", "housing": "house", "kids": "none", "other_pets": "none", "time_per_day": "high",
                     "experience": "some", "activity": "medium", "walks_ready": "yes"},
         "text": "Свой дом, много времени, хотим собаку", "candidates": _EX_ANIMALS_3},
        {"action": "recommend", "question": None, "top": [9102, 9101], "pairs": [
            {"animal_id": 9101, "label": "suitable", "reason": "активность high — на уровень выше запроса, это не исключение; других животных нет, поэтому good_with_pets не важно"},
            {"animal_id": 9102, "label": "suitable", "reason": "активность medium совпадает, ладит с детьми и животными"},
            {"animal_id": 9103, "label": "unsuitable", "reason": "beginner_ok = no, а опыт небольшой; apartment_ok для дома не важно"},
            {"animal_id": 9104, "label": "unsuitable", "reason": "человек ищет собаку, а это кошка"}]},
    ),
    (
        {"profile": {"preferred_type": "dog"}, "text": "собака для пробежек", "candidates": _EX_ANIMALS_3},
        {"action": "clarify", "question": "Где вы живёте, есть ли дети или другие животные и сколько времени в день готовы уделять собаке?",
         "top": [], "pairs": [
            {"animal_id": 9101, "label": "insufficient", "reason": "о человеке неизвестны жильё, дети, время и опыт"},
            {"animal_id": 9102, "label": "insufficient", "reason": "о человеке неизвестны жильё, дети, время и опыт"},
            {"animal_id": 9103, "label": "insufficient", "reason": "о человеке неизвестны жильё, дети, время и опыт"},
            {"animal_id": 9104, "label": "unsuitable", "reason": "человек ищет собаку, а это кошка"}]},
    ),
    (
        {"profile": {"preferred_type": "any", "housing": "apartment", "kids": "under6", "other_pets": "dog", "time_per_day": "low",
                     "experience": "none"},
         "text": "Ребёнку 3 года, дома есть собака, времени мало", "candidates": _EX_ANIMALS_3},
        {"action": "no_safe_match", "question": None, "top": [], "pairs": [
            {"animal_id": 9101, "label": "unsuitable", "reason": "good_with_pets = no, а дома есть собака"},
            {"animal_id": 9102, "label": "unsuitable", "reason": "собаке нужно больше часа в день, а времени мало"},
            {"animal_id": 9103, "label": "unsuitable", "reason": "apartment_ok = no, beginner_ok = no"},
            {"animal_id": 9104, "label": "insufficient", "reason": "good_with_kids = unknown, а в семье ребёнок до 6 лет"}]},
    ),
]
PROMPTS = {"reco-v1": (SYSTEM, FEW_SHOT), "reco-v3": (SYSTEM_V3, FEW_SHOT_V3)}

# Structured Outputs (reco-v3): схема заставляет вернуть метку для каждого кандидата
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["recommend", "clarify", "no_safe_match"]},
        "question": {"type": ["string", "null"]},
        "pairs": {"type": "array", "items": {"type": "object", "properties": {
            "animal_id": {"type": "integer"},
            "label": {"type": "string", "enum": ["suitable", "unsuitable", "insufficient"]},
            "reason": {"type": "string"}}, "required": ["animal_id", "label", "reason"], "additionalProperties": False}},
        "top": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["action", "question", "pairs", "top"],
    "additionalProperties": False,
}


_PHONE = re.compile(r"(?:\+?\d[\s\-()]*){7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def scrub_pii(text: str) -> str:
    return _PHONE.sub("[телефон]", _EMAIL.sub("[email]", text or ""))


def _compact(a: dict) -> dict:
    n = norm_animal(a)
    keys = (
        "id",
        "name",
        "type",
        "breed",
        "age_group",
        "city",
        "size",
        "activity",
        "temperament",
        "good_with_kids",
        "good_with_pets",
        "apartment_ok",
        "beginner_ok",
        "care_level",
        "special_needs",
    )
    return {k: n[k] for k in keys if n[k] not in ("", None)}


def build_messages(profile: dict, text: str, animals: list[dict], mode: str, version: str | None = None) -> list[dict]:
    system, few = PROMPTS[version or PROMPT_VERSION]
    msgs = [{"role": "system", "content": system}]
    if mode == "few":
        for inp, out in few:
            msgs.append({"role": "user", "content": json.dumps(inp, ensure_ascii=False)})
            msgs.append({"role": "assistant", "content": json.dumps(out, ensure_ascii=False)})
    payload = {
        "profile": {k: v for k, v in clean_profile(profile).items() if v},
        "text": scrub_pii(text),
        "candidates": [_compact(a) for a in animals],
    }
    msgs.append({"role": "user", "content": json.dumps(payload, ensure_ascii=False)})
    return msgs


def _parse(raw: str, ids: list[int]) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        obj = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        obj = {}
    pairs = {}
    for it in obj.get("pairs") or []:
        try:
            aid = int(it.get("animal_id"))
        except (TypeError, ValueError):
            continue
        lab = str(it.get("label", "")).lower()
        if aid in ids:
            pairs[aid] = {
                "animal_id": aid,
                "label": lab if lab in LABELS else "invalid",
                "reason": str(it.get("reason", ""))[:300],
            }
    top = []
    for x in obj.get("top") or []:
        try:
            x = int(x)
        except (TypeError, ValueError):
            continue
        if x in ids and x not in top:
            top.append(x)
    action = str(obj.get("action", "")).lower()
    return {
        "action": action if action in ("recommend", "clarify", "no_safe_match") else "invalid",
        "question": obj.get("question") if isinstance(obj.get("question"), str) else None,
        "pairs": [pairs.get(i, {"animal_id": i, "label": "missing", "reason": ""}) for i in ids],
        "top": top[:TOP_K],
        "parse_ok": bool(obj),
    }


class AIUnavailable(Exception):
    """kind: not_configured | rate_limit | auth | model | network | timeout | bad_response"""

    def __init__(self, message: str, kind: str = "network"):
        super().__init__(message)
        self.kind = kind


def _retry_after(e: urllib.error.HTTPError, body: str) -> float:
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", body)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    try:
        return float(e.headers.get("retry-after", "0"))
    except ValueError:
        return 0.0


def llm_recommend(
    profile: dict,
    text: str,
    animals: list[dict],
    mode: str = "few",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    version: str | None = None,
) -> dict:
    base_url = (base_url or AI_BASE_URL).rstrip("/")
    model = model or AI_MODEL
    api_key = AI_API_KEY if api_key is None else api_key
    version = version or PROMPT_VERSION
    structured = version != "reco-v1" and os.environ.get("AI_STRUCTURED", "1") != "0"
    body = {
        "model": model,
        "messages": build_messages(profile, text, animals, mode, version),
        "temperature": 0,
        "seed": 42,
        "max_tokens": 2500,
        "response_format": {"type": "json_schema", "json_schema": {"name": "pethome_reco", "strict": True,
                                                                    "schema": RESPONSE_SCHEMA}}
        if structured else {"type": "json_object"},
    }
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"  # рассуждения тоже оплачиваются как выходные токены

    def make_req():
        return urllib.request.Request(
            base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "pethome-reco/1.0",
                **({"Authorization": "Bearer " + api_key} if api_key else {}),
            },
        )

    req = make_req()
    if not api_key and "localhost" not in base_url:
        raise AIUnavailable("не задан AI_API_KEY", "not_configured")
    t0 = time.perf_counter()
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as r:
                data = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            try:
                body = e.read()[:600].decode(errors="replace")
            except OSError:
                body = ""
            body = re.sub(r"org_\w+", "org_***", body)  # в журнал не пишем идентификатор организации
            if e.code == 429:
                wait = _retry_after(e, body)
                # минутный лимит токенов: Groq просит подождать несколько секунд — ждём один раз и повторяем
                if attempt < 3 and 0 < wait <= float(os.environ.get("AI_MAX_RETRY_WAIT", "8")):
                    time.sleep(wait + 0.3)
                    continue
                raise AIUnavailable(f"HTTP 429: {body[:300]}", "rate_limit") from e
            if e.code == 400 and structured and attempt < 3 and re.search(r"schema|response_format", body):
                # провайдер не принял схему для этой модели — повторяем в режиме JSON (фиксируется в ответе)
                structured = False
                body_fmt = {"type": "json_object"}
                body.update(response_format=body_fmt)
                req = make_req()
                continue
            kind = "auth" if e.code in (401, 403) else "model" if e.code in (400, 404) else "network"
            raise AIUnavailable(f"HTTP {e.code}: {body[:300]}", kind) from e
        except TimeoutError as e:
            raise AIUnavailable(f"таймаут {AI_TIMEOUT} с", "timeout") from e
        except (urllib.error.URLError, OSError) as e:
            raise AIUnavailable(str(e), "network") from e
    choice = (data.get("choices") or [{}])[0]
    raw = choice.get("message", {}).get("content") or ""
    if not raw.strip():
        # у gpt-oss рассуждения идут в отдельном поле reasoning; пустой content — это сбой, а не «нет вариантов»
        raise AIUnavailable(f"пустой ответ модели, finish_reason={choice.get('finish_reason')}", "bad_response")
    out = _parse(raw, [a["id"] for a in animals])
    out.update(
        variant="B" if mode == "zero" else "C",
        raw=raw,
        model=data.get("model", model),
        system_fingerprint=data.get("system_fingerprint"),
        finish_reason=choice.get("finish_reason"),
        structured_output=structured,
        prompt_version=version,
        usage=data.get("usage", {}),
        latency_s=round(time.perf_counter() - t0, 3),
        source="ai",
    )
    return out


# ============================================================ D. проверка ограничений + правило отказа
def missing_required(profile: dict, text: str = "") -> list[str]:
    p = profile_with_text(profile, text)
    return [f for f in REQUIRED_FIELDS if not p[f]]


QUESTIONS = {
    "housing": "Вы живёте в квартире или в частном доме?",
    "kids": "Есть ли в семье дети и какого возраста?",
    "other_pets": "Есть ли у вас другие животные?",
    "time_per_day": "Сколько времени в день вы готовы уделять питомцу?",
    "experience": "Был ли у вас опыт содержания животных?",
}


def apply_refusal(result: dict, profile: dict, text: str, animals: list[dict], version: str | None = None) -> dict:
    """Детерминированная надстройка над ответом модели (вариант D). version: refusal-v1 | refusal-v2."""
    version = version or REFUSAL_VERSION
    by_id = {a["id"]: a for a in animals}
    out = dict(result)
    miss = missing_required(profile, text)
    incomplete = len(miss) >= 2
    pairs, notes = [], []
    for pr in result["pairs"]:
        label_rules, why = classify_pair_rules(profile, by_id[pr["animal_id"]], text)
        lab = pr["label"]
        if label_rules == "unsuitable":  # проверяемое ограничение сильнее мнения модели
            lab, reason = "unsuitable", "; ".join(why)
        elif label_rules == "insufficient" and lab == "suitable":
            lab, reason = "insufficient", "; ".join(why)
        else:
            reason = pr.get("reason", "")
        if lab not in LABELS:
            lab = "insufficient"
        if version in ("refusal-v2", "refusal-v3") and incomplete and label_rules != "unsuitable":
            lab, reason = "insufficient", "мало сведений о человеке: " + ", ".join(miss)
        pairs.append({**pr, "label": lab, "reason": reason})
    labels = {p["animal_id"]: p["label"] for p in pairs}
    top = [i for i in result["top"] if labels.get(i) == "suitable"]
    if version == "refusal-v3":
        prof = profile_with_text(profile, text)
        ranked = sorted((i for i, lab in labels.items() if lab == "suitable"),
                        key=lambda i: (-_score(prof, norm_animal(by_id[i]), text), i))
        top = ranked[:TOP_K]
    removed = [i for i in result["top"] if i not in top]
    if removed:
        notes.append(f"убрано из рекомендаций после проверки ограничений: {removed}")
    if incomplete:  # анкета неполная -> уточняем, не рекомендуем
        out.update(action="clarify", question=" ".join(QUESTIONS[m] for m in miss[:2]), top=[])
        notes.append(f"не заполнены обязательные поля: {miss}")
    elif not top:
        out.update(
            action="no_safe_match",
            top=[],
            question=result.get("question") or "Свяжитесь с сотрудником приюта — он подберёт варианты лично.",
        )
    else:
        out.update(action="recommend", top=top)
    out.update(
        variant="D",
        refusal_version=version,
        pairs=pairs,
        refusal_notes=notes,
        handoff=out["action"] != "recommend",
        alternatives=[p["animal_id"] for p in pairs if p["label"] == "insufficient"][:3],
    )
    return out


def safe_recommend(profile: dict, text: str, animals: list[dict], **kw) -> dict:
    return apply_refusal(llm_recommend(profile, text, animals, mode="few", **kw), profile, text, animals)


# ============================================================ проверка объяснений
_CLAIMS = [
    (r"ладит с детьми|подходит (для )?(семь|дет)|хорош[ао] с детьми", "good_with_kids"),
    (r"ладит с (другими )?(животными|кошками|собаками)", "good_with_pets"),
    (r"(подходит|подойд[её]т) для квартиры|в квартир[еу] (подходит|можно)", "apartment_ok"),
    (r"для новичк|без опыта|начинающ", "beginner_ok"),
]


def explanation_errors(reason: str, animal: dict) -> list[str]:
    """Объяснение утверждает свойство, которое в карточке не подтверждено ('yes')."""
    a, t, errs = norm_animal(animal), (reason or "").lower(), []
    for rx, field in _CLAIMS:
        if (
            re.search(rx, t)
            and not re.search(r"не\s+(ладит|подходит|подойд)|нет данных|неизвестн", t)
            and a[field] != "yes"
        ):
            errs.append(f"утверждает {field}, а в карточке {a[field]}")
    return errs


# ============================================================ для сайта
SITE_MAX_CANDIDATES = int(os.environ.get("AI_MAX_CANDIDATES", "12"))


def site_pool(profile: dict, text: str, animals: list[dict]) -> list[dict]:
    """Гибрид для сайта: правила R1–R10 отсекают явно неподходящих, модели уходит не больше 12 кандидатов
    (лимит бесплатного тарифа Groq — 8000 токенов в минуту). Сначала те, кого правила считают подходящими."""
    ranked = []
    for a in animals:
        label, _ = classify_pair_rules(profile, a, text)
        if label == "unsuitable":
            continue
        score = _score(profile_with_text(profile, text), norm_animal(a), text) if label == "suitable" else -1
        ranked.append((label == "suitable", score, -a["id"], a))
    ranked.sort(key=lambda x: x[:3], reverse=True)
    return [x[3] for x in ranked[:SITE_MAX_CANDIDATES]]


def recommend_for_site(profile: dict, text: str, animals: list[dict], ai_enabled: bool) -> dict:
    """Предфильтр правилами -> D. При отключении/недоступности ИИ — правила A с пометкой."""
    pool = site_pool(profile, text, animals)
    if not pool:  # правила исключили всех: безопасных вариантов нет, модель не нужна
        r = baseline_recommend(profile, [], text)
        r.update(mode="ai" if ai_enabled else "disabled", action="no_safe_match", handoff=True, alternatives=[],
                 question="Свяжитесь с сотрудником приюта — он подберёт варианты лично.")
        return r
    if ai_enabled and AI_API_KEY or ai_enabled and "localhost" in AI_BASE_URL:
        try:
            r = safe_recommend(profile, text, pool)
            r["mode"] = "ai"
            return r
        except AIUnavailable as e:
            r = baseline_recommend(profile, pool, text)
            r.update(mode="fallback", error=str(e)[:200], error_kind=e.kind)
            return r
    r = baseline_recommend(profile, pool, text)
    r["mode"] = "disabled" if not ai_enabled else "fallback"
    if ai_enabled:
        r.update(error="не задан AI_API_KEY", error_kind="not_configured")
    return r
