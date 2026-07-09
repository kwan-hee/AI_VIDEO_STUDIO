# orchestrator.orchestrate() 의 3단계 결합·일관성·결합 스키마 준수를 검증하는 통합 테스트
"""Orchestrator 통합 테스트. 결합 출력은 schemas/orchestration_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

from orchestrator import orchestrate  # noqa: E402
from task_analyzer import analyze_task  # noqa: E402
from provider_selector import select_providers  # noqa: E402
from prompt_generator import generate_prompts  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "orchestration_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

TOP_KEYS = {"request", "project", "needs_clarification",
            "task_analysis", "provider_recommendation", "prompts"}
PROMPT_KEYS = {"story_prompt", "image_prompt", "video_prompt", "voice_prompt", "thumbnail_prompt"}


def _assert_valid(out):
    errs = sorted(_VALIDATOR.iter_errors(out), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 통합: 5개 카테고리 전 구간 ---

def test_integration_five_categories_schema():
    cases = {
        "말리가 달님을 만난 날": "malli",
        "보크 규칙 설명 영상": "baseball",
        "건강검진 대상자 조회 썸네일": "thumbnail",
        "국민연금 블로그 작성": "blog",
        "unknown input": "unknown",
    }
    for req, proj in cases.items():
        out = orchestrate(req)
        assert out["project"] == proj
        assert set(out.keys()) == TOP_KEYS
        assert set(out["prompts"].keys()) == PROMPT_KEYS
        _assert_valid(out)  # 결합 스키마 검증


def test_combined_shape():
    out = orchestrate("보크 규칙 설명 영상", topic="보크")
    assert set(out.keys()) == TOP_KEYS
    assert out["project"] == "baseball"
    _assert_valid(out)
    json.dumps(out)


def test_matches_manual_chain():
    # orchestrate 결과 == 단계별 수동 호출 (순수 파이프 증명)
    req, topic = "말리가 달님을 만난 날", "달님"
    ta = analyze_task(req)
    pr = select_providers(ta)
    ps = generate_prompts(ta, pr, topic=topic)
    out = orchestrate(req, topic=topic)
    assert out["task_analysis"] == ta
    assert out["provider_recommendation"] == pr
    assert out["prompts"] == ps["prompts"]


def test_integration_baseball_providers_and_prompts():
    out = orchestrate("보크 규칙 설명 영상", topic="보크")
    pv = out["provider_recommendation"]["providers"]
    assert pv["video"] == {"primary": "Higgsfield", "backup": "Google Flow"}
    assert out["prompts"]["video_prompt"]["provider"] == "Higgsfield"
    assert out["prompts"]["voice_prompt"]["provider"] == "Edge TTS"


def test_unknown_flags_clarification():
    out = orchestrate("unknown input")
    assert out["needs_clarification"] is True
    assert all(v is None for v in out["prompts"].values())
    assert all(v is None for v in out["provider_recommendation"]["providers"].values())
    _assert_valid(out)


def test_topic_defaults_to_request():
    out = orchestrate("보크 규칙 영상")
    assert "보크 규칙 영상" in out["prompts"]["image_prompt"]["text"]


def test_no_execution_markers():
    out = orchestrate("보크 규칙 설명 영상", topic="보크")
    banned = {"status", "result", "url", "job_id", "output_path", "rendered", "media_url"}
    assert banned.isdisjoint(set(out.keys()))


def test_bad_input_rejected():
    for bad in ["", "   ", None, 5, []]:
        try:
            orchestrate(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
