# ffmpeg_composer.compose() 의 합성 결과·인자 구성·거부 규칙·스키마 준수를 검증하는 테스트 (ffmpeg 는 가짜 runner 로 대체)
"""FFmpeg Composer 단위 테스트. 네트워크/ffmpeg 없이 가짜 runner 로 검증. 결과는 schemas/composition_result_schema.json 으로 검증."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "composer"))

import ffmpeg_composer as FC  # noqa: E402
from ffmpeg_composer import compose, _build_args  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "composition_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _fake_runner(args, output_path):
    # ffmpeg 없이 더미 mp4 바이트 기록
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42dummy")


def _fail_runner(args, output_path):
    raise RuntimeError("ffmpeg 없음")


def _touch(dir_, name, data=b"dummy-media"):
    p = os.path.join(dir_, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


# --- 성공 합성 ---

def test_video_plus_audio_compose():
    with tempfile.TemporaryDirectory() as d:
        vid = _touch(d, "clip.mp4")
        aud = _touch(d, "voice.mp3")
        out = os.path.join(d, "out")
        r = compose({"videos": [vid], "audio": [aud],
                     "execution_plan": {"project": "baseball"}},
                    output_dir=out, runner=_fake_runner)
        assert r["status"] == "success"
        assert r["provider"] == "FFmpeg"
        assert r["output_path"].endswith(".mp4")
        assert r["format"] == "mp4"
        assert r["inputs_used"] == {"images": 0, "videos": 1, "audio": 1}
        # 실제 산출 파일 생성됨
        files = [f for f in os.listdir(out) if f.endswith(".mp4")]
        assert len(files) == 1
        _assert_valid(r)


def test_images_slideshow_compose():
    with tempfile.TemporaryDirectory() as d:
        imgs = [_touch(d, "a.png"), _touch(d, "b.png")]
        aud = _touch(d, "v.mp3")
        out = os.path.join(d, "out")
        r = compose({"images": imgs, "audio": [aud]}, output_dir=out, runner=_fake_runner)
        assert r["status"] == "success"
        assert r["inputs_used"] == {"images": 2, "videos": 0, "audio": 1}
        _assert_valid(r)


def test_default_output_dir_is_output_final():
    with tempfile.TemporaryDirectory() as d:
        vid = _touch(d, "clip.mp4")
        r = compose({"videos": [vid]}, runner=_fake_runner)  # output_dir 미지정
        try:
            assert r["status"] == "success"
            assert r["output_path"].startswith("output/final/")
            assert os.path.exists(os.path.join(_ROOT, r["output_path"]))
        finally:
            p = os.path.join(_ROOT, r["output_path"])
            if os.path.exists(p):
                os.remove(p)


# --- 인자 구성 ---

def test_build_args_single_video_audio():
    args = _build_args(["v.mp4"], [], [], "out.mp4")  # 비디오만
    assert "-i" in args and "v.mp4" in args and args[-1] == "out.mp4"
    assert "libx264" in args


def test_build_args_multi_video_concat():
    args = _build_args([], ["a.mp4", "b.mp4"], ["s.mp3"], "out.mp4")
    joined = " ".join(args)
    assert "concat=n=2" in joined
    assert args[-1] == "out.mp4"


def test_build_args_images_slideshow():
    args = _build_args(["a.png", "b.png"], [], [], "out.mp4")
    joined = " ".join(args)
    assert "-loop" in args and "concat=n=2" in joined


def test_build_args_no_visual_raises():
    try:
        _build_args([], [], ["s.mp3"], "out.mp4")
    except ValueError:
        return
    raise AssertionError("영상 소스 없음이 거부되지 않음")


# --- 실패/거부 ---

def test_missing_file_failed():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out")
        r = compose({"videos": [os.path.join(d, "nope.mp4")]}, output_dir=out, runner=_fake_runner)
        assert r["status"] == "failed"
        assert r["output_path"] is None
        _assert_valid(r)


def test_runner_failure_reported():
    with tempfile.TemporaryDirectory() as d:
        vid = _touch(d, "clip.mp4")
        out = os.path.join(d, "out")
        r = compose({"videos": [vid]}, output_dir=out, runner=_fail_runner)
        assert r["status"] == "failed"
        assert "실패" in r["message"]
        _assert_valid(r)


def test_no_visual_input_raises():
    try:
        compose({"audio": ["x.mp3"]}, runner=_fake_runner)
    except ValueError:
        return
    raise AssertionError("이미지/비디오 없음이 거부되지 않음")


def test_bad_input_rejected():
    for bad in [None, "x", 3, []]:
        try:
            compose(bad, runner=_fake_runner)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


# --- ffmpeg 바이너리 탐지 ---

def test_ffmpeg_binary_probe():
    # 환경에 따라 있거나 없다. bool 계약만 확인.
    assert isinstance(FC.ffmpeg_available(), bool)


# --- 옵트인 실제 합성 (RUN_REAL_FFMPEG=1 이고 ffmpeg 존재 시) ---

def test_real_compose_optional():
    if os.environ.get("RUN_REAL_FFMPEG") != "1" or not FC.ffmpeg_available():
        return  # ffmpeg 없거나 옵트인 아님 → 건너뜀
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        vid = os.path.join(d, "src.mp4")
        binary = FC.ffmpeg_binary()
        subprocess.run([binary, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
                        vid], check=True, capture_output=True)
        out = os.path.join(d, "out")
        r = compose({"videos": [vid]}, output_dir=out)
        assert r["status"] == "success"
        assert os.path.getsize(os.path.join(out, os.path.basename(r["output_path"]))) > 0


# --- Timeline 통합 (Sprint 13 enhancement) ---
# compose_from_timeline: Timeline Builder 출력 + Asset Manager 레지스트리로 합성.
# 기존 compose() 는 건드리지 않는다.

from ffmpeg_composer import compose_from_timeline  # noqa: E402


def _asset(asset_id, type, path, status="ready"):
    return {"asset_id": asset_id, "type": type, "provider": None,
            "path": path, "status": status, "created_at": "2026-07-09T00:00:00+00:00"}


def _entry(asset_id, asset_type, start, dur, layer):
    return {"asset_id": asset_id, "asset_type": asset_type, "start_time": start,
            "end_time": round(start + dur, 3), "duration": dur, "layer": layer}


class _Capture:
    def __init__(self):
        self.args = None

    def __call__(self, args, output_path):
        self.args = args
        with open(output_path, "wb") as f:
            f.write(b"\x00\x00\x00\x18ftypmp42dummy")


def test_timeline_image_audio_compose():
    with tempfile.TemporaryDirectory() as d:
        img = _touch(d, "01.png")
        aud = _touch(d, "voice.mp3")
        out = os.path.join(d, "out")
        assets = [_asset("image_0001", "image", img), _asset("audio_0001", "audio", aud)]
        timeline = {
            "project": "malli",
            "entries": [_entry("image_0001", "image", 0.0, 5.0, "visual"),
                        _entry("audio_0001", "audio", 0.0, 5.0, "audio")],
            "total_duration": 5.0,
        }
        r = compose_from_timeline(timeline, assets, output_dir=out, runner=_fake_runner)
        assert r["status"] == "success"
        assert r["provider"] == "FFmpeg"
        assert r["format"] == "mp4"
        assert r["inputs_used"] == {"images": 1, "videos": 0, "audio": 1}
        files = [f for f in os.listdir(out) if f.endswith(".mp4")]
        assert len(files) == 1
        _assert_valid(r)


def test_timeline_visual_order_and_duration_in_args():
    # video 가 등록상 먼저여도 timeline start_time 순서(이미지 0s, 비디오 5s)를 따른다.
    with tempfile.TemporaryDirectory() as d:
        img = _touch(d, "01.png")
        vid = _touch(d, "02.mp4")
        out = os.path.join(d, "out")
        assets = [_asset("video_0002", "video", vid), _asset("image_0001", "image", img)]
        timeline = {
            "project": "malli",
            "entries": [_entry("image_0001", "image", 0.0, 3.0, "visual"),
                        _entry("video_0002", "video", 3.0, 7.0, "visual")],
            "total_duration": 10.0,
        }
        cap = _Capture()
        r = compose_from_timeline(timeline, assets, output_dir=out, runner=cap)
        assert r["status"] == "success"
        # 입력 순서: 이미지(start 0) 먼저, 비디오(start 3) 다음
        assert cap.args.index(img) < cap.args.index(vid)
        # 각 클립 duration 이 -t 값으로 반영
        assert "3.0" in cap.args  # 이미지 duration
        assert "7.0" in cap.args  # 비디오 duration
        assert "concat=n=2" in " ".join(cap.args)


def test_timeline_multi_audio_concat():
    with tempfile.TemporaryDirectory() as d:
        img = _touch(d, "01.png")
        a1 = _touch(d, "a1.mp3")
        a2 = _touch(d, "a2.mp3")
        out = os.path.join(d, "out")
        assets = [_asset("image_0001", "image", img),
                  _asset("audio_0001", "audio", a1), _asset("audio_0002", "audio", a2)]
        timeline = {
            "project": "baseball",
            "entries": [_entry("image_0001", "image", 0.0, 5.0, "visual"),
                        _entry("audio_0001", "audio", 0.0, 3.0, "audio"),
                        _entry("audio_0002", "audio", 3.0, 2.0, "audio")],
            "total_duration": 5.0,
        }
        cap = _Capture()
        r = compose_from_timeline(timeline, assets, output_dir=out, runner=cap)
        assert r["status"] == "success"
        assert r["inputs_used"]["audio"] == 2
        assert "concat=n=2:v=0:a=1" in " ".join(cap.args)


def test_timeline_missing_asset_id_failed():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out")
        timeline = {
            "project": "malli",
            "entries": [_entry("ghost_0001", "image", 0.0, 5.0, "visual")],
            "total_duration": 5.0,
        }
        r = compose_from_timeline(timeline, [], output_dir=out, runner=_fake_runner)
        assert r["status"] == "failed"
        assert r["output_path"] is None
        _assert_valid(r)


def test_timeline_asset_without_path_failed():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out")
        assets = [_asset("image_0001", "image", None)]  # path 없음
        timeline = {
            "project": "malli",
            "entries": [_entry("image_0001", "image", 0.0, 5.0, "visual")],
            "total_duration": 5.0,
        }
        r = compose_from_timeline(timeline, assets, output_dir=out, runner=_fake_runner)
        assert r["status"] == "failed"
        _assert_valid(r)


def test_timeline_no_visual_raises():
    with tempfile.TemporaryDirectory() as d:
        aud = _touch(d, "voice.mp3")
        assets = [_asset("audio_0001", "audio", aud)]
        timeline = {
            "project": "malli",
            "entries": [_entry("audio_0001", "audio", 0.0, 5.0, "audio")],
            "total_duration": 5.0,
        }
        try:
            compose_from_timeline(timeline, assets, runner=_fake_runner)
        except ValueError:
            return
        raise AssertionError("시각 항목 없음이 거부되지 않음")


def test_timeline_bad_input_rejected():
    for bad in [None, "x", 3, []]:
        try:
            compose_from_timeline(bad, [], runner=_fake_runner)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 timeline 이 거부되지 않음: {bad!r}")


def test_existing_compose_unchanged_by_enhancement():
    # 기존 compose() 경로가 그대로 동작함을 재확인 (enhancement 가 회귀 없음).
    with tempfile.TemporaryDirectory() as d:
        vid = _touch(d, "clip.mp4")
        out = os.path.join(d, "out")
        r = compose({"videos": [vid]}, output_dir=out, runner=_fake_runner)
        assert r["status"] == "success"
        assert r["inputs_used"] == {"images": 0, "videos": 1, "audio": 0}


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
