# provider_harness.run_harness 의 검사 실행·리포트 형식·미지원 거부·핸들러 검증을 확인하는 테스트
"""Provider Test Harness 단위 테스트. 리포트는 schemas/provider_harness_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from provider_harness import run_harness, CHECK_NAMES  # noqa: E402
from provider_sdk import PROVIDERS, make_result  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_harness_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(report):
    errs = sorted(_VALIDATOR.iter_errors(report), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 기본 stub 핸들러로 정상 통과 ---

def test_default_stub_passes_all_checks():
    report = run_harness("Nano Banana")
    assert report["provider"] == "Nano Banana"
    assert report["passed"] is True
    assert report["failed"] == 0
    assert report["total"] == len(report["checks"])
    _assert_valid(report)


def test_report_structure_keys():
    report = run_harness("FFmpeg")
    assert set(report.keys()) == {"provider", "passed", "total", "failed", "checks"}
    for c in report["checks"]:
        assert set(c.keys()) == {"name", "passed", "detail"}


def test_all_six_providers_pass_with_stub():
    for p in PROVIDERS:
        report = run_harness(p)
        assert report["passed"] is True, f"{p} 하네스 실패: {report}"
        _assert_valid(report)


def test_expected_checks_present():
    report = run_harness("Higgsfield")
    names = {c["name"] for c in report["checks"]}
    assert names == set(CHECK_NAMES)


# --- 각 검사 개별 확인 ---

def test_unsupported_capability_rejection_check_passes():
    report = run_harness("Nano Banana")
    check = next(c for c in report["checks"] if c["name"] == "unsupported_capability_rejected")
    assert check["passed"] is True


def test_unsupported_provider_rejection_check_passes():
    report = run_harness("Nano Banana")
    check = next(c for c in report["checks"] if c["name"] == "unsupported_provider_rejected")
    assert check["passed"] is True


# --- 핸들러 결함 탐지 ---

def test_handler_returning_wrong_provider_fails():
    # 핸들러가 다른 공급자 이름의 result 를 돌려주면 result_format 검사 실패
    def bad_handler(request):
        return make_result("Google Flow", "generate_video", status="pending")
    report = run_harness("Nano Banana", handler=bad_handler)
    assert report["passed"] is False
    check = next(c for c in report["checks"] if c["name"] == "result_format")
    assert check["passed"] is False
    _assert_valid(report)


def test_handler_returning_schema_invalid_result_fails():
    def bad_handler(request):
        return {"provider": "Nano Banana"}  # 필수 키 누락
    report = run_harness("Nano Banana", handler=bad_handler)
    assert report["passed"] is False
    check = next(c for c in report["checks"] if c["name"] == "result_format")
    assert check["passed"] is False


def test_handler_raising_is_caught_and_marked_failed():
    def boom(request):
        raise RuntimeError("provider down")
    report = run_harness("Nano Banana", handler=boom)  # 예외로 하네스가 죽지 않는다
    assert report["passed"] is False
    check = next(c for c in report["checks"] if c["name"] == "result_format")
    assert check["passed"] is False
    _assert_valid(report)


def test_handler_bad_status_fails():
    def bad_handler(request):
        r = make_result(request["provider"], request["capability"])
        r["status"] = "running"  # 스키마 밖 status
        return r
    report = run_harness("Nano Banana", handler=bad_handler)
    assert report["passed"] is False


# --- 미지원 공급자로 하네스 호출 ---

def test_run_harness_unsupported_provider_raises():
    try:
        run_harness("DALL-E")
    except ValueError:
        return
    raise AssertionError("미지원 공급자로 하네스 호출이 거부되지 않음")


# --- 안전성: 검증만, 부작용 없음 ---

def test_no_file_written():
    run_harness("Edge TTS")
    assert not os.path.exists(os.path.join(_ROOT, "output", "audio", "harness.mp3"))


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
