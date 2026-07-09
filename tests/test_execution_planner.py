# execution_planner.plan_execution() 의 project별 순서·공급자 매핑·스키마 준수를 검증하는 테스트
"""Execution Planner 단위 테스트. 입력은 Orchestrator 결합 JSON. 계획은 스키마로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

from execution_planner import plan_execution  # noqa: E402
from orchestrator import orchestrate  # noqa: E402  (Sprint 4, 읽기 전용)

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "execution_plan_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _plan(request, topic=None):
    return plan_execution(orchestrate(request, topic=topic))


def _steps(plan):
    return [s["step"] for s in plan["steps"]]


def _assert_valid(plan):
    errs = sorted(_VALIDATOR.iter_errors(plan), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _assert_order_sequential(plan):
    orders = [s["order"] for s in plan["steps"]]
    assert orders == list(range(1, len(orders) + 1)), f"order 비연속: {orders}"


# --- 필수 카테고리 5종 ---

def test_malli_plan():
    plan = _plan("말리가 달님을 만난 날", topic="달님")
    assert _steps(plan) == ["story", "image", "video", "voice", "thumbnail", "edit"]
    video = next(s for s in plan["steps"] if s["step"] == "video")
    assert video["provider"] == "Google Flow"
    assert video["backup"] == "Higgsfield"
    _assert_order_sequential(plan)
    _assert_valid(plan)


def test_baseball_plan():
    plan = _plan("보크 규칙 설명 영상", topic="보크")
    assert _steps(plan) == ["script", "image", "video", "voice", "thumbnail", "edit"]
    video = next(s for s in plan["steps"] if s["step"] == "video")
    assert video["provider"] == "Higgsfield"
    assert video["backup"] == "Google Flow"
    edit = next(s for s in plan["steps"] if s["step"] == "edit")
    assert edit["provider"] == "FFmpeg"
    _assert_order_sequential(plan)
    _assert_valid(plan)


def test_thumbnail_plan():
    plan = _plan("건강검진 대상자 조회 썸네일", topic="건강검진")
    assert _steps(plan) == ["image", "thumbnail"]
    img = next(s for s in plan["steps"] if s["step"] == "image")
    assert img["provider"] == "Nano Banana"
    _assert_order_sequential(plan)
    _assert_valid(plan)


def test_blog_plan():
    plan = _plan("국민연금 블로그 작성", topic="국민연금")
    assert _steps(plan) == ["outline", "article", "thumbnail"]
    _assert_order_sequential(plan)
    _assert_valid(plan)


def test_unknown_plan():
    plan = _plan("unknown input")
    assert plan["steps"] == []
    _assert_valid(plan)


# --- 계약/매핑/안전성 ---

def test_malli_uses_story_baseball_uses_script():
    assert _steps(_plan("말리 동화", topic="달님"))[0] == "story"
    assert _steps(_plan("보크 규칙 영상", topic="보크"))[0] == "script"


def test_prompt_keys_referenced():
    plan = _plan("말리 동화", topic="달님")
    by_step = {s["step"]: s for s in plan["steps"]}
    assert by_step["story"]["prompt_key"] == "story_prompt"
    assert by_step["image"]["prompt_key"] == "image_prompt"
    assert by_step["video"]["prompt_key"] == "video_prompt"
    assert by_step["voice"]["prompt_key"] == "voice_prompt"
    assert by_step["thumbnail"]["prompt_key"] == "thumbnail_prompt"


def test_all_categories_schema():
    for req in ["말리 동화", "보크 규칙 영상", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _assert_valid(_plan(req))


def test_no_execution_markers():
    plan = _plan("보크 규칙 영상", topic="보크")
    banned = {"status", "result", "url", "job_id", "output_path", "rendered", "media"}
    for s in plan["steps"]:
        assert banned.isdisjoint(set(s.keys()))


def test_input_not_mutated():
    combined = orchestrate("보크 규칙 영상", topic="보크")
    before = json.dumps(combined, ensure_ascii=False, sort_keys=True)
    plan_execution(combined)
    after = json.dumps(combined, ensure_ascii=False, sort_keys=True)
    assert before == after, "입력이 변형됨"


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, {"project": "malli"}]:
        try:
            plan_execution(bad)
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
