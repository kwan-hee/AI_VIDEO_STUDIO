"""채널 / 플레이리스트 생성 및 목록."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .paths import ProjectPaths, channels_dir
from .util import ensure_dir, now_iso, read_json, slugify, write_json, write_text

NUM_PREFIX = re.compile(r"^(\d{3})_(.+)$")


def _next_number(directory: Path) -> int:
    ensure_dir(directory)
    used = []
    for child in directory.iterdir():
        m = NUM_PREFIX.match(child.name)
        if m and child.is_dir():
            used.append(int(m.group(1)))
    return (max(used) + 1) if used else 1


def _unique_slug(directory: Path, slug: str) -> str:
    existing = {NUM_PREFIX.match(c.name).group(2) for c in directory.iterdir()
                if c.is_dir() and NUM_PREFIX.match(c.name)} if directory.exists() else set()
    if slug not in existing:
        return slug
    for i in range(2, 100):
        cand = f"{slug}-{i}"
        if cand not in existing:
            return cand
    raise RuntimeError(f"slug 를 만들 수 없습니다: {slug}")


# ---------------------------------------------------------------- 채널
def create_channel(name: str, *, genre: str = "", concept: str = "",
                   base: Path | None = None) -> dict:
    root = channels_dir(base)
    ensure_dir(root)
    number = _next_number(root)
    slug = _unique_slug(root, slugify(name, fallback=f"channel-{number:03d}"))
    dirname = f"{number:03d}_{slug}"
    cdir = ensure_dir(root / dirname)
    ensure_dir(cdir / "playlists")

    info = {
        "number": number,
        "slug": slug,
        "dirname": dirname,
        "name": name,
        "genre": genre,
        "concept": concept,
        "created_at": now_iso(),
        "playlists": [],
    }
    write_json(cdir / "channel.json", info)
    write_text(cdir / "CHANNEL.md", _channel_md(info))
    return info


def _channel_md(info: dict) -> str:
    return f"""# {info['name']}

- 채널 번호: {info['number']:03d}
- slug: `{info['slug']}`
- 장르: {info.get('genre') or '—'}
- 생성일: {info['created_at']}

## 콘셉트

{info.get('concept') or '(미작성)'}

## 규칙

- 실존 가수·밴드 이름을 프롬프트에 쓰지 않는다. 장르·악기·리듬·믹싱·정서로만 기술한다.
- 이미지 AI 에는 글자를 그리게 하지 않는다. 모든 텍스트는 로컬 렌더에서 합성한다.
- 업로드는 자동으로 하지 않는다. 산출물과 메타데이터까지만 만든다.

## 플레이리스트

<!-- playlist-manager 가 갱신한다 -->
"""


def load_channel(dirname_or_slug: str, base: Path | None = None) -> tuple[Path, dict]:
    root = channels_dir(base)
    if not root.exists():
        raise FileNotFoundError(f"채널 폴더가 없습니다: {root}")
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        m = NUM_PREFIX.match(child.name)
        slug = m.group(2) if m else child.name
        if dirname_or_slug in (child.name, slug):
            info = read_json(child / "channel.json", {})
            return child, info
    raise FileNotFoundError(f"채널을 찾을 수 없습니다: {dirname_or_slug}")


def list_channels(base: Path | None = None) -> list[dict]:
    root = channels_dir(base)
    out: list[dict] = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / "channel.json").exists():
            continue
        info = read_json(child / "channel.json", {})
        pls = []
        pl_dir = child / "playlists"
        if pl_dir.is_dir():
            for pl in sorted(pl_dir.iterdir()):
                if (pl / "workspace.json").exists():
                    ws = read_json(pl / "workspace.json", {})
                    pls.append({
                        "dirname": pl.name,
                        "state": ws.get("state", "?"),
                        "updated_at": ws.get("updated_at", ""),
                        "path": str(pl),
                    })
        info["playlists"] = pls
        info["path"] = str(child)
        out.append(info)
    return out


def refresh_channel_md(channel_dir: Path) -> Path:
    info = read_json(channel_dir / "channel.json", {})
    lines = []
    pl_dir = channel_dir / "playlists"
    if pl_dir.is_dir():
        for pl in sorted(pl_dir.iterdir()):
            ws_p = pl / "workspace.json"
            if not ws_p.exists():
                continue
            ws = read_json(ws_p, {})
            title = (ws.get("channel") or {}).get("playlist_title") or pl.name
            lines.append(f"- `{pl.name}` — {title} — 상태 **{ws.get('state','?')}** (갱신 {ws.get('updated_at','')})")
    body = _channel_md(info).replace(
        "<!-- playlist-manager 가 갱신한다 -->",
        "\n".join(lines) if lines else "(아직 없음)",
    )
    write_text(channel_dir / "CHANNEL.md", body)
    return channel_dir / "CHANNEL.md"


# ---------------------------------------------------------------- 플레이리스트
def create_playlist(channel_dirname: str, title: str, base: Path | None = None) -> tuple[ProjectPaths, dict]:
    cdir, cinfo = load_channel(channel_dirname, base)
    pl_root = ensure_dir(cdir / "playlists")
    number = _next_number(pl_root)
    slug = _unique_slug(pl_root, slugify(title, fallback=f"playlist-{number:03d}"))
    dirname = f"{number:03d}_{slug}"
    paths = ProjectPaths((pl_root / dirname).resolve()).mkdirs()

    meta = {
        "channel_number": cinfo.get("number"),
        "channel_slug": cinfo.get("slug"),
        "channel_name": cinfo.get("name"),
        "channel_dirname": cdir.name,
        "playlist_number": number,
        "playlist_slug": slug,
        "playlist_dirname": dirname,
        "playlist_title": title,
    }
    return paths, meta
