"""Закрывает незавершённый прогон по правилу из METRICS.md: сценарии, для которых модель не ответила
(суточный лимит бесплатного тарифа Groq), записываются для B, C, D как action=error — все их пары считаются
«нет ответа». Вариант A (правила, без API) досчитывается для всех сценариев.
    python evals/finalize_partial.py [run_id]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import recommender as R  # noqa: E402
import seed_animals  # noqa: E402

run = sys.argv[1] if len(sys.argv) > 1 else (ROOT / "evals/raw/LATEST").read_text().strip()
raw = ROOT / "evals/raw" / run
cat = {a["id"]: a for a in seed_animals.catalog()}
scen = [json.loads(x) for x in open(ROOT / "evals/scenarios.jsonl", encoding="utf-8")]
done = [json.loads(x)["id"] for x in open(raw / "D.jsonl", encoding="utf-8")]
note = "не выполнено: исчерпан суточный лимит бесплатного тарифа Groq (200 000 токенов), прогон закрыт 25.11.2026"
for v in "ABCD":
    rows = {}
    for x in open(raw / f"{v}.jsonl", encoding="utf-8"):
        r = json.loads(x)
        if r["id"] in done:
            rows[r["id"]] = r
    with open(raw / f"{v}.jsonl", "w", encoding="utf-8") as f:
        for s in scen:
            if s["id"] in rows:
                r = rows[s["id"]]
            elif v == "A":
                r = {"id": s["id"], **R.baseline_recommend(s["profile"], [cat[i] for i in s["candidates"]], s["text"])}
            else:
                r = {"id": s["id"], "variant": v, "action": "error", "pairs": [], "top": [], "raw": "", "usage": {},
                     "latency_s": None, "error": note}
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
meta = json.loads((raw / "meta.json").read_text(encoding="utf-8"))
missing = [s["id"] for s in scen if s["id"] not in done]
meta.update(complete=False, finished_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            completed_scenarios=len(done), not_completed=missing, not_completed_reason=note)
(raw / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
print("выполнено:", len(done), "| не выполнено:", missing)
