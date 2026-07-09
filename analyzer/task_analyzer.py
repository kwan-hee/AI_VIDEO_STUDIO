# 자연어 요청을 project/content_type/task 목록의 구조화 JSON으로 변환하는 Task Analyzer (Sprint 1)
"""
Task Analyzer (Sprint 1)

입력: 자연어 사용자 요청 (문자열)
출력: 구조화된 작업 분석 (dict / JSON 직렬화 가능)

판단 항목.
  - project        : malli | baseball | thumbnail | blog | unknown
  - content_type   : story_video | explainer_video | thumbnail_image | blog_text | unknown
  - required_tasks : 실행해야 할 추상 작업 목록 (공급자 이름 없음)

공급자(Provider) 선택 없음. 외부 AI 호출 없음. 워크플로 실행 없음. 미디어 생성 없음.
출력 스키마: schemas/task_schema.json
"""

# --- 분류 신호 사전 (키워드 기반) ---

BASEBALL_SIGNALS = [
    "야구", "kbo", "보크", "인필드", "플라이", "스트라이크", "볼넷", "번트",
    "이닝", "타자", "투수", "포수", "심판", "규칙", "선수", "홈런", "도루",
    "야구백과", "야구사전",
]

STORY_SIGNALS = [
    "동화", "이야기", "말리", "캐릭터", "교훈", "옛날", "모험", "친구",
    "숲", "마법", "그림책", "잠자리",
]

THUMBNAIL_SIGNALS = ["썸네일", "thumbnail", "표지", "커버"]

BLOG_SIGNALS = ["블로그", "포스팅", "포스트", "기사", "글 써", "글써", "본문"]

# project → content_type
CONTENT_TYPE = {
    "malli": "story_video",
    "baseball": "explainer_video",
    "thumbnail": "thumbnail_image",
    "blog": "blog_text",
    "unknown": "unknown",
}

# project → 필요한 추상 작업 목록 (순서 있음, 공급자 무관)
REQUIRED_TASKS = {
    "malli": ["image_generation", "video_generation", "voice_generation",
              "subtitle_generation", "composition"],
    "baseball": ["image_generation", "video_generation", "voice_generation",
                 "subtitle_generation", "composition"],
    "thumbnail": ["image_generation", "quality_enhancement"],
    "blog": ["text_writing"],
    "unknown": [],
}


def _count_hits(text, signals):
    return sum(1 for s in signals if s in text)


def _detect_project(text):
    """
    요청으로 project 를 판별한다.
    형식 지시(썸네일/블로그)를 먼저 검사하고, 그다음 야구 vs 동화를 신호 수로 겨룬다.
    """
    if _count_hits(text, THUMBNAIL_SIGNALS) > 0:
        return "thumbnail"
    if _count_hits(text, BLOG_SIGNALS) > 0:
        return "blog"

    baseball = _count_hits(text, BASEBALL_SIGNALS)
    story = _count_hits(text, STORY_SIGNALS)

    if baseball == 0 and story == 0:
        return "unknown"
    return "baseball" if baseball >= story else "malli"


def analyze_task(request):
    """
    자연어 요청 → 구조화 작업 분석.
    공급자 선택 없음. 외부 AI 호출 없음. 실행 없음.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")

    text = request.lower()
    project = _detect_project(text)

    return {
        "project": project,
        "content_type": CONTENT_TYPE[project],
        "required_tasks": list(REQUIRED_TASKS[project]),
        "needs_clarification": project == "unknown",
    }


if __name__ == "__main__":
    import json
    import sys

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "인필드 플라이 규칙 영상 만들어줘"
    print(json.dumps(analyze_task(req), ensure_ascii=False, indent=2))
