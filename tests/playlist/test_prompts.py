"""프롬프트 조립 - 모델별 글자수 한도와 실존 아티스트 차단."""
import pytest

from playlist_studio.cost import MUSIC_MODELS
from playlist_studio.dna import (PromptPolicyError, build_sonic_dna,
                                 build_visual_dna, check_no_artist,
                                 dna_paragraph, visual_paragraph)
from playlist_studio.tracks import build_music_prompt, build_plan

CFG = dict(genre="lofi", subgenre="jazzy tape lofi", vocal_mode="vocal",
           lyrics_language="ko", bpm_min=70, bpm_max=90, track_count=6,
           mood_arc="calm-to-warm", track_seconds=180,
           visual_preset="black-gray-red")
LYRICS = "[Verse]\n첫 줄\n둘째 줄\n[Chorus]\n후렴 한 줄\n후렴 두 줄"


@pytest.fixture()
def dna():
    return build_sonic_dna(CFG)


@pytest.mark.parametrize("model", list(MUSIC_MODELS))
def test_prompt_fits_model_limit(dna, model):
    track = build_plan(CFG, dna)[0]
    p = build_music_prompt(track, dna, model, LYRICS)
    spec = MUSIC_MODELS[model]
    assert len(p["prompt"]) <= spec["prompt_max"]
    assert len(p["prompt"]) >= spec["prompt_min"]


@pytest.mark.parametrize("model", list(MUSIC_MODELS))
def test_lyrics_land_in_the_right_place(dna, model):
    track = build_plan(CFG, dna)[0]
    p = build_music_prompt(track, dna, model, LYRICS)
    spec = MUSIC_MODELS[model]
    if spec["lyrics_mode"] == "prompt_merged":
        assert "Lyrics:" in p["prompt"]
        assert not p["options"].get("lyrics")
    else:
        assert p["options"][spec["lyrics_field"]] == LYRICS


def test_vocal_model_without_lyrics_refuses(dna):
    track = build_plan(CFG, dna)[0]
    with pytest.raises(ValueError, match="가사가 필요"):
        build_music_prompt(track, dna, "se-music-v26-t2a", "")


def test_instrumental_sets_flag_and_needs_no_lyrics():
    cfg = dict(CFG, vocal_mode="instrumental")
    d = build_sonic_dna(cfg)
    assert d["vocal_gender"] == "none"
    p = build_music_prompt(build_plan(cfg, d)[0], d, "se-music-v26-t2a", "")
    assert p["options"].get("is_instrumental") is True


def test_oversized_lyrics_refused(dna):
    track = build_plan(CFG, dna)[0]
    with pytest.raises(ValueError, match="한도"):
        build_music_prompt(track, dna, "se-music-v26-t2a", "가" * 4000)


@pytest.mark.parametrize("bad", [
    "warm lofi in the style of some famous singer",
    "sounds like a well known band",
    "a tribute to that artist",
])
def test_artist_imitation_blocked(bad):
    with pytest.raises(PromptPolicyError):
        check_no_artist(bad)


def test_dna_paragraph_carries_no_artist_clause(dna):
    assert "Do not imitate any real, named artist" in dna_paragraph(dna)


def test_visual_prompt_forbids_text():
    v = build_visual_dna(CFG)
    para = visual_paragraph(v)
    assert "no readable characters" in para
    assert "text" in v["forbidden"]


def test_tracks_vary_across_the_album(dna):
    tracks = build_plan(CFG, dna)
    assert len({t["intro_lead"] for t in tracks}) == len(tracks)      # 인트로 전부 다름
    assert len({t["bpm"] for t in tracks}) > 1                        # BPM 변화
    assert len({t["structure"] for t in tracks}) > 1                  # 구조 변형
    # 정서 곡선을 따라 에너지가 올라간다
    assert tracks[-1]["energy_level"] > tracks[0]["energy_level"]


def test_bpm_stays_inside_configured_range(dna):
    for t in build_plan(CFG, dna):
        assert CFG["bpm_min"] <= t["bpm"] <= CFG["bpm_max"]
