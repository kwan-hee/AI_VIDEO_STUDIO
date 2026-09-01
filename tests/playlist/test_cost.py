"""크레딧 견적 - 승인 게이트에 쓰이는 숫자."""
import pytest

from playlist_studio.cost import MUSIC_MODELS, UnknownModel, estimate, model_spec


def test_all_snapshot_models_have_required_fields():
    for key, spec in MUSIC_MODELS.items():
        for f in ("display", "credits", "lyrics_mode", "prompt_max"):
            assert f in spec, f"{key} 에 {f} 없음"
        assert spec["credits"] > 0


def test_unknown_model_raises():
    with pytest.raises(UnknownModel):
        model_spec("se-does-not-exist")


def test_total_is_unit_times_remaining():
    e = estimate("se-music-v26-t2a", 8, already_done=2, balance=1000)
    assert e.to_generate == 6
    assert e.total_credits == 6 * 240


def test_shortfall_reported():
    e = estimate("se-music-v26-t2a", 8, balance=134)
    assert e.shortfall == 8 * 240 - 134
    assert "부족" in e.table()


def test_no_balance_says_so_instead_of_guessing():
    e = estimate("se-lyria3-t2a", 4)
    assert e.balance is None and e.shortfall == 0
    assert "조회 안 됨" in e.table()


def test_live_unit_price_overrides_snapshot():
    e = estimate("se-motion-music-t2a", 5, unit_credits=60)
    assert e.total_credits == 300
    assert "MCP 조회값" in e.source
