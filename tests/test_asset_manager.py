# asset_manager.AssetManager 의 등록·조회·필터·스키마 준수를 검증하는 테스트
"""Asset Manager 단위 테스트. 에셋은 schemas/asset_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "assets"))

from asset_manager import AssetManager, ASSET_TYPES  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "asset_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

FIXED_TS = "2026-07-09T00:00:00+00:00"
ASSET_KEYS = {"asset_id", "type", "provider", "path", "status", "created_at"}


def _assert_valid(a):
    errs = sorted(_VALIDATOR.iter_errors(a), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 지원 5개 타입 등록 ---

def test_register_all_five_types():
    mgr = AssetManager()
    cases = [
        ("story", None, "output/text/s.txt"),
        ("image", "Nano Banana", "output/image/i.png"),
        ("video", "Higgsfield", "output/video/v.mp4"),
        ("audio", "Edge TTS", "output/audio/a.mp3"),
        ("thumbnail", "Nano Banana", "output/image/t.png"),
    ]
    for typ, prov, path in cases:
        a = mgr.register(typ, prov, path, created_at=FIXED_TS)
        assert set(a.keys()) == ASSET_KEYS
        assert a["type"] == typ
        assert a["provider"] == prov
        assert a["path"] == path
        assert a["status"] == "ready"
        assert a["created_at"] == FIXED_TS
        _assert_valid(a)
    assert mgr.count() == 5
    assert ASSET_TYPES == {"story", "image", "video", "audio", "thumbnail"}


def test_auto_asset_id_sequential_and_unique():
    mgr = AssetManager()
    a1 = mgr.register("image", "Nano Banana", "x.png")
    a2 = mgr.register("video", "Higgsfield", "y.mp4")
    assert a1["asset_id"] == "image_0001"
    assert a2["asset_id"] == "video_0002"
    ids = [a["asset_id"] for a in mgr.list_assets()]
    assert len(ids) == len(set(ids))  # 유일


def test_explicit_asset_id():
    mgr = AssetManager()
    a = mgr.register("audio", "Edge TTS", "a.mp3", asset_id="voice-main")
    assert a["asset_id"] == "voice-main"
    assert mgr.get("voice-main") is a


def test_duplicate_asset_id_rejected():
    mgr = AssetManager()
    mgr.register("image", "Nano Banana", "x.png", asset_id="dup")
    try:
        mgr.register("video", "Higgsfield", "y.mp4", asset_id="dup")
    except ValueError:
        return
    raise AssertionError("중복 asset_id 가 거부되지 않음")


def test_default_created_at_is_iso_string():
    mgr = AssetManager()
    a = mgr.register("image", "Nano Banana", "x.png")  # created_at 미지정
    assert isinstance(a["created_at"], str) and len(a["created_at"]) >= 10
    assert "T" in a["created_at"]  # ISO 8601


# --- 상태 ---

def test_status_values():
    mgr = AssetManager()
    r = mgr.register("image", "Nano Banana", "x.png", status="ready")
    p = mgr.register("video", "Higgsfield", None, status="pending")
    fst = mgr.register("audio", "Edge TTS", None, status="failed")
    assert r["status"] == "ready"
    assert p["status"] == "pending"
    assert fst["status"] == "failed"
    for a in (r, p, fst):
        _assert_valid(a)


def test_invalid_type_rejected():
    mgr = AssetManager()
    try:
        mgr.register("gif", "Nano Banana", "x.gif")
    except ValueError:
        return
    raise AssertionError("잘못된 타입이 거부되지 않음")


def test_invalid_status_rejected():
    mgr = AssetManager()
    try:
        mgr.register("image", "Nano Banana", "x.png", status="running")
    except ValueError:
        return
    raise AssertionError("잘못된 상태가 거부되지 않음")


# --- 조회/필터 ---

def test_list_filter_by_type():
    mgr = AssetManager()
    mgr.register("image", "Nano Banana", "a.png")
    mgr.register("image", "Nano Banana", "b.png")
    mgr.register("video", "Higgsfield", "c.mp4")
    assert len(mgr.list_assets(type="image")) == 2
    assert len(mgr.list_assets(type="video")) == 1
    assert len(mgr.list_assets()) == 3


def test_list_filter_by_status():
    mgr = AssetManager()
    mgr.register("image", "Nano Banana", "a.png", status="ready")
    mgr.register("video", "Higgsfield", None, status="failed")
    assert len(mgr.list_assets(status="failed")) == 1
    assert len(mgr.list_assets(status="ready")) == 1


def test_get_missing_returns_none():
    mgr = AssetManager()
    assert mgr.get("nope") is None


def test_to_dict_shape_and_schema():
    mgr = AssetManager()
    mgr.register("story", None, "s.txt", created_at=FIXED_TS)
    mgr.register("audio", "Edge TTS", "a.mp3", created_at=FIXED_TS)
    d = mgr.to_dict()
    assert set(d.keys()) == {"assets"}
    for a in d["assets"]:
        _assert_valid(a)
    json.dumps(d)


# --- 안전성: 레지스트리 전용, 부작용 없음 ---

def test_no_side_effects_no_file_written():
    mgr = AssetManager()
    a = mgr.register("audio", "Edge TTS", "output/audio/should_not_exist.mp3")
    # 등록은 파일을 만들지 않는다
    assert not os.path.exists(os.path.join(_ROOT, a["path"]))


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
