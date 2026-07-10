# 멀티씬 파이프라인 오케스트레이션(순서·재개·skip·실패정지·상태·중복호출없음)을 mock 단계로 검증하는 테스트
"""
Multi-Scene Pipeline 단위 테스트.

실 provider/네트워크 없이 가짜 steps 를 주입해 오케스트레이션만 검증한다.
요구 케이스: 전체 순서 처리 / 부분 완료 재개 / 유효 자산 skip / 실패 안전 정지 /
씬별 상태 보고 / 중복 provider 호출 없음.
"""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "pipeline"))

from scene_pipeline import (  # noqa: E402
    run_pipeline, scene_paths, valid_png, valid_mp4, valid_mp3,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16
_MP3 = b"ID3" + b"\x00" * 32


def _story(path, n=3):
    scenes = [{"scene_number": i, "narration": f"나레이션{i}", "image_prompt": f"img{i}",
               "video_prompt": f"vid{i}", "duration": 8.0} for i in range(1, n + 1)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, ensure_ascii=False)


def _writer(data):
    def _w(out_path, *a, **k):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
    return _w


def _recording_steps(calls):
    """호출을 기록하는 가짜 steps. 각 단계는 유효한 산출물을 만든다."""
    def image(scene, out_path):
        calls.append(("image", scene["scene_number"]))
        _writer(_PNG)(out_path)

    def video(scene, image_path, out_path):
        calls.append(("video", scene["scene_number"]))
        assert os.path.exists(image_path), "영상 단계는 이미지가 선행돼야 한다."
        _writer(_MP4)(out_path)

    def tts(scene, out_path):
        calls.append(("tts", scene["scene_number"]))
        _writer(_MP3)(out_path)

    def compose(scene, video_path, audio_path, out_path):
        calls.append(("compose", scene["scene_number"]))
        assert os.path.exists(video_path) and os.path.exists(audio_path)
        _writer(_MP4)(out_path)

    return {"image": image, "video": video, "tts": tts, "compose": compose}


# --- 전체 씬을 순서대로 처리 ---

def test_all_scenes_processed_in_order():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 3)
        calls = []
        rep = run_pipeline(story, d, steps=_recording_steps(calls))
        assert rep["status"] == "success"
        assert [s["scene_number"] for s in rep["scenes"]] == [1, 2, 3]
        # 씬별 단계 순서 + 씬 간 순서
        assert calls == [
            ("image", 1), ("video", 1), ("tts", 1), ("compose", 1),
            ("image", 2), ("video", 2), ("tts", 2), ("compose", 2),
            ("image", 3), ("video", 3), ("tts", 3), ("compose", 3),
        ]
        for n in (1, 2, 3):
            assert valid_mp4(scene_paths(d, n)["final"])


# --- 부분 완료에서 재개 ---

def test_resume_from_partial_output():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 3)
        # 씬1 전체 + 씬2 이미지까지 선점 생성
        p1, p2 = scene_paths(d, 1), scene_paths(d, 2)
        for key, data in (("image", _PNG), ("video", _MP4), ("audio", _MP3), ("final", _MP4)):
            _writer(data)(p1[key])
        _writer(_PNG)(p2["image"])

        calls = []
        rep = run_pipeline(story, d, steps=_recording_steps(calls))
        assert rep["status"] == "success"
        # 씬1 은 어떤 단계도 재호출되지 않음(모두 skip)
        assert all(c[1] != 1 for c in calls)
        # 씬2 이미지도 skip, video/tts/compose 만 호출
        assert ("image", 2) not in calls
        assert ("video", 2) in calls and ("compose", 2) in calls
        assert rep["scenes"][0]["steps"]["image"]["status"] == "skipped"
        assert rep["scenes"][1]["steps"]["image"]["status"] == "skipped"
        assert rep["scenes"][1]["steps"]["video"]["status"] == "generated"


# --- 유효한 기존 자산 skip / 중복 호출 없음 ---

def test_skip_valid_assets_no_duplicate_calls():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 2)
        # 모든 자산 선점 → 아무 단계도 호출되면 안 됨
        for n in (1, 2):
            p = scene_paths(d, n)
            for key, data in (("image", _PNG), ("video", _MP4), ("audio", _MP3), ("final", _MP4)):
                _writer(data)(p[key])
        calls = []
        rep = run_pipeline(story, d, steps=_recording_steps(calls))
        assert rep["status"] == "success"
        assert calls == []  # 중복 provider 호출 없음
        for sc in rep["scenes"]:
            for step in sc["steps"].values():
                assert step["status"] == "skipped"


# --- overwrite=True 는 재생성 ---

def test_overwrite_regenerates():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 1)
        p = scene_paths(d, 1)
        for key, data in (("image", _PNG), ("video", _MP4), ("audio", _MP3), ("final", _MP4)):
            _writer(data)(p[key])
        calls = []
        rep = run_pipeline(story, d, steps=_recording_steps(calls), overwrite=True)
        assert rep["status"] == "success"
        assert ("image", 1) in calls and ("compose", 1) in calls


# --- 실패 시 안전 정지 ---

def test_failure_stops_safely():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 3)
        calls = []
        steps = _recording_steps(calls)
        orig_tts = steps["tts"]

        def failing_tts(scene, out_path):
            if scene["scene_number"] == 2:
                raise RuntimeError("TTS 백엔드 다운")
            orig_tts(scene, out_path)
        steps["tts"] = failing_tts

        rep = run_pipeline(story, d, steps=steps)
        assert rep["status"] == "failed"
        assert rep["failed_scene"] == 2
        # 씬3 은 시작조차 안 함(안전 정지)
        assert [s["scene_number"] for s in rep["scenes"]] == [1, 2]
        assert all(c[1] != 3 for c in calls)
        # 씬2 는 tts 에서 실패, compose 는 미실행
        s2 = rep["scenes"][1]
        assert s2["failed_step"] == "tts"
        assert s2["steps"]["tts"]["status"] == "failed"
        assert "TTS 백엔드 다운" in s2["steps"]["tts"]["error"]
        assert "compose" not in s2["steps"]


# --- 씬별 상태 보고 ---

def test_per_scene_status_reporting():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 2)
        calls = []
        rep = run_pipeline(story, d, steps=_recording_steps(calls))
        assert set(rep.keys()) >= {"status", "scenes"}
        for sc in rep["scenes"]:
            assert set(sc["steps"].keys()) == {"image", "video", "tts", "compose"}
            for step in sc["steps"].values():
                assert step["status"] in ("generated", "skipped", "failed")
                assert "path" in step and "error" in step


# --- 기본은 mock (real 아님) ---

def test_default_mode_is_mock_offline():
    with tempfile.TemporaryDirectory() as d:
        story = os.path.join(d, "story.json")
        _story(story, 1)
        rep = run_pipeline(story, d)  # steps/real 미지정 → mock 기본
        assert rep["status"] == "success"
        p = scene_paths(d, 1)
        assert valid_png(p["image"]) and valid_mp4(p["video"])
        assert valid_mp3(p["audio"]) and valid_mp4(p["final"])


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
