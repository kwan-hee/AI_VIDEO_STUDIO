"""자막 생성 - 보관용 SRT, 스타일 렌더용 ASS.

복잡한 스타일(현재 가사 강조, 다음 줄 미리보기, 곡 제목 카드)은 SRT 로는
표현할 수 없으므로 ASS 로 렌더한다. SRT 는 순수 보관/업로드용이다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .align import TimedLine
from .util import ass_timestamp, srt_timestamp, write_text

PLAY_W, PLAY_H = 1920, 1080

# 비주얼 프리셋 -> ASS 색상 (&HAABBGGRR - alpha 는 00 이 불투명)
STYLE_PRESETS = {
    "black-gray-red": {
        "active": "&H00FFFFFF", "active_outline": "&H00101010",
        "dim": "&H00A0A0A0", "accent": "&H002828A8",   # BGR 이므로 빨강은 002828A8
        "title": "&H00FFFFFF", "shadow": "&H80000000",
    },
    "warm-film": {
        "active": "&H00E8F4FF", "active_outline": "&H00201810",
        "dim": "&H0090A8C0", "accent": "&H005CAAE8",
        "title": "&H00E8F4FF", "shadow": "&H80100804",
    },
    "cold-neon": {
        "active": "&H00FFFFFF", "active_outline": "&H00301808",
        "dim": "&H00C0A890", "accent": "&H00982EC6",
        "title": "&H00FFF0E0", "shadow": "&H80100800",
    },
    "paper-grain": {
        "active": "&H00202028", "active_outline": "&H00F0F4F8",
        "dim": "&H00807870", "accent": "&H004260B0",
        "title": "&H00202028", "shadow": "&H60FFFFFF",
    },
}


def _escape_ass(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace("{", "\\{")
            .replace("}", "\\}").replace("\n", "\\N"))


def _escape_srt(text: str) -> str:
    return str(text).replace("\r", "").strip()


# ---------------------------------------------------------------- SRT
def write_srt(path: Path, lines: Sequence[TimedLine]) -> Path:
    out: list[str] = []
    n = 0
    for tl in sorted(lines, key=lambda l: (l.start, l.line_index)):
        if not tl.text.strip():
            continue
        n += 1
        out.append(str(n))
        out.append(f"{srt_timestamp(tl.start)} --> {srt_timestamp(max(tl.end, tl.start + 0.4))}")
        out.append(_escape_srt(tl.text))
        out.append("")
    return write_text(path, "\n".join(out))


# ---------------------------------------------------------------- ASS
def _header(preset: str, font: str, font_size: int) -> str:
    c = STYLE_PRESETS.get(preset) or STYLE_PRESETS["black-gray-red"]
    # Alignment: 2=하단중앙, 8=상단중앙, 7=상단좌
    styles = [
        # Name, Font, Size, PrimaryC, SecondaryC, OutlineC, BackC, Bold,Italic,U,S,
        # ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Align,ML,MR,MV,Enc
        f"Style: Active,{font},{font_size},{c['active']},{c['accent']},"
        f"{c['active_outline']},{c['shadow']},-1,0,0,0,100,100,0.6,0,1,3.2,1.6,2,200,200,205,1",
        f"Style: Dim,{font},{int(font_size*0.72)},{c['dim']},{c['dim']},"
        f"{c['active_outline']},{c['shadow']},0,0,0,0,100,100,0.4,0,1,2.2,1.0,2,200,200,168,1",
        # 좌상단 곡 카드: 번호(작게, 강조색) -> 제목(크게) -> 부제(작게)
        f"Style: TrackNo,{font},{int(font_size*0.62)},{c['accent']},{c['accent']},"
        f"{c['active_outline']},{c['shadow']},-1,0,0,0,100,100,3.0,0,1,2.4,1.2,7,96,96,64,1",
        f"Style: TrackTitle,{font},{int(font_size*0.92)},{c['title']},{c['accent']},"
        f"{c['active_outline']},{c['shadow']},-1,0,0,0,100,100,1.0,0,1,2.6,1.4,7,96,96,118,1",
        f"Style: Sub,{font},{int(font_size*0.52)},{c['dim']},{c['dim']},"
        f"{c['active_outline']},{c['shadow']},0,0,0,0,100,100,0.8,0,1,2.0,1.0,7,96,96,196,1",
    ]
    return "\n".join([
        "[Script Info]",
        "; playlist-studio 생성. 편집해도 되지만 재렌더하면 덮어써진다.",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {PLAY_W}",
        f"PlayResY: {PLAY_H}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        *styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ])


def _dialogue(start: float, end: float, style: str, text: str,
              layer: int = 0, effect: str = "") -> str:
    if end <= start:
        end = start + 0.4
    return (f"Dialogue: {layer},{ass_timestamp(start)},{ass_timestamp(end)},"
            f"{style},,0,0,0,{effect},{text}")


@dataclass
class TrackCard:
    index: int
    title: str
    subtitle: str
    start: float
    end: float


def write_ass(path: Path, lines: Sequence[TimedLine], *,
              preset: str = "black-gray-red",
              font: str = "DejaVu Sans", font_size: int = 58,
              cards: Sequence[TrackCard] = (),
              card_seconds: float = 8.0,
              show_next_line: bool = True,
              intro: tuple[float, float, str, str] | None = None) -> Path:
    """현재 가사를 강조하고, 다음 줄을 흐리게 미리 보여준다.

    cards 를 주면 각 곡 시작에 곡 번호/제목/부제 카드가 뜬다.
    intro=(start, end, 제목, 부제) 를 주면 인트로 타이틀을 넣는다.
    """
    body: list[str] = [_header(preset, font, font_size)]
    ordered = sorted([l for l in lines if l.text.strip()],
                     key=lambda l: (l.start, l.line_index))

    if intro:
        i_s, i_e, i_title, i_sub = intro
        fade = r"{\fad(700,700)\an5\pos(960,470)}"
        body.append(_dialogue(i_s, i_e, "Active", fade + _escape_ass(i_title), layer=3))
        if i_sub:
            body.append(_dialogue(i_s + 0.4, i_e, "Dim",
                                  r"{\fad(700,700)\an5\pos(960,585)}" + _escape_ass(i_sub),
                                  layer=3))

    for card in cards:
        c_end = min(card.end, card.start + card_seconds)
        body.append(_dialogue(card.start, c_end, "TrackNo",
                              r"{\fad(500,500)}" + f"{card.index:02d}", layer=2))
        body.append(_dialogue(card.start + 0.15, c_end, "TrackTitle",
                              r"{\fad(500,500)}" + _escape_ass(card.title), layer=2))
        if card.subtitle:
            body.append(_dialogue(card.start + 0.3, c_end, "Sub",
                                  r"{\fad(500,500)}" + _escape_ass(card.subtitle), layer=2))

    for i, tl in enumerate(ordered):
        body.append(_dialogue(tl.start, tl.end, "Active",
                              r"{\fad(220,260)}" + _escape_ass(tl.text), layer=1))
        if show_next_line and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            # 다음 줄이 곧 나오는 경우에만 미리보기 (곡이 바뀌면 표시하지 않음)
            if 0 <= nxt.start - tl.end <= 6.0 and nxt.track_index == tl.track_index:
                body.append(_dialogue(tl.start, min(tl.end, nxt.start), "Dim",
                                      r"{\fad(200,200)}" + _escape_ass(nxt.text), layer=0))

    return write_text(path, "\n".join(body) + "\n")
