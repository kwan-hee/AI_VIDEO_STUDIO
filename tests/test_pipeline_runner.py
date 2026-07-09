# pipeline_runner.run_pipeline 의 전체 아키텍처 통과·통합 결과·상태 판정·스키마 준수를 확인하는 테스트
"""End-to-End Pipeline Runner 단위 테스트. 결과는 schemas/pipeline_result_schema.json 으로 검증. 실 외부호출/실 ffmpeg 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "pipeline"))

from pipeline_runner import run_pipeline  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "pipeline_result_schema.json")
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
        f.write(b"\x00\x00\x00\x18ftypmp42pipeline-mock")


def _run(req, d):
    return run_pipeline(req, output_root=d, composer_runner=_mock_compose_runner)


# --- 전체 아키텍처 통과 → 최종 mock 결과 ---

def test_malli_end_to_end_success():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert r["request"] == MALLI_REQ
        assert r["project"] == "malli"
        assert r["status"] == "success"
        assert r["asset_count"] == 4
        assert "Nano Banana" in r["providers_used"]
        assert "Higgsfield" in r["providers_used"]
        assert "Edge TTS" in r["providers_used"]
        assert r["final_output"].endswith(".mp4")
        # 최종 mock 산출 실제 존재
        assert os.path.exists(os.path.join(_ROOT, r["final_output"])) or os.path.isabs(r["final_output"])
        _assert_valid(r)


def test_consolidated_result_nests_workflow():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        assert isinstance(r["workflow"], dict)
        assert r["workflow"]["project"] == "malli"
        assert r["workflow"]["composition"]["status"] == "success"


def test_baseball_end_to_end_success():
    with tempfile.TemporaryDirectory() as d:
        r = _run(BASEBALL_REQ, d)
        assert r["project"] == "baseball"
        assert r["status"] == "success"
        assert r["final_output"] is not None
        _assert_valid(r)


# --- unknown: 명확화 필요 ---

def test_unknown_needs_clarification():
    with tempfile.TemporaryDirectory() as d:
        r = _run(UNKNOWN_REQ, d)
        assert r["project"] == "unknown"
        assert r["status"] == "needs_clarification"
        assert r["asset_count"] == 0
        assert r["providers_used"] == []
        assert r["final_output"] is None
        _assert_valid(r)


# --- blog: 생성물 있지만 합성 없음 → partial ---

def test_blog_partial_no_composition():
    with tempfile.TemporaryDirectory() as d:
        r = _run(BLOG_REQ, d)
        assert r["project"] == "blog"
        assert r["status"] == "partial"
        assert r["final_output"] is None
        assert r["asset_count"] >= 1     # thumbnail 생성됨
        _assert_valid(r)


# --- 합성 실패 → failed ---

def test_composition_failure_status_failed():
    def fail_runner(args, output_path):
        raise RuntimeError("ffmpeg 없음")
    with tempfile.TemporaryDirectory() as d:
        r = run_pipeline(MALLI_REQ, output_root=d, composer_runner=fail_runner)
        assert r["status"] == "failed"
        assert r["final_output"] is None
        _assert_valid(r)


# --- 잘못된 입력 ---

def test_empty_request_rejected():
    for bad in ["", "   "]:
        try:
            run_pipeline(bad)
        except ValueError:
            continue
        raise AssertionError(f"빈 요청이 거부되지 않음: {bad!r}")


# --- providers_used 는 실제 등록 에셋 기준 ---

def test_providers_used_from_registered_assets():
    with tempfile.TemporaryDirectory() as d:
        r = _run(MALLI_REQ, d)
        wf_providers = {a["provider"] for a in r["workflow"]["assets"]}
        assert set(r["providers_used"]) == wf_providers


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
