"""Загрузка каталога животных из backend/data/animals.json (одна версия базы для сайта и evals).

    python seed_animals.py            # добавить отсутствующих и обновить существующих по id
Сервер также вызывает seed_if_empty() при старте, если таблица animals пуста (новая база на Render).
"""

import hashlib
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "animals.json"
FIELDS = (
    "name",
    "type",
    "age",
    "city",
    "description",
    "image_url",
    "status",
    "breed",
    "sex",
    "size",
    "temperament",
    "activity_level",
    "good_with_kids",
    "good_with_pets",
    "vaccinated",
    "sterilized",
    "special_needs",
    "age_group",
    "apartment_ok",
    "beginner_ok",
    "care_level",
)


def catalog():
    return json.loads(DATA.read_text(encoding="utf-8"))


def catalog_version():
    return hashlib.sha256(DATA.read_bytes()).hexdigest()[:12]


def upsert(session, Animal):
    n_new = n_upd = 0
    for row in catalog():
        a = session.get(Animal, row["id"])
        if a is None:
            a = Animal(id=row["id"])
            session.add(a)
            n_new += 1
        else:
            n_upd += 1
        for k in FIELDS:
            if k in row and row[k] is not None:
                setattr(a, k, row[k])
    session.commit()
    return n_new, n_upd


def seed_if_empty(session, Animal):
    from sqlalchemy import func, select

    if session.scalar(select(func.count()).select_from(Animal)) == 0:
        upsert(session, Animal)
        # PostgreSQL: сдвигаем счётчик id после вставки с явными id
        if session.bind.dialect.name == "postgresql":
            from sqlalchemy import text

            session.execute(
                text("SELECT setval(pg_get_serial_sequence('animals','id'), (SELECT MAX(id) FROM animals))")
            )
            session.commit()


if __name__ == "__main__":
    import main

    with main.SessionLocal() as s:
        print("добавлено %d, обновлено %d; версия каталога %s" % (*upsert(s, main.Animal), catalog_version()))
