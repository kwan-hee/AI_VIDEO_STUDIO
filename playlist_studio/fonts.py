"""폰트 해석 - Windows / Linux / macOS 공통.

ASS 는 폰트 '이름'을, Pillow 는 폰트 '파일 경로'를 필요로 한다.
둘 다 돌려주고, 요청한 언어의 글자를 실제로 그릴 수 있는지 검사한다.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# 언어별 후보. (ASS 용 패밀리명, 파일 후보들)
CANDIDATES: dict[str, list[tuple[str, list[str]]]] = {
    "ko": [
        ("Malgun Gothic", ["C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunsl.ttf"]),
        ("Pretendard", ["C:/Windows/Fonts/Pretendard-Regular.ttf",
                        "/usr/share/fonts/truetype/pretendard/Pretendard-Regular.ttf"]),
        ("Noto Sans CJK KR", ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"]),
        ("Noto Sans KR", ["/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf"]),
        ("AppleSDGothicNeo", ["/System/Library/Fonts/AppleSDGothicNeo.ttc"]),
        ("NanumGothic", ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                         "C:/Windows/Fonts/NanumGothic.ttf"]),
        ("WenQuanYi Zen Hei", ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]),
        ("Unifont", ["/usr/share/fonts/opentype/unifont/unifont.otf"]),
    ],
    "ja": [
        ("Yu Gothic", ["C:/Windows/Fonts/YuGothR.ttc", "C:/Windows/Fonts/msgothic.ttc"]),
        ("Noto Sans CJK JP", ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]),
        ("IPAGothic", ["/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
                       "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"]),
        ("WenQuanYi Zen Hei", ["/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]),
    ],
    "en": [
        ("Segoe UI", ["C:/Windows/Fonts/segoeui.ttf"]),
        ("Arial", ["C:/Windows/Fonts/arial.ttf"]),
        ("Helvetica Neue", ["/System/Library/Fonts/HelveticaNeue.ttc"]),
        ("DejaVu Sans", ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]),
        ("Liberation Sans", ["/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]),
    ],
}
CANDIDATES["ko+en"] = CANDIDATES["ko"]

PROBE_TEXT = {"ko": "가나다힣", "ja": "あアン漢", "en": "Aa1", "ko+en": "가나Aa"}


@dataclass(frozen=True)
class FontChoice:
    family: str
    file: str | None
    language: str
    covers: bool
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.file is not None and self.covers


@lru_cache(maxsize=16)
def _fc_match(family_query: str) -> tuple[str, str] | None:
    """fontconfig 로 (실제 패밀리명, 파일 경로) 찾기.

    fc-match 는 요청한 이름이 없어도 무조건 무언가를 돌려준다. 그래서 요청한
    이름을 그대로 쓰면 ASS 가 존재하지 않는 폰트를 가리키게 된다. 반드시
    *돌아온* 패밀리명을 쓴다.
    """
    try:
        out = subprocess.run(["fc-match", "-f", "%{family[0]}\t%{file}", family_query],
                             capture_output=True, text=True, timeout=15)
        raw = (out.stdout or "").strip()
        if "\t" not in raw:
            return None
        fam, path = raw.split("\t", 1)
        fam, path = fam.strip(), path.strip()
        return (fam, path) if path and Path(path).exists() else None
    except Exception:
        return None


def _family_of(font_file: str, fallback: str) -> str:
    """파일에서 실제 패밀리 이름을 읽는다 (ASS 가 참조할 이름)."""
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(font_file, fontNumber=0, lazy=True)
        for rec in tt["name"].names:
            if rec.nameID == 1:
                val = rec.toUnicode().strip()
                if val.isascii():
                    return val
        for rec in tt["name"].names:
            if rec.nameID == 1:
                return rec.toUnicode().strip()
    except Exception:
        pass
    return fallback


def _covers(font_file: str, text: str) -> bool:
    """이 폰트 파일이 해당 글자들을 실제로 갖고 있는가."""
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(font_file, 32)
        try:
            from fontTools.ttLib import TTFont       # 있으면 정확하게
            tt = TTFont(font_file, fontNumber=0, lazy=True)
            cmap = tt.getBestCmap()
            return all(ord(c) in cmap for c in text)
        except Exception:
            pass
        # fontTools 가 없으면 렌더 폭으로 근사 판정 (.notdef 는 보통 폭이 같다)
        widths = {f.getlength(c) for c in text}
        return f.getlength(text) > 0 and len(widths) > 1 or f.getlength(text[0]) > 0
    except Exception:
        return False


def resolve(language: str = "ko", *, override_family: str | None = None,
            override_file: str | None = None) -> FontChoice:
    """언어에 맞는 폰트를 고른다. 환경변수로도 지정 가능.

    PLAYLIST_FONT_FILE / PLAYLIST_FONT_FAMILY 가 최우선.
    """
    lang = language if language in CANDIDATES else "en"
    probe = PROBE_TEXT.get(lang, "Aa")

    ov_file = override_file or os.environ.get("PLAYLIST_FONT_FILE")
    ov_family = override_family or os.environ.get("PLAYLIST_FONT_FAMILY")
    if ov_file and Path(ov_file).exists():
        return FontChoice(ov_family or Path(ov_file).stem, ov_file, lang,
                          _covers(ov_file, probe), "환경변수/인자 지정")

    for family, files in CANDIDATES[lang]:
        for f in files:
            if Path(f).exists() and _covers(f, probe):
                return FontChoice(family, f, lang, True, "후보 목록에서 발견")
        got = _fc_match(family)
        # fc-match 가 요청과 다른 폰트를 돌려줬으면 그 폰트의 진짜 이름을 쓴다
        if got and _covers(got[1], probe):
            real_family = got[0] if got[0] else _family_of(got[1], family)
            note = ("fontconfig 해석" if real_family.lower() == family.lower()
                    else f"fontconfig 대체 ('{family}' 없음 -> '{real_family}')")
            return FontChoice(real_family, got[1], lang, True, note)

    # 마지막 수단: 시스템이 이 언어로 무엇을 주는지 물어본다
    got = _fc_match(f":lang={lang.split('+')[0]}")
    if got:
        return FontChoice(got[0] or _family_of(got[1], Path(got[1]).stem), got[1],
                          lang, _covers(got[1], probe), "fontconfig :lang 폴백")

    last = _fc_match("DejaVu Sans")
    return FontChoice(last[0] if last else "DejaVu Sans",
                      last[1] if last else None, lang, False,
                      f"{lang} 글자를 그릴 수 있는 폰트를 찾지 못했습니다. "
                      f"Windows 라면 맑은 고딕(malgun.ttf)이 기본 설치되어 있습니다. "
                      f"PLAYLIST_FONT_FILE 로 직접 지정하세요.")


def report() -> list[dict]:
    out = []
    for lang in ("ko", "ja", "en"):
        fc = resolve(lang)
        out.append({"language": lang, "family": fc.family, "file": fc.file,
                    "covers": fc.covers, "ok": fc.ok, "note": fc.note})
    return out
