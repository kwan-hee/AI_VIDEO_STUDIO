"""유튜브 메타데이터 · rights.json."""
import pytest

from playlist_studio import metadata as MD

CFG = {"playlist_title": "비 오는 날 창가에서", "situation": "야근", "purpose": "집중",
       "genre": "lofi", "subgenre": "jazzy tape lofi", "music_model": "se-music-v26-t2a"}
TRACKS = [
    {"index": 1, "title": "창가의 새벽", "subtitle": "first light",
     "lyrical_theme": "아침으로 건너가는 순간", "duration_seconds": 180,
     "provider": "se-music-v26-t2a", "provider_job_id": "job-1", "credit_cost": 240,
     "sha256": "a" * 64, "output_path": "audio/raw/01.mp3",
     "lyrics_path": "lyrics/01_a.md", "lyrics_sha256": "b" * 64,
     "prompt_fingerprint": "c" * 64, "updated_at": "2026-09-01T00:00:00+00:00"},
    {"index": 2, "title": "두 시의 라디오", "subtitle": "two a.m.",
     "lyrical_theme": "잠들지 못하는 밤", "duration_seconds": 200,
     "provider": "se-music-v26-t2a", "provider_job_id": "job-2", "credit_cost": 240,
     "sha256": "d" * 64, "output_path": "audio/raw/02.mp3",
     "lyrics_path": "lyrics/02_b.md", "lyrics_sha256": "e" * 64,
     "prompt_fingerprint": "f" * 64, "updated_at": "2026-09-01T00:00:00+00:00"},
]
STARTS = [0.0, 178.5]


def test_title_within_youtube_limit():
    t = MD.build_title(CFG, TRACKS, 380)
    assert len(t) <= MD.MAX_TITLE
    assert "2곡" in t


def test_very_long_title_is_truncated():
    cfg = dict(CFG, playlist_title="긴 제목 " * 40)
    assert len(MD.build_title(cfg, TRACKS, 380)) <= MD.MAX_TITLE


def test_chapters_start_at_zero():
    ch = MD.build_chapters(TRACKS, STARTS).splitlines()
    assert ch[0].startswith("0:00")
    assert len(ch) == 2


def test_chapters_use_hours_for_long_playlists():
    ch = MD.build_chapters(TRACKS, [0.0, 3700.0]).splitlines()
    assert ch[0].startswith("0:00:00")
    assert ch[1].startswith("1:01:")


def test_tags_stay_under_the_500_char_cap():
    tags = MD.build_tags(CFG)
    assert sum(len(t) + 1 for t in tags) <= MD.MAX_TAGS_CHARS
    assert len(tags) == len(set(t.lower() for t in tags))


def test_description_has_chapters_and_disclosure():
    d = MD.build_description(CFG, TRACKS, STARTS, disclosure="AI 로 만들었습니다.")
    assert "0:00" in d and "창가의 새벽" in d and "AI 로 만들었습니다." in d
    assert len(d) <= MD.MAX_DESCRIPTION


def test_no_revenue_or_copyright_guarantees():
    """근거 없는 보장 문구를 쓰지 않는다."""
    text = "\n".join([
        MD.build_description(CFG, TRACKS, STARTS,
                             disclosure=MD.build_disclosure(CFG, TRACKS)),
        MD.build_disclosure(CFG, TRACKS),
    ])
    for banned in ("수익 보장", "저작권 보장", "저작권을 보장", "100% 안전",
                   "수익화 보장", "저작권 문제 없음"):
        assert banned not in text


def test_rights_records_every_asset(project):
    r = MD.build_rights(project, CFG, TRACKS, plan_note="Pro 플랜",
                        image_records=[{"role": "bg", "path": "images/bg/01.png",
                                        "sha256": "1" * 64, "provider": "abocado",
                                        "provider_job_id": "img-1",
                                        "generated_at": "2026-09-01T00:00:00+00:00",
                                        "credit_cost": 10}])
    assert len(r["items"]) == 3
    music = [i for i in r["items"] if i["type"] == "music"]
    for m in music:
        for f in ("provider", "generated_at", "plan_at_generation", "prompt_file",
                  "source_sha256", "usage_rights"):
            assert m[f] != "" and f in m
    assert "보장하지 않으며" in r["notice"]


def test_write_all_creates_every_file(project):
    r = MD.write_all(project, CFG, TRACKS, STARTS, channel_name="테스트 채널",
                     total_seconds=380, plan_note="Pro")
    for name in ("youtube_title.txt", "youtube_description.txt", "chapters.txt",
                 "tags.txt", "generation_disclosure.txt", "rights.json"):
        p = project.meta / name
        assert p.exists() and p.stat().st_size > 0
    assert r["title_chars"] <= 100
