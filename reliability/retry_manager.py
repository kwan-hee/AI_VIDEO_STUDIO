# 공급자 실행에 재사용 가능한 재시도·failover 를 제공하는 Retry Manager (핸들러 주입, 직접 실행 없음)
"""
Retry Manager (Phase 5 / Step 4)

목적.
  - 공급자 실행에 재사용 가능한 재시도/failover 지원을 제공한다.

책임.
  - 실패한 공급자 호출을 재시도한다.
  - 시도 횟수를 추적한다.
  - max_attempts 를 지원한다.
  - 단순 backoff 전략을 지원한다.
  - Provider Router 출력으로 failover 후보를 선택한다.
  - 구조화 재시도 결과를 반환한다.

핸들러가 주입되지 않으면 공급자를 직접 실행하지 않는다. 외부 API 없음. 미디어 생성 없음.
모델: 후보(primary→backup) 순회, 각 후보를 max_attempts 까지 재시도, 첫 성공에 멈춘다.
backoff: 후보 내 n번째 시도의 지연 = backoff_base * (n-1). 첫 시도는 지연 0.
출력 스키마: schemas/retry_result_schema.json
"""

import time


def candidates_from_route(route_selection):
    """Provider Router 선택 결과에서 failover 후보 목록을 뽑는다."""
    if not isinstance(route_selection, dict) or "candidates" not in route_selection:
        raise ValueError("route_selection 에 candidates 가 필요하다.")
    return list(route_selection["candidates"])


def _entry(attempt, provider, status, delay, message):
    return {"attempt": attempt, "provider": provider, "status": status,
            "delay": delay, "message": str(message)}


def _result(status, selected, attempts, max_attempts, candidates, log, result):
    return {
        "status": status,
        "selected_provider": selected,
        "attempts": attempts,
        "max_attempts": max_attempts,
        "candidates": list(candidates),
        "log": log,
        "result": result,
    }


def run_with_retry(candidates, handler, max_attempts=1, backoff_base=0.0, sleeper=None):
    """
    후보 공급자들을 재시도/failover 로 실행한다.
    handler(provider, attempt) -> dict(최소 "status": success|failed). 예외는 실패로 기록하고 계속.
    첫 성공에 멈추고, 모두 소진하면 실패. 아무것도 직접 실행하지 않는다(handler 만 호출).
    """
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates 는 비어 있지 않은 리스트여야 한다.")
    if not callable(handler):
        raise ValueError("handler 는 콜러블이어야 한다.")
    if not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts 는 1 이상의 정수여야 한다.")

    sleeper = sleeper or time.sleep
    log = []
    attempts = 0
    last_result = None

    for provider in candidates:
        for a in range(1, max_attempts + 1):
            attempts += 1
            delay = backoff_base * (a - 1)
            if delay > 0:
                sleeper(delay)
            try:
                res = handler(provider, attempts)
                status = res.get("status", "failed") if isinstance(res, dict) else "failed"
                message = res.get("message", "") if isinstance(res, dict) else ""
            except Exception as e:  # noqa: BLE001
                res, status, message = None, "failed", str(e)

            last_result = res
            log.append(_entry(attempts, provider, "success" if status == "success" else "failed",
                              delay, message))

            if status == "success":
                return _result("success", provider, attempts, max_attempts, candidates, log, res)

    return _result("failed", None, attempts, max_attempts, candidates, log, last_result)


if __name__ == "__main__":
    import json

    def demo_handler(provider, attempt):
        # 데모: Higgsfield 는 실패, Google Flow 성공
        return {"status": "success" if provider == "Google Flow" else "failed",
                "message": f"{provider} attempt {attempt}"}

    print(json.dumps(run_with_retry(["Higgsfield", "Google Flow"], demo_handler, max_attempts=2),
                     ensure_ascii=False, indent=2))
