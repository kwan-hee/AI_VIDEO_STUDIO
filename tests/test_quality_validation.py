# 품질검증 상한(최대3: 말리2/야구1)·리뷰 리포트·승인 게이트 테스트 (유료연산 없음)
"""
Quality Validation 테스트. 필수: 2 검증 클립이 설정 상한에서 멈춤.
추가: 리포트 형식, 실패 시 승인 불가, 명시 승인 후에만 approved.
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "quality"))

from quality_validation import (  # noqa: E402
    QualityValidationSession, QualityValidationError, VALIDATION_LIMITS, GLOBAL_MAX_CLIPS,
)


# 2) 검증 클립이 설정 상한에서 멈춘다 (말리 2, 야구 1, 전역 3)
def test_validation_stops_at_malli_limit():
    s = QualityValidationSession("malli")
    assert s.clip_limit() == 2
    s.review_clip({c: "pass" for c in ("character_consistency", "hand_quality")})
    s.review_clip({c: "pass" for c in ("character_consistency", "hand_quality")})
    assert not s.can_generate_another()
    with pytest.raises(QualityValidationError):
        s.review_clip({"character_consistency": "pass"})   # 3번째 자동 생성 금지


def test_validation_stops_at_baseball_limit():
    s = QualityValidationSession("baseball_dictionary")
    assert s.clip_limit() == 1
    s.review_clip({"realistic_sports_motion": "pass"})
    assert not s.can_generate_another()
    with pytest.raises(QualityValidationError):
        s.review_clip({"realistic_sports_motion": "pass"})


def test_global_max_three():
    assert GLOBAL_MAX_CLIPS == 3
    assert VALIDATION_LIMITS["malli"] + VALIDATION_LIMITS["baseball_dictionary"] == 3


# 리뷰 리포트 형식 + 권고
def test_review_report_and_action():
    s = QualityValidationSession("malli")
    rep = s.review_clip({"character_consistency": "pass", "face_stability": "pass",
                         "hand_quality": "warning", "camera_motion": "pass", "flicker": "pass"})
    assert rep["clip"] == 1
    assert rep["checks"]["hand_quality"] == "warning"
    assert "adjust" in rep["recommended_action"]
    text = s.render_report(rep)
    assert "Quality validation report" in text
    assert "hand_quality: warning" in text


# 승인 게이트: 실패 있으면 승인 불가, 명시 승인 필요
def test_approval_gate_requires_explicit_approval():
    s = QualityValidationSession("malli")
    s.review_clip({"character_consistency": "pass", "hand_quality": "pass"})
    assert s.is_approved() is False        # 자동 승인 없음
    assert s.can_approve() is True
    s.approve()
    assert s.is_approved() is True


def test_failed_check_blocks_approval():
    s = QualityValidationSession("baseball_dictionary")
    s.review_clip({"realistic_sports_motion": "fail", "no_extra_limbs": "pass"})
    assert s.can_approve() is False
    with pytest.raises(QualityValidationError):
        s.approve()                         # 실패 있으면 승인 불가
    assert s.approve(force=True) is True    # 강제만 가능


def test_extra_clips_require_explicit_allowance():
    s = QualityValidationSession("baseball_dictionary", allow_extra=1)
    assert s.clip_limit() == 2              # 명시 승인으로만 상한 확장
    s.review_clip({"realistic_sports_motion": "pass"})
    s.review_clip({"realistic_sports_motion": "pass"})
    assert not s.can_generate_another()


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
