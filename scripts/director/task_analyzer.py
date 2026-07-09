# 자연어 요청을 프로젝트·단계·도구·Magnific 판단이 담긴 작업 분석으로 변환하는 Task Analyzer
"""
Task Analyzer (Phase 2)

입력: 자연어 사용자 요청 (문자열)
출력: 구조화된 작업 분석 (dict)

판단 항목.
  - project          : malli | baseball | thumbnail | blog | unknown
  - content_type     : story_video | explainer_video | thumbnail_image | blog_text | unknown
  - quality_level    : premium | standard | draft   (Magnific 게이트에 필요)
  - required_steps   : 실행해야 할 추상 단계 목록
  - recommended_tools: 단계별 추천 도구 (1순위 우선, 폴백 뒤)
  - magnific         : 사용 여부와 대상 지점

외부 AI 호출 없음. 미디어 생성 없음. 워크플로 자동화 없음.
분류 규칙은 analyze.py 재사용. 정책 근거: docs/30_DECISION_TREE.md, docs/06_MAGNIFIC_POLICY.md.
"""

from analyze import _classify_content_type, _detect_quality


# project → content_type 매핑
CONTENT_TYPE = {
    "malli": "story_video",
    "baseball": "explainer_video",
    "thumbnail": "thumbnail_image",
    "blog": "blog_text",
    "unknown": "unknown",
}

# project → 필요한 추상 단계 (순서 있음)
REQUIRED_STEPS = {
    "malli": ["image_generation", "video_generation", "voice_generation",
              "subtitle_generation", "composition"],
    "baseball": ["image_generation", "video_generation", "voice_generation",
                 "subtitle_generation", "composition"],
    "thumbnail": ["image_generation", "quality_enhancement"],
    "blog": ["text_writing"],
    "unknown": [],
}

# 단계 → 추천 도구. video_generation 은 project 로 갈린다(아래에서 처리).
STEP_TOOLS = {
    "image_generation": ["Nano Banana"],
    "voice_generation": ["Hedra"],
    "subtitle_generation": ["Whisper"],
    "composition": ["FFmpeg"],
    "quality_enhancement": ["Magnific"],
    "text_writing": ["Claude Code"],
}

# project 별 영상 엔진 우선순위 (1순위 먼저, 폴백 뒤)
VIDEO_TOOLS = {
    "malli": ["Google Flow", "Higgsfield"],
    "baseball": ["Higgsfield", "Google Flow"],
}

# project 별 Magnific 대상 지점
MAGNIFIC_TARGETS = {
    "thumbnail": ["thumbnail"],
    "malli": ["first_scene", "last_scene"],
    "baseball": ["opening_scene", "key_scene"],
}


def _recommend_tools(project, steps):
    """단계 목록을 project 기준 추천 도구로 매핑한다."""
    tools = {}
    for step in steps:
        if step == "video_generation":
            tools[step] = list(VIDEO_TOOLS[project])
        else:
            tools[step] = list(STEP_TOOLS[step])
    return tools


def _decide_magnific(project, quality):
    """
    Magnific 사용 여부와 대상을 판단한다.
    대상 project 이고 품질이 draft 가 아닐 때만 사용한다.
    """
    targets = MAGNIFIC_TARGETS.get(project, [])
    needed = bool(targets) and quality != "draft"
    return {
        "needed": needed,
        "targets": list(targets) if needed else [],
    }


def analyze_task(request):
    """
    자연어 요청을 Phase 2 작업 분석으로 변환한다.
    외부 AI 호출 없음. 실행 없음.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")

    text = request.lower()
    project = _classify_content_type(text)
    quality = _detect_quality(text)

    steps = list(REQUIRED_STEPS[project])
    magnific = _decide_magnific(project, quality)

    # Magnific 불필요면 품질 향상 단계 제거 (썸네일 draft 등)
    if not magnific["needed"] and "quality_enhancement" in steps:
        steps.remove("quality_enhancement")

    return {
        "project": project,
        "content_type": CONTENT_TYPE[project],
        "quality_level": quality,
        "required_steps": steps,
        "recommended_tools": _recommend_tools(project, steps),
        "magnific": magnific,
        "needs_clarification": project == "unknown",
    }


if __name__ == "__main__":
    import json
    import sys

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "인필드 플라이 규칙 영상 만들어줘"
    print(json.dumps(analyze_task(req), ensure_ascii=False, indent=2))
