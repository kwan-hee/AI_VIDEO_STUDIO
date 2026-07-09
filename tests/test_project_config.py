# project_config 의 설정 로드·deep-merge 기본·헬퍼 API·provider_config 연동·검증·스키마 준수를 확인하는 테스트
"""Project Configuration Layer 단위 테스트. 설정은 schemas/project_config_schema.json 으로 검증. 실행 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "config"))

from project_config import (  # noqa: E402
    DEFAULT_PROJECT_CONFIG,
    ROLES,
    load_project_config,
    project_name,
    project_description,
    output_directory,
    provider_for,
    provider_display_for,
    voice_settings,
    video_settings,
    timeline_settings,
    output_settings,
)

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "project_config_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(cfg):
    errs = sorted(_VALIDATOR.iter_errors(cfg), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 기본 설정 ---

def test_default_config_valid_and_safe():
    cfg = load_project_config()
    _assert_valid(cfg)
    assert output_directory(cfg) == "output"
    assert output_settings(cfg)["format"] == "mp4"
    assert output_settings(cfg)["overwrite"] is False


def test_default_config_constant_valid():
    _assert_valid(DEFAULT_PROJECT_CONFIG)


def test_default_provider_roles():
    cfg = load_project_config()
    assert provider_for(cfg, "image") == "nano_banana"
    assert provider_for(cfg, "enhance") == "magnific"
    assert provider_for(cfg, "video") == "higgsfield"
    assert provider_for(cfg, "tts") == "edge_tts"
    assert provider_for(cfg, "compose") == "ffmpeg"


# --- deep-merge: 부분 override 시 나머지 기본 유지 ---

def test_partial_override_keeps_defaults():
    cfg = load_project_config(data={"video": {"fps": 60}})
    assert video_settings(cfg)["fps"] == 60          # override 반영
    assert video_settings(cfg)["resolution"] == "1280x720"  # 나머지 기본 유지
    assert provider_for(cfg, "image") == "nano_banana"      # 다른 섹션 기본 유지
    _assert_valid(cfg)


def test_partial_project_override():
    cfg = load_project_config(data={"project": {"name": "말리동화"}})
    assert project_name(cfg) == "말리동화"
    assert output_directory(cfg) == "output"   # 기본 유지


# --- 파일 로드 ---

def test_load_from_json_file():
    data = {"providers": {"video": "google_flow"}}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "project.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        cfg = load_project_config(path=p)
        assert provider_for(cfg, "video") == "google_flow"
        assert provider_for(cfg, "image") == "nano_banana"  # 기본 유지


# --- provider_config 연동: 표시명 매핑 ---

def test_provider_display_for_uses_provider_config():
    cfg = load_project_config()
    assert provider_display_for(cfg, "image") == "Nano Banana"
    assert provider_display_for(cfg, "video") == "Higgsfield"
    assert provider_display_for(cfg, "compose") == "FFmpeg"


# --- 헬퍼 API ---

def test_section_helpers():
    cfg = load_project_config()
    assert set(voice_settings(cfg).keys()) == {"speaker", "rate"}
    assert set(video_settings(cfg).keys()) == {"resolution", "fps", "aspect_ratio"}
    assert set(timeline_settings(cfg).keys()) == {"default_transition", "default_duration"}
    assert project_description(cfg) == DEFAULT_PROJECT_CONFIG["project"]["description"]


def test_roles_constant():
    assert set(ROLES) == {"image", "enhance", "video", "tts", "compose"}


# --- 검증/거부 ---

def test_unknown_role_rejected():
    cfg = load_project_config()
    try:
        provider_for(cfg, "subtitle")
    except ValueError:
        return
    raise AssertionError("알 수 없는 role 이 거부되지 않음")


def test_invalid_provider_key_rejected():
    try:
        load_project_config(data={"providers": {"image": "dalle"}})
    except ValueError:
        return
    raise AssertionError("알 수 없는 provider 키가 거부되지 않음")


def test_invalid_fps_type_rejected():
    try:
        load_project_config(data={"video": {"fps": "삼십"}})
    except ValueError:
        return
    raise AssertionError("잘못된 fps 타입이 거부되지 않음")


def test_unknown_section_rejected():
    try:
        load_project_config(data={"bogus": {"x": 1}})
    except ValueError:
        return
    raise AssertionError("알 수 없는 섹션이 거부되지 않음")


def test_unknown_field_in_section_rejected():
    try:
        load_project_config(data={"output": {"codec": "h265"}})
    except ValueError:
        return
    raise AssertionError("알 수 없는 필드가 거부되지 않음")


def test_unsupported_extension_rejected():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "project.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        try:
            load_project_config(path=p)
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
