"""중복 생성 차단 - 크레딧 이중 지출 방지."""
import pytest

from playlist_studio.ledger import Ledger, fingerprint


def test_same_inputs_same_fingerprint():
    a = fingerprint("m1", "prompt", "[Verse]\n가사", {"lyrics": "x"})
    b = fingerprint("m1", "prompt", "[Verse]\n가사", {"lyrics": "x"})
    assert a == b


def test_whitespace_normalized_but_content_matters():
    a = fingerprint("m1", "prompt  text", "가사\n\n둘")
    b = fingerprint("m1", "prompt text", "가사\n둘")
    assert a == b
    c = fingerprint("m1", "prompt text", "가사\n셋")
    assert a != c


def test_model_change_changes_fingerprint():
    assert fingerprint("m1", "p", "l") != fingerprint("m2", "p", "l")


def test_claim_blocks_duplicate(tmp_path):
    led = Ledger.load(tmp_path / "l.json")
    fp = fingerprint("m", "p", "l")
    assert led.claim(fp, track_index=1, model="m", credits=240)[0] is True
    assert led.claim(fp, track_index=1, model="m", credits=240)[0] is False


def test_release_allows_retry_but_done_does_not(tmp_path):
    led = Ledger.load(tmp_path / "l.json")
    fp = fingerprint("m", "p", "l")
    led.claim(fp, track_index=1, model="m", credits=48)
    led.release(fp, "생성 실패")
    assert led.claim(fp, track_index=1, model="m", credits=48)[0] is True

    led.complete(fp, provider_job_id="job-1")
    with pytest.raises(ValueError):
        led.release(fp, "이미 완료")


def test_spent_counts_only_completed(tmp_path):
    led = Ledger.load(tmp_path / "l.json")
    f1, f2 = fingerprint("m", "p1", ""), fingerprint("m", "p2", "")
    led.claim(f1, track_index=1, model="m", credits=240)
    led.claim(f2, track_index=2, model="m", credits=240)
    led.complete(f1, provider_job_id="j1")
    assert led.total_credits_spent() == 240
    assert led.done_indices() == {1}


def test_ledger_persists(tmp_path):
    p = tmp_path / "l.json"
    fp = fingerprint("m", "p", "l")
    Ledger.load(p).claim(fp, track_index=1, model="m", credits=64)
    assert Ledger.load(p).get(fp)["status"] == "claimed"
