# 실행 큐를 로컬에서 시뮬레이션해 표준 모의 실행 결과만 반환하는 Local Executor (외부 호출·실제 미디어 없음)
"""
Local Executor (Sprint 9 / Phase 2)

입력: Sprint 7/8 Execution Queue (ExecutionQueue 인스턴스 또는 {project, queue} dict).

책임.
  - 실행 큐 항목을 읽는다.
  - 공급자 실행을 로컬에서 시뮬레이션한다.
  - 표준 모의 실행 결과를 반환한다.

금지.
  - 외부 API 호출 없음.
  - 실제 미디어 생성 없음 (output_path 는 문자열일 뿐, 파일을 쓰지 않는다).
  - 브라우저 자동화 없음.
  - FFmpeg 사용 없음.

각 모의 결과는 다음을 포함한다.
  order, step, provider, action, status, output_path, message

출력 스키마: schemas/local_execution_result_schema.json
Sprint 1~8 파일은 수정하지 않는다.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "execution"))

from execution_manager import ExecutionQueue  # noqa: E402  (Sprint 7, 읽기 전용)

# action → 모의 산출물 확장자
MEDIA_EXT = {
    "generate_image": ".png",
    "enhance_image": ".png",
    "generate_video": ".mp4",
    "text_to_speech": ".mp3",
    "compose": ".mp4",
}


def _ext(action, step):
    if action in MEDIA_EXT:
        return MEDIA_EXT[action]
    if step == "thumbnail":
        return ".png"
    return ".txt"  # 내부 텍스트 단계(story/script/outline/article)


def _mock_result(item, project, failed):
    order = item["order"]
    step = item["step"]
    provider = item["provider"]
    action = item["action"]

    if failed:
        return {
            "order": order, "step": step, "provider": provider, "action": action,
            "status": "failed", "output_path": None,
            "message": f"{provider or 'internal'} {step} 로컬 시뮬레이션 실패",
        }

    ext = _ext(action, step)
    output_path = f"output/{project}/{order:02d}_{step}{ext}"
    return {
        "order": order, "step": step, "provider": provider, "action": action,
        "status": "success", "output_path": output_path,
        "message": f"{provider or 'internal'} {action or step} 로컬 시뮬레이션 완료",
    }


def _read_queue(queue):
    """ExecutionQueue 또는 {project, queue} dict 에서 (project, items) 추출. 읽기 전용."""
    if isinstance(queue, ExecutionQueue):
        return queue.project, queue.items
    if isinstance(queue, dict) and "project" in queue and "queue" in queue:
        if not isinstance(queue["queue"], list):
            raise ValueError("queue['queue'] 는 리스트여야 한다.")
        return queue["project"], queue["queue"]
    raise ValueError("queue 는 ExecutionQueue 또는 {project, queue} dict 여야 한다.")


def execute_local(queue, fail_orders=None):
    """
    실행 큐를 로컬 시뮬레이션한다. 외부 호출·실제 미디어 없음.
    입력을 변형하지 않는다. 표준 모의 결과 dict 를 반환한다.
    """
    project, items = _read_queue(queue)
    fail_set = set(fail_orders or [])

    results = [_mock_result(item, project, item["order"] in fail_set) for item in items]
    return {"project": project, "results": results}


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
    print(json.dumps(execute_local(q), ensure_ascii=False, indent=2))
