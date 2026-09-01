"""환경 검사 - 무엇이 되고 무엇이 안 되는지 정직하게 보고한다."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import fonts
from .paths import studio_root
from .util import run, which


def _ffmpeg_features() -> dict:
    exe = which("ffmpeg")
    if not exe:
        return {"found": False}
    out: dict = {"found": True, "path": exe}
    try:
        v = run([exe, "-hide_banner", "-version"], check=False, timeout=30)
        out["version"] = (v.stdout or "").splitlines()[0] if v.stdout else ""
        conf = run([exe, "-hide_banner", "-buildconf"], check=False, timeout=30)
        blob = (conf.stdout or "") + (conf.stderr or "")
        out["libass"] = "--enable-libass" in blob
        out["libx264"] = "--enable-libx264" in blob
        out["libfreetype"] = "--enable-libfreetype" in blob
        out["libmp3lame"] = "--enable-libmp3lame" in blob
        f = run([exe, "-hide_banner", "-filters"], check=False, timeout=30)
        fl = f.stdout or ""
        for name in ("ass", "showwaves", "loudnorm", "zoompan", "drawtext",
                     "acrossfade", "noise", "silencedetect"):
            out[f"filter_{name}"] = f" {name} " in fl
        e = run([exe, "-hide_banner", "-encoders"], check=False, timeout=30)
        el = e.stdout or ""
        out["encoder_libx264"] = "libx264" in el
        out["encoder_aac"] = " aac " in el
    except Exception as ex:
        out["error"] = str(ex)[:300]
    return out


def _python_packages() -> dict:
    import importlib
    out = {}
    for m in ("yaml", "PIL", "numpy", "faster_whisper", "fontTools"):
        try:
            mod = importlib.import_module(m)
            out[m] = getattr(mod, "__version__", "설치됨")
        except Exception:
            out[m] = None
    return out


def doctor(base: Path | None = None) -> dict:
    ff = _ffmpeg_features()
    pkgs = _python_packages()
    fnt = fonts.report()

    blockers: list[str] = []
    warnings: list[str] = []

    if not ff.get("found"):
        blockers.append("ffmpeg 을 찾을 수 없습니다. 설치하거나 FFMPEG_BINARY 를 지정하세요.")
    else:
        if not which("ffprobe"):
            blockers.append("ffprobe 를 찾을 수 없습니다. 음원 검사를 할 수 없습니다.")
        if not ff.get("libass"):
            blockers.append("ffmpeg 에 libass 가 없습니다. ASS 자막을 태울 수 없습니다.")
        if not ff.get("encoder_libx264"):
            blockers.append("libx264 인코더가 없습니다. H.264 출력을 만들 수 없습니다.")
        if not ff.get("filter_loudnorm"):
            warnings.append("loudnorm 필터가 없습니다. 음량 정규화를 건너뜁니다.")
        if not ff.get("filter_showwaves"):
            warnings.append("showwaves 필터가 없습니다. 파형을 그릴 수 없습니다.")

    if pkgs.get("PIL") is None:
        blockers.append("Pillow 가 없습니다. 썸네일을 합성할 수 없습니다. (pip install Pillow)")
    if pkgs.get("yaml") is None:
        blockers.append("PyYAML 이 없습니다. playlist.yaml 을 읽을 수 없습니다.")
    if pkgs.get("faster_whisper") is None:
        warnings.append(
            "faster-whisper 가 없습니다. 가사 싱크는 추정 배분(300ms 미보장)으로 "
            "떨어집니다. `pip install faster-whisper` 하거나 외부 SRT 를 넣으세요.")

    for f in fnt:
        if not f["ok"]:
            warnings.append(f"{f['language']} 폰트를 찾지 못했습니다: {f['note']}")

    return {
        "platform": {
            "system": platform.system(), "release": platform.release(),
            "machine": platform.machine(), "python": sys.version.split()[0],
            "executable": sys.executable,
        },
        "studio_root": str(studio_root(base)),
        "ffmpeg": ff,
        "packages": pkgs,
        "fonts": fnt,
        "blockers": blockers,
        "warnings": warnings,
        "ready": not blockers,
    }


def report_markdown(d: dict) -> str:
    p = d["platform"]
    ff = d["ffmpeg"]
    lines = [
        "# 환경 검사",
        "",
        f"- OS: {p['system']} {p['release']} ({p['machine']})",
        f"- Python: {p['python']} — `{p['executable']}`",
        f"- 스튜디오 루트: `{d['studio_root']}`",
        "",
        "| 도구 | 상태 |",
        "|---|---|",
        f"| ffmpeg | {'✅ ' + ff.get('version','') if ff.get('found') else '❌ 없음'} |",
        f"| libass (ASS 자막) | {'✅' if ff.get('libass') else '❌'} |",
        f"| libx264 (H.264) | {'✅' if ff.get('encoder_libx264') else '❌'} |",
        f"| loudnorm (음량) | {'✅' if ff.get('filter_loudnorm') else '❌'} |",
        f"| showwaves (파형) | {'✅' if ff.get('filter_showwaves') else '❌'} |",
        f"| zoompan (줌·패닝) | {'✅' if ff.get('filter_zoompan') else '❌'} |",
    ]
    lines.append("")
    lines.append("| 파이썬 패키지 | 버전 |")
    lines.append("|---|---|")
    for k, v in d["packages"].items():
        lines.append(f"| {k} | {v if v else '❌ 없음'} |")
    lines.append("")
    lines.append("| 언어 | 폰트 | 파일 |")
    lines.append("|---|---|---|")
    for f in d["fonts"]:
        mark = "✅" if f["ok"] else "⚠️"
        lines.append(f"| {f['language']} | {mark} {f['family']} | `{f['file'] or '—'}` |")
    if d["blockers"]:
        lines += ["", "## ❌ 진행 불가", ""] + [f"- {b}" for b in d["blockers"]]
    if d["warnings"]:
        lines += ["", "## ⚠️ 경고", ""] + [f"- {w}" for w in d["warnings"]]
    if d["ready"] and not d["warnings"]:
        lines += ["", "모든 검사 통과. 바로 진행할 수 있습니다."]
    elif d["ready"]:
        lines += ["", "필수 도구는 모두 있습니다. 위 경고를 확인하고 진행하세요."]
    return "\n".join(lines) + "\n"
