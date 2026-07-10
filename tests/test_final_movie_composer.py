# 최종 영화 합성기(탐지·정렬·누락·copy/재인코딩·검증실패·재개)를 가짜 runner/prober 로 검증하는 테스트
"""
Final Movie Composer 단위 테스트.

실제 ffmpeg 없이 runner/prober/validator 를 주입해 오케스트레이션만 검증한다.
케이스: 씬 정렬 / 누락 탐지 / concat 성공 / 재인코딩 폴백 / 검증 실패 / 중단 후 재개.
"""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "composer"))

from final_movie_composer import compose_movie, discover_scenes  # noqa: E402

_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16


def _make_finals(d, numbers):
    for n in numbers:
        with open(os.path.join(d, f"scene_{n:03d}_final.mp4"), "wb") as f:
            f.write(_MP4)


def _uniform_probe(paths):
    return [{"vcodec": "h264", "width": 960, "height": 960, "pix_fmt": "yuv420p",
             "acodec": "aac", "sample_rate": 24000, "duration": 5.0,
             "has_video": True, "has_audio": True} for _ in paths]


def _mixed_probe(paths):
    out = []
    for i, _ in enumerate(paths):
        out.append({"vcodec": "h264", "width": 960 if i == 0 else 1280,
                    "height": 960 if i == 0 else 720, "pix_fmt": "yuv420p",
                    "acodec": "aac", "sample_rate": 24000, "duration": 5.0,
                    "has_video": True, "has_audio": True})
    return out


def _ok_validator(path):
    return {"mp4_signature": True, "has_video": True, "has_audio": True,
            "duration": 15.0, "width": 960, "height": 960, "vcodec": "h264",
            "acodec": "aac", "ok": True}


def _bad_validator(path):
    return {"mp4_signature": False, "has_video": False, "has_audio": False, "ok": False}


def _writing_runner(record):
    """출력 파일을 만들고 args 를 기록하는 가짜 runner."""
    def _r(args):
        record.append(args)
        out = args[-1]
        with open(out, "wb") as f:
            f.write(_MP4)
        return 0, ""
    return _r


# --- 씬 정렬 ---

def test_scene_ordering():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [3, 1, 2])
        scenes, missing = discover_scenes(d)
        assert [n for n, _ in scenes] == [1, 2, 3]
        assert missing == []


# --- 누락 씬 탐지 ---

def test_missing_scene_detection():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 3])  # 2 누락
        scenes, missing = discover_scenes(d)
        assert [n for n, _ in scenes] == [1, 3]
        assert missing == [2]
        rec = []
        rep = compose_movie(d, runner=_writing_runner(rec), prober=_uniform_probe,
                            validator=_ok_validator)
        assert rep["status"] == "failed"
        assert rep["missing"] == [2]
        assert rec == []  # 병합 시도 안 함


# --- concat 성공(무재인코딩 copy) ---

def test_concatenation_success_copy():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2, 3])
        rec = []
        rep = compose_movie(d, runner=_writing_runner(rec), prober=_uniform_probe,
                            validator=_ok_validator)
        assert rep["status"] == "success"
        assert rep["method"] == "copy"
        assert rep["scenes_merged"] == 3
        assert rep["scene_order"] == [1, 2, 3]
        # copy 경로: -c copy + faststart 사용
        args = rec[0]
        assert "-c" in args and "copy" in args
        assert "+faststart" in args
        assert os.path.exists(rep["output_path"])


# --- 파라미터 불일치 → 재인코딩 폴백 ---

def test_fallback_reencode_on_mixed_params():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2])
        rec = []
        rep = compose_movie(d, runner=_writing_runner(rec), prober=_mixed_probe,
                            validator=_ok_validator)
        assert rep["status"] == "success"
        assert rep["method"] == "reencode"
        args = rec[0]
        assert "-filter_complex" in args
        assert "libx264" in args and "aac" in args
        assert "+faststart" in args


# --- copy 실패 시 재인코딩 폴백 ---

def test_copy_failure_falls_back_to_reencode():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2])
        rec = []

        def flaky_runner(args):
            rec.append(args)
            if "copy" in args:      # copy 시도는 실패
                return 1, "copy failed"
            out = args[-1]
            with open(out, "wb") as f:
                f.write(_MP4)
            return 0, ""
        rep = compose_movie(d, runner=flaky_runner, prober=_uniform_probe,
                            validator=_ok_validator)
        assert rep["status"] == "success"
        assert rep["method"] == "reencode"
        assert len(rec) == 2  # copy 시도 후 재인코딩


# --- 검증 실패 ---

def test_validation_failure():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2])
        rec = []
        rep = compose_movie(d, runner=_writing_runner(rec), prober=_mixed_probe,
                            validator=_bad_validator)
        assert rep["status"] == "failed"
        assert "검증" in rep["message"]


# --- 중단 후 재개: 유효한 최종본 존재 시 재실행 안 함 ---

def test_resume_after_interruption():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2, 3])
        with open(os.path.join(d, "malli_final.mp4"), "wb") as f:
            f.write(_MP4)
        rec = []
        rep = compose_movie(d, runner=_writing_runner(rec), prober=_uniform_probe,
                            validator=_ok_validator)
        assert rep["status"] == "success"
        assert rep["method"] == "skipped"
        assert rec == []  # 재합성 안 함


def test_resume_overwrite_forces_rebuild():
    with tempfile.TemporaryDirectory() as d:
        _make_finals(d, [1, 2, 3])
        with open(os.path.join(d, "malli_final.mp4"), "wb") as f:
            f.write(_MP4)
        rec = []
        rep = compose_movie(d, overwrite=True, runner=_writing_runner(rec),
                            prober=_uniform_probe, validator=_ok_validator)
        assert rep["status"] == "success"
        assert rep["method"] == "copy"
        assert len(rec) == 1


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
