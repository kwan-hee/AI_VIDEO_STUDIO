# Orchestrator 결합 JSON을 받아 project 유형별로 순서가 정해진 실행 계획만 생성하는 Execution Planner
"""
Execution Planner (Sprint 5)

입력: Sprint 4 Orchestrator 결합 JSON.
      키: project, provider_recommendation, prompts (외 request/task_analysis 등)

책임.
  - 실행 계획만 만든다. project 유형에 따라 순서가 정해진 단계 목록을 반환한다.
  - 공급자 실행 없음. AI 호출 없음. 미디어 생성 없음. 구조화 JSON 만 반환.

project 별 실행 순서 (고정 템플릿).
  Malli    : Story  → Image → Video → Voice → Thumbnail → Edit
  Baseball : Script → Image → Video → Voice → Thumbnail → Edit
  Thumbnail: Image  → Thumbnail
  Blog     : Outline → Article → Thumbnail
  Unknown  : (빈 계획)

출력 스키마: schemas/execution_plan_schema.json
Sprint 1~4 파일은 수정하지 않는다.
"""

# project 유형별 고정 실행 순서
PLAN_TEMPLATES = {
    "malli": ["story", "image", "video", "voice", "thumbnail", "edit"],
    "baseball": ["script", "image", "video", "voice", "thumbnail", "edit"],
    "thumbnail": ["image", "thumbnail"],
    "blog": ["outline", "article", "thumbnail"],
    "unknown": [],
}


def _validate_input(orchestration):
    if not isinstance(orchestration, dict):
        raise ValueError("orchestration 은 dict 여야 한다.")
    for k in ("project", "provider_recommendation", "prompts"):
        if k not in orchestration:
            raise ValueError(f"orchestration 에 {k} 가 필요하다.")
    if "providers" not in orchestration["provider_recommendation"]:
        raise ValueError("provider_recommendation 에 providers 가 필요하다.")


def _resolve(step, providers, prompts):
    """단계명 → (provider, backup, prompt_key). Orchestrator 데이터에서만 채운다."""
    def pk(key):
        return key if prompts.get(key) is not None else None

    if step in ("story", "script"):
        return None, None, pk("story_prompt")
    if step in ("outline", "article"):
        return None, None, None
    if step == "image":
        return providers.get("image"), None, pk("image_prompt")
    if step == "video":
        v = providers.get("video")
        return (v["primary"] if v else None), (v["backup"] if v else None), pk("video_prompt")
    if step == "voice":
        return providers.get("voice"), None, pk("voice_prompt")
    if step == "thumbnail":
        return providers.get("image"), None, pk("thumbnail_prompt")
    if step == "edit":
        return providers.get("editing"), None, None
    return None, None, None


def plan_execution(orchestration):
    """
    Orchestrator 결합 JSON → project 유형별 순서 실행 계획.
    계획만 만든다. 실행/호출/미디어 없음. 입력을 변형하지 않는다.
    """
    _validate_input(orchestration)

    project = orchestration["project"]
    providers = orchestration["provider_recommendation"]["providers"]
    prompts = orchestration["prompts"]

    template = PLAN_TEMPLATES.get(project, [])

    steps = []
    for i, name in enumerate(template):
        provider, backup, prompt_key = _resolve(name, providers, prompts)
        steps.append({
            "order": i + 1,
            "step": name,
            "provider": provider,
            "backup": backup,
            "prompt_key": prompt_key,
        })

    return {"project": project, "steps": steps}


if __name__ == "__main__":
    import json
    import os
    import sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(_ROOT, "orchestrator"))
    from orchestrator import orchestrate

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "보크 규칙 설명 영상"
    print(json.dumps(plan_execution(orchestrate(req)), ensure_ascii=False, indent=2))
