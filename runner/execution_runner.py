# Execution Queue를 상태 전이로만 처리하고 실행 결과를 반환하는 Execution Runner (공급자 실행 없음)
"""
Execution Runner (Sprint 8)

입력: Sprint 7 Execution Queue (ExecutionQueue 인스턴스).

책임.
  - 큐를 읽는다.
  - ready 단계를 start 한다.
  - completed 또는 failed 로 표시한다.
  - 큐 상태를 갱신한다.
  - 실행 결과를 반환한다.

상태: pending → ready → running → completed | failed.

외부 API 호출 없음. 미디어 생성 없음. 공급자 실행 없음. 상태 전이만.
실제 공급자를 부르지 않으므로 기본은 모두 completed 로 처리한다.
실패 경로는 fail_orders 로 주입해 검증한다 (드라이런).
출력 스키마: schemas/execution_result_schema.json
Sprint 1~7 파일은 수정하지 않는다.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "execution"))

from execution_manager import ExecutionQueue  # noqa: E402  (Sprint 7, 읽기 전용)


def run(queue, fail_orders=None):
    """
    실행 큐를 상태 전이로만 처리한다.
    ready → running → completed(기본) 또는 failed(fail_orders 지정 시).
    failed 는 다음 단계 승격을 막아 진행이 멈춘다 (Sprint 7 규칙).
    큐를 갱신하고 실행 결과 dict 를 반환한다. 공급자 호출 없음.
    """
    if not isinstance(queue, ExecutionQueue):
        raise ValueError("queue 는 ExecutionQueue 인스턴스여야 한다.")

    fail_set = set(fail_orders or [])

    # ready 가 남아 있는 동안 하나씩 처리. 한 번에 하나만 ready (Sprint 7).
    while queue.ready_steps():
        item = queue.ready_steps()[0]
        order = item["order"]
        queue.start(order)                 # ready -> running
        if order in fail_set:
            queue.fail(order)              # running -> failed (승격 중단)
        else:
            queue.complete(order)          # running -> completed (다음 승격)

    return _build_result(queue)


def _build_result(queue):
    items = queue.items
    counts = {"pending": 0, "ready": 0, "running": 0, "completed": 0, "failed": 0}
    for it in items:
        counts[it["state"]] += 1

    if not items:
        status = "empty"
    elif counts["failed"] > 0:
        status = "failed"
    elif counts["completed"] == len(items):
        status = "completed"
    else:
        status = "incomplete"  # 방어적: 진행 중단 등

    return {
        "project": queue.project,
        "status": status,
        "summary": {
            "total": len(items),
            "completed": counts["completed"],
            "failed": counts["failed"],
            "pending": counts["pending"],
        },
        "steps": [
            {"order": it["order"], "step": it["step"],
             "provider": it["provider"], "state": it["state"]}
            for it in items
        ],
    }


if __name__ == "__main__":
    import json

    for _sub in ("adapters", "planner", "orchestrator"):
        sys.path.insert(0, os.path.join(_ROOT, _sub))
    from orchestrator import orchestrate
    from execution_planner import plan_execution
    from provider_adapter import build_payloads
    from execution_manager import build_queue

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "보크 규칙 설명 영상"
    combined = orchestrate(req)
    plan = plan_execution(combined)
    q = build_queue(plan, build_payloads(plan, combined["prompts"]))
    print(json.dumps(run(q), ensure_ascii=False, indent=2))
