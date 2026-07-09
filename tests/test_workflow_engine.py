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


# --- Phase 7-2: Retry Manager + Execution Logger 배선 증명 ---

sys.path.insert(0, os.path.join(_ROOT, "logging"))
from execution_logger import ExecutionLogger  # noqa: E402
from provider_sdk import make_result  # noqa: E402


def test_logger_receives_workflow_events():
    # (1) 로거가 워크플로 이벤트를 받는다.
    with tempfile.TemporaryDirectory() as d:
        lg = ExecutionLogger(run_id="wf_test")
        run_workflow(MALLI_REQ, output_root=d, composer_runner=_mock_compose_runner, logger=lg)
        types = [e["event_type"] for e in lg.events()]
        assert "run_start" == types[0]
        assert "run_end" == types[-1]
        assert "provider_call" in types
        assert "output" in types
        # provider_call 이벤트는 실제 공급자/단계 정보를 담는다
        pc = next(e for e in lg.events() if e["event_type"] == "provider_call")
        assert pc["provider"] in ("Nano Banana", "Higgsfield", "Edge TTS")
        assert pc["capability"] in ("generate_image", "generate_video", "text_to_speech")


def test_retry_manager_invoked_on_provider_failure():
    # (2) 공급자 실패 시 Retry Manager 가 동작(failover)하고 retry 이벤트가 남는다.
    def fail_higgs(request, output_dir=None, writer=None):
        return make_result("Higgsfield", "generate_video", status="failed",
                           output=None, message="mock 강제 실패")
    with tempfile.TemporaryDirectory() as d:
        lg = ExecutionLogger(run_id="wf_retry")
        r = run_workflow(MALLI_REQ, output_root=d, composer_runner=_mock_compose_runner,
                         handlers={"Higgsfield": fail_higgs}, logger=lg)
        by_step = {s["step"]: s for s in r["selections"]}
        # Higgsfield 실패 → Google Flow 로 failover
        assert by_step["video"]["provider"] == "Google Flow"
        # retry 이벤트 방출됨
        assert any(e["event_type"] == "retry" for e in lg.events())
        # 영상 에셋은 여전히 등록됨(백업 성공)
        assert "video" in [a["type"] for a in r["assets"]]
        _assert_valid(r)


def test_malli_mock_pipeline_still_success():
    # (3) 성공 Malli mock 파이프라인은 여전히 success 를 반환한다.
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["project"] == "malli"
        assert r["composition"]["status"] == "success"
        assert sorted(a["type"] for a in r["assets"]) == ["audio", "image", "thumbnail", "video"]
        _assert_valid(r)


def test_output_paths_unchanged():
    # (4) 기존 출력 경로 스킴이 그대로 유지된다.
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        by_type = {a["type"]: a["path"] for a in r["assets"]}
        assert "images/nano_banana_" in by_type["image"].replace("\\", "/")
        assert "videos/higgsfield_" in by_type["video"].replace("\\", "/")
        assert "audio/tts_" in by_type["audio"].replace("\\", "/")
        assert "images/nano_banana_" in by_type["thumbnail"].replace("\\", "/")
        # 최종 합성 경로 스킴 유지
        final = r["composition"]["output_path"].replace("\\", "/")
        assert "final/malli_timeline_" in final and final.endswith(".mp4")


# --- Phase 7-2b: Story Generator 배선 증명 ---


def test_story_generated_and_attached():
    # title -> story generation: 워크플로가 스토리를 생성해 결과에 담는다.
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["story"] is not None
        assert r["story"]["title"] == MALLI_REQ
        assert len(r["story"]["scenes"]) == 3
        _assert_valid(r)


def test_story_scenes_feed_provider_prompts():
    # story -> workflow -> providers: 장면 프롬프트가 공급자 요청 프롬프트로 흐른다.
    captured = {}

    def capture_image(request, output_dir=None, writer=None):
        captured.setdefault("image_prompt", request["prompt"])  # 첫 호출=image 단계
        from provider_sdk import make_result
        import os as _os
        _os.makedirs(output_dir, exist_ok=True)
        p = _os.path.join(output_dir, "img.png")
        open(p, "wb").write(b"\x89PNGmock")
        return make_result("Nano Banana", "generate_image", status="success",
                           output={"path": p, "type": "image", "mock": True, "prompt": request["prompt"]},
                           message="ok")

    with tempfile.TemporaryDirectory() as d:
        r = run_workflow(MALLI_REQ, output_root=d, composer_runner=_mock_compose_runner,
                         handlers={"Nano Banana": capture_image})
        # image 단계 프롬프트 = 스토리 첫 장면 image_prompt
        assert captured["image_prompt"] == r["story"]["scenes"][0]["image_prompt"]


def test_injected_story_generator_used():
    # 커스텀 story generator 주입 → 그 장면이 워크플로에 반영된다.
    def custom(title, topic, num_scenes):
        return {
            "title": title, "summary": "요약", "moral": "교훈",
            "scenes": [{"scene_number": 1, "narration": "내레이션",
                        "image_prompt": "CUSTOM_IMG", "video_prompt": "CUSTOM_VID",
                        "duration": 7.0}],
        }
    with tempfile.TemporaryDirectory() as d:
        r = run_workflow(MALLI_REQ, output_root=d, composer_runner=_mock_compose_runner,
                         story_generator=custom)
        assert r["story"]["scenes"][0]["image_prompt"] == "CUSTOM_IMG"
        # 장면 길이가 타임라인에 반영(첫 장면 7.0)
        img_entry = next(e for e in r["timeline"]["entries"] if e["asset_type"] == "image")
        assert img_entry["duration"] == 7.0


def test_end_to_end_malli_still_succeeds_with_story():
    # end-to-end Malli 파이프라인은 스토리 배선 후에도 성공한다.
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["composition"]["status"] == "success"
        assert sorted(a["type"] for a in r["assets"]) == ["audio", "image", "thumbnail", "video"]
        _assert_valid(r)


def test_non_story_project_has_no_story():
    # blog 등 비영상 프로젝트는 스토리 미생성.
    with tempfile.TemporaryDirectory() as d:
        r = _run(BLOG_REQ, d)
        assert r["story"] is None
        _assert_valid(r)


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
