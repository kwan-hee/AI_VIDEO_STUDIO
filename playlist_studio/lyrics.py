"""가사 - 저장 / 중복 검사 / 해시 대조.

규칙
  - 곡마다 제목과 주제가 달라야 한다.
  - 첫 줄과 후렴 첫 줄이 다른 곡과 겹치지 않아야 한다.
  - 구조 태그([Verse] 등)를 쓴다.
  - 가사 언어와 자막 언어를 분리해 보관한다.
  - lyrics_all.md 와 개별 파일에 함께 저장한다.
  - 음악 생성에 넘긴 가사와 로컬 파일이 같은지 정규화 해시로 검증한다.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .paths import ProjectPaths
from .tracks import track_slug
from .util import (lyrics_fingerprint, normalize_lyrics, read_text, rel_posix,
                   write_text)

TAG_RE = re.compile(r"^\s*\[([A-Za-z][A-Za-z \-]*)\]\s*$")
VALID_TAGS = {
    "intro", "verse", "pre chorus", "prechorus", "chorus", "post chorus",
    "bridge", "outro", "interlude", "hook", "break", "solo", "inst",
    "transition", "build up",
}


class LyricsError(ValueError):
    pass


# ---------------------------------------------------------------- 파싱
def parse_sections(text: str) -> list[tuple[str, list[str]]]:
    """[(태그, [줄...]), ...]. 태그 앞의 내용은 '' 태그로 담긴다."""
    sections: list[tuple[str, list[str]]] = []
    cur_tag, cur_lines = "", []
    for raw in normalize_lyrics(text).split("\n"):
        m = TAG_RE.match(raw)
        if m:
            if cur_lines or cur_tag:
                sections.append((cur_tag, cur_lines))
            cur_tag, cur_lines = m.group(1).strip(), []
        else:
            cur_lines.append(raw)
    if cur_lines or cur_tag:
        sections.append((cur_tag, cur_lines))
    return [(t, [l for l in ls if l]) for t, ls in sections if t or any(ls)]


def first_line(text: str) -> str:
    for tag, lines in parse_sections(text):
        if lines:
            return lines[0]
    return ""


def chorus_lines(text: str) -> list[str]:
    out: list[str] = []
    for tag, lines in parse_sections(text):
        if tag.lower().replace("-", " ") in ("chorus", "hook", "post chorus"):
            out.extend(lines)
    return out


def sung_lines(text: str) -> list[str]:
    """자막으로 쓸 실제 발화 줄 (태그·마크다운 헤더 제외).

    파일 원문이 그대로 들어와도 안전하도록 헤더를 먼저 벗긴다.
    """
    out: list[str] = []
    text = _strip_header(text)
    for tag, lines in parse_sections(text):
        if tag.lower().replace("-", " ") in ("inst", "solo", "break"):
            continue
        out.extend(lines)
    return out


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_lyrics(a), normalize_lyrics(b)).ratio()


# ---------------------------------------------------------------- 저장
def save_track_lyrics(paths: ProjectPaths, track: dict, text: str) -> dict:
    """개별 가사 파일 저장 후 track 딕셔너리를 갱신해 돌려준다."""
    if not (text or "").strip():
        raise LyricsError(f"트랙 {track['index']} 가사가 비어 있습니다.")
    target = paths.track_lyrics(int(track["index"]), track_slug(track))
    header = (
        f"# {track['index']:02d}. {track.get('title') or '(제목 미정)'}\n\n"
        f"> {track.get('subtitle') or ''}\n"
        f"> 주제: {track.get('lyrical_theme') or '—'} / BPM {track['bpm']} / "
        f"감정 {track['mood']}\n\n"
    )
    body = normalize_lyrics(text)
    write_text(target, header + body + "\n")
    track["lyrics_path"] = rel_posix(target, paths.root)
    track["lyrics_sha256"] = lyrics_fingerprint(body)
    if track.get("status") == "planned":
        track["status"] = "lyrics_ready"
    return track


def load_track_lyrics(paths: ProjectPaths, track: dict) -> str:
    """저장된 가사 본문만(헤더 제외) 돌려준다."""
    rel = track.get("lyrics_path")
    if not rel:
        raise LyricsError(f"트랙 {track['index']} 에 가사 파일이 없습니다.")
    p = paths.root / rel
    raw = read_text(p)
    if raw is None:
        raise LyricsError(f"가사 파일이 사라졌습니다: {p}")
    return _strip_header(raw)


def _strip_header(raw: str) -> str:
    lines = raw.split("\n")
    out, seen_body = [], False
    for ln in lines:
        if not seen_body:
            if ln.startswith("#") or ln.startswith(">") or not ln.strip():
                continue
            seen_body = True
        out.append(ln)
    return normalize_lyrics("\n".join(out))


def verify_lyrics_hash(paths: ProjectPaths, track: dict) -> tuple[bool, str]:
    """제출 직전 대조: 로컬 파일 == tracks.json 에 기록된 해시."""
    try:
        body = load_track_lyrics(paths, track)
    except LyricsError as e:
        return False, str(e)
    fp = lyrics_fingerprint(body)
    if not track.get("lyrics_sha256"):
        return False, "tracks.json 에 가사 해시가 없습니다."
    if fp != track["lyrics_sha256"]:
        return False, (f"가사 파일이 기록과 다릅니다. "
                       f"기록 {track['lyrics_sha256'][:12]} / 현재 {fp[:12]}")
    return True, "ok"


# ---------------------------------------------------------------- 검사
def validate_set(paths: ProjectPaths, tracks: list[dict], *,
                 dup_threshold: float = 0.80) -> dict:
    """전 곡을 함께 검사. errors 가 비어야 LYRICS_READY 로 넘어간다."""
    errors: list[str] = []
    warnings: list[str] = []
    bodies: dict[int, str] = {}

    for t in tracks:
        idx = t["index"]
        if not (t.get("title") or "").strip():
            errors.append(f"트랙 {idx:02d}: 제목이 비었습니다.")
        if not (t.get("lyrical_theme") or "").strip():
            warnings.append(f"트랙 {idx:02d}: 가사 주제(lyrical_theme)가 비었습니다.")
        try:
            bodies[idx] = load_track_lyrics(paths, t)
        except LyricsError as e:
            errors.append(f"트랙 {idx:02d}: {e}")
            continue
        ok, why = verify_lyrics_hash(paths, t)
        if not ok:
            errors.append(f"트랙 {idx:02d}: {why}")
        tags = {tag.lower() for tag, _ in parse_sections(bodies[idx]) if tag}
        if not tags:
            errors.append(f"트랙 {idx:02d}: 구조 태그가 하나도 없습니다. [Verse] 등을 넣으세요.")
        bad = tags - VALID_TAGS
        if bad:
            warnings.append(f"트랙 {idx:02d}: 표준이 아닌 태그 {sorted(bad)}")
        if "chorus" not in tags and "hook" not in tags:
            warnings.append(f"트랙 {idx:02d}: [Chorus] 또는 [Hook] 이 없습니다.")

    # 제목 중복
    titles: dict[str, int] = {}
    for t in tracks:
        key = normalize_lyrics(t.get("title") or "")
        if key and key in titles:
            errors.append(f"트랙 {t['index']:02d}: 제목이 트랙 {titles[key]:02d} 와 같습니다.")
        elif key:
            titles[key] = t["index"]

    # 주제 중복
    themes: dict[str, int] = {}
    for t in tracks:
        key = normalize_lyrics(t.get("lyrical_theme") or "")
        if key and key in themes:
            errors.append(f"트랙 {t['index']:02d}: 가사 주제가 트랙 {themes[key]:02d} 와 같습니다.")
        elif key:
            themes[key] = t["index"]

    idxs = sorted(bodies)
    # 첫 줄 / 후렴 중복
    for i, a in enumerate(idxs):
        fa, ca = first_line(bodies[a]), chorus_lines(bodies[a])
        for b in idxs[i + 1:]:
            fb, cb = first_line(bodies[b]), chorus_lines(bodies[b])
            if fa and fb and _similar(fa, fb) >= dup_threshold:
                errors.append(
                    f"첫 줄 중복: {a:02d} '{fa}' / {b:02d} '{fb}' "
                    f"(유사도 {_similar(fa, fb):.2f})")
            if ca and cb:
                sim = _similar("\n".join(ca), "\n".join(cb))
                if sim >= dup_threshold:
                    errors.append(f"후렴 중복: {a:02d} 와 {b:02d} (유사도 {sim:.2f})")
            sim_all = _similar(bodies[a], bodies[b])
            if sim_all >= 0.70:
                warnings.append(f"가사 전체가 비슷합니다: {a:02d} 와 {b:02d} (유사도 {sim_all:.2f})")

    return {"errors": errors, "warnings": warnings, "checked": len(bodies)}


# ---------------------------------------------------------------- 모음 파일
def write_lyrics_all(paths: ProjectPaths, tracks: list[dict], config: dict) -> Path:
    lines = [
        f"# {config.get('playlist_title') or paths.root.name} — 전체 가사",
        "",
        f"- 가사 언어: `{config.get('lyrics_language', '—')}`",
        f"- 자막 언어: `{config.get('subtitle_language', '—')}`",
        f"- 곡 수: {len(tracks)}",
        "",
        "---",
        "",
    ]
    for t in tracks:
        lines.append(f"## {t['index']:02d}. {t.get('title') or '(제목 미정)'}")
        if t.get("subtitle"):
            lines.append(f"*{t['subtitle']}*")
        lines.append("")
        lines.append(f"- BPM {t['bpm']} / 감정 {t['mood']} / 인트로 {t['intro_lead']}")
        lines.append(f"- 주제: {t.get('lyrical_theme') or '—'}")
        lines.append(f"- 가사 해시: `{(t.get('lyrics_sha256') or '')[:16]}`")
        lines.append("")
        try:
            body = load_track_lyrics(paths, t)
        except LyricsError:
            body = "_(가사 없음)_"
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")
    write_text(paths.lyrics_all, "\n".join(lines))
    return paths.lyrics_all
