# provider_config 의 설정 로드·모드 조회·라우팅 정책·검증·스키마 준수를 확인하는 테스트
"""Provider Configuration Layer 단위 테스트. 설정은 schemas/provider_config_schema.json 으로 검증. 실행 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "config"))

from provider_config import (  # noqa: E402
    DEFAULT_CONFIG,
    KNOWN_PROVIDERS,
    load_config,
    provider_mode,
    is_real,
    is_mock,
    is_disabled,
    routing_primary,
    routing_backup,
    routing_candidates,
    provider_display_name,
)

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_config_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(cfg):
    errs = sorted(_VALIDATOR.iter_errors(cfg), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 기본 설정: 전부 mock(안전), ffmpeg local ---

def test_default_config_is_safe_mock():
    cfg = load_config()
    _assert_valid(cfg)
    for key in ("nano_banana", "magnific", "higgsfield", "google_flow", "edge_tts"):
        assert provider_mode(cfg, key) == "mock"
    assert provider_mode(cfg, "ffmpeg") == "local"


def test_default_config_constant_valid():
    _assert_valid(DEFAULT_CONFIG)


# --- dict / JSON 파일 로드 ---

def test_load_from_dict():
    data = {
        "providers": {"nano_banana": {"mode": "real"}, "ffmpeg": {"mode": "local"}},
        "routing": {"generate_image": {"primary": "nano_banana"},
                    "compose": {"primary": "ffmpeg"}},
    }
    cfg = load_config(data=data)
    assert provider_mode(cfg, "nano_banana") == "real"


def test_load_from_json_file():
    data = {
        "providers": {"higgsfield": {"mode": "real"}},
        "routing": {"generate_video": {"primary": "higgsfield", "backup": "google_flow"}},
    }
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cfg.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        cfg = load_config(path=p)
        assert provider_mode(cfg, "higgsfield") == "real"
        assert routing_backup(cfg, "generate_video") == "google_flow"


# --- 모드 조회 ---

def test_provider_mode_default_mock_when_absent():
    cfg = load_config(data={"providers": {}, "routing": {}})
    assert provider_mode(cfg, "nano_banana") == "mock"   # 미기재 → 안전 기본 mock


def test_provider_mode_unknown_key_rejected():
    cfg = load_config()
    try:
        provider_mode(cfg, "dalle")
    except ValueError:
        return
    raise AssertionError("알 수 없는 provider 키가 거부되지 않음")


def test_mode_predicates():
    cfg = load_config(data={
        "providers": {"nano_banana": {"mode": "real"}, "magnific": {"mode": "disabled"},
                      "higgsfield": {"mode": "mock"}},
        "routing": {},
    })
    assert is_real(cfg, "nano_banana") is True
    assert is_disabled(cfg, "magnific") is True
    assert is_mock(cfg, "higgsfield") is True
    assert is_mock(cfg, "nano_banana") is False


# --- 라우팅 정책 ---

def test_routing_primary_backup():
    cfg = load_config()
    assert routing_primary(cfg, "generate_image") == "nano_banana"
    assert routing_backup(cfg, "generate_image") is None
    assert routing_primary(cfg, "generate_video") == "higgsfield"
    assert routing_backup(cfg, "generate_video") == "google_flow"


def test_routing_unknown_capability_rejected():
    cfg = load_config()
    try:
        routing_primary(cfg, "fly")
    except ValueError:
        return
    raise AssertionError("알 수 없는 capability 가 거부되지 않음")


def test_routing_candidates_skips_disabled():
    cfg = load_config(data={
        "providers": {"higgsfield": {"mode": "disabled"}, "google_flow": {"mode": "mock"}},
        "routing": {"generate_video": {"primary": "higgsfield", "backup": "google_flow"}},
    })
    # primary 가 disabled → 후보에서 제외, backup 만 남음
    assert routing_candidates(cfg, "generate_video") == ["google_flow"]


def test_routing_candidates_include_disabled_flag():
    cfg = load_config(data={
        "providers": {"higgsfield": {"mode": "disabled"}, "google_flow": {"mode": "mock"}},
        "routing": {"generate_video": {"primary": "higgsfield", "backup": "google_flow"}},
    })
    assert routing_candidates(cfg, "generate_video", include_disabled=True) == ["higgsfield", "google_flow"]


# --- 표시명 매핑 ---

def test_display_name_mapping():
    assert provider_display_name("nano_banana") == "Nano Banana"
    assert provider_display_name("google_flow") == "Google Flow"
    assert provider_display_name("ffmpeg") == "FFmpeg"
    assert set(KNOWN_PROVIDERS) == {"nano_banana", "magnific", "higgsfield",
                                    "google_flow", "edge_tts", "ffmpeg"}


def test_display_name_unknown_rejected():
    try:
        provider_display_name("dalle")
    except ValueError:
        return
    raise AssertionError("알 수 없는 provider 표시명 요청이 거부되지 않음")


# --- 검증/거부 ---

def test_invalid_mode_rejected():
    try:
        load_config(data={"providers": {"nano_banana": {"mode": "turbo"}}, "routing": {}})
    except ValueError:
        return
    raise AssertionError("잘못된 mode 가 거부되지 않음")


def test_missing_required_key_rejected():
    try:
        load_config(data={"providers": {}})   # routing 누락
    except ValueError:
        return
    raise AssertionError("필수 키 누락이 거부되지 않음")


def test_unknown_provider_key_in_config_rejected():
    try:
        load_config(data={"providers": {"dalle": {"mode": "mock"}}, "routing": {}})
    except ValueError:
        return
    raise AssertionError("알 수 없는 provider 키 설정이 거부되지 않음")


def test_unsupported_file_extension_rejected():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "cfg.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("nonsense")
        try:
            load_config(path=p)
        except ValueError:
            return
        raise AssertionError("지원하지 않는 확장자가 거부되지 않음")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
