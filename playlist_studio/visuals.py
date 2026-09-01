"""이미지 프롬프트 조립 + 로컬 텍스트 합성(썸네일).

이미지 AI 에는 절대 글자를 그리게 하지 않는다. 제목·곡명·로고는 전부
여기(Pillow)에서 합성한다. 그래야 오타·깨진 글자·잘림이 생기지 않고,
같은 배경으로 언어만 바꿔 다시 뽑을 수 있다.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .dna import THUMBNAIL_CONCEPTS, visual_paragraph
from .fonts import FontChoice, resolve as resolve_font
from .util import ensure_dir

THUMB_W, THUMB_H = 1280, 720
BG_W, BG_H = 1920, 1080

NO_TEXT_CLAUSE = (
    "The image must contain absolutely no text, no letters, no numbers, "
    "no logos, no watermarks, no captions and no signage of any script. "
    "Leave the designated negative space empty and unobstructed."
)

CONCEPT_DIRECTION = {
    "A": "Tight close-up of a single everyday object with very shallow depth of field. "
         "The object fills the right half; the left third stays empty.",
    "B": "A human silhouette or back-lit figure seen from behind. No facial features "
         "are visible. The figure sits in the right third of the frame.",
    "C": "A wide environmental shot with no people. Architecture, window, or landscape. "
         "Horizon low, large empty sky or wall area on the upper left.",
    "D": "Pure texture and light abstraction. No identifiable objects. Soft gradients, "
         "bokeh, grain and colour fields only.",
}


# ---------------------------------------------------------------- 프롬프트
def _base(vdna: dict, config: dict) -> str:
    situ = config.get("situation", "")
    purpose = config.get("purpose", "")
    ctx = f"Scene context: {situ}, intended for {purpose} listening. " if situ else ""
    return f"{ctx}{visual_paragraph(vdna)} {NO_TEXT_CLAUSE}"


def track_bg_prompt(vdna: dict, track: dict, config: dict) -> str:
    return (
        f"{_base(vdna, config)} "
        f"This frame accompanies a {track['mood']} piece at {track['bpm']} BPM "
        f"with the feeling of: {track.get('lyrical_theme') or track['mood']}. "
        f"Keep it consistent with the other frames in the same set - same palette, "
        f"same lighting logic, same grain - but change the subject and camera angle. "
        f"Aspect ratio 16:9, {BG_W}x{BG_H}."
    )


def thumbnail_prompt(vdna: dict, concept: str, config: dict) -> str:
    concept = (concept or "A").upper()
    direction = CONCEPT_DIRECTION.get(concept, CONCEPT_DIRECTION["A"])
    return (
        f"{_base(vdna, config)} "
        f"Thumbnail composition {concept}: {direction} "
        f"High contrast so overlaid text will be readable. Aspect ratio 16:9."
    )


def intro_prompt(vdna: dict, config: dict) -> str:
    return (
        f"{_base(vdna, config)} "
        f"An opening title frame: darker and quieter than the rest of the set, "
        f"with a large uncluttered area in the centre for a title to be placed later. "
        f"Slow, still, cinematic. Aspect ratio 16:9, {BG_W}x{BG_H}."
    )


def concept_menu() -> str:
    return "\n".join(f"- **{k}** — {v}" for k, v in THUMBNAIL_CONCEPTS.items())


# ---------------------------------------------------------------- 텍스트 합성
PALETTES = {
    "black-gray-red": {"fg": (245, 245, 246), "sub": (176, 176, 182),
                       "accent": (196, 38, 46), "scrim": (0, 0, 0)},
    "warm-film": {"fg": (255, 246, 232), "sub": (208, 182, 148),
                  "accent": (232, 150, 68), "scrim": (24, 16, 8)},
    "cold-neon": {"fg": (240, 248, 255), "sub": (150, 180, 210),
                  "accent": (198, 46, 152), "scrim": (4, 8, 20)},
    "paper-grain": {"fg": (32, 32, 40), "sub": (110, 108, 100),
                    "accent": (176, 96, 66), "scrim": (255, 255, 255)},
}


@dataclass
class TextFit:
    lines: list[str]
    size: int
    width: int
    height: int
    overflow: bool


def fit_text(text: str, font_file: str, *, max_width: int, max_height: int,
             start_size: int, min_size: int = 20, max_lines: int = 3,
             line_gap: float = 1.18) -> TextFit:
    """폭·높이 안에 들어갈 때까지 줄바꿈하고 글자 크기를 줄인다."""
    from PIL import ImageFont

    text = (text or "").strip()
    if not text:
        return TextFit([], start_size, 0, 0, False)

    for size in range(start_size, min_size - 1, -2):
        font = ImageFont.truetype(font_file, size)
        # 글자 폭 기준으로 대략적인 줄당 글자수를 구한 뒤 줄바꿈
        avg = max(1.0, font.getlength("가나다ABCabc") / 9)
        approx = max(4, int(max_width / avg))
        for width_chars in (approx, approx - 2, approx + 2):
            lines = textwrap.wrap(text, width=max(4, width_chars),
                                  break_long_words=True) or [text]
            if len(lines) > max_lines:
                continue
            w = max(font.getlength(l) for l in lines)
            h = len(lines) * size * line_gap
            if w <= max_width and h <= max_height:
                return TextFit(lines, size, int(w), int(h), False)

    # 최소 크기에서도 안 들어가면 잘라내고 overflow 표시
    font = ImageFont.truetype(font_file, min_size)
    lines = textwrap.wrap(text, width=max(4, int(max_width / max(1.0, font.getlength("가")))),
                          break_long_words=True)[:max_lines] or [text[:20]]
    w = int(max(font.getlength(l) for l in lines))
    h = int(len(lines) * min_size * line_gap)
    return TextFit(lines, min_size, w, h, True)


def compose_thumbnail(background: Path, out: Path, *, title: str,
                      subtitle: str = "", badge: str = "",
                      preset: str = "black-gray-red",
                      language: str = "ko",
                      font: FontChoice | None = None,
                      width: int = THUMB_W, height: int = THUMB_H) -> dict:
    """배경 이미지 위에 제목·부제·뱃지를 합성해 1280x720 썸네일을 만든다.

    반환에 overflow 여부가 들어 있다. QA 가 이 값을 본다.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    fc = font or resolve_font(language)
    if not fc.file:
        raise RuntimeError(f"썸네일용 폰트를 찾지 못했습니다: {fc.note}")
    pal = PALETTES.get(preset) or PALETTES["black-gray-red"]

    src = Image.open(background).convert("RGB")
    # 16:9 로 커버 크롭
    sw, sh = src.size
    scale = max(width / sw, height / sh)
    src = src.resize((max(1, int(sw * scale)), max(1, int(sh * scale))), Image.LANCZOS)
    sw, sh = src.size
    img = src.crop(((sw - width) // 2, (sh - height) // 2,
                    (sw - width) // 2 + width, (sh - height) // 2 + height))

    # 텍스트 가독성용 스크림 (왼쪽 -> 오른쪽 그라디언트)
    scrim = Image.new("L", (width, height), 0)
    sd = ImageDraw.Draw(scrim)
    for x in range(width):
        a = int(210 * max(0.0, 1.0 - (x / (width * 0.72)) ** 1.4))
        sd.rectangle([x, 0, x + 1, height], fill=a)
    dark = Image.new("RGB", (width, height), pal["scrim"])
    img = Image.composite(dark, img, scrim.filter(ImageFilter.GaussianBlur(6)))

    d = ImageDraw.Draw(img)
    margin = int(width * 0.06)
    box_w = int(width * 0.60)
    y = int(height * 0.30)
    result: dict = {"overflow": False, "font": fc.family, "font_file": fc.file}

    if badge:
        bf = ImageFont.truetype(fc.file, int(height * 0.038))
        bw = int(bf.getlength(badge)) + int(margin * 0.7)
        bh = int(height * 0.072)
        by = int(height * 0.19)
        d.rectangle([margin, by, margin + bw, by + bh], fill=pal["accent"])
        d.text((margin + int(margin * 0.35), by + int(bh * 0.22)), badge,
               font=bf, fill=(255, 255, 255))
        result["badge_box"] = [margin, by, margin + bw, by + bh]
        if margin + bw > width - margin:
            result["overflow"] = True
            result["overflow_reason"] = "뱃지가 화면을 벗어남"

    tfit = fit_text(title, fc.file, max_width=box_w, max_height=int(height * 0.34),
                    start_size=int(height * 0.115), min_size=int(height * 0.045),
                    max_lines=3)
    tfont = ImageFont.truetype(fc.file, tfit.size)
    for line in tfit.lines:
        d.text((margin + 3, y + 3), line, font=tfont, fill=(0, 0, 0))   # 그림자
        d.text((margin, y), line, font=tfont, fill=pal["fg"])
        y += int(tfit.size * 1.18)
    if tfit.overflow:
        result["overflow"] = True
        result["overflow_reason"] = "제목이 너무 길어 잘림"
    result["title_lines"] = tfit.lines
    result["title_size"] = tfit.size

    if subtitle:
        y += int(height * 0.025)
        sfit = fit_text(subtitle, fc.file, max_width=box_w,
                        max_height=int(height * 0.14),
                        start_size=int(height * 0.052),
                        min_size=int(height * 0.028), max_lines=2)
        sfont = ImageFont.truetype(fc.file, sfit.size)
        d.rectangle([margin, y - int(height * 0.012),
                     margin + int(height * 0.008), y + sfit.size * len(sfit.lines)],
                    fill=pal["accent"])
        for line in sfit.lines:
            d.text((margin + int(height * 0.028), y), line, font=sfont, fill=pal["sub"])
            y += int(sfit.size * 1.2)
        if sfit.overflow:
            result["overflow"] = True
            result["overflow_reason"] = "부제가 너무 길어 잘림"
        result["subtitle_lines"] = sfit.lines

    # 안전 여백 검사 (YouTube 는 가장자리를 잘라 보여주기도 한다)
    safe = int(width * 0.04)
    result["safe_margin_px"] = safe
    result["text_right_edge"] = margin + box_w
    if margin < safe:
        result["overflow"] = True
        result["overflow_reason"] = "텍스트가 안전 여백 안쪽에 있음"

    ensure_dir(Path(out).parent)
    img.save(out, "PNG", optimize=True)

    # YouTube 썸네일 권장: 2MB 이하. 넘으면 JPEG 로도 하나 저장한다.
    size_bytes = Path(out).stat().st_size
    result["bytes"] = size_bytes
    result["path"] = str(out)
    if size_bytes > 2 * 1024 * 1024:
        jpg = Path(out).with_suffix(".jpg")
        img.save(jpg, "JPEG", quality=88, optimize=True, progressive=True)
        result["jpeg_path"] = str(jpg)
        result["jpeg_bytes"] = jpg.stat().st_size
    return result
