# timeline_builder.build_timeline 의 배치·레이어·계획순서·스키마 준수를 검증하는 테스트
"""Timeline Builder 단위 테스트. 타임라인은 schemas/timeline_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "timeline"))

from timeline_builder import build_timeline, DEFAULT_DURATIONS  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "timeline_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

FIXED_TS = "2026-07-09T00:00:00+00:00"
ENTRY_KEYS = {"asset_id", "asset_type", "start_time", "end_time", "duration", "layer"}

# malli 실행 계획의 최소 형태 (build_timeline 은 step/order 만 읽는다)
MALLI_STEPS = [
    {"order": 1, "step": "story"},
    {"order": 2, "step": "image"},
    {"order": 3, "step": "video"},
    {"order": 4, "step": "voice"},
    {"order": 5, "step": "thumbnail"},
    {"order": 6, "step": "edit"},
]


def _plan(project="malli", steps=None):
    return {"project": project, "steps": steps if steps is not None else MALLI_STEPS}


def _asset(asset_id, type, status="ready"):
    return {
        "asset_id": asset_id,
        "type": type,
        "provider": None,
        "path": None,
        "status": status,
        "created_at": FIXED_TS,
    }


def _assert_valid(timeline):
    errs = sorted(_VALIDATOR.iter_errors(timeline), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 항목 형식 / 스키마 ---

def test_entry_has_required_keys_and_schema_valid():
    assets = [_asset("image_0001", "image"), _asset("audio_0001", "audio")]
    tl = build_timeline(_plan(), assets)
    assert set(tl.keys()) == {"project", "entries", "total_duration"}
    assert tl["project"] == "malli"
    for e in tl["entries"]:
        assert set(e.keys()) == ENTRY_KEYS
    _assert_valid(tl)


# --- visual 레이어 순차 배치 ---

def test_visual_layer_sequential_placement():
    assets = [_asset("image_0001", "image"), _asset("video_0001", "video")]
    tl = build_timeline(_plan(), assets, durations={"image_0001": 5.0, "video_0001": 10.0})
    visual = [e for e in tl["entries"] if e["layer"] == "visual"]
    assert [e["asset_id"] for e in visual] == ["image_0001", "video_0001"]
    assert visual[0]["start_time"] == 0.0
    assert visual[0]["end_time"] == 5.0
    assert visual[1]["start_time"] == 5.0   # 직전 항목 end 에 이어짐
    assert visual[1]["end_time"] == 15.0


# --- audio 레이어는 0초부터 독립 트랙 ---

def test_audio_layer_independent_track_starts_at_zero():
    assets = [
        _asset("image_0001", "image"),
        _asset("audio_0001", "audio"),
        _asset("audio_0002", "audio"),
    ]
    tl = build_timeline(_plan(), assets,
                        durations={"image_0001": 5.0, "audio_0001": 3.0, "audio_0002": 4.0})
    audio = [e for e in tl["entries"] if e["layer"] == "audio"]
    assert audio[0]["start_time"] == 0.0   # 시각 레이어와 무관하게 0 부터
    assert audio[0]["end_time"] == 3.0
    assert audio[1]["start_time"] == 3.0
    assert audio[1]["end_time"] == 7.0


# --- 기본 duration ---

def test_default_durations_applied_when_not_given():
    assets = [_asset("image_0001", "image"), _asset("video_0001", "video"),
              _asset("audio_0001", "audio")]
    tl = build_timeline(_plan(), assets)
    by_id = {e["asset_id"]: e for e in tl["entries"]}
    assert by_id["image_0001"]["duration"] == DEFAULT_DURATIONS["image"]
    assert by_id["video_0001"]["duration"] == DEFAULT_DURATIONS["video"]
    assert by_id["audio_0001"]["duration"] == DEFAULT_DURATIONS["audio"]


def test_custom_duration_overrides_default():
    assets = [_asset("image_0001", "image")]
    tl = build_timeline(_plan(), assets, durations={"image_0001": 12.5})
    assert tl["entries"][0]["duration"] == 12.5
    assert tl["entries"][0]["end_time"] == 12.5


# --- 대상 아닌 타입 제외 ---

def test_story_and_thumbnail_excluded():
    assets = [
        _asset("story_0001", "story"),
        _asset("image_0001", "image"),
        _asset("thumbnail_0001", "thumbnail"),
    ]
    tl = build_timeline(_plan(), assets)
    ids = [e["asset_id"] for e in tl["entries"]]
    assert ids == ["image_0001"]


# --- 계획 step 순서가 시각 배치 순서를 정한다 ---

def test_plan_step_order_orders_visual_entries():
    # video 가 먼저 등록됐지만, 계획상 image(2) 가 video(3) 보다 앞 → image 먼저 배치
    assets = [_asset("video_0001", "video"), _asset("image_0001", "image")]
    tl = build_timeline(_plan(), assets,
                        durations={"video_0001": 10.0, "image_0001": 5.0})
    visual = [e for e in tl["entries"] if e["layer"] == "visual"]
    assert [e["asset_id"] for e in visual] == ["image_0001", "video_0001"]
    assert visual[0]["asset_id"] == "image_0001"
    assert visual[0]["start_time"] == 0.0


def test_same_type_keeps_registration_order():
    assets = [_asset("image_0002", "image"), _asset("image_0001", "image")]
    tl = build_timeline(_plan(), assets,
                        durations={"image_0002": 5.0, "image_0001": 5.0})
    ids = [e["asset_id"] for e in tl["entries"]]
    assert ids == ["image_0002", "image_0001"]  # 등록 순서 보존


# --- total_duration ---

def test_total_duration_is_max_end_time():
    assets = [
        _asset("image_0001", "image"),
        _asset("video_0001", "video"),
        _asset("audio_0001", "audio"),
    ]
    tl = build_timeline(_plan(), assets,
                        durations={"image_0001": 5.0, "video_0001": 10.0, "audio_0001": 20.0})
    # visual 끝 = 15, audio 끝 = 20 → total 20
    assert tl["total_duration"] == 20.0


# --- 빈 입력 ---

def test_empty_assets_yields_empty_timeline():
    tl = build_timeline(_plan(), [])
    assert tl["entries"] == []
    assert tl["total_duration"] == 0.0
    _assert_valid(tl)


def test_only_excluded_assets_yields_empty_timeline():
    assets = [_asset("story_0001", "story"), _asset("thumbnail_0001", "thumbnail")]
    tl = build_timeline(_plan(), assets)
    assert tl["entries"] == []
    assert tl["total_duration"] == 0.0


# --- 검증/거부 ---

def test_invalid_plan_rejected():
    for bad in (None, [], {"steps": []}, {"project": "malli"}):
        try:
            build_timeline(bad, [])
        except ValueError:
            continue
        raise AssertionError(f"잘못된 plan 이 거부되지 않음: {bad!r}")


def test_invalid_assets_rejected():
    try:
        build_timeline(_plan(), "notalist")
    except ValueError:
        pass
    else:
        raise AssertionError("list 아닌 assets 가 거부되지 않음")
    try:
        build_timeline(_plan(), [{"type": "image"}])  # asset_id 없음
    except ValueError:
        return
    raise AssertionError("asset_id 없는 asset 이 거부되지 않음")


def test_nonpositive_duration_rejected():
    assets = [_asset("image_0001", "image")]
    for bad in (0, -3, 0.0):
        try:
            build_timeline(_plan(), assets, durations={"image_0001": bad})
        except ValueError:
            continue
        raise AssertionError(f"양수 아닌 duration 이 거부되지 않음: {bad}")


# --- 안전성: 배치만, 부작용 없음 ---

def test_no_side_effects_no_file_written():
    assets = [_asset("video_0001", "video")]
    build_timeline(_plan(), assets)
    assert not os.path.exists(os.path.join(_ROOT, "output", "video", "v.mp4"))


def test_output_json_serializable():
    assets = [_asset("image_0001", "image"), _asset("audio_0001", "audio")]
    tl = build_timeline(_plan(), assets)
    json.dumps(tl)  # 직렬화 가능해야 한다


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
