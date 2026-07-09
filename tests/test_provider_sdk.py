# provider_sdk 의 capability 매핑·request/result 헬퍼·미지원 공급자 검증·스키마 준수를 검증하는 테스트
"""Provider SDK 단위 테스트. request/result 는 schemas/provider_sdk_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from provider_sdk import (  # noqa: E402
    PROVIDERS,
    CAPABILITIES,
    PROVIDER_CAPABILITIES,
    make_request,
    make_result,
    supports,
    capabilities_of,
)

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_sdk_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)

_REQUEST_SCHEMA = SCHEMA["definitions"]["request"]
_RESULT_SCHEMA = SCHEMA["definitions"]["result"]
Draft7Validator.check_schema(_REQUEST_SCHEMA)
Draft7Validator.check_schema(_RESULT_SCHEMA)
_REQ_V = Draft7Validator(_REQUEST_SCHEMA)
_RES_V = Draft7Validator(_RESULT_SCHEMA)


def _assert_req(r):
    errs = sorted(_REQ_V.iter_errors(r), key=str)
    assert not errs, "request 스키마 위반: " + "; ".join(e.message for e in errs)


def _assert_res(r):
    errs = sorted(_RES_V.iter_errors(r), key=str)
    assert not errs, "result 스키마 위반: " + "; ".join(e.message for e in errs)


# --- capability 매핑 ---

def test_all_six_providers_present():
    assert set(PROVIDERS) == {
        "Nano Banana", "Google Flow", "Higgsfield", "Magnific", "Edge TTS", "FFmpeg"
    }
    assert set(PROVIDER_CAPABILITIES.keys()) == set(PROVIDERS)


def test_each_provider_has_capabilities_within_known_set():
    known = set(CAPABILITIES)
    for prov, caps in PROVIDER_CAPABILITIES.items():
        assert caps, f"{prov} 에 capability 가 없음"
        for c in caps:
            assert c in known, f"{prov} 의 알 수 없는 capability: {c}"


def test_capability_mapping_matches_provider_roles():
    assert "generate_image" in PROVIDER_CAPABILITIES["Nano Banana"]
    assert "generate_video" in PROVIDER_CAPABILITIES["Google Flow"]
    assert "generate_video" in PROVIDER_CAPABILITIES["Higgsfield"]
    assert "enhance_image" in PROVIDER_CAPABILITIES["Magnific"]
    assert "text_to_speech" in PROVIDER_CAPABILITIES["Edge TTS"]
    assert "compose" in PROVIDER_CAPABILITIES["FFmpeg"]


def test_supports_true_and_false():
    assert supports("Nano Banana", "generate_image") is True
    assert supports("Nano Banana", "generate_video") is False
    assert supports("FFmpeg", "compose") is True


def test_capabilities_of_returns_list():
    caps = capabilities_of("Higgsfield")
    assert isinstance(caps, list)
    assert "generate_video" in caps


def test_capabilities_of_unknown_provider_raises():
    try:
        capabilities_of("DALL-E")
    except ValueError:
        return
    raise AssertionError("미지원 공급자가 거부되지 않음")


# --- request 헬퍼 ---

def test_make_request_valid_and_schema():
    req = make_request("Nano Banana", "generate_image", prompt="달을 그린다",
                       parameters={"model": "nano-banana"})
    assert req["provider"] == "Nano Banana"
    assert req["capability"] == "generate_image"
    assert req["prompt"] == "달을 그린다"
    assert req["parameters"] == {"model": "nano-banana"}
    assert req["inputs"] == []
    _assert_req(req)


def test_make_request_defaults_parameters_and_inputs():
    req = make_request("FFmpeg", "compose")
    assert req["prompt"] is None
    assert req["parameters"] == {}
    assert req["inputs"] == []
    _assert_req(req)


def test_make_request_with_inputs():
    req = make_request("Google Flow", "generate_video", prompt="장면",
                       inputs=["output/image/01.png"])
    assert req["inputs"] == ["output/image/01.png"]
    _assert_req(req)


def test_make_request_unsupported_provider_rejected():
    try:
        make_request("DALL-E", "generate_image")
    except ValueError:
        return
    raise AssertionError("미지원 공급자 request 가 거부되지 않음")


def test_make_request_capability_not_supported_by_provider_rejected():
    # Nano Banana 는 영상 생성을 지원하지 않는다
    try:
        make_request("Nano Banana", "generate_video")
    except ValueError:
        return
    raise AssertionError("공급자가 지원하지 않는 capability 가 거부되지 않음")


def test_make_request_unknown_capability_rejected():
    try:
        make_request("Nano Banana", "fly_to_moon")
    except ValueError:
        return
    raise AssertionError("알 수 없는 capability 가 거부되지 않음")


# --- result 헬퍼 ---

def test_make_result_default_pending():
    res = make_result("Higgsfield", "generate_video")
    assert res["status"] == "pending"       # 실행 전 기본 상태
    assert res["output"] is None
    assert res["message"] == ""
    _assert_res(res)


def test_make_result_success_with_output():
    res = make_result("Nano Banana", "generate_image", status="success",
                      output={"path": "output/image/01.png"}, message="완료")
    assert res["status"] == "success"
    assert res["output"] == {"path": "output/image/01.png"}
    _assert_res(res)


def test_make_result_invalid_status_rejected():
    try:
        make_result("FFmpeg", "compose", status="running")
    except ValueError:
        return
    raise AssertionError("잘못된 status 가 거부되지 않음")


def test_make_result_unsupported_provider_rejected():
    try:
        make_result("DALL-E", "generate_image", status="success")
    except ValueError:
        return
    raise AssertionError("미지원 공급자 result 가 거부되지 않음")


def test_make_result_capability_not_supported_rejected():
    try:
        make_result("Edge TTS", "generate_video", status="success")
    except ValueError:
        return
    raise AssertionError("공급자가 지원 않는 capability result 가 거부되지 않음")


# --- 안전성: 준비만, 실행/미디어 없음 ---

def test_helpers_are_pure_no_file_written():
    make_request("Nano Banana", "generate_image", prompt="x")
    make_result("Nano Banana", "generate_image", status="success",
                output={"path": "output/image/nope.png"})
    assert not os.path.exists(os.path.join(_ROOT, "output", "image", "nope.png"))


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
