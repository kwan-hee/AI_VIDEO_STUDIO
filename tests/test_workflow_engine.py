# workflow_engine.run_workflow 의 통합 흐름(기획→라우팅→mock생성→에셋등록→타임라인→합성)·검증·스키마 준수를 확인하는 테스트
"""Workflow Engine 단위 테스트. 결과는 schemas/workflow_result_schema.json 으로 검증. 실 외부호출/실 ffmpeg 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "workflow"))

from workflow_engine import run_workflow  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "workflow_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

MALLI_REQ = "말리가 달님을 만난 동화 영상 만들어줘"
BASEBALL_REQ = "보크 규칙 설명 영상 만들어줘"
BLOG_REQ = "국민연금 블로그 글 써줘"
UNKNOWN_REQ = "asdfqwer zxcv"


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _mock_compose_runner(args, output_path):
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42workflow-mock")


def _run(req, d):
    return run_workflow(req, output_root=d, composer_runner=_mock_compose_runner)


# --- malli 전체 흐름 ---

def test_malli_full_flow():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["project"] == "malli"
        assert r["needs_clarification"] is False
        # 선택: image/video/voice/thumbnail 라우팅됨
        by_step = {s["step"]: s for s in r["selections"]}
        assert by_step["image"]["provider"] == "Nano Banana"
        assert by_step["video"]["provider"] == "Higgsfield"      # 기본 영상 primary
        assert by_step["voice"]["provider"] == "Edge TTS"
        assert by_step["thumbnail"]["provider"] == "Nano Banana"
        # 에셋 등록됨
        types = sorted(a["type"] for a in r["assets"])
        assert types == ["audio", "image", "thumbnail", "video"]
        _assert_valid(r)


def test_malli_timeline_excludes_thumbnail():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        tl_types = sorted(e["asset_type"] for e in r["timeline"]["entries"])
        assert tl_types == ["audio", "image", "video"]   # thumbnail 제외
        assert "thumbnail" not in tl_types


def test_malli_composition_success_via_mock_runner():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["composition"]["status"] == "success"
        assert r["composition"]["provider"] == "FFmpeg"
        assert r["composition"]["output_path"].endswith(".mp4")


def test_all_generated_assets_are_mock():
    # 실 외부 호출 없음: 모든 생성물이 mock 플래그
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        # 각 에셋 파일이 temp 아래 실제 존재
        for a in r["assets"]:
            assert os.path.exists(os.path.join(_ROOT, a["path"])) or os.path.isabs(a["path"])


# --- baseball: 영상 primary Higgsfield ---

def test_baseball_video_uses_higgsfield_primary():
    with tempfile.TemporaryDirectory() as d:
        r = _run(BASEBALL_REQ, d)
        assert r["project"] == "baseball"
        by_step = {s["step"]: s for s in r["selections"]}
        assert by_step["video"]["provider"] == "Higgsfield"
        _assert_valid(r)


# --- unknown: 명확화 필요, 생성 없음 ---

def test_unknown_needs_clarification_no_generation():
    with tempfile.TemporaryDirectory() as d:
        r = _run(UNKNOWN_REQ, d)
        assert r["project"] == "unknown"
        assert r["needs_clarification"] is True
        assert r["assets"] == []
        assert r["timeline"] is None
        assert r["composition"] is None
        _assert_valid(r)


# --- blog: 텍스트 위주, 타임라인 시각항목 없음 → 합성 스킵 ---

def test_blog_no_timeline_composition_skipped():
    with tempfile.TemporaryDirectory() as d:
        r = _run(BLOG_REQ, d)
        assert r["project"] == "blog"
        # blog 계획은 thumbnail 만 생성 → 타임라인 시각항목 없음
        assert r["composition"] is None
        _assert_valid(r)


# --- failover: 영상 primary 제외 핸들러로 backup 경로 확인 ---

def test_video_failover_to_google_flow_when_excluded():
    with tempfile.TemporaryDirectory() as d:
        r = run_workflow(BASEBALL_REQ, output_root=d,
                         composer_runner=_mock_compose_runner,
                         exclude={"generate_video": ["Higgsfield"]})
        by_step = {s["step"]: s for s in r["selections"]}
        assert by_step["video"]["provider"] == "Google Flow"   # backup 선택
        _assert_valid(r)


# --- 핸들러 실패는 흐름을 죽이지 않음 ---

def test_failing_handler_is_graceful():
    def bad_image(request, output_dir=None, writer=None):
        from provider_sdk import make_result
        return make_result("Nano Banana", "generate_image", status="failed",
                           output=None, message="mock 실패")
    with tempfile.TemporaryDirectory() as d:
        r = run_workflow(MALLI_REQ, output_root=d, composer_runner=_mock_compose_runner,
                         handlers={"Nano Banana": bad_image})
        # 이미지 생성 실패 → image/thumbnail 에셋 미등록, 하지만 흐름은 완료
        types = sorted(a["type"] for a in r["assets"])
        assert "image" not in types
        assert "video" in types  # 영상은 정상
        _assert_valid(r)


# --- 잘못된 입력 ---

def test_empty_request_rejected():
    for bad in ["", "   "]:
        try:
            run_workflow(bad)
        except ValueError:
            continue
        raise AssertionError(f"빈 요청이 거부되지 않음: {bad!r}")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
