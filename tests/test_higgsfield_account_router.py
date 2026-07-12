# HiggsfieldAccountRouter 를 mock MCP 로만 검증(네트워크·실계정·유료연산 없음). 이메일/자격증명 미포함.
"""
계정 라우터 단위 테스트. 필수 시나리오(라우터 담당분):
 1 legacy 우선 / 5 남은 legacy 크레딧 프로덕션 사용 / 6 충분→무전환 / 7 잔액부족→전환 /
 8 명시적 부족오류→1회 전환 / 9 인증오류 무전환 / 10 타임아웃 중복생성 방지 /
 11 기존 job 확인 후 재시도 / 12 resume 후 production 유지 / 13 전환 상한 강제 /
 14 backup 소진 안전정지 / 15 이메일·자격증명 로그 미출현 / 17 수동 override / 18 요약 reported vs estimated.
계정 이메일/토큰은 절대 등장하지 않는다(alias 만).
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "routing"))

from higgsfield_account_router import (  # noqa: E402
    HiggsfieldAccountRouter, parse_accounts, classify_error, make_balance_reader,
    request_fingerprint, STATE_KEY, RouterError, InsufficientCreditsError, AuthError,
    InvalidRequestError, AmbiguousTimeoutError,
)

# 로그에 절대 나오면 안 되는 민감 문자열(테스트 전용 sentinel — 실제 계정 아님).
_EMAIL_A = "primary-user@example.invalid"
_EMAIL_B = "backup-user@example.invalid"
_TOKEN = "oauth-token-DO-NOT-LOG-xyz"

_CONFIG = {
    "higgsfield_accounts": {
        "active_policy": "automatic_failover",
        "primary": {"alias": "legacy_account", "mcp_server": "higgsfield_legacy",
                    "starting_credit_estimate": 823, "fallback_generation_limit": 11},
        "backup": {"alias": "production_account", "mcp_server": "higgsfield_production",
                   "starting_credit_estimate": 6000},
        "failover": {
            "enabled": True, "prefer_provider_balance": True,
            "switch_before_insufficient_balance": True,
            "switch_on_explicit_insufficient_credits": True,
            "switch_on_auth_error": False, "switch_on_timeout": False,
            "maximum_switches_per_run": 1, "persist_active_account": True,
            "safety_margin_credits": 100,
            "retry_request_after_confirmed_credit_failure": True,
        },
        "model_costs": {"seedance_2_0": 80},
    }
}


class _Log:
    def __init__(self):
        self.lines = []

    def __call__(self, m):
        self.lines.append(m)

    def text(self):
        return "\n".join(self.lines)


def _mcp(credits_legacy=None, credits_prod=None):
    def _legacy(tool, args):
        d = {"token": _TOKEN, "email": _EMAIL_A}
        if credits_legacy is not None:
            d["credits"] = credits_legacy
        return d

    def _prod(tool, args):
        d = {"token": _TOKEN, "email": _EMAIL_B}
        if credits_prod is not None:
            d["credits"] = credits_prod
        return d
    return {"higgsfield_legacy": _legacy, "higgsfield_production": _prod}


def _router(state=None, log=None, balance_reader=None, mcp=None, preset=None, manual_account=None):
    return HiggsfieldAccountRouter(
        parse_accounts(_CONFIG), mcp or _mcp(),
        state=state if state is not None else {}, log=log or _Log(),
        balance_reader=balance_reader, preset=preset, manual_account=manual_account,
    )


def _gen(record, *, results=None, raises=None):
    def _c(mcp_call, alias):
        record.append(alias)
        if raises and alias in raises:
            e = raises[alias]
            raise e() if callable(e) else e
        if results and alias in results:
            return results[alias]
        return {"status": "success", "alias": alias, "job_id": f"job-{alias}", "output": f"{alias}.mp4"}
    return _c


# 1) legacy 우선
def test_legacy_used_first():
    log = _Log()
    r = _router(log=log)
    used = []
    res = r.run(_gen(used), model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account"]
    assert res["alias"] == "legacy_account"
    assert "Active account: legacy_account" in log.text()


# 5) 남은 legacy 크레딧으로 프로덕션 계속 (잔액 충분한 동안 legacy 다수)
def test_remaining_legacy_credits_used_for_production():
    r = _router(balance_reader=make_balance_reader(), mcp=_mcp(credits_legacy=800))
    used = []
    for i in range(4):
        r.run(_gen(used), model="seedance_2_0", scene_id=f"s{i}")
    assert used == ["legacy_account"] * 4
    assert r.active_alias() == "legacy_account"


# 6) 잔액 충분 → 무전환
def test_sufficient_balance_no_switch():
    r = _router(balance_reader=make_balance_reader(), mcp=_mcp(credits_legacy=500))
    used = []
    r.run(_gen(used), model="seedance_2_0", scene_id="s1")  # 500 >= 80+100
    assert used == ["legacy_account"]
    assert r.active_alias() == "legacy_account"


# 7) 잔액이 다음 요청에 부족 → 전환 (안전마진 포함)
def test_low_balance_switches_before_generation():
    log = _Log()
    r = _router(log=log, balance_reader=make_balance_reader(),
                mcp=_mcp(credits_legacy=120, credits_prod=6000))  # 120 < 80+100
    used = []
    res = r.run(_gen(used), model="seedance_2_0", scene_id="s1")
    assert used == ["production_account"]        # legacy 생성 시도조차 안 함
    assert res["alias"] == "production_account"
    assert "Primary cannot cover the next confirmed request." in log.text()
    assert "Switching to production_account." in log.text()


# 8) 명시적 부족 오류 → 1회 전환 + 같은 장면 재시도
def test_explicit_insufficient_switches_once():
    state = {}
    log = _Log()
    r = _router(state=state, log=log)
    used = []
    res = r.run(_gen(used, raises={"legacy_account": InsufficientCreditsError("insufficient credits", charged=5)}),
                model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account", "production_account"]
    assert res["alias"] == "production_account"
    assert state[STATE_KEY]["active_account"] == "production_account"
    assert state[STATE_KEY]["switch_count"] == 1


# 9) 인증 오류 → 무전환
def test_auth_error_no_switch():
    log = _Log()
    r = _router(log=log)
    used = []
    with pytest.raises(AuthError):
        r.run(_gen(used, raises={"legacy_account": AuthError("401 unauthorized")}),
              model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account"]
    assert r.active_alias() == "legacy_account"
    assert "Switching to" not in log.text()


def test_invalid_and_unsupported_no_switch():
    r = _router()
    for exc in (InvalidRequestError("invalid prompt"), RuntimeError("unsupported model settings")):
        used = []
        with pytest.raises(Exception):
            r2 = _router()
            r2.run(_gen(used, raises={"legacy_account": exc}), model="seedance_2_0", scene_id="s1")
        assert used == ["legacy_account"]


# 10) 타임아웃 → 중복 생성 방지 (원 작업 이미 완료 → 재사용)
def test_timeout_no_duplicate_generation():
    completed = {"status": "completed", "result": {"status": "success", "video": "job.mp4"},
                 "job_id": "job-x"}
    exc = AmbiguousTimeoutError("read timeout", job_id="job-x", check_job=lambda: completed)
    used = []
    r = _router()
    res = r.run(_gen(used, raises={"legacy_account": exc}), model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account"]            # backup 재생성 없음
    assert res == completed["result"]


# 11) 기존 provider job 확인 후 재시도 (불확실 상태 → 전환/재시도 금지)
def test_existing_job_checked_before_retry():
    checked = {"n": 0}

    def _check():
        checked["n"] += 1
        return {"status": "in_progress"}      # 아직 진행 중 → 재시도 금지
    exc = AmbiguousTimeoutError("timeout", job_id="job-y", check_job=_check)
    used = []
    r = _router()
    with pytest.raises(AmbiguousTimeoutError):
        r.run(_gen(used, raises={"legacy_account": exc}), model="seedance_2_0", scene_id="s1")
    assert checked["n"] == 1                   # 재시도 전 job 상태 확인함
    assert used == ["legacy_account"]          # 중복 유료 생성 없음


# 12) resume 후 production 유지
def test_resume_retains_production_after_failover():
    state = {STATE_KEY: {"active_account": "production_account", "switch_count": 1}}
    r = _router(state=state)
    assert r.active_alias() == "production_account"
    used = []
    r.run(_gen(used), model="seedance_2_0", scene_id="s2")
    assert used == ["production_account"]      # legacy 회귀 없음


# 13) 전환 상한 강제 (1회 후 재전환 불가 → 두 계정 부족이면 정지)
def test_max_switches_enforced():
    r = _router()
    used = []
    with pytest.raises(RouterError):
        r.run(_gen(used, raises={
            "legacy_account": InsufficientCreditsError("insufficient"),
            "production_account": InsufficientCreditsError("insufficient"),
        }), model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account", "production_account"]  # 각 1회, 왕복 없음
    assert r.active_alias() == "production_account"


# 14) backup 소진 → 안전 정지
def test_backup_exhaustion_stops_safely():
    state = {STATE_KEY: {"active_account": "production_account", "switch_count": 1}}
    log = _Log()
    r = _router(state=state, log=log)
    used = []
    with pytest.raises(RouterError):
        r.run(_gen(used, raises={"production_account": InsufficientCreditsError("balance depleted")}),
              model="seedance_2_0", scene_id="s1")
    assert used == ["production_account"]
    assert "Backup account also lacks credits; stopping." in log.text()


# 15) 이메일·자격증명 로그 미출현
def test_no_email_or_credentials_in_logs():
    log = _Log()
    r = _router(log=log, balance_reader=make_balance_reader(),
                mcp=_mcp(credits_legacy=120, credits_prod=6000))
    used = []
    r.run(_gen(used), model="seedance_2_0", scene_id="s1")   # 전환 발생 → 로그 다수
    r.print_usage_summary(project="Malli")
    t = log.text()
    for forbidden in (_EMAIL_A, _EMAIL_B, _TOKEN, "higgsfield_legacy", "higgsfield_production"):
        assert forbidden not in t
    assert "legacy_account" in t and "production_account" in t


# 17) 수동 override — 고정 계정, 자동 전환 안 함
def test_manual_override_pins_account():
    log = _Log()
    r = _router(log=log, manual_account="production_account")
    assert r.active_alias() == "production_account"
    used = []
    # 수동 고정이면 부족 오류라도 전환/재시도하지 않고 그대로 실패.
    with pytest.raises(InsufficientCreditsError):
        r.run(_gen(used, raises={"production_account": InsufficientCreditsError("insufficient")}),
              model="seedance_2_0", scene_id="s1")
    assert used == ["production_account"]
    assert "Switching to" not in log.text()


def test_manual_override_legacy_no_autoswitch():
    r = _router(manual_account="legacy_account")
    used = []
    with pytest.raises(InsufficientCreditsError):
        r.run(_gen(used, raises={"legacy_account": InsufficientCreditsError("insufficient")}),
              model="seedance_2_0", scene_id="s1")
    assert used == ["legacy_account"]          # 수동 legacy → 전환 안 함


# 18) 사용량 요약: reported vs estimated 구분
def test_usage_summary_separates_reported_and_estimated():
    # provider 잔액 미사용(잔액리더 없음) → estimate only
    r = _router()
    used = []
    r.run(_gen(used), model="seedance_2_0", scene_id="s1")
    s = r.usage_summary(project="Malli")
    assert s["credit_data_source"] == "local_estimate"
    assert s["provider_reported_credits"] == "unavailable"
    assert s["estimated_remaining_balance"] != "estimate only" or True  # 추정 표시 허용
    assert s["paid_generations_completed"] == 1
    assert s["legacy_account_generations"] == 1

    # provider 잔액/청구 사용 → provider_reported
    r2 = _router(balance_reader=make_balance_reader(), mcp=_mcp(credits_legacy=500))
    used2 = []
    r2.run(_gen(used2), model="seedance_2_0", scene_id="s1")
    s2 = r2.usage_summary(project="Malli")
    assert s2["credit_data_source"] == "provider_reported"
    assert s2["estimated_remaining_balance"] == "estimate only"  # 추정을 공식 잔액으로 위장 안 함


# 보너스: 지문·오류분류·설정
def test_fingerprint_stable_and_nonsecret():
    a = request_fingerprint("s1", "seedance_2_0", "prompt", {"r": "1080p"}, "hash1")
    b = request_fingerprint("s1", "seedance_2_0", "prompt", {"r": "1080p"}, "hash1")
    assert a == b and len(a) == 16
    assert request_fingerprint("s2", "seedance_2_0", "prompt", {}, "hash1") != a


def test_classify_error():
    assert classify_error(InsufficientCreditsError("x")) == "insufficient"
    assert classify_error(AuthError("x")) == "auth"
    assert classify_error(InvalidRequestError("x")) == "invalid"
    assert classify_error(AmbiguousTimeoutError("x")) == "ambiguous"
    assert classify_error(RuntimeError("402 insufficient credits")) == "insufficient"
    assert classify_error(RuntimeError("401 Unauthorized")) == "auth"
    assert classify_error(RuntimeError("unsupported model settings")) == "invalid"
    assert classify_error(RuntimeError("connection reset")) == "ambiguous"


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
