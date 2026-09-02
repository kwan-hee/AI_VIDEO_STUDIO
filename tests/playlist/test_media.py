"""실제 ffmpeg/Pillow 를 쓰는 검사. 합성 자산만 사용한다 (크레딧 0)."""
import pytest

from playlist_studio import audio as A
from playlist_studio import testkit as TK
from playlist_studio import visuals as V
from playlist_studio.util import which

pytestmark = pytest.mark.skipif(
    not (which("ffmpeg") and which("ffprobe")), reason="ffmpeg 없음")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    d = tmp_path_factory.mktemp("clips")
    return [TK.synth_mp3(d / f"{i:02d}.mp3", seconds=8 + i, bpm=70 + i * 5, seed=i)
            for i in range(1, 4)]


def test_probe_reads_real_metadata(clips):
    info = A.probe(clips[0])
    assert info.ok and info.codec == "mp3"
    assert 8.5 < info.duration < 10.0
    assert info.sample_rate == 44100


def test_missing_and_empty_files_are_rejected(tmp_path):
    assert not A.probe(tmp_path / "nope.mp3").ok
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert "0바이트 파일" in A.probe(empty).issues


def test_garbage_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"this is definitely not audio" * 50)
    assert not A.probe(bad).ok


def test_too_short_is_excluded(clips):
    info = A.validate(clips[0], min_seconds=60)
    assert not info.ok and any("너무 짧음" in i for i in info.issues)


def test_silence_is_detected(tmp_path):
    import subprocess
    from playlist_studio.util import ffmpeg
    p = tmp_path / "silent.wav"
    ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "6", str(p)])
    assert A.silence_ratio(p) > 0.8
    info = A.validate(p, min_seconds=3)
    assert not info.ok


def test_synth_clip_is_not_silent(clips):
    assert A.silence_ratio(clips[0]) < 0.3


def test_normalize_hits_targets(clips, tmp_path):
    out = tmp_path / "n.wav"
    A.normalize(clips[0], out)
    m = A.measure_loudness(out)
    assert abs(m["input_i"] - A.TARGET_I) < 1.0        # -14 LUFS 부근
    assert m["input_tp"] <= A.TARGET_TP + 0.5          # True Peak -1dB 이하


def test_concat_without_crossfade_sums_durations(clips, tmp_path):
    norms = []
    for i, c in enumerate(clips, 1):
        n = tmp_path / f"n{i}.wav"
        A.normalize(c, n)
        norms.append(n)
    r = A.concat(norms, tmp_path / "m.wav", crossfade=0)
    assert abs(r["duration"] - sum(r["track_durations"])) < 0.2
    assert r["track_starts"][0] == 0.0


def test_crossfade_shortens_total_and_shifts_starts(clips, tmp_path):
    norms = []
    for i, c in enumerate(clips, 1):
        n = tmp_path / f"x{i}.wav"
        A.normalize(c, n)
        norms.append(n)
    xf = 1.0
    r = A.concat(norms, tmp_path / "mx.wav", crossfade=xf)
    expected = sum(r["track_durations"]) - (len(norms) - 1) * xf
    assert abs(r["duration"] - expected) < 0.2
    assert abs(r["track_starts"][1] - (r["track_durations"][0] - xf)) < 0.05


def test_crossfade_clamped_for_short_clips(tmp_path):
    a = TK.synth_mp3(tmp_path / "s1.mp3", seconds=4, seed=1)
    b = TK.synth_mp3(tmp_path / "s2.mp3", seconds=4, seed=2)
    r = A.concat([a, b], tmp_path / "sm.wav", crossfade=10.0)
    assert 0 < r["crossfade"] < 4.0        # 곡보다 긴 크로스페이드는 줄인다


def test_concat_refuses_broken_input(clips, tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio")
    with pytest.raises(ValueError, match="손상"):
        A.concat([clips[0], bad], tmp_path / "z.wav")


# ---------------------------------------------------------------- 이미지
def test_thumbnail_is_1280x720_and_readable(tmp_path):
    from PIL import Image
    bg = TK.synth_image(tmp_path / "bg.png", seed=3)
    out = tmp_path / "thumb.png"
    r = V.compose_thumbnail(bg, out, title="비 오는 날 창가에서",
                            subtitle="집중이 필요한 밤", badge="LOFI", language="ko")
    with Image.open(out) as im:
        assert im.size == (1280, 720)
    assert r["overflow"] is False
    assert out.stat().st_size < 2 * 1024 * 1024      # YouTube 2MB 한도


def test_thumbnail_shrinks_long_titles_instead_of_clipping(tmp_path):
    bg = TK.synth_image(tmp_path / "bg2.png", seed=4)
    short = V.compose_thumbnail(bg, tmp_path / "a.png", title="짧은 제목", language="ko")
    long = V.compose_thumbnail(bg, tmp_path / "b.png",
                               title="아주 긴 제목을 넣어 자동 축소가 동작하는지 확인한다 " * 2,
                               language="ko")
    assert long["title_size"] < short["title_size"]
    assert len(long["title_lines"]) <= 3


def test_fit_text_flags_true_overflow(tmp_path):
    from playlist_studio.fonts import resolve
    fc = resolve("ko")
    fit = V.fit_text("가" * 400, fc.file, max_width=300, max_height=80,
                     start_size=60, min_size=40, max_lines=1)
    assert fit.overflow is True


# ---------------------------------------------------------------- 렌더 재사용
def test_damaged_segment_is_not_reused(tmp_path):
    """잘리거나 손상된 중간 파일을 그대로 이어붙이면 안 된다."""
    from playlist_studio.render import Segment, build_background, segment_is_reusable

    img = TK.synth_image(tmp_path / "bg.png", seed=2)
    work = tmp_path / "work"
    out = tmp_path / "bg.mp4"
    segs = [Segment(1, img, 2.0)]
    build_background(segs, out, work, preset="ultrafast", crf=30)

    segfile = work / "seg_01.mp4"
    assert segment_is_reusable(segfile, 2.0)
    assert not segment_is_reusable(segfile, 8.0)      # 길이가 다르면 재사용 불가

    segfile.write_bytes(b"x" * 100_000)                # 크기는 크지만 깨진 파일
    assert not segment_is_reusable(segfile, 2.0)

    assert not segment_is_reusable(tmp_path / "missing.mp4", 2.0)


def test_final_mp4_meets_spec(tmp_path):
    """1920x1080 / 30fps / h264 yuv420p / aac / faststart / 길이 일치."""
    from playlist_studio.align import TimedLine
    from playlist_studio.render import (Segment, build_background,
                                        build_waveform, compose_final, probe_video)
    from playlist_studio.subtitles import TrackCard, write_ass

    work = tmp_path / "w"
    clip = TK.synth_mp3(tmp_path / "a.mp3", seconds=6, seed=1)
    master = tmp_path / "master.wav"
    A.normalize(clip, master)
    dur = A.probe(master).duration

    img = TK.synth_image(tmp_path / "bg.png", seed=1)
    bg = build_background([Segment(1, img, dur)], tmp_path / "bg.mp4", work,
                          preset="ultrafast", crf=30)
    waves = build_waveform(master, tmp_path / "w.mp4")
    ass = write_ass(tmp_path / "s.ass",
                    [TimedLine(1, 0, "가사 한 줄", 1.0, 3.0)],
                    cards=[TrackCard(1, "제목", "부제", 0.0, dur)],
                    intro=(0.3, 3.0, "플레이리스트", "1곡"))
    intro_img = TK.synth_image(tmp_path / "intro.png", seed=9)

    out = compose_final(bg, waves, master, ass, tmp_path / "final.mp4",
                        intro_image=intro_img, intro_seconds=3.0,
                        crf=30, preset="ultrafast")
    v = probe_video(out)
    assert (v["width"], v["height"]) == (1920, 1080)
    assert v["fps"] == "30/1"
    assert v["video_codec"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert v["audio_codec"] == "aac" and v["audio_sample_rate"] == 48000
    assert v["has_faststart"] is True
    assert abs(v["video_duration"] - v["audio_duration"]) < 0.5
    assert abs(v["duration"] - dur) < 1.0


def test_short_song_is_a_warning_not_a_failure(tmp_path):
    """생성 모델은 목표 길이를 정확히 맞추지 않는다.

    짧게 나왔다고 '손상'으로 처리하면 멀쩡한 곡이 렌더링에서 빠진다.
    """
    clip = TK.synth_mp3(tmp_path / "short.mp3", seconds=40, seed=1)
    info = A.validate(clip, min_seconds=20, expect_seconds=180)
    assert info.ok is True                       # 렌더링에 포함된다
    assert info.issues == ()
    assert any("목표 길이" in w for w in info.warnings)


def test_real_damage_is_still_a_failure(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all" * 100)
    info = A.validate(bad, min_seconds=1, expect_seconds=180)
    assert info.ok is False and info.issues


def test_too_short_to_be_usable_is_still_a_failure(tmp_path):
    clip = TK.synth_mp3(tmp_path / "tiny.mp3", seconds=3, seed=1)
    info = A.validate(clip, min_seconds=20, expect_seconds=180)
    assert info.ok is False
    assert any("너무 짧음" in i for i in info.issues)
