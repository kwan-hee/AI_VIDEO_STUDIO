# retry_manager.run_with_retry 의 재시도·failover·시도추적·backoff·검증·스키마 준수를 확인하는 테스트
"""Retry Manager 단위 테스트. 결과는 schemas/retry_result_schema.json 으로 검증. 공급자 직접 실행 없음(핸들러 주입)."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "reliability"))

from retry_manager import run_with_retry, candidates_from_route  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "retry_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

VIDEO_CANDS = ["Higgsfield", "Google Flow"]


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _ok(provider, attempt):
    return {"status": "success", "message": f"{provider} ok"}


def _fail(provider, attempt):
    return {"status": "failed", "message": f"{provider} fail"}


# --- 첫 시도 성공 ---

def test_success_first_attempt():
    r = run_with_retry(VIDEO_CANDS, _ok)
    assert r["status"] == "success"
    assert r["selected_provider"] == "Higgsfield"
    assert r["attempts"] == 1
    assert len(r["log"]) == 1
    assert r["result"] == {"status": "success", "message": "Higgsfield ok"}
    _assert_valid(r)


# --- 같은 공급자 재시도 후 성공 ---

def test_retry_same_provider_then_success():
    calls = {"n": 0}

    def flaky(provider, attempt):
        calls["n"] += 1
        return {"status": "success"} if calls["n"] >= 2 else {"status": "failed"}

    r = run_with_retry(VIDEO_CANDS, flaky, max_attempts=2)
    assert r["status"] == "success"
    assert r["selected_provider"] == "Higgsfield"   # 두 번째 시도에 성공
    assert r["attempts"] == 2
    _assert_valid(r)


# --- primary 소진 후 backup 으로 failover ---

def test_failover_to_backup():
    def only_backup_ok(provider, attempt):
        return {"status": "success"} if provider == "Google Flow" else {"status": "failed"}

    r = run_with_retry(VIDEO_CANDS, only_backup_ok, max_attempts=2)
    assert r["status"] == "success"
    assert r["selected_provider"] == "Google Flow"
    assert r["attempts"] == 3   # primary 2회 실패 + backup 1회 성공
    providers_tried = [e["provider"] for e in r["log"]]
    assert providers_tried == ["Higgsfield", "Higgsfield", "Google Flow"]
    _assert_valid(r)


# --- 전부 실패 ---

def test_all_fail():
    r = run_with_retry(VIDEO_CANDS, _fail, max_attempts=2)
    assert r["status"] == "failed"
    assert r["selected_provider"] is None
    assert r["attempts"] == 4   # 2 후보 x 2 시도
    assert r["result"] == {"status": "failed", "message": "Google Flow fail"}  # 마지막 결과
    _assert_valid(r)


# --- 핸들러 예외는 실패로 기록하고 계속 ---

def test_handler_exception_treated_as_failed():
    def boom(provider, attempt):
        if provider == "Higgsfield":
            raise RuntimeError("provider down")
        return {"status": "success"}

    r = run_with_retry(VIDEO_CANDS, boom, max_attempts=1)
    assert r["status"] == "success"
    assert r["selected_provider"] == "Google Flow"
    # 예외 시도가 failed 로 기록됨
    assert r["log"][0]["status"] == "failed"
    assert "provider down" in r["log"][0]["message"]
    _assert_valid(r)


# --- backoff: 시도 간 지연 계산 + sleeper 주입 ---

def test_backoff_delays_and_sleeper():
    slept = []

    def spy_sleeper(sec):
        slept.append(sec)

    r = run_with_retry(VIDEO_CANDS, _fail, max_attempts=3, backoff_base=0.5, sleeper=spy_sleeper)
    # 각 후보 첫 시도는 지연 0, 이후 0.5,1.0 ... (attempt-1)*base
    delays = [e["delay"] for e in r["log"]]
    assert delays[0] == 0.0
    assert delays[1] == 0.5
    assert delays[2] == 1.0
    # 실제 sleeper 는 지연>0 일 때만 호출
    assert 0.0 not in slept
    assert 0.5 in slept and 1.0 in slept


# --- 라우터 출력 연동 ---

def test_candidates_from_route():
    selection = {"capability": "generate_video", "primary": "Higgsfield",
                 "backup": "Google Flow", "candidates": ["Higgsfield", "Google Flow"],
                 "selected": "Higgsfield"}
    assert candidates_from_route(selection) == ["Higgsfield", "Google Flow"]


def test_run_with_route_candidates():
    selection = {"candidates": ["Higgsfield", "Google Flow"]}
    r = run_with_retry(candidates_from_route(selection), _ok)
    assert r["status"] == "success"
    assert r["selected_provider"] == "Higgsfield"


# --- 검증 ---

def test_empty_candidates_rejected():
    try:
        run_with_retry([], _ok)
    except ValueError:
        return
    raise AssertionError("빈 후보가 거부되지 않음")


def test_bad_max_attempts_rejected():
    for bad in (0, -1):
        try:
            run_with_retry(VIDEO_CANDS, _ok, max_attempts=bad)
        except ValueError:
            continue
        raise AssertionError(f"잘못된 max_attempts 가 거부되지 않음: {bad}")


def test_non_callable_handler_rejected():
    try:
        run_with_retry(VIDEO_CANDS, "not-callable")
    except (ValueError, TypeError):
        return
    raise AssertionError("콜러블 아닌 핸들러가 거부되지 않음")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
