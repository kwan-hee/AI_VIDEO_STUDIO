# Kling 전용 파이프라인 단위 테스트. 외부 호출 없음.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kling.kling_pipeline import (  # noqa: E402
    CREDITS_PER_SECOND,
    ENGINE,
    MAX_DURATION,
    MIN_DURATION,
    KlingPipelineError,
    SOUND,
    build_payloads,
    build_plan,
    find_duplicates,
    format_report,
    normalize_duration,
    scene_cost,
    validate_scenes,
)

SCENES = [
    {"key": "s1", "prompt": "The huge grey steel cutterhead rotates slowly in murky brown slurry",
     "duration": 5, "start_image": "img-1", "end_image": "img-1e"},
    {"key": "s2", "prompt": "Ripples drift across the river surface above the tunnel tube, "
                            "a thin blue vertical dimension line draws down to the tunnel crown",
     "duration": 6, "start_image": "img-2"},
    {"key": "s3", "prompt": "Wet sand at the excavation face collapses and pours into the empty bore",
     "duration": 5},
]


# --- 단가 ---

def test_rate_is_fixed():
    assert CREDITS_PER_SECOND == 1.25


def test_scene_cost_matches_ledger():
    # Higgsfield 거래 내역 실측값과 일치해야 한다.
    assert scene_cost(5) == 6.25
    assert scene_cost(6) == 7.50
    assert scene_cost(7) == 8.75


# --- 길이 정책 ---

def test_duration_clamped_both_ends():
    assert normalize_duration(1) == MIN_DURATION
    assert normalize_duration(30) == MAX_DURATION
    assert normalize_duration(None) == 5


def test_duration_rejects_non_integer():
    for bad in ["5", 5.5, True]:
        try:
            normalize_duration(bad)
        except KlingPipelineError:
            continue
        raise AssertionError(f"{bad!r} 가 거부되지 않음")


# --- 엔진 고정 ---

def test_other_engine_rejected():
    bad = [{"key": "s1", "prompt": "x", "duration": 5, "engine": "wan3_0"}]
    try:
        validate_scenes(bad)
    except KlingPipelineError:
        return
    raise AssertionError("Wan 엔진 지정이 거부되지 않음")


def test_plan_engine_is_always_kling():
    plan = build_plan("tunnel", SCENES)
    assert plan["engine"] == ENGINE
    assert all(s["engine"] == ENGINE for s in plan["steps"])


# --- 비용 산출 ---

def test_plan_totals():
    plan = build_plan("tunnel", SCENES)
    assert plan["total_seconds"] == 16
    assert plan["estimated_cost"] == 20.0
    assert plan["wan_equivalent_cost"] == 28.0
    assert plan["saving_vs_wan"] == 8.0


def test_budget_gate_blocks_plan():
    try:
        build_plan("tunnel", SCENES, budget=10)
    except KlingPipelineError:
        return
    raise AssertionError("예산 초과가 막히지 않음")


def test_budget_gate_allows_within():
    plan = build_plan("tunnel", SCENES, budget=25)
    assert plan["budget"] == 25


# --- 중복 탐지 ---

def test_duplicate_detected():
    dup = [
        {"key": "a", "prompt": "Ripples drift across the river surface and a thin blue "
                               "vertical dimension line draws down to the tunnel crown", "duration": 6},
        {"key": "b", "prompt": "Ripples pass slowly over the river surface and the thin blue "
                               "vertical dimension line extends down to the tunnel crown", "duration": 7},
    ]
    found = find_duplicates(dup)
    assert len(found) == 1
    assert found[0]["refundable"] == 8.75


def test_distinct_scenes_not_flagged():
    assert find_duplicates(SCENES) == []


# --- 구조 검증 ---

def test_duplicate_key_rejected():
    bad = [{"key": "s1", "prompt": "a", "duration": 5},
           {"key": "s1", "prompt": "b", "duration": 5}]
    try:
        validate_scenes(bad)
    except KlingPipelineError:
        return
    raise AssertionError("중복 key 가 거부되지 않음")


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, [{"prompt": "no key"}], [{"key": "k"}]]:
        try:
            validate_scenes(bad)
        except KlingPipelineError:
            continue
        raise AssertionError(f"{bad!r} 가 거부되지 않음")


# --- 페이로드 ---

def test_payload_shape():
    payloads = build_payloads(build_plan("tunnel", SCENES))
    assert len(payloads) == 3
    first = payloads[0]["params"]
    assert first["model"] == ENGINE
    assert first["aspect_ratio"] == "9:16"
    assert first["duration"] == 5
    roles = [m["role"] for m in first["medias"]]
    assert roles == ["start_image", "end_image"]


def test_payload_forces_sound_off():
    # sound 기본값이 on 이면 초당 1.75 가 되어 Wan 과 같아진다. 반드시 꺼서 보내야 한다.
    assert SOUND == "off"
    for payload in build_payloads(build_plan("tunnel", SCENES)):
        assert payload["params"]["sound"] == "off"


def test_payload_omits_missing_media():
    payloads = build_payloads(build_plan("tunnel", SCENES))
    assert "medias" not in payloads[2]["params"]


def test_input_not_mutated():
    before = json.dumps(SCENES, ensure_ascii=False, sort_keys=True)
    build_payloads(build_plan("tunnel", SCENES))
    assert json.dumps(SCENES, ensure_ascii=False, sort_keys=True) == before


# --- 스키마 ---

def test_plan_matches_schema_keys():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "schemas", "kling_plan_schema.json"), encoding="utf-8") as f:
        schema = json.load(f)
    plan = build_plan("tunnel", SCENES)
    allowed = set(schema["properties"])
    assert set(plan).issubset(allowed), set(plan) - allowed
    for req in schema["required"]:
        assert req in plan
    step_allowed = set(schema["properties"]["steps"]["items"]["properties"])
    for step in plan["steps"]:
        assert set(step).issubset(step_allowed), set(step) - step_allowed


def test_report_is_readable():
    report = format_report(build_plan("tunnel", SCENES))
    assert "Kling v3.0" in report
    assert "20.0" in report


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
