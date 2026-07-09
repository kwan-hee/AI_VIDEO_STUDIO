# 실행 계획과 어댑터 페이로드로 실행 큐를 만들고 순서·상태만 관리하는 Execution Manager
"""
Execution Manager (Sprint 7)

입력.
  - execution_plan  : Sprint 5 Execution Planner 출력 (project, steps[...])
  - adapter_output  : Sprint 6 Provider Adapter 출력 (project, payloads[...])

책임.
  - 실행 큐를 만든다.
  - 실행 순서만 관리한다 (한 번에 하나 ready).
  - 실행 상태를 추적한다.

상태: pending → ready → running → completed | failed.

외부 API 호출 없음. 미디어 생성 없음. 공급자 실행 없음. 상태만 관리한다.
상태 전이는 오직 명시적 호출(start/complete/fail)로만 일어난다. 자동 실행 없음.
출력 스키마: schemas/execution_queue_schema.json
Sprint 1~6 파일은 수정하지 않는다.
"""

# 허용 상태 전이
ALLOWED_TRANSITIONS = {
    "pending": {"ready"},
    "ready": {"running"},
    "running": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


class ExecutionQueue:
    """실행 큐. 순서와 상태만 관리한다. 아무것도 실행하지 않는다."""

    def __init__(self, project, items):
        self.project = project
        self.items = items
        # 첫 단계만 ready, 나머지는 pending
        if self.items:
            self.items[0]["state"] = "ready"

    # --- 조회 ---

    def _find(self, order):
        for item in self.items:
            if item["order"] == order:
                return item
        raise ValueError(f"order {order} 단계를 찾을 수 없다.")

    def ready_steps(self):
        return [it for it in self.items if it["state"] == "ready"]

    def pending_steps(self):
        return [it for it in self.items if it["state"] == "pending"]

    def is_done(self):
        return all(it["state"] in ("completed", "failed") for it in self.items)

    # --- 상태 전이 ---

    def _transition(self, order, new_state):
        item = self._find(order)
        cur = item["state"]
        if new_state not in ALLOWED_TRANSITIONS[cur]:
            raise ValueError(f"잘못된 상태 전이: {cur} -> {new_state} (order {order})")
        item["state"] = new_state
        return item

    def _promote_next(self):
        """다음 pending 단계를 ready 로 승격 (순서 관리)."""
        for item in sorted(self.items, key=lambda x: x["order"]):
            if item["state"] == "pending":
                item["state"] = "ready"
                return

    def start(self, order):
        """ready → running."""
        return self._transition(order, "running")

    def complete(self, order):
        """running → completed. 다음 단계를 ready 로 승격."""
        item = self._transition(order, "completed")
        self._promote_next()
        return item

    def fail(self, order):
        """running → failed. 승격하지 않는다 (순서 중단)."""
        return self._transition(order, "failed")

    # --- 직렬화 ---

    def to_dict(self):
        return {"project": self.project, "queue": self.items}


def _validate_inputs(execution_plan, adapter_output):
    if not isinstance(execution_plan, dict) or not isinstance(adapter_output, dict):
        raise ValueError("두 입력은 모두 dict 여야 한다.")
    if "project" not in execution_plan or "steps" not in execution_plan:
        raise ValueError("execution_plan 에 project 와 steps 가 필요하다.")
    if "project" not in adapter_output or "payloads" not in adapter_output:
        raise ValueError("adapter_output 에 project 와 payloads 가 필요하다.")
    if execution_plan["project"] != adapter_output["project"]:
        raise ValueError("두 입력의 project 가 일치하지 않는다.")


def build_queue(execution_plan, adapter_output):
    """
    실행 계획 + 어댑터 페이로드 → 실행 큐 (모든 단계 pending, 첫 단계 ready).
    provider 있는 단계는 순서대로 페이로드와 짝짓는다. 내부 작성 단계는 페이로드 없음.
    """
    _validate_inputs(execution_plan, adapter_output)

    payloads = adapter_output["payloads"]
    pi = 0
    items = []

    for step in execution_plan["steps"]:
        provider = step.get("provider")
        if provider is None:
            items.append({
                "order": step["order"], "step": step["step"],
                "provider": None, "action": None,
                "state": "pending", "payload": None,
            })
        else:
            if pi >= len(payloads):
                raise ValueError("공급자 단계보다 페이로드가 부족하다.")
            pl = payloads[pi]
            pi += 1
            if pl["provider"] != provider:
                raise ValueError(f"페이로드/단계 공급자 불일치: {pl['provider']} != {provider}")
            items.append({
                "order": step["order"], "step": step["step"],
                "provider": provider, "action": pl["action"],
                "state": "pending", "payload": pl,
            })

    if pi != len(payloads):
        raise ValueError("페이로드가 단계보다 많다.")

    return ExecutionQueue(execution_plan["project"], items)


if __name__ == "__main__":
    import json
    import os
    import sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _sub in ("adapters", "planner", "orchestrator"):
        sys.path.insert(0, os.path.join(_ROOT, _sub))
    from orchestrator import orchestrate
    from execution_planner import plan_execution
    from provider_adapter import build_payloads

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "보크 규칙 설명 영상"
    combined = orchestrate(req)
    plan = plan_execution(combined)
    adapters_out = build_payloads(plan, combined["prompts"])
    q = build_queue(plan, adapters_out)
    print(json.dumps(q.to_dict(), ensure_ascii=False, indent=2))
