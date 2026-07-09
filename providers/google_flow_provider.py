# Provider SDK request 를 받아 영상을 생성(현재는 안전 mock)하고 SDK result 를 반환하는 Google Flow Provider (백업 영상)
"""
Google Flow Provider (Phase 3 / Provider 4)

목적.
  - Provider SDK / Provider Harness 를 실제 Google Flow 공급자 모듈에 연결한다.
  - Google Flow 는 백업 영상 생성 공급자다. (기본 공급자를 이 모듈에서 호출하지 않는다.)

책임.
  - capability: generate_video 지원.
  - 표준 Provider SDK request 를 받는다.
  - 표준 Provider SDK result 를 반환한다.
  - 생성/모의 영상을 output/videos/ 아래에 저장한다.

현재 실 Google Flow 실행은 미가용 → 안전 mock 을 먼저 구현한다.
실 실행이 준비되면 writer 인자로 실제 생성 백엔드를 주입한다(기본은 mock writer).

다른 공급자(이미지/음성/보정/합성)는 호출하지 않는다. 기존 Sprint 동작 미수정.
결과 스키마: schemas/google_flow_result_schema.json (Provider SDK result 형식 준수)
"""

import hashlib
import os

from provider_sdk import make_result

PROVIDER = "Google Flow"
CAPABILITY = "generate_video"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "videos")

# mock 영상 바이트(MP4 ftyp 박스 + 표식). 실 렌더링 아님, 배관 검증용 placeholder.
_MOCK_BYTES = b"\x00\x00\x00\x18ftypmp42google-flow-mock"


def _mock_writer(path, prompt):
    """실 공급자 없이 placeholder 영상 파일을 기록한다."""
    with open(path, "wb") as f:
        f.write(_MOCK_BYTES)


def _rel(path):
    try:
        return os.path.relpath(path, _ROOT).replace(os.sep, "/")
    except ValueError:
        return path


def _validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("request 는 dict 여야 한다.")
    if request.get("provider") != PROVIDER:
        raise ValueError(f"이 provider 는 {PROVIDER} 전용이다: {request.get('provider')}")
    if request.get("capability") != CAPABILITY:
        raise ValueError(f"지원 capability 는 {CAPABILITY} 뿐이다: {request.get('capability')}")


def generate(request, output_dir=None, writer=None):
    """
    Provider SDK request → 영상 생성 후 SDK result.
    현재는 mock writer 로 placeholder 영상을 output/videos/ 에 저장한다.
    request 오류는 ValueError. 생성 실패는 status="failed".
    """
    _validate_request(request)

    prompt = request.get("prompt")
    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    key = hashlib.md5((prompt or "").encode("utf-8")).hexdigest()[:10]
    path = os.path.join(out_dir, f"google_flow_{key}.mp4")

    is_mock = writer is None
    writer = writer or _mock_writer
    try:
        writer(path, prompt)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("영상 파일이 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        return make_result(PROVIDER, CAPABILITY, status="failed", output=None,
                           message=f"영상 생성 실패: {e}")

    output = {"path": _rel(path), "type": "video", "mock": is_mock, "prompt": prompt}
    return make_result(PROVIDER, CAPABILITY, status="success", output=output,
                       message="mock 영상 생성 완료." if is_mock else "영상 생성 완료.")


# 하네스/파이프라인이 주입할 기본 핸들러 (request -> result)
handler = generate


if __name__ == "__main__":
    import json

    from provider_sdk import make_request

    req = make_request(PROVIDER, CAPABILITY, prompt="달이 떠오르는 밤", inputs=["output/images/01.png"])
    print(json.dumps(generate(req), ensure_ascii=False, indent=2))
