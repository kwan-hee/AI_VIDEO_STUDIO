# prompt_generator.generate_prompts() 의 프롬프트 생성과 스키마 준수를 검증하는 테스트
"""Prompt Generator 단위 테스트. 표준 라이브러리만 사용."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "generator"))
sys.path.insert(0, os.path.join(_ROOT, "selector"))
sys.path.insert(0, os.path.join(_ROOT, "analyzer"))

from prompt_generator import generate_prompts  # noqa: E402
from provider_selector import select_providers  # noqa: E402  (Sprint 2, 읽기 전용)
from task_analyzer import analyze_task  # noqa: E402  (Sprint 1, 읽기 전용)

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "prompt_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)

PROMPT_KEYS = ["story_prompt", "image_prompt", "video_prompt", "voice_prompt", "thumbnail_prompt"]
ALLOWED_PROVIDERS = {"Nano Banana", "Google Flow", "Higgsfield", "Edge TTS", None}


def _validate(obj):
    """schemas/prompt_schema.json 대비 최소 검증. jsonschema 의존 없음."""
    assert set(obj.keys()) == {"project", "prompts"}
    assert obj["project"] in SCHEMA["properties"]["project"]["enum"]
    prompts = obj["prompts"]
    assert set(prompts.keys()) == set(PROMPT_KEYS)
    for k, v in prompts.items():
        if v is None:
            continue
        assert set(v.keys()) == {"provider", "text"}, f"{k} 키 불일치"
        assert v["provider"] in ALLOWED_PROVIDERS, f"{k} 공급자 위반: {v['provider']}"
        assert isinstance(v["text"], str) and len(v["text"]) >= 1
    json.dumps(obj)  # 유효 JSON


def _pipeline(request, topic=None):
    ta = analyze_task(request)
    pr = select_providers(ta)
    return generate_prompts(ta, pr, topic=topic)


# --- 5개 카테고리 ---

def test_malli_story():
    out = _pipeline("말리가 달님을 만난 날", topic="말리와 달님")
    p = out["prompts"]
    assert p["story_prompt"] is not None and p["story_prompt"]["provider"] is None
    assert "말리" in p["story_prompt"]["text"]
    assert p["image_prompt"]["provider"] == "Nano Banana"
    assert p["video_prompt"]["provider"] == "Google Flow"
    assert p["voice_prompt"]["provider"] == "Edge TTS"
    assert p["thumbnail_prompt"] is not None
    _validate(out)


def test_baseball_dictionary():
    out = _pipeline("보크 규칙 설명 영상", topic="보크")
    p = out["prompts"]
    assert p["story_prompt"] is not None
    assert p["video_prompt"]["provider"] == "Higgsfield"
    assert "보크" in p["story_prompt"]["text"]
    assert p["thumbnail_prompt"]["provider"] == "Nano Banana"
    _validate(out)


def test_thumbnail():
    out = _pipeline("건강검진 대상자 조회 썸네일", topic="건강검진 조회")
    p = out["prompts"]
    assert p["thumbnail_prompt"] is not None
    assert p["image_prompt"] is not None
    assert p["story_prompt"] is None
    assert p["video_prompt"] is None
    assert p["voice_prompt"] is None
    _validate(out)


def test_blog():
    out = _pipeline("국민연금 블로그 작성", topic="국민연금")
    # blog 은 미디어 프롬프트 대상 아님 → 모두 null
    assert all(v is None for v in out["prompts"].values())
    _validate(out)


def test_unknown():
    out = _pipeline("unknown input")
    assert all(v is None for v in out["prompts"].values())
    _validate(out)


# --- 계약/안전성 ---

def test_all_categories_schema():
    for req in ["말리 동화", "보크 규칙 영상", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _validate(_pipeline(req))


def test_topic_injected():
    out = _pipeline("보크 규칙 영상", topic="인필드 플라이")
    assert "인필드 플라이" in out["prompts"]["image_prompt"]["text"]


def test_placeholder_when_no_topic():
    out = _pipeline("보크 규칙 영상")
    assert "{subject}" in out["prompts"]["image_prompt"]["text"]


def test_video_backup_mentioned():
    out = _pipeline("말리 동화", topic="달님")
    # 폴백 엔진이 프롬프트에 안내되어야 한다
    assert "Higgsfield" in out["prompts"]["video_prompt"]["text"]


def test_no_execution_markers():
    out = _pipeline("보크 규칙 영상", topic="보크")
    banned = {"status", "result", "url", "job_id", "output_path", "rendered", "media"}
    blob_keys = set()
    for v in out["prompts"].values():
        if v:
            blob_keys |= set(v.keys())
    assert banned.isdisjoint(blob_keys)


def test_inputs_not_mutated():
    ta = analyze_task("보크 규칙 영상")
    pr = select_providers(ta)
    before = json.dumps([ta, pr], ensure_ascii=False, sort_keys=True)
    generate_prompts(ta, pr, topic="보크")
    after = json.dumps([ta, pr], ensure_ascii=False, sort_keys=True)
    assert before == after, "입력이 변형됨"


def test_project_mismatch_rejected():
    ta = analyze_task("보크 규칙 영상")           # baseball
    pr = select_providers(analyze_task("말리 동화"))  # malli
    try:
        generate_prompts(ta, pr)
    except ValueError:
        return
    raise AssertionError("project 불일치가 거부되지 않음")


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}]:
        try:
            generate_prompts(bad, bad)
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
