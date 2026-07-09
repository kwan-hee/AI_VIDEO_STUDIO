# 사용자 요청을 Task Analyzer → Provider Selector → Prompt Generator 순서로 엮어 하나의 JSON으로 반환하는 Orchestrator
"""
Orchestrator (Sprint 4)

사용자 요청 하나를 받아 3단계를 순서대로 호출하고 결합 JSON 을 반환한다.
  1. Task Analyzer   (Sprint 1) : 요청 → 작업 분석
  2. Provider Selector (Sprint 2): 작업 분석 → 공급자 추천
  3. Prompt Generator (Sprint 3) : 분석 + 추천 → 프롬프트

외부 AI 호출 없음. 공급자 실행 없음. 미디어 생성 없음.
Sprint 1, 2, 3 파일은 수정하지 않는다 (읽기 전용 호출).
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("analyzer", "selector", "generator"):
    _p = os.path.join(_ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from task_analyzer import analyze_task          # noqa: E402  (Sprint 1)
from provider_selector import select_providers  # noqa: E402  (Sprint 2)
from prompt_generator import generate_prompts   # noqa: E402  (Sprint 3)


def orchestrate(request, topic=None):
    """
    자연어 요청 → 결합 JSON.
    topic 미지정 시 요청 문자열 자체를 프롬프트 주제로 사용한다.
    실행/호출/미디어 생성 없음.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")

    task_analysis = analyze_task(request)
    provider_recommendation = select_providers(task_analysis)
    prompt_set = generate_prompts(
        task_analysis,
        provider_recommendation,
        topic=topic if topic else request,
    )

    return {
        "request": request,
        "project": task_analysis["project"],
        "needs_clarification": task_analysis.get("needs_clarification", False),
        "task_analysis": task_analysis,
        "provider_recommendation": provider_recommendation,
        "prompts": prompt_set["prompts"],
    }


if __name__ == "__main__":
    import json

    if len(sys.argv) > 1:
        request, topic = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        demo_path = os.path.join(_ROOT, "examples", "demo_request.json")
        with open(demo_path, encoding="utf-8") as f:
            demo = json.load(f)
        request, topic = demo["request"], demo.get("topic")

    print(json.dumps(orchestrate(request, topic), ensure_ascii=False, indent=2))
