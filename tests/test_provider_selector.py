# provider_selector.select_providers() 의 능력별 공급자 추천과 스키마 준수를 검증하는 테스트
"""Provider Selector 단위 테스트. 표준 라이브러리만 사용."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "selector"))
sys.path.insert(0, os.path.join(_ROOT, "analyzer"))

from provider_selector import select_providers  # noqa: E402
from task_analyzer import analyze_task  # noqa: E402  (Sprint 1, 읽기 전용 통합용)

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)


def _validate(obj):
    """schemas/provider_schema.json 대비 최소 검증. jsonschema 의존 없음."""
    props = SCHEMA["properties"]
    for key in SCHEMA["required"]:
        assert key in obj, f"필수 키 누락: {key}"
    for key in obj:
        assert key in props, f"스키마 밖 키: {key}"

    assert obj["project"] in props["project"]["enum"]

    pv = obj["providers"]
    pprops = props["providers"]["properties"]
    for key in props["providers"]["required"]:
        assert key in pv, f"providers 필수 키 누락: {key}"
    for key in pv:
        assert key in pprops, f"providers 스키마 밖 키: {key}"

    assert pv["image"] in [None, "Nano Banana"]
    assert pv["voice"] in [None, "Edge TTS"]
    assert pv["editing"] in [None, "FFmpeg"]

    if pv["video"] is not None:
        assert set(pv["video"].keys()) == {"primary", "backup"}
        assert pv["video"]["primary"] in ["Google Flow", "Higgsfield"]
        assert pv["video"]["backup"] in ["Google Flow", "Higgsfield"]

    ie = pv["image_enhancement"]
    if ie is not None:
        assert set(ie.keys()) == {"provider", "targets"}
        assert ie["provider"] == "Magnific"
        allowed = {"thumbnail", "first_scene", "last_scene", "opening_scene"}
        for t in ie["targets"]:
            assert t in allowed, f"허용되지 않은 Magnific 지점: {t}"

    json.dumps(obj)  # 유효 JSON


def _ta(project, tasks, needs=False):
    return {
        "project": project,
        "content_type": "x",
        "required_tasks": tasks,
        "needs_clarification": needs,
    }


VIDEO_TASKS = ["image_generation", "video_generation", "voice_generation",
               "subtitle_generation", "composition"]


def test_malli_full_policy():
    r = select_providers(_ta("malli", VIDEO_TASKS))
    p = r["providers"]
    assert p["image"] == "Nano Banana"
    assert p["video"] == {"primary": "Google Flow", "backup": "Higgsfield"}
    assert p["voice"] == "Edge TTS"
    assert p["editing"] == "FFmpeg"
    assert p["image_enhancement"] == {
        "provider": "Magnific",
        "targets": ["thumbnail", "first_scene", "last_scene"],
    }


def test_baseball_full_policy():
    r = select_providers(_ta("baseball", VIDEO_TASKS))
    p = r["providers"]
    assert p["video"] == {"primary": "Higgsfield", "backup": "Google Flow"}
    assert p["image_enhancement"] == {
        "provider": "Magnific",
        "targets": ["thumbnail", "opening_scene"],
    }


def test_thumbnail_enhancement_only_thumbnail():
    r = select_providers(_ta("thumbnail", ["image_generation", "quality_enhancement"]))
    p = r["providers"]
    assert p["image"] == "Nano Banana"
    assert p["video"] is None
    assert p["voice"] is None
    assert p["editing"] is None
    assert p["image_enhancement"] == {"provider": "Magnific", "targets": ["thumbnail"]}


def test_blog_no_providers():
    r = select_providers(_ta("blog", ["text_writing"]))
    assert r["providers"] == {
        "image": None, "video": None, "voice": None,
        "editing": None, "image_enhancement": None,
    }


def test_unknown_no_providers():
    r = select_providers(_ta("unknown", [], needs=True))
    assert all(v is None for v in r["providers"].values())


def test_all_outputs_match_schema():
    for ta in [
        _ta("malli", VIDEO_TASKS),
        _ta("baseball", VIDEO_TASKS),
        _ta("thumbnail", ["image_generation", "quality_enhancement"]),
        _ta("blog", ["text_writing"]),
        _ta("unknown", [], needs=True),
    ]:
        _validate(select_providers(ta))


def test_integration_from_sprint1():
    # Sprint 1 출력을 그대로 Sprint 2 입력으로 연결 (통합)
    cases = {
        "보크 규칙 설명 영상": ("baseball", {"primary": "Higgsfield", "backup": "Google Flow"}),
        "말리가 달님을 만난 날": ("malli", {"primary": "Google Flow", "backup": "Higgsfield"}),
        "건강검진 대상자 조회 썸네일": ("thumbnail", None),
        "국민연금 블로그 작성": ("blog", None),
        "unknown input": ("unknown", None),
    }
    for req, (proj, video) in cases.items():
        ta = analyze_task(req)
        r = select_providers(ta)
        assert r["project"] == proj
        assert r["providers"]["video"] == video
        _validate(r)


def test_recommend_only_input_not_mutated():
    ta = _ta("baseball", VIDEO_TASKS)
    before = json.dumps(ta, ensure_ascii=False, sort_keys=True)
    select_providers(ta)
    after = json.dumps(ta, ensure_ascii=False, sort_keys=True)
    assert before == after, "입력이 변형됨"


def test_no_provider_execution_markers():
    # 반환은 순수 데이터여야 한다. 호출/실행 흔적 키가 없어야 한다.
    r = select_providers(_ta("malli", VIDEO_TASKS))
    banned = {"status", "result", "url", "job_id", "output_path", "rendered"}
    assert banned.isdisjoint(set(str(k) for k in r.keys()))


def test_bad_input_rejected():
    for bad in [None, [], "x", {"project": "baseball"}, {"required_tasks": []}]:
        try:
            select_providers(bad)
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
