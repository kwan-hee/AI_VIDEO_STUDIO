"""마법사 · 경로 · slug."""
import pytest

from playlist_studio import wizard as WZ
from playlist_studio.util import romanize_hangul, safe_filename, slugify
from playlist_studio.paths import ProjectPaths, find_project


def test_questions_follow_the_specified_order():
    keys = [q.key for q in WZ.QUESTIONS]
    expected = ["channel", "genre", "subgenre", "purpose", "situation",
                "vocal_mode", "lyrics_language", "subtitle_language",
                "track_count", "track_seconds", "total_seconds",
                "bpm_min", "bpm_max", "mood_arc", "visual_preset",
                "thumbnail_language", "thumbnail_concept"]
    assert keys == expected


def test_only_unanswered_questions_are_asked():
    answers = {"channel": "c", "genre": "lofi"}
    nxt = [q.key for q in WZ.next_questions(answers, limit=2)]
    assert nxt == ["subgenre", "purpose"]


def test_limit_keeps_the_dialogue_short():
    assert len(WZ.next_questions({}, limit=2)) == 2


def test_lyrics_language_skipped_for_instrumental():
    answers = {"channel": "c", "genre": "lofi", "subgenre": "s", "purpose": "집중",
               "situation": "야근", "vocal_mode": "instrumental"}
    assert "lyrics_language" not in [q.key for q in WZ.missing_questions(answers)]


def test_invalid_choice_rejected():
    with pytest.raises(ValueError):
        WZ.coerce("genre", "존재하지않는장르")
    assert WZ.coerce("track_count", "8") == 8


def test_length_mismatch_warns():
    warns = WZ.validate({"track_count": 8, "track_seconds": 180, "total_seconds": 600})
    assert any("전체 목표" in w for w in warns)


def test_bpm_inversion_warns():
    assert any("BPM" in w for w in WZ.validate({"bpm_min": 95, "bpm_max": 70}))


def test_config_roundtrip(tmp_path):
    cfg = {"genre": "lofi", "track_count": 8, "playlist_title": "비 오는 날"}
    p = tmp_path / "playlist.yaml"
    WZ.save_config(p, cfg)
    assert WZ.load_config(p) == cfg
    assert "비 오는 날" in p.read_text(encoding="utf-8")   # 한글이 이스케이프되지 않는다


def test_hangul_slug_is_readable():
    assert slugify("로파이 밤 채널") == "ropai-bam-chaeneol"
    assert romanize_hangul("한글") == "hangeul"


def test_slug_never_empty():
    assert slugify("!!!", fallback="fb") == "fb"
    assert slugify("東京", fallback="fb") == "fb"


def test_windows_reserved_characters_removed():
    assert safe_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"


def test_paths_are_posix_in_json(project):
    from playlist_studio.util import rel_posix
    p = project.track_audio_raw(3)
    assert rel_posix(p, project.root) == "audio/raw/03.mp3"


def test_find_project_by_slug_and_path(project):
    assert find_project(str(project.root)).root == project.root
    key = f"{project.root.parent.parent.name}/{project.root.name}"
    assert find_project(key).root == project.root


def test_find_project_missing_raises():
    with pytest.raises(FileNotFoundError):
        find_project("없는-프로젝트")
