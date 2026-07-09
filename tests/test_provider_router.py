# provider_router.route 의 정책 라우팅·primary/backup·failover(exclude)·검증·스키마 준수를 확인하는 테스트
"""Provider Router 단위 테스트. 선택 결과는 schemas/provider_router_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "routing"))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from provider_router import route, candidates_for, ROUTING_POLICY  # noqa: E402
from provider_sdk import supports, CAPABILITIES  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_router_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(sel):
    errs = sorted(_VALIDATOR.iter_errors(sel), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 기본 정책 라우팅 ---

def test_generate_image_routes_to_nano_banana():
    sel = route("generate_image")
    assert sel["primary"] == "Nano Banana"
    assert sel["backup"] is None
    assert sel["selected"] == "Nano Banana"
    _assert_valid(sel)


def test_enhance_image_routes_to_magnific():
    sel = route("enhance_image")
    assert sel["selected"] == "Magnific"
    _assert_valid(sel)


def test_generate_video_primary_higgsfield_backup_google_flow():
    sel = route("generate_video")
    assert sel["primary"] == "Higgsfield"
    assert sel["backup"] == "Google Flow"
    assert sel["candidates"] == ["Higgsfield", "Google Flow"]
    assert sel["selected"] == "Higgsfield"
    _assert_valid(sel)


def test_text_to_speech_routes_to_edge_tts():
    sel = route("text_to_speech")
    assert sel["selected"] == "Edge TTS"
    _assert_valid(sel)


def test_compose_routes_to_ffmpeg():
    sel = route("compose")
    assert sel["selected"] == "FFmpeg"
    _assert_valid(sel)


# --- failover: exclude 로 실패한 공급자 스킵 ---

def test_failover_excludes_primary_selects_backup():
    sel = route("generate_video", exclude=["Higgsfield"])
    assert sel["selected"] == "Google Flow"
    _assert_valid(sel)


def test_failover_all_excluded_selects_none():
    sel = route("generate_video", exclude=["Higgsfield", "Google Flow"])
    assert sel["selected"] is None
    _assert_valid(sel)


def test_exclude_on_single_candidate_selects_none():
    sel = route("generate_image", exclude=["Nano Banana"])
    assert sel["selected"] is None
    _assert_valid(sel)


# --- candidates 헬퍼 ---

def test_candidates_for_returns_ordered_list():
    assert candidates_for("generate_video") == ["Higgsfield", "Google Flow"]
    assert candidates_for("generate_image") == ["Nano Banana"]


# --- 검증 ---

def test_unknown_capability_rejected():
    try:
        route("fly_to_moon")
    except ValueError:
        return
    raise AssertionError("알 수 없는 capability 가 거부되지 않음")


# --- 정책 일관성: 모든 후보가 해당 capability 를 실제로 지원 (SDK 기준) ---

def test_policy_consistent_with_sdk_capabilities():
    assert set(ROUTING_POLICY.keys()) == set(CAPABILITIES)
    for cap, cands in ROUTING_POLICY.items():
        assert cands, f"{cap} 후보 없음"
        for prov in cands:
            assert supports(prov, cap), f"{prov} 는 {cap} 를 지원하지 않음"


# --- 실행 없음: 선택만, 부작용 없음 ---

def test_route_is_pure_no_file():
    route("compose")
    assert not os.path.exists(os.path.join(_ROOT, "output", "final", "router.mp4"))


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
