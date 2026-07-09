# Task Analyzer 출력을 받아 능력별 최적 공급자와 Magnific 적용 지점을 추천하는 Provider Selector
"""
Provider Selector (Sprint 2)

입력: Sprint 1 Task Analyzer 가 낸 작업 분석 dict/JSON.
      키: project, content_type, required_tasks, needs_clarification

책임.
  1. 능력별 최적 공급자를 추천한다.
  2. 어떤 공급자도 실행하지 않는다.
  3. 구조화 JSON 만 반환한다.

외부 AI 호출 없음. 미디어 생성 없음. 워크플로 없음.
출력 스키마: schemas/provider_schema.json

공급자 정책.
  Malli Story
    - Image: Nano Banana
    - Video: Google Flow (Primary) / Backup: Higgsfield
    - Voice: Edge TTS
    - Image Enhancement: Magnific (Thumbnail + First Scene + Last Scene)
    - Editing: FFmpeg
  Baseball Dictionary
    - Image: Nano Banana
    - Video: Higgsfield (Primary) / Backup: Google Flow
    - Voice: Edge TTS
    - Image Enhancement: Magnific (Thumbnail + Opening Scene)
    - Editing: FFmpeg
"""

# project 별 영상 엔진 우선순위 (Primary + Backup)
VIDEO_PRIORITY = {
    "malli": {"primary": "Google Flow", "backup": "Higgsfield"},
    "baseball": {"primary": "Higgsfield", "backup": "Google Flow"},
}

# project 별 Magnific 적용 지점
MAGNIFIC_TARGETS = {
    "malli": ["thumbnail", "first_scene", "last_scene"],
    "baseball": ["thumbnail", "opening_scene"],
    "thumbnail": ["thumbnail"],
}

# 고정 공급자
IMAGE_PROVIDER = "Nano Banana"
VOICE_PROVIDER = "Edge TTS"
EDITING_PROVIDER = "FFmpeg"
ENHANCEMENT_PROVIDER = "Magnific"

# Task Analyzer 작업명
IMAGE_TASK = "image_generation"
VIDEO_TASK = "video_generation"
VOICE_TASK = "voice_generation"
EDITING_TASK = "composition"


def _validate_input(task_analysis):
    """Sprint 1 출력 형식인지 최소 검증."""
    if not isinstance(task_analysis, dict):
        raise ValueError("task_analysis 는 dict 여야 한다.")
    if "project" not in task_analysis or "required_tasks" not in task_analysis:
        raise ValueError("task_analysis 에 project 와 required_tasks 가 필요하다.")
    if not isinstance(task_analysis["required_tasks"], list):
        raise ValueError("required_tasks 는 리스트여야 한다.")


def _empty_providers():
    return {
        "image": None,
        "video": None,
        "voice": None,
        "editing": None,
        "image_enhancement": None,
    }


def select_providers(task_analysis):
    """
    작업 분석 → 능력별 공급자 추천.
    추천만 한다. 실행/호출 없음. 입력을 변형하지 않는다.
    """
    _validate_input(task_analysis)

    project = task_analysis["project"]
    tasks = task_analysis["required_tasks"]

    # 판별 실패나 unknown 은 추천하지 않는다.
    if project == "unknown" or task_analysis.get("needs_clarification"):
        return {"project": project, "providers": _empty_providers()}

    providers = _empty_providers()

    if IMAGE_TASK in tasks:
        providers["image"] = IMAGE_PROVIDER

    if VIDEO_TASK in tasks and project in VIDEO_PRIORITY:
        providers["video"] = dict(VIDEO_PRIORITY[project])

    if VOICE_TASK in tasks:
        providers["voice"] = VOICE_PROVIDER

    if EDITING_TASK in tasks:
        providers["editing"] = EDITING_PROVIDER

    if project in MAGNIFIC_TARGETS and IMAGE_TASK in tasks:
        providers["image_enhancement"] = {
            "provider": ENHANCEMENT_PROVIDER,
            "targets": list(MAGNIFIC_TARGETS[project]),
        }

    return {"project": project, "providers": providers}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        ta = json.loads(sys.argv[1])
    else:
        ta = {
            "project": "malli",
            "content_type": "story_video",
            "required_tasks": ["image_generation", "video_generation",
                               "voice_generation", "subtitle_generation", "composition"],
            "needs_clarification": False,
        }
    print(json.dumps(select_providers(ta), ensure_ascii=False, indent=2))
