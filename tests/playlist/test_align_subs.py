"""정렬 · 자막 - 인식 오류 보정과 ASS 구조."""
import pytest

from playlist_studio.align import (TimedLine, align_with_reference,
                                   estimate_lines, parse_srt, timing_report)
from playlist_studio.subtitles import TrackCard, write_ass, write_srt

SRT = """1
00:00:05,000 --> 00:00:08,200
창밖에 비가 내려요

2
00:00:08,500 --> 00:00:11,000
조용이 안자 있어

3
00:00:12,000 --> 00:00:15,500
오늘은 천천히 숨을 고르자
"""
REF = ["창밖에 비가 내려", "조용히 앉아 있어", "오늘은 천천히", "숨을 고르자"]


def test_parse_srt():
    segs = parse_srt(SRT)
    assert len(segs) == 3
    assert segs[0]["start"] == 5.0 and segs[0]["end"] == 8.2


def test_asr_typos_are_replaced_by_reference_text():
    """화면에 나가는 글자는 항상 원문 가사여야 한다."""
    lines = align_with_reference(parse_srt(SRT), REF, track_index=1)
    assert [l.text for l in lines] == REF
    assert all("안자" not in l.text for l in lines)


def test_timings_come_from_asr():
    lines = align_with_reference(parse_srt(SRT), REF, track_index=1)
    assert abs(lines[0].start - 5.0) < 0.5
    assert abs(lines[1].start - 8.5) < 0.5


def test_track_start_offsets_are_applied():
    lines = align_with_reference(parse_srt(SRT), REF, track_start=100.0, track_index=2)
    assert lines[0].start >= 100.0


def test_unmatched_lines_are_interpolated_not_dropped():
    ref = REF + ["ASR 이 전혀 못 들은 줄"]
    lines = align_with_reference(parse_srt(SRT), ref, track_index=1)
    assert len(lines) == len(ref)
    assert lines[-1].source == "interpolated"
    assert lines[-1].start > 0


def test_lines_are_monotonic_and_non_overlapping():
    lines = align_with_reference(parse_srt(SRT), REF, track_index=1)
    for a, b in zip(lines, lines[1:]):
        assert a.end <= b.start + 1e-6
        assert a.end > a.start


def test_estimate_stays_inside_the_track():
    lines = estimate_lines(REF, track_start=10.0, duration=60.0, track_index=1)
    assert lines[0].start >= 10.0
    assert lines[-1].end <= 70.5


def test_estimate_is_honest_about_accuracy():
    rep = timing_report(estimate_lines(REF, track_start=0, duration=60), "estimate")
    assert rep["meets_300ms_target"] is False
    assert "보장하지 않습니다" in rep["accuracy_claim"]


def test_good_asr_claims_target_met():
    lines = align_with_reference(parse_srt(SRT), REF, track_index=1)
    assert timing_report(lines, "srt")["meets_300ms_target"] is True


def test_srt_is_written_in_order(tmp_path):
    lines = [TimedLine(2, 0, "나중 줄", 30.0, 32.0),
             TimedLine(1, 0, "먼저 줄", 5.0, 7.0)]
    p = write_srt(tmp_path / "a.srt", lines)
    body = p.read_text(encoding="utf-8")
    assert body.index("먼저 줄") < body.index("나중 줄")
    assert "00:00:05,000 --> 00:00:07,000" in body


def test_ass_has_styles_cards_and_intro(tmp_path):
    lines = [TimedLine(1, 0, "가사 한 줄", 5.0, 8.0),
             TimedLine(1, 1, "다음 줄", 8.4, 11.0)]
    cards = [TrackCard(1, "창가의 새벽", "first light", 0.0, 30.0)]
    p = write_ass(tmp_path / "a.ass", lines, cards=cards,
                  intro=(0.5, 6.0, "플레이리스트 제목", "3곡 · 12분"))
    body = p.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in body and "[Events]" in body
    assert "PlayResX: 1920" in body and "PlayResY: 1080" in body
    for style in ("Active", "Dim", "TrackTitle", "TrackNo", "Sub"):
        assert f"Style: {style}," in body
    assert "창가의 새벽" in body and "플레이리스트 제목" in body
    assert "Dialogue:" in body


def test_ass_escapes_braces(tmp_path):
    p = write_ass(tmp_path / "a.ass", [TimedLine(1, 0, "중괄호 {test} 포함", 1.0, 3.0)])
    body = p.read_text(encoding="utf-8")
    assert r"\{test\}" in body


def test_next_line_preview_only_within_same_track(tmp_path):
    lines = [TimedLine(1, 0, "일번곡 마지막", 25.0, 28.0),
             TimedLine(2, 0, "이번곡 첫줄", 31.0, 34.0)]
    body = write_ass(tmp_path / "a.ass", lines).read_text(encoding="utf-8")
    dim_events = [l for l in body.splitlines() if l.startswith("Dialogue:") and ",Dim," in l]
    assert dim_events == []


# ---------------------------------------------------------------- 전주 처리
def test_lyrics_do_not_start_during_the_intro():
    """전주에 가사가 뜨는 것이 실사용에서 가장 거슬리는 문제였다."""
    ref = ["첫 줄", "둘째 줄", "셋째 줄"]
    lines = estimate_lines(ref, track_start=0.0, duration=90.0)
    assert lines[0].start >= 90.0 * 0.14        # 기본 전주 15% 이상 비운다


def test_explicit_intro_length_is_respected():
    ref = ["첫 줄", "둘째 줄", "셋째 줄"]
    lines = estimate_lines(ref, track_start=0.0, duration=90.0, lead_in_seconds=20.0)
    assert abs(lines[0].start - 20.0) < 0.01
    assert lines[-1].end <= 90.0


def test_absurd_intro_length_is_clamped():
    """전주를 곡보다 길게 넣어도 가사가 사라지면 안 된다."""
    ref = ["첫 줄", "둘째 줄"]
    lines = estimate_lines(ref, track_start=0.0, duration=60.0, lead_in_seconds=500.0)
    assert lines[0].start <= 60.0 * 0.6 + 0.01
    assert len(lines) == 2


def test_track_offset_still_applies_with_explicit_intro():
    lines = estimate_lines(["가", "나"], track_start=100.0, duration=60.0,
                           lead_in_seconds=10.0)
    assert abs(lines[0].start - 110.0) < 0.01
