# PetHome
## ЛЗ 12 — интеллектуальный подбор питомца (ИИ)
Страница «Подбор с ИИ»: анкета + ИИ-чат + рекомендации. Модель `openai/gpt-oss-20b` через Groq, правила — предфильтр и резерв.
Отчёт: `docs/lab12/ЛЗ_12_PetHome_План_ИИ_функции.docx`, Wiki: `docs/wiki/`, эксперимент: `evals/`.

**Render (Environment):** `AI_API_KEY` — ключ Groq (console.groq.com/keys), `FRONTEND_ORIGINS=https://pet-home-nine.vercel.app`,
`DATABASE_URL` — PostgreSQL. Пустая база сама заполнится каталогом из `backend/data/animals.json`.
**Vercel (Environment Variables):** `VITE_API_URL=https://<сервис>.onrender.com`, затем Redeploy.
Локально ключ можно положить в `backend/.env` (в git не попадает, см. `backend/.env.example`).
Отключить ИИ без остановки сайта: панель сотрудника → «ИИ-подбор» → «Отключить ИИ».
