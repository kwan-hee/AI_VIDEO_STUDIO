"""CLI 통합 - 스킬이 실제로 호출하는 경로."""
import io
import json
from contextlib import redirect_stdout

import pytest

from playlist_studio import cli
from playlist_studio.paths import channels_dir
from playlist_studio.state import Workspace


def run(argv):
    """(성공여부, stdout)"""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            cli.main(argv)
        return True, buf.getvalue()
    except SystemExit as e:
        return (e.code in (0, None)), buf.getvalue()


def run_json(argv):
    ok, out = run(["--json", *argv])
    return ok, json.loads(out)


@pytest.fixture()
def proj(studio):
    ok, _ = run(["channel-new", "--name", "CLI 테스트", "--genre", "lofi"])
    assert ok
    ch = sorted(channels_dir().iterdir())[-1].name
    ok, d = run_json(["playlist-new", "--channel", ch, "--title", "CLI 플레이리스트"])
    assert ok
    return d["path"]


def test_channel_and_playlist_creation(proj):
    ok, d = run_json(["status", "--project", proj])
    assert ok and d["state"] == "CHANNEL_READY"


def test_wizard_asks_only_unanswered(proj):
    ok, d = run_json(["config-status", "--project", proj])
    assert ok
    first = [q["key"] for q in d["next"]]
    run(["config-set", "--project", proj, f"{first[0]}=lofi"])
    ok, d2 = run_json(["config-status", "--project", proj])
    assert first[0] not in d2["missing"]


def test_plan_blocked_until_config_complete(proj):
    ok, _ = run(["plan", "--project", proj])
    assert not ok


def _fill_config(proj, n=2):
    run(["config-set", "--project", proj, "genre=lofi", "subgenre=jazzy lofi",
         "purpose=집중", "situation=야근", "vocal_mode=vocal", "lyrics_language=ko",
         "subtitle_language=ko", f"track_count={n}", "track_seconds=30",
         f"total_seconds={30*n}", "bpm_min=70", "bpm_max=88",
         "mood_arc=calm-to-warm", "visual_preset=black-gray-red",
         "thumbnail_language=ko"])


def test_plan_creates_dna_and_tracks(proj):
    _fill_config(proj)
    ok, d = run_json(["plan", "--project", proj])
    assert ok and len(d["tracks"]) == 2
    assert d["sonic_dna"]["genre"] == "lofi"
    ok, s = run_json(["status", "--project", proj])
    assert s["state"] == "PLAN_READY"


def _write_lyrics(proj):
    run(["track-set", "--project", proj, "--index", "1",
         "title=창가의 새벽", "lyrical_theme=아침"])
    run(["track-lyrics", "--project", proj, "--index", "1",
         "--text", "[Verse]\n창틀에 물기\n[Chorus]\n천천히 밝아지는 쪽으로"])
    run(["track-set", "--project", proj, "--index", "2",
         "title=두 시의 라디오", "lyrical_theme=밤"])
    run(["track-lyrics", "--project", proj, "--index", "2",
         "--text", "[Verse]\n식은 컵을 데운다\n[Chorus]\n혼자 불러 본다"])


def test_lyrics_flow_reaches_lyrics_ready(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    _write_lyrics(proj)
    ok, _ = run(["lyrics-validate", "--project", proj])
    assert ok
    ok, _ = run(["lyrics-collect", "--project", proj])
    assert ok
    ok, s = run_json(["status", "--project", proj])
    assert s["state"] == "LYRICS_READY"


def test_duplicate_lyrics_block_collection(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    same = "[Verse]\n같은 첫 줄\n[Chorus]\n같은 후렴"
    for i in (1, 2):
        run(["track-set", "--project", proj, "--index", str(i), f"title=제목{i}",
             f"lyrical_theme=주제{i}"])
        run(["track-lyrics", "--project", proj, "--index", str(i), "--text", same])
    ok, _ = run(["lyrics-validate", "--project", proj])
    assert not ok
    ok, _ = run(["lyrics-collect", "--project", proj])
    assert not ok               # --force 없이는 넘어가지 않는다


def test_cost_shows_shortfall_with_real_balance(proj):
    _fill_config(proj, n=8)
    ok, d = run_json(["cost", "--project", proj, "--model", "se-music-v26-t2a",
                      "--balance", "134"])
    assert ok and d["total_credits"] == 8 * 240 and d["shortfall"] > 0


def test_submit_payload_then_duplicate_is_blocked(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    _write_lyrics(proj)
    run(["lyrics-collect", "--project", proj])

    ok, d = run_json(["submit-payload", "--project", proj, "--index", "1", "--claim"])
    assert ok and d["arguments"]["model"] and d["claimed"] is True
    assert d["mcp_tool"] == "abocado_generate_audio"

    ok2, d2 = run_json(["submit-payload", "--project", proj, "--index", "1", "--claim"])
    assert not ok2 and d2["blocked"] is True and d2["reason"] == "duplicate"


def test_release_then_resubmit_allowed(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    _write_lyrics(proj)
    run(["lyrics-collect", "--project", proj])
    run(["submit-payload", "--project", proj, "--index", "1", "--claim"])
    ok, _ = run(["ledger-release", "--project", proj, "--index", "1",
                 "--reason", "생성 실패"])
    assert ok
    ok, d = run_json(["submit-payload", "--project", proj, "--index", "1", "--claim"])
    assert ok and d["claimed"] is True


def test_tampered_lyrics_block_submission(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    _write_lyrics(proj)
    run(["lyrics-collect", "--project", proj])
    from playlist_studio.paths import find_project
    from playlist_studio.tracks import get_track, load_tracks
    p = find_project(proj)
    t = get_track(load_tracks(p.tracks), 1)
    f = p.root / t["lyrics_path"]
    f.write_text(f.read_text(encoding="utf-8") + "\n몰래 고침", encoding="utf-8")
    ok, out = run(["submit-payload", "--project", proj, "--index", "1"])
    assert not ok


def test_resume_points_at_the_next_step(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    ok, d = run_json(["resume", "--project", proj])
    assert ok and d["next"]["key"] == "lyrics"


def test_verify_detects_and_repairs_damage(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    from playlist_studio.paths import find_project
    p = find_project(proj)
    p.sonic_dna.write_text("{}", encoding="utf-8")
    ok, d = run_json(["verify", "--project", proj])
    assert not ok and d["broken"]
    ok2, _ = run_json(["verify", "--project", proj, "--repair"])
    assert ok2


def test_visual_prompts_never_ask_for_text_in_image(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    ok, d = run_json(["visual-prompts", "--project", proj])
    assert ok
    for p in list(d["thumbnail_prompts"].values()) + [d["intro_prompt"]] + \
             list(d["bg_prompts"].values()):
        assert "no text" in p.lower()
        assert "no readable characters" in p


def test_json_output_is_parseable_everywhere(proj):
    for argv in (["status"], ["config-status"], ["config-show"], ["resume"],
                 ["ledger-show"], ["channel-list"], ["list"]):
        cmd = argv + (["--project", proj] if argv[0] not in ("channel-list", "list") else [])
        ok, out = run(["--json", *cmd])
        json.loads(out)


# ---------------------------------------------------------------- 모델 선택 유지
def _ready_for_submit(proj):
    _fill_config(proj)
    run(["plan", "--project", proj])
    _write_lyrics(proj)
    run(["lyrics-collect", "--project", proj])


def test_cost_persists_the_chosen_model(proj):
    """견적에서 고른 모델이 저장되지 않으면 제출 때 기본값(최고가)로 돌아간다."""
    _ready_for_submit(proj)
    ok, d = run_json(["cost", "--project", proj, "--model", "se-motion-music-t2a",
                      "--balance", "134"])
    assert ok and d["saved_to_config"] is True

    ok, cfg = run_json(["config-show", "--project", proj])
    assert cfg["music_model"] == "se-motion-music-t2a"

    ok, p = run_json(["submit-payload", "--project", proj, "--index", "1"])
    assert p["arguments"]["model"] == "se-motion-music-t2a"
    assert p["credits"] == 48


def test_submit_warns_loudly_when_no_model_was_chosen(proj):
    """모델을 안 고르면 240cr 짜리 기본값이 조용히 쓰이면 안 된다."""
    _ready_for_submit(proj)
    ok, out = run(["submit-payload", "--project", proj, "--index", "1"])
    assert ok
    assert "모델을 고른 적이 없어" in out
    assert "se-motion-music-t2a" in out          # 더 싼 대안을 알려준다


def test_explicit_model_flag_still_wins(proj):
    _ready_for_submit(proj)
    run(["cost", "--project", proj, "--model", "se-motion-music-t2a", "--balance", "134"])
    ok, p = run_json(["submit-payload", "--project", proj, "--index", "1",
                      "--model", "se-lyria3-t2a"])
    assert p["arguments"]["model"] == "se-lyria3-t2a"
    assert p["credits"] == 64


def test_cost_without_model_flag_does_not_overwrite_config(proj):
    _ready_for_submit(proj)
    run(["cost", "--project", proj, "--model", "se-lyria3-t2a", "--balance", "500"])
    ok, d = run_json(["cost", "--project", proj, "--balance", "500"])
    assert d["saved_to_config"] is False
    ok, cfg = run_json(["config-show", "--project", proj])
    assert cfg["music_model"] == "se-lyria3-t2a"
