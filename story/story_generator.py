# 제목/주제로부터 구조화 스토리 패키지(제목/요약/교훈/장면)를 만드는 Story Generator (기본 mock, 실 Claude 옵트인)
"""
Story Generator (Phase 7 / Step 1)

목적.
  - 이미지/영상 생성 이전에, 제목/주제로부터 구조화된 장면 대본을 만든다.
  - 대상 프로젝트: 말리 동화 우선.

입력.
  - request: 사용자 요청(필수)
  - title/topic: 제목/주제(선택, 미지정 시 request 사용)
  - num_scenes: 장면 수(기본 3)

출력(결과 래퍼).
  {status, story, mock, message}
  story = {title, summary, moral, scenes:[{scene_number, narration, image_prompt, video_prompt, duration}]}

기본은 mock 이다. 실 Claude 생성은 옵트인 전용이다(real=True 또는 환경변수 CLAUDE_STORY_REAL=1).
실 Claude/API 가 미가용이면 status="failed" 로 graceful 처리한다. 일반 테스트는 실 Claude 를 호출하지 않는다.
generator 를 직접 주입하면 그것이 최우선이다(테스트/커스텀 백엔드).
기존 provider 는 수정하지 않는다. 스토리 스키마: schemas/story_schema.json
"""

import json
import os

from jsonschema import Draft7Validator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "story_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)
_VALIDATOR = Draft7Validator(_SCHEMA)

# 실 실행 옵트인 환경변수. "1" 일 때만 실 Claude 를 시도한다(기본은 mock).
_REAL_ENV = "CLAUDE_STORY_REAL"

# 기본 장면 길이(초)
_DEFAULT_SCENE_DURATION = 5.0


def _mock_generator(title, topic, num_scenes):
    """실 Claude 없이 결정적 구조화 스토리를 만든다(배관 검증용 placeholder 대본)."""
    scenes = []
    for i in range(1, num_scenes + 1):
        scenes.append({
            "scene_number": i,
            "narration": f"{title} 장면 {i}. 이야기가 이어진다.",
            "image_prompt": f"{topic}, 장면 {i}, 동화풍 일러스트, 따뜻한 색감",
            "video_prompt": f"{topic}, 장면 {i}, 부드러운 카메라 움직임",
            "duration": _DEFAULT_SCENE_DURATION,
        })
    return {
        "title": title,
        "summary": f"{title}에 대한 짧은 이야기.",
        "moral": "작은 용기가 큰 변화를 만든다.",
        "scenes": scenes,
    }


def _real_generator(title, topic, num_scenes):
    """
    실 Claude 로 구조화 스토리를 생성한다(옵트인 전용).
    실 백엔드(Claude API/SDK)가 연결되어 있지 않으면 RuntimeError 를 올려
    generate_story 가 status=failed 로 graceful 처리하게 한다. 준비되면 여기서 호출하도록 교체한다.
    """
    try:
        import anthropic  # 실 백엔드(선택 설치). 미설치 시 ImportError.
    except ImportError as e:
        raise RuntimeError(
            "실 Claude 백엔드가 연결되어 있지 않다. "
            f"({_REAL_ENV}=1 옵트인했으나 anthropic SDK 미설치)"
        ) from e
    # pragma: no cover 아래는 실 백엔드 준비 시 구현
    raise RuntimeError("실 Claude 스토리 생성이 아직 구현되지 않았다.")  # pragma: no cover


def generate_story(request, title=None, topic=None, num_scenes=3, real=None, generator=None):
    """
    요청/제목/주제 → 구조화 스토리 패키지.
    기본은 mock. 실 Claude 는 옵트인(real=True 또는 CLAUDE_STORY_REAL=1)일 때만 시도, 미가용 시 graceful fail.
    request 오류/잘못된 num_scenes 는 ValueError. 생성/검증 실패는 status="failed".
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")
    if not isinstance(num_scenes, int) or num_scenes < 1:
        raise ValueError("num_scenes 는 1 이상의 정수여야 한다.")

    title = title or request
    topic = topic or title

    # 모드 결정: 주입 generator > 실 옵트인 > mock(기본)
    if real is None:
        real = os.environ.get(_REAL_ENV) == "1"
    if generator is not None:
        gen, is_mock = generator, False
    elif real:
        gen, is_mock = _real_generator, False
    else:
        gen, is_mock = _mock_generator, True

    try:
        story = gen(title, topic, num_scenes)
        errs = sorted(_VALIDATOR.iter_errors(story), key=str)
        if errs:
            raise ValueError("스토리 스키마 위반: " + "; ".join(e.message for e in errs))
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "story": None, "mock": is_mock,
                "message": f"스토리 생성 실패: {e}"}

    return {"status": "success", "story": story, "mock": is_mock,
            "message": "mock 스토리 생성 완료." if is_mock else "스토리 생성 완료."}


if __name__ == "__main__":
    r = generate_story("말리가 달님을 만난 날", num_scenes=3)
    print(json.dumps(r, ensure_ascii=False, indent=2))
