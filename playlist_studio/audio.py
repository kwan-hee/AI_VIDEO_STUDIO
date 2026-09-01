"""음원 검사 · 정규화 · 병합.

- ffprobe 로 길이/코덱/샘플레이트를 실측한다.
- 손상되었거나 지나치게 짧은 파일은 렌더링에서 제외한다.
- loudnorm 2-pass 로 -14 LUFS / True Peak -1dB 이하로 맞춘다.
- 곡 연결은 acrossfade 로 짧은 크로스페이드를 지원한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from .util import CommandFailed, ffmpeg, ffprobe_json, require, run

TARGET_I = -14.0      # LUFS
TARGET_TP = -1.0      # dBTP
TARGET_LRA = 11.0


# ---------------------------------------------------------------- 검사
@dataclass
class AudioInfo:
    path: str
    ok: bool
    duration: float = 0.0
    codec: str = ""
    sample_rate: int = 0
    channels: int = 0
    bit_rate: int = 0
    format_name: str = ""
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["issues"] = list(self.issues)
        return d


def probe(path: Path) -> AudioInfo:
    path = Path(path)
    if not path.exists():
        return AudioInfo(str(path), False, issues=("파일 없음",))
    if path.stat().st_size == 0:
        return AudioInfo(str(path), False, issues=("0바이트 파일",))
    try:
        data = ffprobe_json(path)
    except (CommandFailed, json.JSONDecodeError) as e:
        return AudioInfo(str(path), False, issues=(f"ffprobe 실패: {str(e)[:200]}",))

    astreams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not astreams:
        return AudioInfo(str(path), False, issues=("오디오 스트림 없음",))
    s = astreams[0]
    fmt = data.get("format", {})
    dur = float(s.get("duration") or fmt.get("duration") or 0.0)
    return AudioInfo(
        path=str(path), ok=True, duration=dur,
        codec=s.get("codec_name", ""),
        sample_rate=int(s.get("sample_rate") or 0),
        channels=int(s.get("channels") or 0),
        bit_rate=int(float(fmt.get("bit_rate") or s.get("bit_rate") or 0)),
        format_name=fmt.get("format_name", ""),
    )


_SILENCE_RE = re.compile(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)")


def silence_ratio(path: Path, *, threshold_db: float = -50.0,
                  min_silence: float = 1.0) -> float:
    """전체 길이 중 무음이 차지하는 비율 (0.0~1.0)."""
    info = probe(path)
    if not info.ok or info.duration <= 0:
        return 1.0
    exe = require("ffmpeg")
    proc = run(
        [exe, "-hide_banner", "-nostdin", "-i", str(path),
         "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
         "-f", "null", "-"],
        check=False, timeout=600,
    )
    log = (proc.stderr or "") + (proc.stdout or "")
    starts: list[float] = []
    ends: list[float] = []
    for kind, val in _SILENCE_RE.findall(log):
        (starts if kind == "start" else ends).append(float(val))
    total = 0.0
    for i, st in enumerate(starts):
        en = ends[i] if i < len(ends) else info.duration
        total += max(0.0, en - st)
    return min(1.0, total / info.duration)


def validate(path: Path, *, min_seconds: float = 20.0,
             max_silence_ratio: float = 0.60,
             expect_seconds: float | None = None,
             tolerance: float = 0.45) -> AudioInfo:
    """렌더링에 넣어도 되는지 판정. issues 가 있으면 ok=False."""
    info = probe(path)
    issues = list(info.issues)
    if info.ok:
        if info.duration < min_seconds:
            issues.append(f"너무 짧음: {info.duration:.1f}s < {min_seconds:.0f}s")
        if info.channels == 0:
            issues.append("채널 정보 없음")
        if info.sample_rate < 8000:
            issues.append(f"샘플레이트 비정상: {info.sample_rate}")
        if expect_seconds:
            drift = abs(info.duration - expect_seconds) / max(1.0, expect_seconds)
            if drift > tolerance:
                issues.append(
                    f"목표 길이와 {drift*100:.0f}% 차이 "
                    f"(목표 {expect_seconds:.0f}s / 실제 {info.duration:.1f}s)")
        try:
            sr = silence_ratio(path)
            if sr > max_silence_ratio:
                issues.append(f"무음 비율 과다: {sr*100:.0f}%")
        except Exception as e:  # 검사 실패가 곧 손상은 아니므로 경고로만
            issues.append(f"무음 검사 불가: {str(e)[:120]}")
    info.issues = tuple(issues)
    info.ok = info.ok and not issues
    return info


# ---------------------------------------------------------------- 정규화
def _measure_loudnorm(src: Path) -> dict:
    exe = require("ffmpeg")
    flt = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json")
    proc = run([exe, "-hide_banner", "-nostdin", "-i", str(src), "-af", flt,
                "-f", "null", "-"], check=False, timeout=900)
    log = (proc.stderr or "") + (proc.stdout or "")
    start = log.rfind("{")
    end = log.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"loudnorm 측정 실패: {log[-600:]}")
    return json.loads(log[start:end + 1])


def normalize(src: Path, dst: Path, *, sample_rate: int = 48000,
              channels: int = 2, two_pass: bool = True) -> dict:
    """-14 LUFS / TP -1dB 로 정규화해 WAV(pcm_s16le)로 저장."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    measured: dict[str, Any] = {}
    if two_pass:
        try:
            m = _measure_loudnorm(src)
            measured = m
            flt = (
                f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
                f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
                f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
                f":offset={m.get('target_offset', 0)}:linear=true:print_format=summary"
            )
        except Exception:
            two_pass = False
    if not two_pass:
        flt = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"

    ffmpeg(["-i", str(src), "-af", f"{flt},aresample={sample_rate}",
            "-ac", str(channels), "-ar", str(sample_rate),
            "-c:a", "pcm_s16le", str(dst)])
    out = probe(dst)
    return {"src": str(src), "dst": str(dst), "measured": measured,
            "duration": out.duration, "ok": out.ok}


def measure_loudness(path: Path) -> dict:
    """정규화 결과 확인용 (integrated LUFS / true peak)."""
    m = _measure_loudnorm(path)
    return {
        "input_i": float(m["input_i"]), "input_tp": float(m["input_tp"]),
        "input_lra": float(m["input_lra"]),
        "output_i": float(m.get("output_i", m["input_i"])),
        "output_tp": float(m.get("output_tp", m["input_tp"])),
    }


# ---------------------------------------------------------------- 병합
def concat(sources: Sequence[Path], dst: Path, *, crossfade: float = 0.0,
           sample_rate: int = 48000) -> dict:
    """크로스페이드 병합. 각 곡의 시작 시각(초)을 함께 돌려준다.

    크로스페이드 D 로 n곡을 이으면 전체 길이는 sum - (n-1)*D 이고,
    k번째 곡의 시작은 (앞 곡들 길이 합) - k*D 이다.
    """
    sources = [Path(s) for s in sources]
    if not sources:
        raise ValueError("병합할 음원이 없습니다.")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    durations: list[float] = []
    for s in sources:
        info = probe(s)
        if not info.ok:
            raise ValueError(f"병합 불가 (손상): {s} — {', '.join(info.issues)}")
        durations.append(info.duration)

    xf = float(crossfade)
    if xf > 0 and len(sources) > 1:
        shortest = min(durations)
        if xf >= shortest / 2:
            xf = max(0.0, shortest / 4)

    inputs: list[str] = []
    for s in sources:
        inputs += ["-i", str(s)]

    if len(sources) == 1:
        ffmpeg([*inputs, "-ac", "2", "-ar", str(sample_rate),
                "-c:a", "pcm_s16le", str(dst)])
        starts = [0.0]
    elif xf <= 0:
        parts = "".join(f"[{i}:a]" for i in range(len(sources)))
        flt = f"{parts}concat=n={len(sources)}:v=0:a=1[out]"
        ffmpeg([*inputs, "-filter_complex", flt, "-map", "[out]",
                "-ac", "2", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)])
        starts = []
        acc = 0.0
        for d in durations:
            starts.append(acc)
            acc += d
    else:
        chain: list[str] = []
        prev = "[0:a]"
        for i in range(1, len(sources)):
            label = f"[x{i}]"
            chain.append(f"{prev}[{i}:a]acrossfade=d={xf:g}:c1=tri:c2=tri{label}")
            prev = label
        flt = ";".join(chain)
        ffmpeg([*inputs, "-filter_complex", flt, "-map", prev,
                "-ac", "2", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)])
        starts = []
        acc = 0.0
        for k, d in enumerate(durations):
            starts.append(max(0.0, acc - k * xf))
            acc += d

    out = probe(dst)
    return {
        "dst": str(dst), "duration": out.duration, "crossfade": xf,
        "track_starts": [round(s, 3) for s in starts],
        "track_durations": [round(d, 3) for d in durations],
        "expected_duration": round(sum(durations) - max(0, len(sources) - 1) * xf, 3),
    }


def to_aac(src: Path, dst: Path, *, bitrate: str = "256k",
           sample_rate: int = 48000) -> Path:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-i", str(src), "-c:a", "aac", "-b:a", bitrate,
            "-ar", str(sample_rate), "-ac", "2", "-movflags", "+faststart", str(dst)])
    return dst
