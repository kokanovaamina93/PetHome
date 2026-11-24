"""Эксперимент ЛЗ 12: варианты A (правила), B (zero-shot), C (few-shot), D (few-shot + отказ).

    export AI_API_KEY=...            # ключ Groq (или положите в backend/.env строку AI_API_KEY=...)
    python evals/run_experiment.py   # -> evals/raw/<run_id>/  (сырые ответы, промпты, параметры, токены, ошибки)
    python evals/score.py            # -> evals/results/  (метрики, графики, ошибки) — нужен evals/gold.jsonl

Все варианты получают одни и те же сценарии и одну версию каталога (хэш data/animals.json пишется в meta).
D не делает отдельного запроса: это ответ C + детерминированная проверка ограничений и правило отказа.
"""

import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
env = Path(os.environ.get("PETHOME_ENV_FILE", ROOT / "backend/.env")).expanduser()
if env.exists():  # ключ кладёт сам пользователь; в git .env не попадает
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

import recommender as R  # noqa: E402
import seed_animals  # noqa: E402

catalog = {a["id"]: a for a in seed_animals.catalog()}
scenarios = [json.loads(s) for s in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")]
if "--limit" in sys.argv:
    scenarios = scenarios[: int(sys.argv[sys.argv.index("--limit") + 1])]

RESUME = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None
run_id = RESUME or datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_" + R.AI_MODEL.replace("/", "_").replace(":", "-")
out = ROOT / "evals/raw" / run_id
out.mkdir(parents=True, exist_ok=bool(RESUME))
done = set()
if RESUME:  # продолжение прерванного прогона: сценарии, уже записанные в D, пропускаем
    done = {json.loads(x)["id"] for x in open(out / "D.jsonl", encoding="utf-8")}
    for v in "ABC":  # обрезаем недописанный хвост
        rows = [x for x in open(out / f"{v}.jsonl", encoding="utf-8") if json.loads(x)["id"] in done]
        (out / f"{v}.jsonl").write_text("".join(rows), encoding="utf-8")
meta = {
    "run_id": run_id,
    "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "provider_base_url": R.AI_BASE_URL,
    "model": R.AI_MODEL,
    "prompt_version": R.PROMPT_VERSION,
    "params": {
        "temperature": 0,
        "seed": 42,
        "max_tokens": 2500,
        "response_format": "json_object",
        **({"reasoning_effort": "low"} if "gpt-oss" in R.AI_MODEL else {}),
    },
    "determinism_note": "seed поддерживается провайдером в режиме best effort; детерминированность не гарантируется",
    "catalog_version": seed_animals.catalog_version(),
    "n_scenarios": len(scenarios),
    "python": platform.python_version(),
    "git_commit": __import__("subprocess").run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                              text=True).stdout.strip(),
}
prev = json.loads((out / "meta.json").read_text(encoding="utf-8")) if RESUME and (out / "meta.json").exists() else {}
if prev:
    meta["started_utc"] = prev["started_utc"]
    meta["resumed_utc"] = prev.get("resumed_utc", []) + [datetime.now(timezone.utc).isoformat(timespec="seconds")]
    if prev["catalog_version"] != meta["catalog_version"] or prev["prompt_version"] != meta["prompt_version"]:
        sys.exit("Каталог или промпт изменились — продолжать этот прогон нельзя")
(out / "prompts").mkdir(exist_ok=True)
(out / "prompts/system.txt").write_text(R.SYSTEM, encoding="utf-8")
(out / "prompts/few_shot.json").write_text(json.dumps(R.FEW_SHOT, ensure_ascii=False, indent=1), encoding="utf-8")

files = {v: open(out / f"{v}.jsonl", "a" if RESUME else "w", encoding="utf-8", buffering=1) for v in "ABCD"}
errors = prev.get("api_errors", [])
TPM = float(os.environ.get("EVAL_TPM", "7000"))  # лимит бесплатного тарифа Groq — 8000 токенов/мин, держим запас
stopped = False
for s in scenarios:
    if s["id"] in done:
        continue
    cands = [catalog[i] for i in s["candidates"]]
    a = R.baseline_recommend(s["profile"], cands, s["text"])
    files["A"].write(json.dumps({"id": s["id"], **a}, ensure_ascii=False) + "\n")
    for mode, v in (("zero", "B"), ("few", "C")):
        for attempt in range(5):
            try:
                r = R.llm_recommend(s["profile"], s["text"], cands, mode=mode)
                break
            except R.AIUnavailable as e:
                msg = str(e)[:400]
                errors.append({"id": s["id"], "variant": v, "attempt": attempt + 1, "error": msg,
                               "utc": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                if "429" in msg and ("per day" in msg or "TPD" in msg or "RPD" in msg):
                    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", msg)
                    wait = (int(m.group(1) or 0) * 60 + float(m.group(2))) if m else 1e9
                    if wait <= float(os.environ.get("EVAL_MAX_DAILY_WAIT", "600")):  # скользящее окно суток: подождать несколько минут дешевле, чем бросить прогон
                        print(f"суточный лимит, ждём {wait:.0f} с", flush=True)
                        time.sleep(wait + 5)
                        continue
                    stopped = True  # ждать долго: останавливаемся, продолжить можно с --resume
                    break
                time.sleep(20 * (attempt + 1))  # минутный лимит или сбой: ждём и повторяем
        else:
            r = {
                "variant": v,
                "action": "error",
                "pairs": [],
                "top": [],
                "raw": "",
                "usage": {},
                "latency_s": None,
                "error": errors[-1]["error"],
            }
        if stopped:
            break
        files[v].write(json.dumps({"id": s["id"], **r}, ensure_ascii=False) + "\n")
        if v == "C":
            d = R.apply_refusal(r, s["profile"], s["text"], cands) if r["action"] != "error" else {**r, "variant": "D"}
            files["D"].write(json.dumps({"id": s["id"], **d}, ensure_ascii=False) + "\n")
        print(f"{s['id']} {v}: {r['action']:14} top={r['top']} {r.get('latency_s')}s", flush=True)
        used = (r.get("usage") or {}).get("total_tokens", 0) or 0
        time.sleep(max(2.5, used / TPM * 60))  # пауза по фактическим токенам: не превышаем лимит в минуту
    if stopped:
        print("Суточный лимит Groq исчерпан. Продолжить: python evals/run_experiment.py --resume", run_id)
        break
for f in files.values():
    f.close()
meta["finished_utc"] = None if stopped else datetime.now(timezone.utc).isoformat(timespec="seconds")
meta["complete"] = not stopped
meta["api_errors"] = errors
(out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
(ROOT / "evals/raw/LATEST").write_text(run_id)
print("готово:", out, "ошибок API:", len(errors))
