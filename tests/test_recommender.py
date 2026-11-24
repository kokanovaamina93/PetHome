"""Проверки логики ИИ-подбора без обращения к сети."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import recommender as R  # noqa: E402
import seed_animals as S  # noqa: E402

CAT = {a["id"]: a for a in S.catalog()}


def test_catalog_has_animals():
    assert len(CAT) == 50


def test_hard_rule_wrong_type():
    label, why = R.classify_pair_rules({"preferred_type": "cat"}, CAT[8])  # 8 — собака
    assert label == "unsuitable" and why[0].startswith("R2")


def test_rule_r19_dog_low_time():
    label, why = R.classify_pair_rules({"preferred_type": "dog", "time_per_day": "low"}, CAT[8])
    assert label == "unsuitable" and any(w.startswith("R19") for w in why)


def test_text_facts_fill_profile():
    p = R.profile_with_text({}, "Живу в квартире, детей нет, других животных нет, работаю из дома, опыта нет")
    assert (p["housing"], p["kids"], p["other_pets"], p["time_per_day"], p["experience"]) == (
        "apartment", "none", "none", "high", "none")
    assert R.missing_required({}, "хочу питомца") == list(R.REQUIRED_FIELDS)


def test_refusal_incomplete_profile_gives_insufficient():
    cands = [CAT[33], CAT[34]]
    model = {"action": "recommend", "question": None, "top": [33, 34],
             "pairs": [{"animal_id": 33, "label": "suitable", "reason": ""}, {"animal_id": 34, "label": "suitable", "reason": ""}]}
    d = R.apply_refusal(model, {"preferred_type": "cat"}, "кошка", cands, version="refusal-v2")
    assert d["action"] == "clarify" and d["top"] == []
    assert all(p["label"] == "insufficient" for p in d["pairs"])


def test_refusal_removes_hard_violation():
    cands = [CAT[33], CAT[8]]
    model = {"action": "recommend", "question": None, "top": [8, 33],
             "pairs": [{"animal_id": 33, "label": "suitable", "reason": ""}, {"animal_id": 8, "label": "suitable", "reason": ""}]}
    prof = {"preferred_type": "cat", "housing": "apartment", "kids": "none", "other_pets": "none",
            "time_per_day": "medium", "experience": "some"}
    d = R.apply_refusal(model, prof, "", cands)
    assert 8 not in d["top"] and {p["animal_id"]: p["label"] for p in d["pairs"]}[8] == "unsuitable"


def test_pii_scrub():
    assert "[телефон]" in R.scrub_pii("звоните +7 700 123 45 67") and "[email]" in R.scrub_pii("a@b.kz")


def test_prompt_v1_preserved_and_v3_present():
    assert R.PROMPTS["reco-v1"][0] == R.SYSTEM and len(R.PROMPTS["reco-v3"][1]) == 3


def test_missing_key_is_not_configured():
    try:
        R.llm_recommend({}, "x", [CAT[33]], api_key="", base_url="https://api.groq.com/openai/v1")
    except R.AIUnavailable as e:
        assert e.kind == "not_configured"
    else:
        raise AssertionError("ожидалась ошибка not_configured")
