"""가사 타이밍 정렬.

세 가지 경로를 지원한다. 어느 쪽을 썼는지 결과에 반드시 기록하고
QA 보고서에도 그대로 드러낸다.

  whisper  : faster-whisper 로 단어/문장 타임스탬프를 뽑고, **원문 가사를
             기준으로 인식 결과를 보정**한다. 목표 오차 300ms 이하.
  srt      : 외부 ASR(예: Abocado abocado_transcribe_audio)이 준 SRT 를
             읽어 같은 보정 절차를 태운다.
  estimate : ASR 이 없을 때의 폴백. 글자수 비례로 배분한다.
             **300ms 정확도를 보장하지 않는다.** 결과에 정직하게 표기한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Sequence

from .util import normalize_lyrics

METHODS = ("whisper", "srt", "estimate")


@dataclass
class TimedLine:
    track_index: int
    line_index: int
    text: str
    start: float
    end: float
    source: str = "estimate"     # 이 줄의 타이밍이 어디서 왔는지
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- 정규화
_STRIP = re.compile(r"[\s\.,!\?~\-·…\"'’“”\(\)\[\]/]+")


def _key(text: str) -> str:
    return _STRIP.sub("", normalize_lyrics(text)).lower()


def _char_stream(lines: Sequence[str]) -> tuple[str, list[int]]:
    """줄 목록 -> (정규화 문자열, 각 문자가 속한 줄 인덱스)."""
    buf: list[str] = []
    owner: list[int] = []
    for i, ln in enumerate(lines):
        k = _key(ln)
        buf.append(k)
        owner.extend([i] * len(k))
    return "".join(buf), owner


# ---------------------------------------------------------------- SRT 파싱
_SRT_TIME = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


def _to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_srt(text: str) -> list[dict]:
    """SRT -> [{start, end, text}]"""
    out: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip())
    for b in blocks:
        m = _SRT_TIME.search(b)
        if not m:
            continue
        g = m.groups()
        body_lines = [l for l in b.split("\n") if not _SRT_TIME.search(l) and not l.strip().isdigit()]
        body = " ".join(l.strip() for l in body_lines).strip()
        if not body:
            continue
        out.append({"start": _to_sec(*g[:4]), "end": _to_sec(*g[4:]), "text": body})
    return out


# ---------------------------------------------------------------- 보정 정렬
def align_with_reference(asr_segments: Sequence[dict], ref_lines: Sequence[str],
                         *, track_start: float = 0.0, track_index: int = 1,
                         source: str = "asr") -> list[TimedLine]:
    """ASR 결과를 원문 가사에 맞춰 되돌린다.

    ASR 텍스트를 문자 단위 시간축으로 펼친 뒤, 원문 가사 문자열과
    difflib 로 매칭한다. 매칭된 구간의 최소/최대 시각이 그 줄의 시작/끝이 된다.
    ASR 이 잘못 알아들은 부분은 매칭이 안 되므로, 앞뒤 줄 사이를 보간한다.
    최종 자막 텍스트는 **항상 원문 가사**를 쓴다. (인식 오타를 화면에 내보내지 않는다)
    """
    ref_lines = [l for l in ref_lines if l.strip()]
    if not ref_lines:
        return []

    # ASR 문자열 + 문자별 시각
    asr_chars: list[str] = []
    asr_times: list[float] = []
    for seg in asr_segments:
        k = _key(seg.get("text", ""))
        if not k:
            continue
        s, e = float(seg["start"]), float(seg["end"])
        span = max(1e-6, e - s)
        for j, ch in enumerate(k):
            asr_chars.append(ch)
            asr_times.append(s + span * (j / max(1, len(k))))
    if not asr_chars:
        return []

    ref_str, owner = _char_stream(ref_lines)
    asr_str = "".join(asr_chars)

    sm = SequenceMatcher(None, ref_str, asr_str, autojunk=False)
    hits: dict[int, list[float]] = {i: [] for i in range(len(ref_lines))}
    matched_chars = 0
    for r0, a0, size in sm.get_matching_blocks():
        if size <= 0:
            continue
        matched_chars += size
        for d in range(size):
            li = owner[r0 + d]
            hits[li].append(asr_times[a0 + d])

    coverage = matched_chars / max(1, len(ref_str))

    out: list[TimedLine] = []
    for i, text in enumerate(ref_lines):
        ts = hits[i]
        if ts:
            out.append(TimedLine(track_index, i, text, track_start + min(ts),
                                 track_start + max(ts), source, 1.0))
        else:
            out.append(TimedLine(track_index, i, text, -1.0, -1.0, "interpolated", 0.0))

    _fill_gaps(out, track_start)
    _enforce_order(out)
    for tl in out:
        tl.confidence = round(coverage, 3) if tl.source != "interpolated" else 0.0
    return out


def _fill_gaps(lines: list[TimedLine], track_start: float) -> None:
    """매칭 실패한 줄을 앞뒤 사이에 균등 배치."""
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].start >= 0:
            i += 1
            continue
        j = i
        while j < n and lines[j].start < 0:
            j += 1
        prev_end = lines[i - 1].end if i > 0 else track_start
        next_start = lines[j].start if j < n else (prev_end + 3.0 * (j - i))
        gap = max(0.4, (next_start - prev_end) / max(1, (j - i)))
        for k in range(i, j):
            s = prev_end + gap * (k - i)
            lines[k].start = s
            lines[k].end = s + gap * 0.9
        i = j


def _enforce_order(lines: list[TimedLine], min_dur: float = 0.6,
                   max_dur: float = 12.0) -> None:
    """단조 증가 보장 + 지나치게 길거나 짧은 줄 보정."""
    for i, tl in enumerate(lines):
        if tl.end - tl.start < min_dur:
            tl.end = tl.start + min_dur
        if tl.end - tl.start > max_dur:
            tl.end = tl.start + max_dur
        if i > 0 and tl.start < lines[i - 1].end:
            # 겹치면 앞 줄을 잘라 준다 (가사는 겹쳐 나오면 안 읽힌다)
            lines[i - 1].end = max(lines[i - 1].start + min_dur * 0.5, tl.start - 0.05)


# ---------------------------------------------------------------- 폴백 배분
def estimate_lines(ref_lines: Sequence[str], *, track_start: float,
                   duration: float, track_index: int = 1,
                   lead_in_ratio: float = 0.10, tail_ratio: float = 0.08,
                   ) -> list[TimedLine]:
    """글자수 비례 배분. 인트로/아웃트로 구간은 비워 둔다."""
    ref_lines = [l for l in ref_lines if l.strip()]
    if not ref_lines or duration <= 0:
        return []
    lead = duration * lead_in_ratio
    tail = duration * tail_ratio
    usable = max(1.0, duration - lead - tail)
    weights = [max(1, len(_key(l))) for l in ref_lines]
    total_w = sum(weights)

    out: list[TimedLine] = []
    acc = 0.0
    for i, (text, w) in enumerate(zip(ref_lines, weights)):
        s = track_start + lead + usable * (acc / total_w)
        acc += w
        e = track_start + lead + usable * (acc / total_w)
        out.append(TimedLine(track_index, i, text, s, max(s + 0.6, e - 0.15),
                             "estimate", 0.0))
    _enforce_order(out)
    return out


# ---------------------------------------------------------------- whisper
def whisper_segments(audio: Path, *, model_size: str = "small",
                     language: str | None = None,
                     compute_type: str = "int8") -> list[dict]:
    """faster-whisper 로 단어 단위 타임스탬프. 미설치면 ImportError."""
    from faster_whisper import WhisperModel   # 선택적 의존성

    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    segments, _info = model.transcribe(
        str(audio), language=language, word_timestamps=True,
        vad_filter=True, beam_size=5,
    )
    out: list[dict] = []
    for seg in segments:
        words = getattr(seg, "words", None)
        if words:
            for w in words:
                out.append({"start": float(w.start), "end": float(w.end),
                            "text": w.word})
        else:
            out.append({"start": float(seg.start), "end": float(seg.end),
                        "text": seg.text})
    return out


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 품질 리포트
def timing_report(lines: Sequence[TimedLine], method: str) -> dict:
    if not lines:
        return {"method": method, "lines": 0, "accuracy_claim": "없음"}
    interp = sum(1 for l in lines if l.source == "interpolated")
    est = sum(1 for l in lines if l.source == "estimate")
    cov = max((l.confidence for l in lines), default=0.0)
    if method == "estimate":
        claim = ("추정 배분입니다. 300ms 목표 오차를 보장하지 않습니다. "
                 "정확한 싱크가 필요하면 faster-whisper 를 설치하거나 SRT 를 넣으세요.")
    elif interp > len(lines) * 0.3:
        claim = (f"{interp}/{len(lines)} 줄이 인식 실패로 보간되었습니다. "
                 f"300ms 오차를 보장할 수 없습니다.")
    else:
        claim = (f"원문 대조 매칭률 {cov*100:.0f}%. 보간 {interp}줄. "
                 f"300ms 목표를 만족할 가능성이 높지만 육안 확인을 권장합니다.")
    return {
        "method": method, "lines": len(lines),
        "interpolated": interp, "estimated": est,
        "reference_match_coverage": round(cov, 3),
        "accuracy_claim": claim,
        "meets_300ms_target": method != "estimate" and interp <= len(lines) * 0.3,
    }
