"""Создаёт evals/scenarios.jsonl — 36 ТЕСТОВЫХ сценариев (не реальные обращения: реальных в PetHome нет).
Кандидаты (10 животных на сценарий) выбираются детерминированно (seed = номер сценария) только по виду,
без учёта остальных свойств, — чтобы выбор не подгонялся под ответ."""

import json
from collections import Counter
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
animals = [
    a
    for a in json.loads((ROOT / "backend/data/animals.json").read_text(encoding="utf-8"))
    if a["status"] == "available"
]
cats = sorted(a["id"] for a in animals if a["type"] == "Кошка")
dogs = sorted(a["id"] for a in animals if a["type"] == "Собака")
A, H, K, N, ACT, T = "apartment", "house", "family_kids", "no_experience", "active", "limited_time"
S = [
    # --- 1. Квартира
    (
        A,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "low",
        },
        "Ищу спокойную кошку в однокомнатную квартиру, работаю в офисе",
        None,
    ),
    (
        A,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "medium",
            "walks_ready": "yes",
            "size_pref": "small",
        },
        "Небольшая собака для квартиры, гуляю утром и вечером",
        None,
    ),
    (
        A,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "experienced",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Хочу крупную активную собаку, но живу в квартире 40 м²",
        "contradictory",
    ),
    (
        A,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "cat",
            "time_per_day": "medium",
            "experience": "experienced",
            "activity": "medium",
        },
        "Дома уже есть кот, ищем ему компанию",
        None,
    ),
    (
        A,
        {
            "preferred_type": "any",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "low",
            "allergy": "yes",
        },
        "У мужа лёгкая аллергия, но очень хотим питомца",
        None,
    ),
    (
        A,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "none",
            "walks_ready": "no",
        },
        "Хочу собаку, но гулять с ней не смогу — работаю допоздна",
        "no_safe",
    ),
    # --- 2. Частный дом
    (
        H,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "experienced",
            "activity": "high",
            "walks_ready": "yes",
            "size_pref": "large",
        },
        "Частный дом с большим двором, есть опыт с крупными собаками",
        None,
    ),
    (
        H,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "over6",
            "other_pets": "dog",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "medium",
            "walks_ready": "yes",
        },
        "Живём в доме, есть взрослая собака, дети школьники",
        None,
    ),
    (
        H,
        {
            "preferred_type": "cat",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "high",
        },
        "Дом за городом, кошка сможет гулять по участку",
        None,
    ),
    (
        H,
        {
            "preferred_type": "any",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "experienced",
            "activity": "medium",
        },
        "Пенсионеры, свой дом, много свободного времени",
        None,
    ),
    (H, {"preferred_type": "dog", "housing": "house"}, "собака во двор", "insufficient"),
    (
        H,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "medium",
            "walks_ready": "yes",
        },
        "Үйіміз бар, ит керек, күніне екі рет серуендеймін",
        "mixed_kz",
    ),
    # --- 3. Семья с детьми
    (
        K,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "under6",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "medium",
            "walks_ready": "yes",
        },
        "Двое детей 3 и 5 лет, нужна добрая собака",
        None,
    ),
    (
        K,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "over6",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "none",
            "activity": "medium",
        },
        "Дочке 10 лет, мечтает о котёнке, будем ухаживать вместе",
        None,
    ),
    (
        K,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "over6",
            "other_pets": "cat",
            "time_per_day": "high",
            "experience": "some",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Большая семья, есть кошка, хотим активную собаку для походов",
        None,
    ),
    (
        K,
        {
            "preferred_type": "any",
            "housing": "apartment",
            "kids": "under6",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "none",
        },
        "Малышу год, хотим питомца, но времени мало",
        None,
    ),
    (
        K,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "under6",
            "other_pets": "dog",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "low",
        },
        "Балам кішкентай, мысық керек, үйде ит те бар",
        "mixed_kz",
    ),
    (K, {"preferred_type": "dog", "kids": "over6"}, "для ребёнка", "short"),
    # --- 4. Нет опыта
    (
        N,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "none",
            "activity": "low",
        },
        "Первый питомец в жизни, хочу неприхотливую кошку",
        None,
    ),
    (
        N,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "none",
            "activity": "medium",
            "walks_ready": "yes",
        },
        "Никогда не было собак, нужна послушная и несложная",
        None,
    ),
    (
        N,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "none",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Опыта нет, но хочу хаски или овчарку",
        "contradictory",
    ),
    (
        N,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "none",
            "activity": "medium",
        },
        "Студентка, учусь онлайн, впервые беру кошку",
        None,
    ),
    (N, {"preferred_type": "any", "experience": "none"}, "хочу кого-нибудь милого", "ambiguous"),
    (
        N,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "none",
            "activity": "low",
            "walks_ready": "yes",
            "age_pref": "adult",
        },
        "Хочу взрослую спокойную собаку, не щенка — боюсь не справиться",
        None,
    ),
    # --- 5. Активный образ жизни
    (
        ACT,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "experienced",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Бегаю 10 км каждое утро, ищу напарника",
        None,
    ),
    (
        ACT,
        {
            "preferred_type": "dog",
            "housing": "house",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "high",
            "experience": "some",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Часто ходим в горы, нужна выносливая собака",
        None,
    ),
    (
        ACT,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "medium",
            "experience": "some",
            "activity": "high",
        },
        "Хочу игривую кошку, которая не будет спать весь день",
        None,
    ),
    (
        ACT,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "some",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Люблю активный отдых по выходным, в будни работаю по 12 часов",
        "contradictory",
    ),
    (
        ACT,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "dog",
            "time_per_day": "high",
            "experience": "experienced",
            "activity": "high",
            "walks_ready": "yes",
        },
        "Велосипед, бег, есть ещё одна собака",
        None,
    ),
    (ACT, {"preferred_type": "dog"}, "спорт", "short"),
    # --- 6. Ограниченное время
    (
        T,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "some",
            "activity": "low",
        },
        "Работаю по 10 часов, хочу самостоятельную кошку",
        None,
    ),
    (
        T,
        {
            "preferred_type": "dog",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "some",
            "activity": "low",
            "walks_ready": "yes",
        },
        "Мало времени, но могу гулять 30 минут два раза в день",
        None,
    ),
    (
        T,
        {
            "preferred_type": "any",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "none",
            "activity": "low",
        },
        "Часто в командировках, кого посоветуете?",
        None,
    ),
    (
        T,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "none",
            "time_per_day": "low",
            "experience": "none",
        },
        "Хочу персидскую кошку, но на уход времени почти нет",
        "contradictory",
    ),
    (
        T,
        {
            "preferred_type": "cat",
            "housing": "apartment",
            "kids": "none",
            "other_pets": "cat",
            "time_per_day": "low",
            "experience": "some",
            "activity": "medium",
        },
        "Есть кошка, днём никого нет дома, нужна вторая для компании",
        None,
    ),
    (T, {}, "мне бы просто кого-то, не знаю", "insufficient"),
]
assert len(S) == 36
out = []
for i, (cat, prof, text, hard) in enumerate(S, 1):
    rng = random.Random(i)
    want = prof.get("preferred_type")
    if want == "cat":
        cand = rng.sample(cats, 10)
    elif want == "dog":
        cand = rng.sample(dogs, 10)
    else:
        cand = rng.sample(cats, 5) + rng.sample(dogs, 5)
    out.append(
        {
            "id": f"sc-{i:02d}",
            "category": cat,
            "hard": hard,
            "source": "test_scenario",
            "profile": prof,
            "text": text,
            "candidates": sorted(cand),
        }
    )
with open(ROOT / "evals/scenarios.jsonl", "w", encoding="utf-8") as f:
    for x in out:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")


print(
    Counter(x["category"] for x in out), sum(bool(x["hard"]) for x in out), Counter(x["hard"] for x in out if x["hard"])
)
