"""유튜브 메타데이터 + 권리 기록.

수익 보장이나 근거 없는 저작권 보장 문구는 쓰지 않는다.
업로드는 하지 않는다. 사람이 복사해 붙일 파일까지만 만든다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .cost import MUSIC_MODELS
from .paths import ProjectPaths
from .util import hhmmss, now_iso, rel_posix, sha256_file, write_json, write_text

MAX_TITLE = 100          # YouTube 제목 한도
MAX_DESCRIPTION = 5000
MAX_TAGS_CHARS = 500     # 태그 전체 합계


def build_title(config: dict, tracks: Sequence[dict], total_seconds: float) -> str:
    base = config.get("playlist_title") or "플레이리스트"
    situ = config.get("situation", "")
    n = len(tracks)
    mins = int(round(total_seconds / 60))
    tail = f" | {n}곡 {mins}분"
    if situ and len(base) + len(situ) + len(tail) + 3 <= MAX_TITLE:
        title = f"{base} · {situ}{tail}"
    else:
        title = f"{base}{tail}"
    return title[:MAX_TITLE]


def build_chapters(tracks: Sequence[dict], starts: Sequence[float]) -> str:
    """YouTube 챕터. 첫 줄은 반드시 00:00 이어야 인식된다."""
    lines: list[str] = []
    force_h = (starts[-1] + 1 if starts else 0) >= 3600
    for t, s in zip(tracks, starts):
        ts = hhmmss(s, force_hours=force_h)
        if not lines:
            ts = "0:00" if not force_h else "0:00:00"
        title = t.get("title") or f"Track {t['index']:02d}"
        lines.append(f"{ts} {t['index']:02d}. {title}")
    return "\n".join(lines)


def build_description(config: dict, tracks: Sequence[dict], starts: Sequence[float],
                      *, channel_name: str = "", disclosure: str = "") -> str:
    parts: list[str] = []
    situ = config.get("situation", "")
    purpose = config.get("purpose", "")
    genre = config.get("subgenre") or config.get("genre", "")
    mins = int(round((starts[-1] + (tracks[-1].get("duration_seconds") or 0)) / 60)) if starts else 0

    parts.append(f"{config.get('playlist_title') or ''}".strip())
    parts.append("")
    parts.append(f"{situ}에 어울리는 {genre} 플레이리스트입니다. "
                 f"{purpose}을(를) 위해 {len(tracks)}곡 약 {mins}분으로 구성했습니다.")
    parts.append("")
    parts.append("── 수록곡 ──")
    parts.append(build_chapters(tracks, starts))
    parts.append("")
    parts.append("── 곡 소개 ──")
    for t in tracks:
        sub = f" — {t['subtitle']}" if t.get("subtitle") else ""
        parts.append(f"{t['index']:02d}. {t.get('title') or ''}{sub}")
        if t.get("lyrical_theme"):
            parts.append(f"    {t['lyrical_theme']}")
    parts.append("")
    if disclosure:
        parts.append("── 제작 안내 ──")
        parts.append(disclosure)
        parts.append("")
    if channel_name:
        parts.append(f"채널: {channel_name}")
    text = "\n".join(parts).strip()
    if len(text) > MAX_DESCRIPTION:
        text = text[:MAX_DESCRIPTION - 30].rstrip() + "\n…(길이 제한으로 생략)"
    return text


def build_tags(config: dict) -> list[str]:
    genre = config.get("genre", "")
    sub = config.get("subgenre", "")
    tags = [
        config.get("playlist_title", ""), genre, sub,
        config.get("purpose", ""), config.get("situation", ""),
        f"{genre} playlist", f"{config.get('purpose','')} 음악",
        f"{config.get('situation','')} 플레이리스트",
        "플레이리스트", "playlist", "BGM", "study music", "background music",
    ]
    out: list[str] = []
    seen: set[str] = set()
    total = 0
    for t in tags:
        t = " ".join(str(t).split())
        if not t or t.lower() in seen:
            continue
        if total + len(t) + 1 > MAX_TAGS_CHARS:
            break
        seen.add(t.lower())
        out.append(t)
        total += len(t) + 1
    return out


DISCLOSURE_TEMPLATE = """이 영상의 음악과 배경 이미지는 생성형 AI 도구로 제작했습니다.
- 음악: {music_provider} ({music_model})
- 이미지: {image_provider} ({image_model})
- 가사·구성·편집: 사람이 작성하고 검수했습니다.

특정 아티스트나 기존 곡을 모방하지 않도록 장르·악기·리듬·믹싱 속성만으로 프롬프트를 작성했습니다.
플랫폼별 AI 생성물 표기 정책은 각 플랫폼 약관을 확인하고 업로드 시 직접 설정하세요."""


def build_disclosure(config: dict, tracks: Sequence[dict]) -> str:
    model = ""
    for t in tracks:
        if t.get("provider_job_id"):
            model = t.get("provider", "") or model
    music_model = model or config.get("music_model", "(미정)")
    display = (MUSIC_MODELS.get(music_model, {}) or {}).get("display", music_model)
    return DISCLOSURE_TEMPLATE.format(
        music_provider="Abocado AI", music_model=display,
        image_provider="Abocado AI",
        image_model=config.get("image_model", "(미정)"),
    )


def build_rights(paths: ProjectPaths, config: dict, tracks: Sequence[dict],
                 *, plan_note: str = "", image_records: Sequence[dict] = ()) -> dict:
    """각 음악·이미지의 제공자/생성일/플랜/프롬프트/사용권한/원본 해시."""
    items: list[dict] = []

    for t in tracks:
        rec = {
            "type": "music",
            "track_index": t["index"],
            "title": t.get("title", ""),
            "provider": t.get("provider") or config.get("music_model", ""),
            "provider_job_id": t.get("provider_job_id", ""),
            "generated_at": t.get("generated_at") or t.get("updated_at", ""),
            "plan_at_generation": plan_note,
            "credit_cost": t.get("credit_cost", 0),
            "prompt_file": rel_posix(paths.tracks, paths.root),
            "prompt_fingerprint": t.get("prompt_fingerprint", ""),
            "lyrics_file": t.get("lyrics_path", ""),
            "lyrics_sha256": t.get("lyrics_sha256", ""),
            "source_file": t.get("output_path", ""),
            "source_sha256": t.get("sha256", ""),
            "usage_rights": (
                "생성 서비스(Abocado AI)의 이용약관에 따른다. 이 파일은 약관을 "
                "대신하지 않는다. 상업적 이용 가부는 생성 시점의 플랜과 약관을 "
                "사용자가 직접 확인해야 한다."
            ),
            "is_test_asset": bool(t.get("is_test")),
        }
        items.append(rec)

    for img in image_records:
        items.append({
            "type": "image",
            "role": img.get("role", ""),
            "provider": img.get("provider", ""),
            "provider_job_id": img.get("provider_job_id", ""),
            "generated_at": img.get("generated_at", ""),
            "plan_at_generation": plan_note,
            "credit_cost": img.get("credit_cost", 0),
            "prompt_file": img.get("prompt_file", ""),
            "prompt": img.get("prompt", ""),
            "source_file": img.get("path", ""),
            "source_sha256": img.get("sha256", ""),
            "usage_rights": (
                "생성 서비스의 이용약관에 따른다. 이미지에는 AI 가 그린 글자가 "
                "없으며, 화면의 모든 텍스트는 로컬에서 합성했다."
            ),
            "is_test_asset": bool(img.get("is_test")),
        })

    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "project": paths.root.name,
        "playlist_title": config.get("playlist_title", ""),
        "notice": (
            "이 파일은 생성 이력 기록이다. 저작권 귀속이나 수익 발생을 보장하지 "
            "않으며, 법적 자문이 아니다."
        ),
        "items": items,
    }


def write_all(paths: ProjectPaths, config: dict, tracks: Sequence[dict],
              starts: Sequence[float], *, channel_name: str = "",
              total_seconds: float = 0.0, plan_note: str = "",
              image_records: Sequence[dict] = ()) -> dict:
    disclosure = build_disclosure(config, tracks)
    title = build_title(config, tracks, total_seconds)
    chapters = build_chapters(tracks, starts)
    desc = build_description(config, tracks, starts,
                             channel_name=channel_name, disclosure=disclosure)
    tags = build_tags(config)
    rights = build_rights(paths, config, tracks, plan_note=plan_note,
                          image_records=image_records)

    out = {
        "youtube_title.txt": write_text(paths.meta / "youtube_title.txt", title + "\n"),
        "youtube_description.txt": write_text(paths.meta / "youtube_description.txt", desc + "\n"),
        "chapters.txt": write_text(paths.meta / "chapters.txt", chapters + "\n"),
        "tags.txt": write_text(paths.meta / "tags.txt", ", ".join(tags) + "\n"),
        "generation_disclosure.txt": write_text(paths.meta / "generation_disclosure.txt", disclosure + "\n"),
        "rights.json": write_json(paths.meta / "rights.json", rights),
    }
    return {
        "files": {k: str(v) for k, v in out.items()},
        "title": title, "title_chars": len(title),
        "description_chars": len(desc),
        "tags": tags, "tags_chars": sum(len(t) + 1 for t in tags),
        "chapters_count": len(chapters.splitlines()),
    }
