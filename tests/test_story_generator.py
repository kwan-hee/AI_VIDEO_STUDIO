# story_generator.generate_story 의 mock 스토리 생성·구조·실 opt-in graceful fail·스키마 준수를 확인하는 테스트
"""Story Generator 단위 테스트. 스토리 패키지는 schemas/story_schema.json 으로 검증. 실 Claude 미호출."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "story"))

from story_generator import generate_story, _REAL_ENV  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "story_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid_story(story):
    errs = sorted(_VALIDATOR.iter_errors(story), key=str)
    assert not errs, "스토리 스키마 위반: " + "; ".join(e.message for e in errs)


# --- mock 생성 ---

def test_mock_generate_success():
    r = generate_story("말리가 달님을 만난 날")
    assert r["status"] == "success"
    assert r["mock"] is True
    story = r["story"]
    assert story["title"] == "말리가 달님을 만난 날"
    assert isinstance(story["summary"], str) and story["summary"]
    assert isinstance(story["moral"], str)
    assert len(story["scenes"]) == 3       # 기본 장면 수
    _assert_valid_story(story)


def test_scene_structure():
    r = generate_story("테스트 이야기", num_scenes=2)
    scenes = r["story"]["scenes"]
    assert len(scenes) == 2
    for i, sc in enumerate(scenes, start=1):
        assert sc["scene_number"] == i
        assert sc["narration"]
        assert sc["image_prompt"]
        assert sc["video_prompt"]
        assert sc["duration"] > 0


def test_title_override():
    r = generate_story("요청 텍스트", title="명시 제목")
    assert r["story"]["title"] == "명시 제목"


def test_topic_used_in_prompts():
    r = generate_story("아무거나", title="달토끼", topic="달토끼 우주 모험")
    assert "달토끼 우주 모험" in r["story"]["scenes"][0]["image_prompt"]


# --- 주입 generator (실 백엔드 대체) ---

def test_injected_generator_marks_not_mock():
    def custom(title, topic, num_scenes):
        return {
            "title": title, "summary": "커스텀", "moral": "교훈",
            "scenes": [{"scene_number": 1, "narration": "n", "image_prompt": "i",
                        "video_prompt": "v", "duration": 4.0}],
        }
    r = generate_story("x", generator=custom)
    assert r["status"] == "success"
    assert r["mock"] is False
    assert r["story"]["summary"] == "커스텀"
    _assert_valid_story(r["story"])


def test_injected_generator_invalid_output_fails():
    def bad(title, topic, num_scenes):
        return {"title": title}   # scenes 등 누락
    r = generate_story("x", generator=bad)
    assert r["status"] == "failed"
    assert r["story"] is None


# --- 실 Claude opt-in: 백엔드 없으면 graceful fail ---

def test_real_param_optin_fails_gracefully():
    r = generate_story("말리 이야기", real=True)   # 명시 옵트인, 백엔드 미설치
    assert r["status"] == "failed"
    assert r["story"] is None
    assert "실패" in r["message"]


def test_real_env_flag_respected():
    prev = os.environ.get(_REAL_ENV)
    os.environ[_REAL_ENV] = "1"
    try:
        r = generate_story("말리 이야기")   # 환경변수 옵트인 → 실 경로(백엔드 없어 실패)
        assert r["status"] == "failed"
    finally:
        if prev is None:
            os.environ.pop(_REAL_ENV, None)
        else:
            os.environ[_REAL_ENV] = prev


def test_env_unset_stays_mock():
    prev = os.environ.pop(_REAL_ENV, None)
    try:
        r = generate_story("말리 이야기")
        assert r["status"] == "success"
        assert r["mock"] is True
    finally:
        if prev is not None:
            os.environ[_REAL_ENV] = prev


# --- 검증 ---

def test_empty_request_rejected():
    for bad in ["", "   "]:
        try:
            generate_story(bad)
        except ValueError:
            continue
        raise AssertionError(f"빈 요청이 거부되지 않음: {bad!r}")


def test_bad_num_scenes_rejected():
    for bad in (0, -1):
        try:
            generate_story("x", num_scenes=bad)
        except ValueError:
            continue
        raise AssertionError(f"잘못된 num_scenes 가 거부되지 않음: {bad}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
