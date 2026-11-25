// Сборка Word-отчёта ЛЗ 12 из docs/lab12/*.md (тексты карточек, ADR, самопроверка) и report_data.json (цифры).
//   cd docs/lab12/report && npm install && node build_report.cjs
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  HeadingLevel, ImageRun, LevelFormat, BorderStyle, PageBreak, Footer, PageNumber,
} = require("docx");

const ROOT = path.resolve(__dirname, "../../..");
const D = JSON.parse(fs.readFileSync(path.join(ROOT, "docs/lab12/report_data.json"), "utf8"));
const R = D.results;
const md = (f) => fs.readFileSync(path.join(ROOT, "docs/lab12", f), "utf8");
const FONT = "Arial";
const W = 9638; // ширина текста A4 при полях 2 см (DXA)

// ---------- помощники
const clean = (s) => String(s ?? "").replace(/\*\*/g, "").replace(/`/g, "").replace(/(^|\s)_([^_]+)_(?=\s|$|[.,;:])/g, "$1$2").trim();
function mdTable(text, startMarker) {
  const lines = text.split("\n");
  let i = startMarker ? lines.findIndex((l) => l.includes(startMarker)) : 0;
  if (i < 0) throw new Error("нет таблицы после: " + startMarker);
  while (i < lines.length && !lines[i].trim().startsWith("|")) i++;
  const rows = [];
  for (; i < lines.length && lines[i].trim().startsWith("|"); i++) {
    if (/^\|\s*-+/.test(lines[i].trim())) continue;
    rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map(clean));
  }
  return rows;
}
const P = (text, opt = {}) =>
  new Paragraph({
    spacing: { after: opt.after ?? 120, before: opt.before ?? 0 },
    alignment: opt.align,
    children: (Array.isArray(text) ? text : [text]).map((t) =>
      typeof t === "string" ? new TextRun({ text: t, font: FONT, size: opt.size ?? 22, italics: opt.italics, bold: opt.bold, color: opt.color }) : t),
  });
const B = (t) => new TextRun({ text: t, font: FONT, size: 22, bold: true });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun({ text: t, font: FONT })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: t, font: FONT })] });
const bullet = (t) => new Paragraph({ numbering: { reference: "bul", level: 0 }, spacing: { after: 60 },
  children: (Array.isArray(t) ? t : [t]).map((x) => typeof x === "string" ? new TextRun({ text: x, font: FONT, size: 22 }) : x) });
const f3 = (x) => (x === null || x === undefined ? "—" : Number(x).toFixed(3).replace(".", ","));
const f2 = (x) => (x === null || x === undefined ? "—" : Number(x).toFixed(2).replace(".", ","));
const pct = (x) => (x === null || x === undefined ? "—" : (100 * x).toFixed(1).replace(".", ",") + " %");
const num = (x) => Math.round(x).toLocaleString("ru-RU");
const border = { style: BorderStyle.SINGLE, size: 4, color: "BFB8D6" };
function table(rows, widths, opt = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      children: r.map((c, ci) => new TableCell({
        width: { size: widths[ci], type: WidthType.DXA },
        borders: { top: border, bottom: border, left: border, right: border },
        shading: ri === 0 ? { type: ShadingType.CLEAR, fill: "E4DEF4", color: "auto" }
          : opt.firstColShade && ci === 0 ? { type: ShadingType.CLEAR, fill: "F6F4FB", color: "auto" } : undefined,
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        children: String(c).split("\n").map((line) => new Paragraph({ spacing: { after: 0 },
          children: [new TextRun({ text: line, font: FONT, size: opt.size ?? 19, bold: ri === 0 || (opt.boldFirstCol && ci === 0) })] })),
      })),
    })),
  });
}
function img(rel, widthPx, caption) {
  const file = path.join(ROOT, rel);
  if (!fs.existsSync(file)) return [P(`[нет файла ${rel}]`, { italics: true })];
  const buf = fs.readFileSync(file);
  const isPng = rel.endsWith(".png");
  // размеры из заголовка файла
  let w = 1600, h = 1000;
  if (isPng) { w = buf.readUInt32BE(16); h = buf.readUInt32BE(20); }
  else { for (let i = 2; i < buf.length - 9; i++) if (buf[i] === 0xff && (buf[i + 1] === 0xc0 || buf[i + 1] === 0xc2)) { h = buf.readUInt16BE(i + 5); w = buf.readUInt16BE(i + 7); break; } }
  const out = [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new ImageRun({ type: isPng ? "png" : "jpg", data: buf, transformation: { width: widthPx, height: Math.round(widthPx * h / w) } })] })];
  if (caption) out.push(P(caption, { align: AlignmentType.CENTER, italics: true, size: 18, after: 200 }));
  return out;
}
const V = { A: "A. Правила (baseline)", B: "B. Zero-shot", C: "C. Few-shot", D: "D. Few-shot + отказ v1", D2: "D2. Отказ v2 (повторная проверка)", D3: "D3. Отказ v3 + ранжирование правилами" };
const VK = Object.keys(V).filter((k) => R[k]);
const meta = D.meta;

// ---------- 0. Что сдаётся
const s0 = [
  H1("0. Что сдаётся и по каким критериям оценивается"),
  P("Артефакт: карточка ИИ-функции + eval-набор с результатами замера + расчёт стоимости + ADR по решению «делаем / не делаем». Функция — интеллектуальный подбор питомца на платформе PetHome: анкета, ИИ-чат и персональные рекомендации как части одной функции."),
  table([
    ["Артефакт", "Где лежит"],
    ["Рабочая ИИ-функция", "backend/recommender.py, /ai/recommend, страница «Подбор с ИИ» (src/matcher.jsx), панель «ИИ-подбор» у сотрудников"],
    ["Карточка функции, карточка рисков, ADR", "docs/lab12/01-feature-card.md, 05-risk-card.md, 06-adr-002.md; GitHub Wiki"],
    ["Baseline из 18 правил", "evals/BASELINE_RULES.md, recommender.baseline_recommend()"],
    ["Eval-набор, 36 сценариев", "evals/scenarios.jsonl; эталон — evals/gold.jsonl"],
    ["Две таблицы разметки, спорные случаи", "evals/labeling/1_labeling_Fariza.xlsx, 2_labeling_Amina.xlsx, 3_disputes.xlsx"],
    ["Промпты zero-shot и few-shot", `evals/raw/${D.run_id}/prompts/; версия ${meta.prompt_version}`],
    ["Скрипты и сырые ответы", "evals/run_experiment.py, score.py, rescore_refusal.py; evals/raw/<прогон>/A–D3.jsonl, meta.json"],
    ["Таблицы, графики, матрицы ошибок, разбор ошибок", `evals/results/${D.run_id}/; evals/error_analysis.json`],
    ["Стоимость и точка безубыточности", "evals/results/cost-model.xlsx (рабочие формулы), cost_chart.png"],
  ], [3000, W - 3000], { boldFirstCol: true }),
  P(""),
  P("Критерии приёмки работы (по методичке):", { bold: true }),
  bullet("Эталонные ответы составлены не той моделью, которую проверяем, и способ разметки описан честно (раздел 2)."),
  bullet("Результаты замера настоящие: провайдер, модель, дата, параметры, сырые ответы, токены и ошибки API сохранены (раздел 3)."),
  bullet("Тарифы — со ссылкой на официальный прайс и датой проверки, сценарий роста ×10 (раздел 4)."),
  bullet("Есть базовое решение без ИИ, измеренное первым, и сравнение с ним по каждому классу (раздел 3)."),
  bullet("Названо, где человек в контуре и как пользователь узнаёт, что работает ИИ (раздел 5)."),
];

// ---------- 1. Карточка функции
const card = mdTable(md("01-feature-card.md"));
const s1 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 1. Карточка ИИ-функции"),
  table(card, [2500, W - 2500], { boldFirstCol: true, firstColShade: true }),
  P(""),
  ...img(D.images.screen_reco, 430, "Рис. 1. Персональные рекомендации с объяснением ИИ (локальный запуск, модель openai/gpt-oss-20b через Groq)"),
  ...img(D.images.screen_chat, 430, "Рис. 2. ИИ-чат: уточняющий вопрос при неполной информации и подбор после ответа"),
];

// ---------- 2. Набор для оценки
const A = D.agreement, G = D.gold_counts;
const catRu = { apartment: "Квартира", house: "Частный дом", family_kids: "Семья с детьми", no_experience: "Нет опыта", active: "Активный образ жизни", limited_time: "Ограниченное время" };
const hardRu = { contradictory: "противоречивые предпочтения", insufficient: "недостаточно информации", mixed_kz: "смесь русского и казахского", short: "очень короткий запрос", no_safe: "нет безопасных рекомендаций", ambiguous: "неоднозначный запрос" };
const s2 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 2. Набор для оценки"),
  table([
    ["Параметр набора", "Значение"],
    ["Размер", `36 сценариев × 10 кандидатов = 360 пар «запрос — животное» (минимум по заданию — 30 примеров)`],
    ["Источник текстов", "Тестовые сценарии, составленные командой. Реальных обращений пользователей в PetHome нет: в базе 3 тестовые заявки с текстами «чч», «fk». Сценарии помечены source = test_scenario"],
    ["Категории", Object.entries(D.categories).map(([k, v]) => `${catRu[k]} — ${v}`).join("; ")],
    ["Сложные примеры", `${Object.values(D.hard).reduce((a, b) => a + b, 0)} сценариев: ` + Object.entries(D.hard).map(([k, v]) => `${hardRu[k]} — ${v}`).join("; ")],
    ["Животные", `Только существующие в базе PetHome: ${D.n_animals} карточек. Кандидаты выбраны детерминированно (seed = номер сценария) только по виду животного. Карточки заполнены командой и помечены «Синтетические учебные данные, не подтверждено приютом»`],
    ["Распределение классов эталона", `Подходит — ${G.suitable}, Не подходит — ${G.unsuitable}, Недостаточно данных — ${G.insufficient}. Классы неравномерны, поэтому основная метрика — macro F1`],
    ["Решения по сценариям", `Нужен уточняющий вопрос: да — ${D.gold_clarify.yes}, нет — ${D.gold_clarify.no}. Можно выдавать рекомендации: да — ${D.gold_allowed.yes}, нет — ${D.gold_allowed.no}`],
    ["Где лежит", "evals/scenarios.jsonl, evals/gold.jsonl, evals/labeling/; скрипт прогона — evals/run_experiment.py; сырые ответы — evals/raw/"],
  ], [2700, W - 2700], { boldFirstCol: true, firstColShade: true }),
  H2("Как получены эталонные ответы"),
  table(mdTable(md("../../evals/LABELING.md")), [2200, W - 2200], { boldFirstCol: true, firstColShade: true }),
  P(""),
  table([
    ["Что сравнивали", "Совпадение", "Cohen's kappa"],
    ["360 пар «запрос — животное»", pct(A.pairs_agreement), f3(A.pairs_kappa)],
    ["Можно выдавать рекомендации", pct(A.allowed_agreement), f3(A.allowed_kappa)],
    ["Нужен уточняющий вопрос", pct(A.clarify_agreement), f3(A.clarify_kappa)],
  ], [4800, 2400, 2438]),
  P(""),
  P([B("Ограничение. "), "Первичные метки подготовлены автоматически, при проверке участницами не изменились, а спорные случаи закрыты решениями, помеченными в самой таблице как «предложение; согласование ожидается». Поэтому эталон нельзя считать независимой человеческой разметкой: метрики ниже показывают согласие вариантов с этим эталоном, а не подтверждённое качество. Эталон не получен моделью, которую мы проверяем (gpt-oss-20b), но независимость от ИИ не подтверждена."]),
];

// ---------- 3. Замер
const qrow = (k) => [V[k], f3(R[k].accuracy), f3(R[k].macro_precision), f3(R[k].macro_recall), f3(R[k].macro_f1),
  f3(R[k].precision_at_5), f3(R[k].recall_at_5), f3(R[k].ndcg_at_5), `${R[k].violations}/${R[k].recommended_items}`, R[k].correct_refusal, R[k].latency_mean_s == null ? "—" : f2(R[k].latency_mean_s) + " с"];
const clsRu = { suitable: "Подходит", unsuitable: "Не подходит", insufficient: "Недостаточно данных" };
const u = D.usage;
const an = D.analysis;
const errRows = (an.cases || []).map((c) => [c.id, c.request, c.gold, c.answer, c.type, c.cause, c.fix, c.retest]);
const s3 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 3. Замер качества и разбор ошибок"),
  P(`Прогон ${meta.started_utc.replace("T", " ").replace("+00:00", "")} UTC${meta.resumed_utc ? " (продолжен " + meta.resumed_utc.map((x) => x.replace("T", " ").replace("+00:00", "")).join(", ") + " UTC после суточного лимита; завершён " + (meta.finished_utc || "").replace("T", " ").replace("+00:00", "") + " UTC, выполнены все " + meta.n_scenarios + " сценариев)" : ""}. Провайдер — Groq (OpenAI-совместимый API, ${meta.provider_base_url}). Модель — ${meta.model}. Параметры: temperature 0, seed 42, max_tokens 2500, response_format json_object, reasoning_effort low. Версия промпта ${meta.prompt_version}, коммит ${meta.git_commit}, версия каталога животных ${meta.catalog_version}. Ошибок API: ${meta.api_errors.length} (все повторены успешно${meta.api_errors.some((e) => /TPD/.test(e.error)) ? ", " + meta.api_errors.filter((e) => /TPD/.test(e.error)).length + " — суточный лимит бесплатного тарифа" : ""}). Groq поддерживает seed только в режиме best effort: за прогон зафиксировано ${u.C.fingerprints} разных system_fingerprint, детерминированность не гарантируется.`),
  P(`Средние токены по счётчику провайдера: zero-shot — ${u.B.prompt_avg} входных и ${u.B.completion_avg} выходных; few-shot — ${u.C.prompt_avg} входных и ${u.C.completion_avg} выходных (из них в среднем ${u.C.reasoning_avg} токенов рассуждений). Оплата не производилась: использован бесплатный тариф Groq.`),
  table([["Вариант", "Accuracy", "Macro P", "Macro R", "Macro F1", "P@5", "R@5", "NDCG@5", "Нарушения", "Верный отказ", "Время"], ...VK.map(qrow)],
    [1900, 720, 720, 720, 760, 680, 680, 760, 900, 900, 898], { size: 16, boldFirstCol: true }),
  P("Нарушения — рекомендации, которые эталон считает «Не подходит», из всех выданных. Верный отказ — сценарии «рекомендации выдавать нельзя», где вариант никого не порекомендовал. Правила расчёта зафиксированы до прогона: evals/METRICS.md.", { size: 18, italics: true }),
  H2("F1 по классам: ИИ против решения без ИИ"),
  table([["Класс (пар в эталоне)", ...VK.map((k) => V[k])],
    ...["suitable", "unsuitable", "insufficient"].map((c) => [`${clsRu[c]} (${R.A.per_class[c].support})`, ...VK.map((k) => f3(R[k].per_class[c].f1))])],
    [2400, ...VK.map(() => Math.floor((W - 2400) / VK.length))], { size: 18, boldFirstCol: true }),
  P(""),
  ...img(D.images.quality, 560, "Рис. 3. Качество четырёх вариантов и повторных проверок D2, D3"),
  ...img(D.images.latency, 400, "Рис. 4. Среднее время ответа"),
  ...img(D.images.errors, 430, "Рис. 5. Нарушения ограничений, ошибки API и неразобранные ответы"),
  ...img(D.images.confusion_A, 280, "Рис. 6. Матрица ошибок baseline (A)"),
  ...img(R.D2 ? D.images.confusion_D2 : D.images.confusion_D, 280, "Рис. 7. Матрица ошибок итогового варианта"),
  H2("Качество по категориям сценариев"),
  table([["Категория", ...VK.map((k) => `${k}: P@5 / NDCG@5`)],
    ...D.per_category.map((r) => [catRu[r.category] || r.category, ...VK.map((k) => r[`${k}_P@5`] !== undefined && r[`${k}_P@5`] !== "" ? `${String(r[`${k}_P@5`]).replace(".", ",")} / ${String(r[`${k}_NDCG@5`]).replace(".", ",")}` : "—")])],
    [2200, ...VK.map(() => Math.floor((W - 2200) / VK.length))], { size: 17, boldFirstCol: true }),
  H2("Разбор ошибок поштучно"),
  P(an.intro || ""),
  ...(errRows.length ? [table([["ID", "Запрос", "Эталон", "Ответ модели", "Тип ошибки", "Причина", "Исправление", "Повторная проверка"], ...errRows],
    [600, 1500, 1200, 1250, 1100, 1450, 1350, 1188], { size: 15 })] : [P("[разбор ошибок будет добавлен после прогона]", { italics: true })]),
  P(""),
  ...(an.summary_types ? [table([["Тип ошибки", "Сколько", "Что с этим делаем"], ...an.summary_types.map((t) => [t.type, t.count, t.action])], [3000, 1300, W - 4300])] : []),
  H2("Правило отказа: до и после"),
  P(an.refusal || ""),
  H2("Итог замера"),
  P(an.conclusion || ""),
];

// ---------- 4. Стоимость
const C = D.cost;
const s4 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 4. Стоимость эксплуатации"),
  P(`Длина запроса измерена счётчиком токенов провайдера (поле usage), а не на глаз: промпт сайта (few-shot) — в среднем ${num(C.tokens_in)} входных и ${num(C.tokens_out)} выходных токенов, включая токены рассуждений. Тариф Groq для openai/gpt-oss-20b — $0,075 за 1 млн входных и $0,30 за 1 млн выходных токенов (https://console.groq.com/docs/models, проверено 24.11.2026). Курс — ${String(C.usd_kzt).replace(".", ",")} ₸ за $1 (Национальный банк РК, 24.11.2026).`),
  P("Стоимость API в месяц = входные токены за месяц / 1 000 000 × тариф входа + выходные токены за месяц / 1 000 000 × тариф выхода.", { italics: true }),
  table([
    ["Показатель", "Текущий поток (прогноз)", "Рост в 10 раз", "Как считали"],
    ["Запросов в месяц", num(C.requests_month[0]), num(C.requests_month[1]), "30 сессий подбора в день × 1,5 запроса × 30 дней (допущение: истории нет)"],
    ["Входных токенов в месяц", num(C.tokens_in_month[0]), num(C.tokens_in_month[1]), `запросы × ${num(C.tokens_in)}`],
    ["Выходных токенов в месяц", num(C.tokens_out_month[0]), num(C.tokens_out_month[1]), `запросы × ${num(C.tokens_out)}`],
    ["Стоимость одного запроса", "$" + C.per_request_usd.toFixed(6), "$" + C.per_request_usd.toFixed(6), "вход/1e6 × 0,075 + выход/1e6 × 0,30"],
    ["Стоимость в месяц", `$${f2(C.month_usd[0])} ≈ ${num(C.month_kzt[0])} ₸`, `$${f2(C.month_usd[1])} ≈ ${num(C.month_kzt[1])} ₸`, "по формуле выше"],
    ["Стоимость в год", `$${f2(C.year_usd[0])} ≈ ${num(C.year_kzt[0])} ₸`, `$${f2(C.year_usd[1])} ≈ ${num(C.year_kzt[1])} ₸`, "× 12"],
    ["Укладывается в бесплатный тариф Groq", C.free_tier_ok[0], C.free_tier_ok[1], "лимиты: 1 000 запросов и 200 000 токенов в сутки, 8 000 токенов в минуту"],
  ], [2300, 2000, 2000, W - 6300], { boldFirstCol: true, size: 18 }),
  P(""),
  P([B("Бесплатный тариф на практике. "), "Во время замера суточный лимит в 200 000 токенов был исчерпан на 31-м сценарии; оставшиеся 5 сценариев пришлось дозапускать с паузами до обновления лимита. Запросы запросы сайта, сделанные параллельно с прогоном, получали ошибку 429 по лимиту 8 000 токенов в минуту. Один подбор тратит около 3 700 токенов, значит, бесплатный тариф выдерживает примерно 50 подборов в сутки и 2 в минуту. Для учебной демонстрации этого достаточно; для реальной нагрузки нужен платный тариф — по цене он копеечный (см. таблицу)."]),
  H2("Сравнение вариантов размещения"),
  table([
    ["Вариант", "Стоимость в месяц", "Вывод"],
    ["Облачный API (Groq) + текущая инфраструктура", `$${f2(C.month_usd[0])} за API + $${f2(C.infra_current_usd)} за Render Starter, Render Postgres и Vercel Hobby`, "Дешевле всех. Минус: анкета и текст чата уходят внешнему провайдеру за пределы РК"],
    ["Открытая 7B-модель на CPU-сервере (Hetzner CPX42, 8 vCPU, 16 ГБ)", `≈ $${f2(C.cpu_server_usd)} с сопровождением`, `Точка безубыточности — ${num(C.breakeven_cpu)} запросов в месяц, в ${num(C.times_cpu)} раз больше прогноза. Сервер успевает обработать лишь ≈ ${num(C.cpu_capacity)} запросов в месяц (оценка) — до точки перелома не дотягивает: ${C.cpu_can_reach}`],
    ["Открытая модель на GPU-сервере (Hetzner GEX45, 24 ГБ VRAM)", `≈ $${f2(C.gpu_server_usd)} с сопровождением + €209 разово`, `Точка безубыточности — ${num(C.breakeven_gpu)} запросов в месяц, в ${num(C.times_gpu)} раз больше прогноза. Для PetHome недостижимо`],
    ["Модель прямо на Render", "—", "Невозможно: у Render Free и Starter 512 МБ ОЗУ, а 7B-модели нужно около 5 ГБ"],
  ], [3000, 2500, W - 5500], { boldFirstCol: true, size: 18 }),
  P("Точка безубыточности = ежемесячная стоимость своего сервера / стоимость одного запроса к API (переменные затраты своего сервера ≈ 0: электричество и износ входят в аренду).", { italics: true, size: 18 }),
  ...img(D.images.cost_chart, 520, "Рис. 8. Стоимость API и собственного сервера при разной нагрузке"),
  P([B("Главный вывод части. "), "На объёме PetHome стоимость инференса пренебрежимо мала — около 210 ₸ в месяц. Спор «свой сервер или API» — не про деньги, а про то, какие данные уходят наружу. Свой сервер имеет смысл только если передача анкеты внешнему провайдеру окажется недопустимой — и тогда решение принимается вопреки цене."]),
];

// ---------- 5. Риски
const s5 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 5. Карточка рисков ИИ-функции"),
  table(mdTable(md("05-risk-card.md")), [2600, W - 2600], { boldFirstCol: true, firstColShade: true, size: 18 }),
  P(""),
  ...img(D.images.screen_handoff, 430, "Рис. 9. Отказ от небезопасной рекомендации и передача вопроса сотруднику (проверочный запуск интерфейса)"),
];

// ---------- 6. ADR
const s6 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 6. ADR-002. Включаем ли интеллектуальный подбор"),
  table(mdTable(md("06-adr-002.md")), [2600, W - 2600], { boldFirstCol: true, firstColShade: true, size: 18 }),
];

// ---------- 7. Самопроверка
const sc = md("07-self-check.md");
const s7 = [
  new Paragraph({ children: [new PageBreak()] }),
  H1("Часть 7. Самопроверка перед сдачей"),
  table(mdTable(sc, "Типичная ошибка"), [3300, W - 3300], { boldFirstCol: true, size: 18 }),
  H2("Выполнение 15 заданий методички"),
  table(mdTable(sc, "№ | Задание"), [500, 3000, 1300, W - 4800], { size: 17 }),
];

const doc = new Document({
  creator: "PetHome",
  title: "ЛЗ 12. План ИИ-функции PetHome",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: "3B2A8A" }, paragraph: { spacing: { before: 240, after: 160 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "4B3FB5" }, paragraph: { spacing: { before: 220, after: 120 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: ["PetHome · ЛЗ 12 · стр. ", PageNumber.CURRENT], font: FONT, size: 16, color: "888888" })] })] }) },
    children: [
      P("ЛЗ 12. План ИИ-функции: evals, стоимость, риски", { size: 36, bold: true, color: "3B2A8A", after: 80 }),
      P("Интеллектуальная рекомендательная система подбора домашних животных — PetHome", { size: 24, after: 60 }),
      P(`Команда: Fariza, Amina · Управление ИТ-проектами · ${new Date().toLocaleDateString("ru-RU")}`, { size: 20, color: "666666", after: 240 }),
      ...s0, ...s1, ...s2, ...s3, ...s4, ...s5, ...s6, ...s7,
    ],
  }],
});
const out = path.join(ROOT, "docs/lab12/ЛЗ_12_PetHome_План_ИИ_функции.docx");
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(out, b); console.log(out); });
