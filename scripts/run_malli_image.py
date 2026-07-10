# 말리 story.json scene 1 image_prompt 로 실 Nano Banana 이미지 1장 생성 러너 (기존 provider 재사용)
"""
말리 첫 실 이미지 생성.

기존 providers/nano_banana_provider.generate 를 real=True 로 호출한다.
scene 1 의 image_prompt 로 이미지 1장을 생성하고 output/malli/images/scene_001.png 로 저장한다.
저장 파일이 유효한 PNG 시그니처 + 0 바이트 초과인지 검증한다.
모델/실행시간/출력경로/파일크기를 출력한다.

Higgsfield/Magnific/Google Flow/Edge TTS/FFmpeg 는 호출하지 않는다.
"""

import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from nano_banana_provider import generate, PROVIDER, CAPABILITY, _resolve_model  # noqa: E402
from provider_sdk import make_request  # noqa: E402

_STORY_PATH = os.path.join(_ROOT, "output", "malli", "story.json")
_IMG_DIR = os.path.join(_ROOT, "output", "malli", "images")
_OUT_PATH = os.path.join(_IMG_DIR, "scene_001.png")
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _load_scene1_prompt():
    with open(_STORY_PATH, encoding="utf-8") as f:
        story = json.load(f)
    return story["scenes"][0]["image_prompt"]


def main():
    prompt = _load_scene1_prompt()
    model = _resolve_model()
    os.makedirs(_IMG_DIR, exist_ok=True)

    req = make_request(PROVIDER, CAPABILITY, prompt=prompt)
    t0 = time.perf_counter()
    result = generate(req, output_dir=_IMG_DIR, real=True)
    elapsed = time.perf_counter() - t0

    if result["status"] != "success":
        print(f"[실패] {result['message']}")
        return 1

    src = os.path.join(_ROOT, result["output"]["path"])
    os.replace(src, _OUT_PATH)  # provider 산출물을 scene_001.png 로 이동

    # PNG 시그니처 + 크기 검증
    size = os.path.getsize(_OUT_PATH)
    with open(_OUT_PATH, "rb") as f:
        head = f.read(8)
    if head != _PNG_SIG:
        print(f"[실패] 유효한 PNG 시그니처 아님: {head!r}")
        return 1
    if size == 0:
        print("[실패] 파일 크기 0")
        return 1

    print(f"[성공] 실 Nano Banana 이미지 생성 완료 (mock={result['output']['mock']}).")
    print(f"프롬프트: {prompt[:60]}")
    print(f"사용 모델: {model}")
    print(f"실행 시간: {elapsed:.2f}s")
    print(f"출력 경로: {_OUT_PATH}")
    print(f"파일 크기: {size} bytes")
    print("PNG 검증: 시그니처 OK, 크기 > 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
