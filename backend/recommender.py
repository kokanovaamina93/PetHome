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

PROMPT_VERSION = "reco-v1"
LABELS = ("suitable", "unsuitable", "insufficient")
LABELS_RU = {"suitable": "Подходит", "unsuitable": "Не подходит", "insufficient": "Недостаточно данных"}
TOP_K = 5

AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
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
    return v


# Правила неопределённости (нет подтверждённых данных -> «недостаточно данных»)
def _uncertain(p: dict, a: dict) -> list[str]:
    u = []
    if p["kids"] == "under6" and a["good_with_kids"] == "unknown":
        u.append("R11: нет данных о совместимости с маленькими детьми")
    if p["other_pets"] in ("cat", "dog") and a["good_with_pets"] == "unknown":
        u.append("R12: нет данных о совместимости с другими животными")
    if a["special_needs"] and p["experience"] in (None, "none"):
        u.append("R13: особые потребности требуют консультации")
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


def _type_from_text(text: str) -> str | None:
    t = (text or "").lower()
    cat, dog = bool(re.search(r"кош|кот|мысық|cat", t)), bool(re.search(r"собак|пёс|пес|щен|ит\b|dog", t))
    return "cat" if cat and not dog else "dog" if dog and not cat else None


def classify_pair_rules(profile: dict, animal: dict, text: str = "") -> tuple[str, list[str]]:
    p = clean_profile(profile)
    if not p["preferred_type"]:
        p["preferred_type"] = _type_from_text(text)
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
            scored.append((_score(clean_profile(profile), norm_animal(animal), text), -animal["id"], animal["id"]))
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


def build_messages(profile: dict, text: str, animals: list[dict], mode: str) -> list[dict]:
    msgs = [{"role": "system", "content": SYSTEM}]
    if mode == "few":
        for inp, out in FEW_SHOT:
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
    pass


def llm_recommend(
    profile: dict,
    text: str,
    animals: list[dict],
    mode: str = "few",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict:
    base_url = (base_url or AI_BASE_URL).rstrip("/")
    model = model or AI_MODEL
    api_key = AI_API_KEY if api_key is None else api_key
    body = {
        "model": model,
        "messages": build_messages(profile, text, animals, mode),
        "temperature": 0,
        "seed": 42,
        "max_tokens": 2500,
        "response_format": {"type": "json_object"},
    }
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"  # рассуждения тоже оплачиваются как выходные токены
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "pethome-reco/1.0",
            **({"Authorization": "Bearer " + api_key} if api_key else {}),
        },
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AIUnavailable(f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AIUnavailable(str(e)) from e
    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    out = _parse(raw, [a["id"] for a in animals])
    out.update(
        variant="B" if mode == "zero" else "C",
        raw=raw,
        model=data.get("model", model),
        system_fingerprint=data.get("system_fingerprint"),
        usage=data.get("usage", {}),
        latency_s=round(time.perf_counter() - t0, 3),
        source="ai",
        prompt_version=PROMPT_VERSION,
    )
    return out


# ============================================================ D. проверка ограничений + правило отказа
def missing_required(profile: dict) -> list[str]:
    p = clean_profile(profile)
    return [f for f in REQUIRED_FIELDS if not p[f]]


QUESTIONS = {
    "housing": "Вы живёте в квартире или в частном доме?",
    "kids": "Есть ли в семье дети и какого возраста?",
    "other_pets": "Есть ли у вас другие животные?",
    "time_per_day": "Сколько времени в день вы готовы уделять питомцу?",
    "experience": "Был ли у вас опыт содержания животных?",
}


def apply_refusal(result: dict, profile: dict, text: str, animals: list[dict]) -> dict:
    """Детерминированная надстройка над ответом модели (вариант D)."""
    by_id = {a["id"]: a for a in animals}
    out = dict(result)
    miss = missing_required(profile)
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
        pairs.append({**pr, "label": lab, "reason": reason})
    labels = {p["animal_id"]: p["label"] for p in pairs}
    top = [i for i in result["top"] if labels.get(i) == "suitable"]
    removed = [i for i in result["top"] if i not in top]
    if removed:
        notes.append(f"убрано из рекомендаций после проверки ограничений: {removed}")
    if len(miss) >= 2:  # анкета неполная -> уточняем, не рекомендуем
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
def recommend_for_site(profile: dict, text: str, animals: list[dict], ai_enabled: bool) -> dict:
    """Предфильтр (доступность, вид) -> D. При отключении/недоступности ИИ — правила A с пометкой."""
    p = clean_profile(profile)
    want = p["preferred_type"] if p["preferred_type"] in ("cat", "dog") else _type_from_text(text)
    pool = [
        a
        for a in animals
        if (a.get("status") or "available") == "available" and (not want or norm_animal(a)["type"] == want)
    ][:25]
    if ai_enabled and AI_API_KEY or ai_enabled and "localhost" in AI_BASE_URL:
        try:
            r = safe_recommend(profile, text, pool)
            r["mode"] = "ai"
            return r
        except AIUnavailable as e:
            r = baseline_recommend(profile, pool, text)
            r.update(mode="fallback", error=str(e)[:200])
            return r
    r = baseline_recommend(profile, pool, text)
    r["mode"] = "disabled" if not ai_enabled else "fallback"
    return r
