"""최종 영상 렌더링 (FFmpeg).

3단계로 나눈다. 각 단계 산출물은 work/ 에 남기 때문에, 중간에 실패해도
성공한 단계는 다시 만들지 않는다.

  A. 배경 영상   - 곡별 이미지 + 느린 줌/패닝 + 필름 그레인
  B. 파형 영상   - showwaves
  C. 최종 합성   - 배경 + 파형 + 인트로 이미지 + ASS 자막 + AAC 오디오
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .paths import ProjectPaths
from .util import ensure_dir, ffmpeg, ffprobe_json, rel_posix, run, require

WIDTH, HEIGHT, FPS = 1920, 1080, 30
PRE_W, PRE_H = 2304, 1296        # 줌/패닝 여유분
WAVE_H = 140

WAVE_COLORS = {
    "black-gray-red": "0xC4262E|0x707078",
    "warm-film": "0xE89644|0xA8825C",
    "cold-neon": "0xC62E98|0x2E88C6",
    "paper-grain": "0xB06042|0x8C8A82",
}


@dataclass
class Segment:
    index: int
    image: Path
    duration: float


def _fmt(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def probe_video(path: Path) -> dict:
    data = ffprobe_json(path)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    return {
        "duration": float(fmt.get("duration") or 0.0),
        "video_duration": float(v.get("duration") or fmt.get("duration") or 0.0),
        "audio_duration": float(a.get("duration") or fmt.get("duration") or 0.0),
        "width": int(v.get("width") or 0), "height": int(v.get("height") or 0),
        "video_codec": v.get("codec_name", ""), "pix_fmt": v.get("pix_fmt", ""),
        "fps": v.get("r_frame_rate", ""), "audio_codec": a.get("codec_name", ""),
        "audio_sample_rate": int(a.get("sample_rate") or 0),
        "audio_channels": int(a.get("channels") or 0),
        "bit_rate": int(float(fmt.get("bit_rate") or 0)),
        "format_name": fmt.get("format_name", ""),
        "has_faststart": _has_faststart(path),
    }


def _has_faststart(path: Path) -> bool:
    """moov 아톰이 앞쪽에 있는지 확인 (스트리밍 시작 속도)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(2 * 1024 * 1024)
        moov, mdat = head.find(b"moov"), head.find(b"mdat")
        if moov == -1:
            return False
        return mdat == -1 or moov < mdat
    except Exception:
        return False


# ---------------------------------------------------------------- A. 배경
def prescale_image(src: Path, dst: Path) -> Path:
    """줌/패닝 여유를 둔 크기로 한 번만 확대. 매 프레임 scale 을 피한다."""
    ensure_dir(Path(dst).parent)
    ffmpeg(["-i", str(src), "-vf",
            f"scale={PRE_W}:{PRE_H}:force_original_aspect_ratio=increase,"
            f"crop={PRE_W}:{PRE_H}", str(dst)])
    return Path(dst)


def render_segment(image: Path, out: Path, duration: float, *, index: int = 0,
                   grain: int = 7, preset: str = "veryfast", crf: int = 20) -> Path:
    """곡 하나 분량의 배경 영상. 방향을 곡마다 바꿔 지루하지 않게 한다."""
    ensure_dir(Path(out).parent)
    sign = 1 if index % 2 == 0 else -1
    zoom_in = (index % 3) != 2
    if zoom_in:
        z = "min(1+0.00040*on,1.12)"
    else:
        z = "max(1.12-0.00040*on,1.0)"
    x = f"iw/2-(iw/zoom/2)+sin(on/{200 + index * 17})*{70 * sign}"
    y = f"ih/2-(ih/zoom/2)+cos(on/{260 + index * 13})*40"
    flt = (
        f"[0:v]zoompan=z='{z}':d=1:x='{x}':y='{y}':s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"setsar=1,noise=alls={grain}:allf=t+u,format=yuv420p[v]"
    )
    ffmpeg(["-loop", "1", "-framerate", str(FPS), "-t", _fmt(duration), "-i", str(image),
            "-filter_complex", flt, "-map", "[v]",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-r", str(FPS), "-pix_fmt", "yuv420p", str(out)],
           timeout=7200)
    return Path(out)


def concat_segments(segments: Sequence[Path], out: Path, work: Path) -> Path:
    """무손실 concat (재인코딩 없음)."""
    ensure_dir(Path(out).parent)
    listfile = Path(work) / "segments.txt"
    listfile.write_text(
        "".join(f"file '{Path(s).resolve().as_posix()}'\n" for s in segments),
        encoding="utf-8",
    )
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listfile),
            "-c", "copy", str(out)], timeout=3600)
    return Path(out)


def segment_is_reusable(path: Path, expected_duration: float,
                        tolerance: float = 0.25) -> bool:
    """중간 세그먼트를 그대로 써도 되는지 ffprobe 로 실측 확인.

    크기만 보면 잘린 파일이나 손상된 파일을 그대로 이어붙이게 된다.
    실제로 열어서 규격과 길이가 맞는지 확인한다.
    """
    path = Path(path)
    if not path.exists() or path.stat().st_size < 4096:
        return False
    try:
        v = probe_video(path)
    except Exception:
        return False
    if (v["width"], v["height"]) != (WIDTH, HEIGHT):
        return False
    if v["video_codec"] != "h264":
        return False
    return abs(v["video_duration"] - expected_duration) <= tolerance


def build_background(segments: Sequence[Segment], out: Path, work: Path, *,
                     reuse: bool = True, preset: str = "veryfast",
                     crf: int = 20, grain: int = 7,
                     progress=None) -> Path:
    work = ensure_dir(Path(work))
    seg_files: list[Path] = []
    for i, seg in enumerate(segments):
        pre = work / f"pre_{seg.index:02d}.png"
        segf = work / f"seg_{seg.index:02d}.mp4"
        if not (reuse and segment_is_reusable(segf, seg.duration)):
            if not (reuse and pre.exists() and pre.stat().st_size > 4096):
                prescale_image(seg.image, pre)
            if progress:
                progress(f"  배경 세그먼트 {seg.index:02d} 렌더 중 ({seg.duration:.0f}초)")
            render_segment(pre, segf, seg.duration, index=i, grain=grain,
                           preset=preset, crf=crf)
        elif progress:
            progress(f"  배경 세그먼트 {seg.index:02d} 재사용 (검증 통과)")
        seg_files.append(segf)
    return concat_segments(seg_files, out, work)


# ---------------------------------------------------------------- B. 파형
def build_waveform(audio: Path, out: Path, *, preset_key: str = "black-gray-red",
                   height: int = WAVE_H, crf: int = 28) -> Path:
    ensure_dir(Path(out).parent)
    colors = WAVE_COLORS.get(preset_key) or WAVE_COLORS["black-gray-red"]
    flt = (f"[0:a]showwaves=s={WIDTH}x{height}:mode=cline:rate={FPS}:"
           f"colors={colors},format=yuv420p[w]")
    ffmpeg(["-i", str(audio), "-filter_complex", flt, "-map", "[w]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-r", str(FPS), "-pix_fmt", "yuv420p", str(out)], timeout=3600)
    return Path(out)


# ---------------------------------------------------------------- C. 최종
def _ass_path_for_filter(p: Path) -> str:
    """ffmpeg filtergraph 안에서 안전한 경로 문자열.

    Windows 의 'C:\\path' 는 필터에서 ':' 가 인자 구분자라 그대로 못 쓴다.
    작업 디렉터리 기준 상대경로로 바꾸고 구분자를 이스케이프한다.
    """
    s = Path(p).as_posix()
    s = s.replace("\\", "/")
    s = s.replace(":", r"\:").replace("'", r"\'").replace("[", r"\[").replace("]", r"\]")
    return s


def compose_final(background: Path, waveform: Path, audio: Path, ass: Path,
                  out: Path, *, intro_image: Path | None = None,
                  intro_seconds: float = 6.0, wave_opacity: float = 0.72,
                  wave_height: int = WAVE_H, crf: int = 19,
                  preset: str = "medium", audio_bitrate: str = "256k",
                  progress=None) -> Path:
    ensure_dir(Path(out).parent)
    inputs = ["-i", str(background), "-i", str(waveform), "-i", str(audio)]
    parts = [
        # showwaves 는 검은 배경 위에 파형을 그린다. 그대로 얹으면 하단에 검은
        # 띠가 생기므로 검정을 키아웃해 배경이 비치게 한다.
        f"[1:v]format=rgba,colorkey=0x000000:0.30:0.08,"
        f"colorchannelmixer=aa={wave_opacity:g}[wv]",
        f"[0:v][wv]overlay=0:H-{wave_height}:format=auto:shortest=0[bgw]",
    ]
    last = "[bgw]"

    if intro_image and Path(intro_image).exists() and intro_seconds > 0:
        inputs += ["-loop", "1", "-framerate", str(FPS),
                   "-t", _fmt(intro_seconds + 0.5), "-i", str(intro_image)]
        fade_out_at = max(0.5, intro_seconds - 1.2)
        parts.append(
            f"[3:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},setsar=1,format=yuva420p,"
            f"fade=t=in:st=0:d=0.8:alpha=1,"
            f"fade=t=out:st={_fmt(fade_out_at)}:d=1.2:alpha=1,"
            f"setpts=PTS-STARTPTS[intro]"
        )
        parts.append(
            f"{last}[intro]overlay=0:0:format=auto:"
            f"enable='between(t,0,{_fmt(intro_seconds)})'[withintro]"
        )
        last = "[withintro]"

    if ass and Path(ass).exists():
        parts.append(f"{last}ass='{_ass_path_for_filter(ass)}'[vout]")
        last = "[vout]"
    else:
        parts.append(f"{last}null[vout]")
        last = "[vout]"

    flt = ";".join(parts)
    if progress:
        progress("  최종 합성 인코딩 중 (배경 + 파형 + 인트로 + 자막 + 오디오)")
    ffmpeg([*inputs, "-filter_complex", flt,
            "-map", last, "-map", "2:a",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-profile:v", "high", "-level", "4.1",
            "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "48000", "-ac", "2",
            "-shortest", "-movflags", "+faststart", str(out)], timeout=14400)
    return Path(out)
