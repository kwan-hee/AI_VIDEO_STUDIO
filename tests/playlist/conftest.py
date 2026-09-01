import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    """격리된 스튜디오 루트."""
    root = tmp_path / "studio"
    monkeypatch.setenv("PLAYLIST_STUDIO_ROOT", str(root))
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture()
def project(studio):
    """채널 + 플레이리스트 + 기본 설정이 채워진 프로젝트."""
    from playlist_studio import channels as CH
    from playlist_studio import wizard as WZ
    from playlist_studio.state import Workspace

    ch = CH.create_channel("테스트 채널", genre="lofi")
    paths, meta = CH.create_playlist(ch["dirname"], "테스트 플레이리스트")
    ws = Workspace.create(paths, f"{ch['dirname']}/{meta['playlist_dirname']}", meta)
    cfg = {
        "channel": ch["dirname"], "playlist_title": "테스트 플레이리스트",
        "genre": "lofi", "subgenre": "jazzy tape lofi", "purpose": "집중",
        "situation": "야근", "vocal_mode": "vocal", "lyrics_language": "ko",
        "subtitle_language": "ko", "track_count": 3, "track_seconds": 30,
        "total_seconds": 90, "bpm_min": 70, "bpm_max": 88,
        "mood_arc": "calm-to-warm", "visual_preset": "black-gray-red",
        "thumbnail_language": "ko",
    }
    WZ.save_config(paths.config, cfg)
    ws.step_done("channel")
    ws.advance("CHANNEL_READY")
    return paths
