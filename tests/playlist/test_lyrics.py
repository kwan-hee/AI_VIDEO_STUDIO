"""가사 규칙 - 중복 금지, 구조 태그, 제출 전 해시 대조."""
import pytest

from playlist_studio import lyrics as LY
from playlist_studio.util import lyrics_fingerprint, normalize_lyrics

T1 = ("[Verse]\n창틀에 맺힌 물기를 지운다\n어제는 아직 남아 있고\n"
      "[Chorus]\n천천히 밝아지는 쪽으로\n몸을 돌려 본다")
T2 = ("[Verse]\n식은 컵을 다시 데우려다 그만둔다\n주파수 사이 목소리가 스친다\n"
      "[Chorus]\n아무도 부르지 않는 이름을\n혼자 불러 본다")


def _mk(idx, title, theme):
    return {"index": idx, "title": title, "subtitle": "", "bpm": 72,
            "mood": "still", "intro_lead": "piano", "lyrical_theme": theme,
            "status": "planned"}


def test_roundtrip_preserves_body(project):
    t = _mk(1, "창가의 새벽", "아침")
    LY.save_track_lyrics(project, t, T1)
    assert LY.load_track_lyrics(project, t) == normalize_lyrics(T1)


def test_hash_mismatch_is_caught(project):
    t = _mk(1, "창가의 새벽", "아침")
    LY.save_track_lyrics(project, t, T1)
    assert LY.verify_lyrics_hash(project, t)[0] is True

    # 파일만 몰래 바꾸면 제출 전에 반드시 걸려야 한다
    f = project.root / t["lyrics_path"]
    f.write_text(f.read_text(encoding="utf-8") + "\n몰래 추가한 줄", encoding="utf-8")
    ok, why = LY.verify_lyrics_hash(project, t)
    assert ok is False and "다릅니다" in why


def test_duplicate_title_and_theme_are_errors(project):
    a, b = _mk(1, "같은 제목", "같은 주제"), _mk(2, "같은 제목", "같은 주제")
    LY.save_track_lyrics(project, a, T1)
    LY.save_track_lyrics(project, b, T2)
    errs = LY.validate_set(project, [a, b])["errors"]
    assert any("제목이 트랙" in e for e in errs)
    assert any("가사 주제가 트랙" in e for e in errs)


def test_duplicate_first_line_and_chorus_are_errors(project):
    a, b = _mk(1, "A", "a"), _mk(2, "B", "b")
    LY.save_track_lyrics(project, a, T1)
    LY.save_track_lyrics(project, b, T1)
    errs = LY.validate_set(project, [a, b])["errors"]
    assert any("첫 줄 중복" in e for e in errs)
    assert any("후렴 중복" in e for e in errs)


def test_distinct_tracks_pass(project):
    a, b = _mk(1, "창가의 새벽", "아침"), _mk(2, "두 시의 라디오", "밤")
    LY.save_track_lyrics(project, a, T1)
    LY.save_track_lyrics(project, b, T2)
    r = LY.validate_set(project, [a, b])
    assert r["errors"] == []


def test_missing_structure_tags_is_error(project):
    t = _mk(1, "제목", "주제")
    LY.save_track_lyrics(project, t, "태그 없이 그냥 줄만\n두 줄")
    errs = LY.validate_set(project, [t])["errors"]
    assert any("구조 태그" in e for e in errs)


def test_sung_lines_drops_tags_and_header():
    raw = "# 헤더\n\n> 메타\n\n[Verse]\n노래 줄\n[Inst]\n(연주)\n[Chorus]\n후렴 줄"
    assert LY.sung_lines(raw) == ["노래 줄", "후렴 줄"]


def test_empty_lyrics_rejected(project):
    with pytest.raises(LY.LyricsError):
        LY.save_track_lyrics(project, _mk(1, "제목", "주제"), "   \n\n ")


def test_normalization_is_stable():
    assert lyrics_fingerprint("가사\r\n둘  줄") == lyrics_fingerprint("가사\n둘 줄\n")
