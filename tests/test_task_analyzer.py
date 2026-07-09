# task_analyzer.analyze_task() 의 project/content_type/task 판별과 스키마 준수를 검증하는 테스트
"""Task Analyzer 단위 테스트. 표준 라이브러리만 사용."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "analyzer"))

from task_analyzer import analyze_task  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "task_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)


def _validate(obj):
    """schemas/task_schema.json 대비 최소 검증. jsonschema 의존 없음."""
    props = SCHEMA["properties"]
    # 필수 키 존재
    for key in SCHEMA["required"]:
        assert key in obj, f"필수 키 누락: {key}"
    # 추가 키 금지
    for key in obj:
        assert key in props, f"스키마 밖 키: {key}"
    # 타입 및 enum
    assert obj["project"] in props["project"]["enum"]
    assert obj["content_type"] in props["content_type"]["enum"]
    assert isinstance(obj["required_tasks"], list)
    allowed = props["required_tasks"]["items"]["enum"]
    for t in obj["required_tasks"]:
        assert t in allowed, f"허용되지 않은 task: {t}"
    assert isinstance(obj["needs_clarification"], bool)
    # JSON 직렬화 가능
    json.dumps(obj)


def test_baseball_detected():
    r = analyze_task("인필드 플라이 규칙 영상 만들어줘")
    assert r["project"] == "baseball"
    assert r["content_type"] == "explainer_video"


def test_malli_detected():
    r = analyze_task("말리가 숲에서 친구를 만나는 동화")
    assert r["project"] == "malli"
    assert r["content_type"] == "story_video"


def test_thumbnail_precedence():
    r = analyze_task("야구백과 보크편 썸네일")
    assert r["project"] == "thumbnail"
    assert r["content_type"] == "thumbnail_image"


def test_blog_detected():
    r = analyze_task("한화 어제 경기 블로그 글 써줘")
    assert r["project"] == "blog"
    assert r["content_type"] == "blog_text"


def test_video_task_list():
    r = analyze_task("보크 규칙 영상")
    assert r["required_tasks"] == [
        "image_generation", "video_generation", "voice_generation",
        "subtitle_generation", "composition",
    ]


def test_blog_task_list():
    r = analyze_task("블로그 포스팅 써줘")
    assert r["required_tasks"] == ["text_writing"]


def test_unknown():
    r = analyze_task("뭔가 멋진 거 만들어줘")
    assert r["project"] == "unknown"
    assert r["content_type"] == "unknown"
    assert r["required_tasks"] == []
    assert r["needs_clarification"] is True


def test_no_provider_names_leak():
    # 공급자 이름이 출력에 절대 없어야 한다 (Provider 선택은 이 Sprint 범위 밖)
    banned = ["flow", "higgsfield", "nano", "magnific", "hedra", "whisper", "ffmpeg"]
    for req in ["보크 규칙 영상", "말리 동화", "썸네일", "블로그 글"]:
        blob = str(analyze_task(req)).lower()
        for name in banned:
            assert name not in blob, f"공급자 이름 노출: {name}"


def test_output_matches_schema():
    for req in ["보크 규칙 영상", "말리 동화", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _validate(analyze_task(req))


def test_sprint1_sample_inputs():
    # Sprint 1 리뷰용 예시 입력. project 판별 + 스키마 유효 + JSON 직렬화 확인.
    cases = [
        ("말리가 달님을 만난 날", "malli"),
        ("보크 규칙 설명 영상", "baseball"),
        ("건강검진 대상자 조회 썸네일", "thumbnail"),
        ("국민연금 블로그 작성", "blog"),
        ("unknown input", "unknown"),
    ]
    for req, expected_project in cases:
        r = analyze_task(req)
        assert r["project"] == expected_project, f"{req!r} → {r['project']} (기대 {expected_project})"
        _validate(r)
        json.dumps(r)  # 유효 JSON 직렬화


def test_empty_rejected():
    for bad in ["", "   ", None, 7]:
        try:
            analyze_task(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"빈/잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
