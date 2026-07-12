# 유료 검증 클립 수를 상한(최대 3: 말리 2/야구 1)으로 통제하고 리뷰 리포트·승인 게이트를 제공하는 모듈
"""
Quality Validation

목적.
  - 프리셋을 동결하기 전에 최소한의 유료 검증 클립으로 품질을 확인한다.
  - 검증 클립 수를 엄격히 제한한다(전역 최대 3, 말리 2, 야구 1). 사용자 명시 승인 없이 초과 생성 금지.
  - 각 클립마다 리뷰 리포트를 만들고, 명시적 승인 상태가 있어야 프리셋을 동결하게 한다.

이 모듈은 유료 생성을 수행하지 않는다. 생성 여부 허용/차단 판단과 리포트·승인 상태만 관리한다.
실제 클립 생성은 라우터/파이프라인이 담당한다.
"""

# 프로젝트별 유료 검증 클립 상한 + 전역 상한.
VALIDATION_LIMITS = {"malli": 2, "baseball_dictionary": 1}
GLOBAL_MAX_CLIPS = 3

# 프로젝트별 점검 항목(리포트 순서).
CHECKS = {
    "malli": [
        "character_consistency", "face_stability", "clothing_consistency",
        "hand_quality", "body_quality", "walk_run_motion",
        "emotional_expression", "camera_motion", "flicker",
    ],
    "baseball_dictionary": [
        "realistic_sports_motion", "body_mechanics", "equipment_appearance",
        "no_extra_limbs", "no_warped_equipment", "educational_visibility",
        "camera_motion", "flicker",
    ],
}

_PASS = "pass"
_WARN = "warning"
_FAIL = "fail"


class QualityValidationError(Exception):
    """검증 상한 초과 등 오류."""


class QualityValidationSession:
    """
    한 프로젝트의 품질검증 세션. 클립 상한을 강제하고 리뷰 리포트/승인 상태를 관리한다.

    project_type : "malli" | "baseball_dictionary"
    log          : 로그 콜백(str)->None. alias/프로젝트/클립번호만.
    allow_extra  : 사용자가 명시 승인한 추가 클립 수(기본 0). 상한 확장.
    """

    def __init__(self, project_type, *, log=None, allow_extra=0):
        if project_type not in VALIDATION_LIMITS:
            raise QualityValidationError(f"알 수 없는 project_type: {project_type}")
        self.project_type = project_type
        self._log = log or (lambda m: print(m))
        self._extra = max(0, int(allow_extra))
        self._clips = []          # 리포트 목록
        self._approved = False

    # --- 상한 ---
    def clip_limit(self):
        base = min(VALIDATION_LIMITS[self.project_type], GLOBAL_MAX_CLIPS)
        return base + self._extra

    def clips_done(self):
        return len(self._clips)

    def can_generate_another(self):
        """다음 유료 검증 클립을 생성해도 되는가(프로젝트·전역 상한 이내)."""
        return self.clips_done() < self.clip_limit() and self.clips_done() < GLOBAL_MAX_CLIPS + self._extra

    def ensure_can_generate(self):
        """상한 초과면 예외. 상한 도달 후 자동 추가 생성을 막는다."""
        if not self.can_generate_another():
            raise QualityValidationError(
                f"검증 클립 상한 도달({self.clips_done()}/{self.clip_limit()}). "
                "명시적 승인 없이 추가 생성 금지."
            )

    # --- 리뷰 ---
    def review_clip(self, assessments):
        """
        한 검증 클립의 평가(assessments: {check: pass|warning|fail}) → 리뷰 리포트 dict.
        상한을 넘으면 예외. 리포트를 세션에 기록하고, 자동으로 다음 클립을 만들지 않는다.
        recommended_action: 경고/실패가 있으면 조정 권고, 없으면 승인 가능.
        """
        self.ensure_can_generate()
        checks = CHECKS[self.project_type]
        graded = {c: str(assessments.get(c, "unknown")).lower() for c in checks}
        clip_no = self.clips_done() + 1

        worst = _PASS
        for v in graded.values():
            if v == _FAIL:
                worst = _FAIL
                break
            if v == _WARN and worst != _FAIL:
                worst = _WARN
        if worst == _FAIL:
            action = "revise settings and regenerate before approval"
        elif worst == _WARN:
            action = "adjust negative prompt / settings before approval"
        else:
            action = "ready to approve"

        report = {
            "project": self.project_type, "clip": clip_no,
            "checks": graded, "worst": worst,
            "recommended_action": action, "approved": False,
        }
        self._clips.append(report)
        self._log(f"[Quality] Reviewed clip {clip_no}/{self.clip_limit()} "
                  f"for {self.project_type}: {worst} -> {action}")
        return report

    def render_report(self, report):
        """리뷰 리포트를 사람용 텍스트로."""
        lines = ["Quality validation report", "-------------------------",
                 f"Project: {self.project_type}", f"Clip: {report['clip']}"]
        for check, verdict in report["checks"].items():
            lines.append(f"{check}: {verdict}")
        lines.append(f"Recommended action: {report['recommended_action']}")
        return "\n".join(lines)

    # --- 승인 게이트 ---
    def can_approve(self):
        """모든 클립에 실패가 없어야 승인 가능(경고는 사용자 판단)."""
        return bool(self._clips) and all(r["worst"] != _FAIL for r in self._clips)

    def approve(self, *, force=False):
        """
        명시적 승인. 실패 항목이 있으면 force 없이는 승인 불가.
        승인 전에는 프리셋을 동결하지 않는다(preset_manager 가 approved 상태를 요구).
        """
        if not force and not self.can_approve():
            raise QualityValidationError("실패 항목이 있어 승인 불가(강제하려면 force=True).")
        self._approved = True
        for r in self._clips:
            r["approved"] = True
        self._log(f"[Quality] Preset validation approved for {self.project_type}.")
        return True

    def is_approved(self):
        return self._approved


if __name__ == "__main__":
    s = QualityValidationSession("malli")
    rep = s.review_clip({"character_consistency": "pass", "hand_quality": "warning",
                         "camera_motion": "pass", "flicker": "pass"})
    print(s.render_report(rep))
    print("can_approve:", s.can_approve())
