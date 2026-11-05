from main import SessionLocal, Animal
from sqlalchemy import select

data = [
    (
        "Луна",
        "Кошка",
        "1 год",
        "Астана",
        "Любит внимание",
        "https://images.unsplash.com/photo-1573865526739-10659fec78a5?w=900&q=85",
    ),
    (
        "Барни",
        "Собака",
        "2 года",
        "Астана",
        "Активный и дружелюбный",
        "https://images.unsplash.com/photo-1552053831-71594a27632d?w=900&q=85",
    ),
    (
        "Мия",
        "Кошка",
        "8 месяцев",
        "Алматы",
        "Игривая",
        "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=900&q=85",
    ),
    (
        "Ричи",
        "Собака",
        "3 года",
        "Алматы",
        "Спокойный",
        "https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=900&q=85",
    ),
    (
        "Сима",
        "Кошка",
        "2 года",
        "Астана",
        "Любит уют",
        "https://images.unsplash.com/photo-1533738363-b7f9aef128ce?w=900&q=85",
    ),
    (
        "Тедди",
        "Собака",
        "1 год",
        "Караганда",
        "Любит игры",
        "https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=900&q=85",
    ),
]
with SessionLocal() as s:
    if s.scalar(select(Animal.id).limit(1)):
        print("Животные уже есть; ничего не добавлено")
    else:
        for name, type, age, city, description, image_url in data:
            s.add(
                Animal(
                    name=name,
                    type=type,
                    age=age,
                    city=city,
                    description=description,
                    image_url=image_url,
                    status="available",
                )
            )
        s.commit()
        print("Добавлено 6 демонстрационных животных")
