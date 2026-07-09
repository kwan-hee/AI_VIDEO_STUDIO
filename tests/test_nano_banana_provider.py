# nano_banana_provider.generate 의 mock 이미지 생성·SDK result 준수·검증·하네스 통과를 확인하는 테스트
"""Nano Banana Provider 단위 테스트. 결과는 schemas/nano_banana_result_schema.json + SDK result 로 검증."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from nano_banana_provider import generate, PROVIDER, CAPABILITY  # noqa: E402
from provider_sdk import make_request  # noqa: E402
from provider_harness import run_harness  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "nano_banana_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

_SDK_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_sdk_schema.json")
with open(_SDK_SCHEMA_PATH, encoding="utf-8") as f:
    _SDK_RESULT_V = Draft7Validator(json.load(f)["definitions"]["result"])


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "nano 스키마 위반: " + "; ".join(e.message for e in errs)
    sdk_errs = sorted(_SDK_RESULT_V.iter_errors(r), key=str)
    assert not sdk_errs, "SDK result 스키마 위반: " + "; ".join(e.message for e in sdk_errs)


def _req(prompt="달을 그린다"):
    return make_request(PROVIDER, CAPABILITY, prompt=prompt)


def _fake_writer(path, prompt):
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\nreal-ish")


def _fail_writer(path, prompt):
    raise RuntimeError("provider down")


# --- mock 생성 성공 ---

def test_mock_generate_success():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(), output_dir=d)
        assert r["provider"] == "Nano Banana"
        assert r["capability"] == "generate_image"
        assert r["status"] == "success"
        assert r["output"]["type"] == "image"
        assert r["output"]["mock"] is True   # 기본 mock writer
        assert r["output"]["prompt"] == "달을 그린다"
        # 파일 실제 생성
        p = os.path.join(_ROOT, r["output"]["path"])
        assert os.path.exists(p) and os.path.getsize(p) > 0
        _assert_valid(r)


def test_output_path_under_output_images_by_default():
    r = generate(_req("고양이"))
    try:
        assert r["status"] == "success"
        assert r["output"]["path"].startswith("output/images/")
        assert os.path.exists(os.path.join(_ROOT, r["output"]["path"]))
    finally:
        p = os.path.join(_ROOT, r["output"]["path"])
        if os.path.exists(p):
            os.remove(p)


def test_injected_writer_marks_not_mock():
    with tempfile.TemporaryDirectory() as d:
        r = generate(_req(), output_dir=d, writer=_fake_writer)
        assert r["status"] == "success"
        assert r["output"]["mock"] is False   # 주입 writer → 실제 경로 취급
        _assert_valid(r)


def test_same_prompt_deterministic_path():
    with tempfile.TemporaryDirectory() as d:
        r1 = generate(_req("같은프롬프트"), output_dir=d)
        r2 = generate(_req("같은프롬프트"), output_dir=d)
        assert r1["output"]["path"] == r2["output"]["path"]


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
    bad = make_request("Google Flow", "generate_video")
    try:
        generate(bad)
    except ValueError:
        return
    raise AssertionError("다른 공급자 request 가 거부되지 않음")


def test_wrong_capability_request_rejected():
    # provider 는 맞지만 capability 를 손으로 바꿔 넣은 경우
    bad = dict(_req())
    bad["capability"] = "generate_video"
    try:
        generate(bad)
    except ValueError:
        return
    raise AssertionError("잘못된 capability request 가 거부되지 않음")


# --- 하네스 통과 ---

def test_passes_provider_harness():
    with tempfile.TemporaryDirectory() as d:
        def handler(request):
            return generate(request, output_dir=d, writer=_fake_writer)
        report = run_harness(PROVIDER, handler=handler)
        assert report["passed"] is True, f"하네스 실패: {report}"


# --- 안전성: 다른 공급자 미호출 (모듈 임포트 표면 확인) ---

def test_no_other_provider_imports():
    import nano_banana_provider as NB
    src = open(NB.__file__, encoding="utf-8").read()
    for forbidden in ("Google Flow", "Higgsfield", "Magnific", "Edge TTS", "subprocess", "ffmpeg"):
        assert forbidden not in src, f"금지 참조 발견: {forbidden}"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
