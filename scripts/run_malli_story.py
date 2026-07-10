# 말리 동화 첫 실 Claude 스토리 생성 러너 (기존 Story Generator 재사용, 토큰 사용량 캡처)
"""
말리와 숲속의 작은 용기 - 실 Claude 스토리 1건 생성.

기존 story.story_generator.generate_story 를 그대로 사용한다.
토큰 사용량을 얻기 위해 claude_client 를 주입한다(기존 _default_claude_client 는 usage 미노출).
결과를 output/malli/story.json 에 저장하고 story_schema.json 으로 검증한다.
실행 시간과 토큰 사용량을 출력한다.
모델 출력 편차로 JSON 파싱이 실패할 수 있어 최대 3회 재시도한다.

워크플로우/이미지/영상은 실행하지 않는다.
"""

import json
import os
import sys
import time

import anthropic
from jsonschema import Draft7Validator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from story.story_generator import generate_story  # noqa: E402

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2000
_TITLE = "말리와 숲속의 작은 용기"
_MAX_RETRIES = 3
_OUT_DIR = os.path.join(_ROOT, "output", "malli")
_OUT_PATH = os.path.join(_OUT_DIR, "story.json")
_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "story_schema.json")

_usage = {}


def _strip_fence(text):
    """Claude 가 ```json ... ``` 로 감쌀 때 코드펜스를 제거해 순수 JSON 텍스트만 남긴다."""
    t = text.strip()
    if t.startswith("```"):
        t = t[t.find("\n") + 1:].rstrip()  # 첫 줄(``` 또는 ```json) 제거
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _client(prompt):
    """실 Claude 호출. 응답 텍스트(코드펜스 제거) 반환. 토큰 사용량은 _usage 에 누적한다."""
    c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    resp = c.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    _usage["input_tokens"] = _usage.get("input_tokens", 0) + resp.usage.input_tokens
    _usage["output_tokens"] = _usage.get("output_tokens", 0) + resp.usage.output_tokens
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return _strip_fence(text)


def main():
    t0 = time.perf_counter()
    result = None
    for attempt in range(1, _MAX_RETRIES + 1):
        result = generate_story(
            _TITLE,
            title=_TITLE,
            num_scenes=3,
            real=True,
            claude_client=_client,
        )
        if result["status"] == "success":
            break
        print(f"[재시도 {attempt}/{_MAX_RETRIES}] {result['message']}")
    elapsed = time.perf_counter() - t0

    if result["status"] != "success":
        print(f"[실패] {result['message']}")
        return 1

    story = result["story"]

    # 명시적 스키마 재검증
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    errs = sorted(Draft7Validator(schema).iter_errors(story), key=str)
    if errs:
        print("[스키마 위반] " + "; ".join(e.message for e in errs))
        return 1

    os.makedirs(_OUT_DIR, exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    print(f"[성공] 실 Claude 스토리 생성 완료 (mock={result['mock']}).")
    print(f"저장: {_OUT_PATH}")
    print("스키마 검증: 통과")
    print(f"제목: {story['title']} | 장면 수: {len(story['scenes'])}")
    print(f"실행 시간: {elapsed:.2f}s")
    if _usage:
        total = _usage["input_tokens"] + _usage["output_tokens"]
        print(f"토큰 사용량: input={_usage['input_tokens']} "
              f"output={_usage['output_tokens']} total={total}")
    else:
        print("토큰 사용량: 미가용")
    return 0


if __name__ == "__main__":
    sys.exit(main())
