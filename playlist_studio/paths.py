"""프로젝트 폴더 규약.

studio/
  channels/
    001_lofi-night/
      CHANNEL.md
      channel.json
      playlists/
        001_rainy-desk/
          workspace.json
          playlist.yaml
          sonic_dna.json
          visual_dna.json
          tracks.json
          generation_ledger.json
          lyrics/   audio/   images/   subs/   meta/   video/   qa/   work/
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .util import ensure_dir

STUDIO_DIRNAME = "studio"


def studio_root(base: Path | str | None = None) -> Path:
    """스튜디오 루트. 환경변수 PLAYLIST_STUDIO_ROOT 로 재정의 가능."""
    if base is not None:
        return Path(base).resolve()
    env = os.environ.get("PLAYLIST_STUDIO_ROOT")
    if env:
        return Path(env).resolve()
    return (repo_root() / STUDIO_DIRNAME).resolve()


def repo_root() -> Path:
    """playlist_studio 패키지를 담고 있는 저장소 루트."""
    return Path(__file__).resolve().parent.parent


def channels_dir(base: Path | str | None = None) -> Path:
    return studio_root(base) / "channels"


@dataclass(frozen=True)
class ProjectPaths:
    """플레이리스트 프로젝트 한 개의 모든 경로."""

    root: Path

    # --- 파일 ---
    @property
    def workspace(self) -> Path:
        return self.root / "workspace.json"

    @property
    def config(self) -> Path:
        return self.root / "playlist.yaml"

    @property
    def sonic_dna(self) -> Path:
        return self.root / "sonic_dna.json"

    @property
    def visual_dna(self) -> Path:
        return self.root / "visual_dna.json"

    @property
    def tracks(self) -> Path:
        return self.root / "tracks.json"

    @property
    def ledger(self) -> Path:
        return self.root / "generation_ledger.json"

    # --- 디렉터리 ---
    @property
    def lyrics(self) -> Path:
        return self.root / "lyrics"

    @property
    def audio_raw(self) -> Path:
        return self.root / "audio" / "raw"

    @property
    def audio_norm(self) -> Path:
        return self.root / "audio" / "norm"

    @property
    def audio_master(self) -> Path:
        return self.root / "audio" / "master"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def images_bg(self) -> Path:
        return self.root / "images" / "bg"

    @property
    def images_thumb(self) -> Path:
        return self.root / "images" / "thumbnail"

    @property
    def subs(self) -> Path:
        return self.root / "subs"

    @property
    def meta(self) -> Path:
        return self.root / "meta"

    @property
    def video(self) -> Path:
        return self.root / "video"

    @property
    def qa(self) -> Path:
        return self.root / "qa"

    @property
    def work(self) -> Path:
        return self.root / "work"

    # --- 대표 산출물 ---
    @property
    def lyrics_all(self) -> Path:
        return self.lyrics / "lyrics_all.md"

    @property
    def master_wav(self) -> Path:
        return self.audio_master / "playlist_master.wav"

    @property
    def master_m4a(self) -> Path:
        return self.audio_master / "playlist_master.m4a"

    @property
    def srt(self) -> Path:
        return self.subs / "playlist.srt"

    @property
    def ass(self) -> Path:
        return self.subs / "playlist.ass"

    @property
    def thumbnail(self) -> Path:
        return self.images_thumb / "thumbnail.png"

    @property
    def intro_image(self) -> Path:
        return self.images / "intro.png"

    @property
    def final_mp4(self) -> Path:
        return self.video / "final.mp4"

    @property
    def qa_report_md(self) -> Path:
        return self.qa / "qa_report.md"

    @property
    def qa_report_json(self) -> Path:
        return self.qa / "qa_report.json"

    def track_audio_raw(self, index: int, ext: str = "mp3") -> Path:
        return self.audio_raw / f"{index:02d}.{ext.lstrip('.')}"

    def track_audio_norm(self, index: int) -> Path:
        return self.audio_norm / f"{index:02d}.wav"

    def track_bg(self, index: int) -> Path:
        return self.images_bg / f"{index:02d}.png"

    def track_lyrics(self, index: int, slug: str) -> Path:
        return self.lyrics / f"{index:02d}_{slug}.md"

    def thumb_candidate(self, n: int) -> Path:
        return self.images_thumb / f"candidate_{n:02d}.png"

    def mkdirs(self) -> "ProjectPaths":
        for d in (
            self.root, self.lyrics, self.audio_raw, self.audio_norm, self.audio_master,
            self.images, self.images_bg, self.images_thumb, self.subs, self.meta,
            self.video, self.qa, self.work,
        ):
            ensure_dir(d)
        return self


def find_project(project: str, base: Path | str | None = None) -> ProjectPaths:
    """프로젝트 지정자를 경로로 해석.

    허용 형식:
      - 절대/상대 디렉터리 경로 (workspace.json 이 있는 폴더)
      - "<채널slug>/<플레이리스트slug>" 또는 번호 접두 포함
      - "<플레이리스트slug>" (전 채널에서 유일할 때)
    """
    p = Path(project)
    if (p / "workspace.json").exists():
        return ProjectPaths(p.resolve())

    root = channels_dir(base)
    matches: list[Path] = []
    if root.exists():
        for ch in sorted(root.iterdir()):
            pl_dir = ch / "playlists"
            if not pl_dir.is_dir():
                continue
            for pl in sorted(pl_dir.iterdir()):
                if not (pl / "workspace.json").exists():
                    continue
                key_full = f"{ch.name}/{pl.name}"
                if project in (key_full, pl.name):
                    matches.append(pl)
                elif project.endswith(pl.name) and project.split("/")[0] in ch.name:
                    matches.append(pl)
    if len(matches) == 1:
        return ProjectPaths(matches[0].resolve())
    if len(matches) > 1:
        names = ", ".join(m.parent.parent.name + "/" + m.name for m in matches)
        raise ValueError(f"프로젝트 지정이 모호합니다: {project} -> {names}")
    raise FileNotFoundError(f"프로젝트를 찾을 수 없습니다: {project} (검색 위치: {root})")


def iter_projects(base: Path | str | None = None):
    root = channels_dir(base)
    if not root.exists():
        return
    for ch in sorted(root.iterdir()):
        pl_dir = ch / "playlists"
        if not pl_dir.is_dir():
            continue
        for pl in sorted(pl_dir.iterdir()):
            if (pl / "workspace.json").exists():
                yield ProjectPaths(pl.resolve())
