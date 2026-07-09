# 자연어 요청을 구조화된 작업 분석으로 변환하는 AI Director 1차 능력 (규칙 기반, AI 호출 없음)
"""
AI Director - Request Analyzer (Sprint 1)

입력: 자연어 사용자 요청 (문자열)
출력: 구조화된 작업 분석 (dict)

이 모듈은 공급자(Flow / Higgsfield / Nano Banana 등)를 선택하지 않는다.
오직 다음만 판단한다.
  - content_type       : 콘텐츠 유형
  - capabilities       : 필요한 추상 능력 (공급자 아님)
  - outputs            : 기대 산출물
  - priority           : 우선순위
  - quality_level      : 품질 등급

AI를 호출하지 않는다. 미디어를 생성하지 않는다. 실행하지 않는다.
계약 정의는 docs/40_REQUEST_SPEC.md, 판단 근거는 docs/30_DECISION_TREE.md 를 따른다.
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

# 품질 신호
PREMIUM_SIGNALS = ["고품질", "최고", "프리미엄", "premium", "고퀄", "정성"]
DRAFT_SIGNALS = ["초안", "draft", "빠르게", "테스트", "가볍게", "확인용", "샘플"]

# 우선순위 신호
HIGH_PRIORITY_SIGNALS = ["급", "긴급", "지금", "오늘", "당장", "마감", "urgent", "asap"]
LOW_PRIORITY_SIGNALS = ["천천히", "나중", "여유", "언젠가"]

# content_type 별 필요 능력 및 기본 산출물
# capabilities 는 추상 능력이다. 공급자 이름을 절대 담지 않는다.
CONTENT_PROFILE = {
    "baseball": {
        "capabilities": ["image", "video", "voice", "subtitle", "composite"],
        "outputs": ["video"],
    },
    "malli": {
        "capabilities": ["image", "video", "voice", "subtitle", "composite"],
        "outputs": ["video"],
    },
    "thumbnail": {
        "capabilities": ["image"],
        "outputs": ["thumbnail"],
    },
    "blog": {
        "capabilities": ["text"],
        "outputs": ["text"],
    },
    "unknown": {
        "capabilities": [],
        "outputs": [],
    },
}


def _count_hits(text, signals):
    """text 안에 등장하는 신호 개수를 센다."""
    return sum(1 for s in signals if s in text)


def _classify_content_type(text):
    """
    요청 문자열로 콘텐츠 유형을 판별한다.
    썸네일/블로그는 형식 지시가 명시적이므로 먼저 검사한다.
    그 다음 야구 vs 동화를 신호 수로 겨룬다.
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


def _detect_quality(text):
    """품질 등급을 판별한다. 기본값 standard."""
    if _count_hits(text, PREMIUM_SIGNALS) > 0:
        return "premium"
    if _count_hits(text, DRAFT_SIGNALS) > 0:
        return "draft"
    return "standard"


def _detect_priority(text):
    """우선순위를 판별한다. 기본값 normal."""
    if _count_hits(text, HIGH_PRIORITY_SIGNALS) > 0:
        return "high"
    if _count_hits(text, LOW_PRIORITY_SIGNALS) > 0:
        return "low"
    return "normal"


def analyze(request):
    """
    자연어 요청을 구조화된 작업 분석으로 변환한다.

    반환 dict 키.
      content_type   : baseball | malli | thumbnail | blog | unknown
      capabilities   : 추상 능력 목록 (공급자 아님)
      outputs        : 기대 산출물 목록
      priority       : high | normal | low
      quality_level  : premium | standard | draft
      needs_clarification : content_type 이 unknown 이면 True

    공급자 선택 없음. AI 호출 없음. 실행 없음.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")

    text = request.lower()

    content_type = _classify_content_type(text)
    profile = CONTENT_PROFILE[content_type]

    return {
        "content_type": content_type,
        "capabilities": list(profile["capabilities"]),
        "outputs": list(profile["outputs"]),
        "priority": _detect_priority(text),
        "quality_level": _detect_quality(text),
        "needs_clarification": content_type == "unknown",
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1:
        req = " ".join(sys.argv[1:])
    else:
        req = "인필드 플라이 규칙을 고품질 영상으로 만들어줘"

    print(json.dumps(analyze(req), ensure_ascii=False, indent=2))
