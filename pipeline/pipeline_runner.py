# 요청 하나를 Workflow Engine 으로 전체 아키텍처에 통과시키고 통합 실행 결과를 반환하는 End-to-End Pipeline Runner
"""
End-to-End Pipeline Runner (Phase 4 / Step 3)

목적.
  - 요청 하나로 AI_VIDEO_STUDIO 전체 워크플로를 실행한다. 기존 모듈만 사용한다.

책임.
  - 요청 하나를 받는다.
  - Workflow Engine 을 호출한다(중복 로직 없음).
  - 통합 실행 결과 하나를 반환한다(상태/요약 + 원본 워크플로 결과 중첩).

기존 모듈만 사용한다. 기존 로직을 복제하지 않는다. 기존 Provider 구현 미수정.
외부 API 없음. 실 Nano Banana / Higgsfield / Google Flow / Magnific 불요. 실 ffmpeg 불요.
기본은 mock provider + mock 합성 러너(Workflow Engine 기본값).
출력 스키마: schemas/pipeline_result_schema.json
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_p = os.path.join(_ROOT, "workflow")
if _p not in sys.path:
    sys.path.insert(0, _p)

from workflow_engine import run_workflow  # noqa: E402


def _status(wf):
    """워크플로 결과로 통합 상태를 판정한다."""
    if wf.get("needs_clarification"):
        return "needs_clarification"
    assets = wf.get("assets") or []
    comp = wf.get("composition")
    if comp is not None:
        return "success" if comp.get("status") == "success" else "failed"
    # 합성이 없다: 생성물은 있으나 최종 합성이 없는 상태
    return "partial" if assets else "empty"


def run_pipeline(request, output_root=None, handlers=None, composer_runner=None, exclude=None):
    """
    요청 하나 → 전체 아키텍처 통과 → 통합 실행 결과.
    Workflow Engine 을 그대로 호출하고 상태/요약만 덧붙인다(로직 복제 없음).
    """
    wf = run_workflow(request, output_root=output_root, handlers=handlers,
                      composer_runner=composer_runner, exclude=exclude)

    assets = wf.get("assets") or []
    comp = wf.get("composition")
    status = _status(wf)
    final_output = comp.get("output_path") if (comp and status == "success") else None

    # 실제 등록된 에셋이 사용한 공급자(등록 순서 보존, 중복 제거)
    providers_used = list(dict.fromkeys(a.get("provider") for a in assets))

    return {
        "request": wf["request"],
        "project": wf["project"],
        "status": status,
        "asset_count": len(assets),
        "providers_used": providers_used,
        "final_output": final_output,
        "workflow": wf,
    }


if __name__ == "__main__":
    import json

    req = sys.argv[1] if len(sys.argv) > 1 else "말리가 달님을 만난 동화 영상 만들어줘"
    r = run_pipeline(req)
    summary = {k: v for k, v in r.items() if k != "workflow"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
