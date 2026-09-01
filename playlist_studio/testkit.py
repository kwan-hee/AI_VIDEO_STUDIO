"""테스트 전용 합성 자산 생성기.

유료 생성 전에 파이프라인 전체를 검증하기 위한 것이다. 여기서 만든 파일은
전부 파일명과 메타데이터에 TEST 표시가 붙고, `is_test: true` 로 기록된다.
실제 음악이 아니며 배포용이 아니다.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import Sequence

from .util import ensure_dir, ffmpeg

SR = 44100

# 장3화음/단3화음 근음(Hz) - 곡마다 다른 진행을 쓰기 위한 재료
_SCALE = [220.00, 246.94, 261.63, 293.66, 329.63, 349.23, 392.00, 440.00]


def _adsr(i: int, n: int, sr: int) -> float:
    a, r = int(0.02 * sr), int(0.25 * sr)
    if i < a:
        return i / a
    if i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def synth_wav(dst: Path, *, seconds: float = 30.0, bpm: int = 80,
              seed: int = 1, instrumental: bool = False) -> Path:
    """짧은 합성 '곡'. 코드 진행 + 킥 펄스 + 멜로디로 무음 검사를 통과한다."""
    dst = Path(dst)
    ensure_dir(dst.parent)
    total = int(seconds * SR)
    beat = 60.0 / max(1, bpm)
    bar = beat * 4

    prog = [(seed + k) % len(_SCALE) for k in (0, 5, 3, 4)]
    frames = bytearray()
    for i in range(total):
        t = i / SR
        bar_idx = int(t / bar) % len(prog)
        root = _SCALE[prog[bar_idx]]
        # 3화음
        v = 0.0
        for mult in (1.0, 1.25, 1.5):
            v += math.sin(2 * math.pi * root * mult * t) * 0.16
        # 킥 (박마다)
        ph = (t % beat) / beat
        if ph < 0.12:
            v += math.sin(2 * math.pi * 55 * t) * 0.35 * (1 - ph / 0.12)
        # 멜로디 (반박마다 음이 바뀜)
        step = int(t / (beat / 2))
        mel = _SCALE[(seed * 3 + step * 2) % len(_SCALE)] * 2
        if not instrumental:
            v += math.sin(2 * math.pi * mel * t) * 0.12
        v *= _adsr(i, total, SR) * 0.8
        frames += struct.pack("<h", max(-32767, min(32767, int(v * 32767))))

    with wave.open(str(dst), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return dst


def synth_mp3(dst: Path, **kwargs) -> Path:
    """합성 음원을 mp3 로. 실제 Abocado 결과와 같은 형식으로 검증하기 위함."""
    dst = Path(dst)
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(".tmp.wav")
    synth_wav(tmp, **kwargs)
    try:
        ffmpeg(["-i", str(tmp), "-c:a", "libmp3lame", "-b:a", "192k", str(dst)])
    finally:
        tmp.unlink(missing_ok=True)
    return dst


# ---------------------------------------------------------------- 이미지
_PALETTES = {
    "black-gray-red": [(14, 14, 16), (38, 38, 42), (72, 72, 78), (168, 32, 40)],
    "warm-film": [(28, 20, 12), (86, 62, 36), (168, 126, 72), (232, 170, 92)],
    "cold-neon": [(8, 14, 28), (18, 44, 70), (34, 96, 128), (198, 46, 152)],
    "paper-grain": [(238, 234, 226), (206, 200, 188), (150, 150, 142), (176, 96, 66)],
}


def synth_image(dst: Path, *, width: int = 1920, height: int = 1080,
                preset: str = "black-gray-red", seed: int = 1,
                label: str = "TEST") -> Path:
    """테스트용 배경 이미지. 그라디언트 + 비네트 + 그레인 + 도형."""
    from PIL import Image, ImageDraw, ImageFilter

    pal = _PALETTES.get(preset) or _PALETTES["black-gray-red"]
    img = Image.new("RGB", (width, height), pal[0])
    d = ImageDraw.Draw(img)

    # 대각 그라디언트
    for y in range(0, height, 4):
        f = y / height
        c = tuple(int(pal[0][i] + (pal[1][i] - pal[0][i]) * f) for i in range(3))
        d.rectangle([0, y, width, y + 4], fill=c)

    # 도형 (seed 마다 다르게)
    rnd = _lcg(seed)
    for _ in range(5):
        cx = int(next(rnd) * width)
        cy = int(next(rnd) * height)
        r = int(80 + next(rnd) * min(width, height) * 0.35)
        col = pal[2] if next(rnd) > 0.4 else pal[1]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    ax = int(width * 0.62)
    d.rectangle([ax, int(height * 0.30), ax + 6, int(height * 0.70)], fill=pal[3])

    img = img.filter(ImageFilter.GaussianBlur(radius=2.0))

    # 그레인
    px = img.load()
    g = _lcg(seed * 7 + 3)
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            n = int((next(g) - 0.5) * 26)
            r0, g0, b0 = px[x, y]
            px[x, y] = (max(0, min(255, r0 + n)), max(0, min(255, g0 + n)),
                        max(0, min(255, b0 + n)))

    # 테스트 표식 (실제 생성물과 헷갈리지 않게)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 260, 46], fill=(0, 0, 0))
    d.text((12, 14), f"{label} #{seed:02d}", fill=(255, 80, 80))

    ensure_dir(Path(dst).parent)
    img.save(dst, "PNG")
    return Path(dst)


def _lcg(seed: int):
    """재현 가능한 의사난수 (0~1)."""
    x = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    while True:
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        yield x / 0x7FFFFFFF
