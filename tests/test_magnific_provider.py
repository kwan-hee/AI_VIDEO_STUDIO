# magnific_provider.generate 의 mock 보정 이미지 생성·원본 요구·SDK result 준수·하네스 통과를 확인하는 테스트
"""Magnific Provider 단위 테스트. 결과는 schemas/magnific_result_schema.json + SDK result 로 검증."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from magnific_provider import generate, PROVIDER, CAPABILITY  # noqa: E402
from provider_sdk import make_request  # noqa: E402
from provider_harness import run_harness  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "magnific_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

_SDK_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_sdk_schema.json")
with open(_SDK_SCHEMA_PATH, encoding="utf-8") as f:
    _SDK_RESULT_V = Draft7Validator(json.load(f)["definitions"]["result"])

_SRC = "output/images/nano_banana_abc.png"


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "magnific 스키마 위반: " + "; ".join(e.message for e in errs)
    sdk_errs = sorted(_SDK_RESULT_V.iter_errors(r), key=str)
    assert not sdk_errs, "SDK result 스키마 위반: " + "; ".join(e.message for e in sdk_errs)


def _req(source=_SRC):
    inputs = [source] if source is not None else []
    return make_request(PROVIDER, CAPABILITY, prompt=None, inputs=inputs)


def _fake_writer(path, source):
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nreal-ish-enhanced")


def _fail_writer(path, source):
    raise RuntimeError("provider down")


# --- mock 보정 성공 ---

def test_mock_enhance_success():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(), output_dir=d)
        assert r["provider"] == "Magnific"
        assert r["capability"] == "enhance_image"
        assert r["status"] == "success"
        assert r["output"]["type"] == "image"
        assert r["output"]["mock"] is True
        assert r["output"]["source"] == _SRC
        p = os.path.join(_ROOT, r["output"]["path"])
        assert os.path.exists(p) and os.path.getsize(p) > 0
        _assert_valid(r)


def test_output_path_under_output_enhanced_by_default():
    r = generate(_req())
    try:
        assert r["status"] == "success"
        assert r["output"]["path"].startswith("output/enhanced/")
        assert os.path.exists(os.path.join(_ROOT, r["output"]["path"]))
    finally:
        p = os.path.join(_ROOT, r["output"]["path"])
        if os.path.exists(p):
            os.remove(p)


def test_injected_writer_marks_not_mock():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(), output_dir=d, writer=_fake_writer)
        assert r["status"] == "success"
        assert r["output"]["mock"] is False
        _assert_valid(r)


# --- 원본 이미지 요구 ---

def test_missing_source_returns_failed():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(source=None), output_dir=d)   # inputs 비어있음
        assert r["status"] == "failed"
        assert r["output"] is None
        assert "원본" in r["message"]
        _assert_valid(r)


# --- 실패 처리 ---

def test_writer_failure_returns_failed():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(), output_dir=d, writer=_fail_writer)
        assert r["status"] == "failed"
        assert r["output"] is None
        assert "실패" in r["message"]
        _assert_valid(r)


# --- 잘못된 request 거부 ---

def test_wrong_provider_request_rejected():
    bad = make_request("Higgsfield", "generate_video")
    try:
        generate(bad)
    except ValueError:
        return
    raise AssertionError("다른 공급자 request 가 거부되지 않음")


def test_wrong_capability_request_rejected():
    bad = dict(_req())
    bad["capability"] = "generate_image"
    try:
        generate(bad)
    except ValueError:
        return
    raise AssertionError("잘못된 capability request 가 거부되지 않음")


# --- 하네스 통과 (핸들러가 원본을 주입) ---

def test_passes_provider_harness():
    with tempfile.TemporaryDirectory() as d:
        def handler(request):
            req = dict(request)
            req["inputs"] = [_SRC]     # enhance 는 원본이 필요 → 주입
            return generate(req, output_dir=d, writer=_fake_writer)
        report = run_harness(PROVIDER, handler=handler)
        assert report["passed"] is True, f"하네스 실패: {report}"


# --- 안전성: 다른 공급자 미호출 ---

def test_no_other_provider_imports():
    import magnific_provider as MG
    src = open(MG.__file__, encoding="utf-8").read()
    for forbidden in ("Google Flow", "Higgsfield", "Nano Banana", "Edge TTS", "subprocess", "ffmpeg"):
        assert forbidden not in src, f"금지 참조 발견: {forbidden}"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
