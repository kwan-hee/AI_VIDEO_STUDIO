# Provider SDK request 를 받아 이미지를 생성(기본 mock, 실 백엔드 옵트인)하고 SDK result 를 반환하는 Nano Banana Provider
"""
Nano Banana Provider (Phase 3 / Provider 1)

목적.
  - Provider SDK / Provider Harness 를 실제 Nano Banana 공급자 모듈에 연결한다.

책임.
  - capability: generate_image 지원.
  - 표준 Provider SDK request 를 받는다.
  - 표준 Provider SDK result 를 반환한다.
  - 생성/모의 이미지를 output/images/ 아래에 저장한다.

기본은 mock 이다. 실 실행은 옵트인 전용이다(real=True 또는 환경변수 NANO_BANANA_REAL=1).
실 백엔드는 _real_writer() 뒤에만 구현한다(Google Gemini 이미지 모델, "Nano Banana").
  - API 키는 환경변수(GEMINI_API_KEY 또는 GOOGLE_API_KEY)에서 읽는다. 하드코딩 금지.
  - 모델명은 환경변수 NANO_BANANA_MODEL 로 설정한다. 미설정 시 안정 기본값.
SDK 미설치/키 없음 → RuntimeError → generate 가 status=failed 로 graceful 처리한다.
writer 를 직접 주입하면 그 writer 가 최우선이다(테스트/커스텀 백엔드).

다른 공급자(영상/음성/보정/합성)는 호출하지 않는다. Sprint 1~13 미수정.
결과 스키마: schemas/nano_banana_result_schema.json (Provider SDK result 형식 준수)
"""

import base64
import hashlib
import os

from provider_sdk import make_result

PROVIDER = "Nano Banana"
CAPABILITY = "generate_image"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "images")

# mock 이미지 바이트(PNG 시그니처 + 표식). 실 렌더링 아님, 배관 검증용 placeholder.
_MOCK_BYTES = b"\x89PNG\r\n\x1a\nnano-banana-mock"

# 실 실행 옵트인 환경변수. "1" 일 때만 실 백엔드를 시도한다(기본은 mock).
_REAL_ENV = "NANO_BANANA_REAL"

# 실 이미지 모델은 환경변수 NANO_BANANA_MODEL 로 설정한다. 미설정 시 안정 기본값.
# 미래 모델명은 하드코딩하지 않는다(설치 SDK 가 지원하지 않는 이름은 런타임 오류가 되므로).
_MODEL_ENV = "NANO_BANANA_MODEL"
_DEFAULT_MODEL = "gemini-2.5-flash-image"

# API 키 환경변수 후보(google-genai 표준). 키는 절대 하드코딩하지 않는다.
_API_KEY_ENVS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def _mock_writer(path, prompt):
    """실 공급자 없이 placeholder 이미지 파일을 기록한다."""
    with open(path, "wb") as f:
        f.write(_MOCK_BYTES)


def _resolve_model():
    """실 이미지 모델명을 결정한다. NANO_BANANA_MODEL 우선, 없으면 안정 기본값."""
    return os.environ.get(_MODEL_ENV) or _DEFAULT_MODEL


def _resolve_api_key():
    """환경변수에서 API 키를 읽는다. 없으면 None."""
    for env in _API_KEY_ENVS:
        v = os.environ.get(env)
        if v:
            return v
    return None


def _extract_image_bytes(resp):
    """Gemini 응답에서 첫 이미지 바이트를 추출한다(bytes 또는 base64 문자열 모두 처리)."""
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                return base64.b64decode(data) if isinstance(data, str) else data
    raise RuntimeError("Gemini 응답에 이미지 데이터가 없다.")


def _real_writer(path, prompt):
    """
    실 이미지 생성 백엔드로 파일을 기록한다(옵트인 전용).
    Google Gemini 이미지 모델("Nano Banana")을 호출한다.
    - google-genai SDK 미설치 → RuntimeError.
    - API 키 환경변수 없음 → RuntimeError.
    반환 이미지를 디코드해 PNG 로 저장한다.
    실 백엔드 미가용은 RuntimeError → generate 가 status=failed 로 graceful 처리한다.
    """
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError(
            "실 Nano Banana 백엔드가 연결되어 있지 않다. "
            f"({_REAL_ENV}=1 옵트인했으나 google-genai SDK 미설치)"
        ) from e

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError(
            f"API 키 환경변수가 없다({' 또는 '.join(_API_KEY_ENVS)}). 실 이미지 생성 불가."
        )

    client = genai.Client(api_key=api_key)  # pragma: no cover  (실 API — 일반 테스트 미실행)
    resp = client.models.generate_content(model=_resolve_model(), contents=prompt)
    data = _extract_image_bytes(resp)
    with open(path, "wb") as f:
        f.write(data)


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


def generate(request, output_dir=None, writer=None, real=None):
    """
    Provider SDK request → 이미지 생성 후 SDK result.
    기본은 mock writer 로 placeholder 이미지를 output/images/ 에 저장한다.
    실 실행은 옵트인 전용이다. real=True 또는 환경변수 NANO_BANANA_REAL=1 일 때만 실 백엔드를 시도한다.
    writer 를 직접 주입하면 그 writer 가 최우선이다(테스트/커스텀 백엔드).
    request 오류는 ValueError. 생성 실패는 status="failed".
    """
    _validate_request(request)

    prompt = request.get("prompt")
    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    key = hashlib.md5((prompt or "").encode("utf-8")).hexdigest()[:10]
    path = os.path.join(out_dir, f"nano_banana_{key}.png")

    # 모드 결정: 주입 writer > 실 옵트인 > mock(기본)
    if real is None:
        real = os.environ.get(_REAL_ENV) == "1"
    if writer is not None:
        is_mock = False
    elif real:
        writer, is_mock = _real_writer, False
    else:
        writer, is_mock = _mock_writer, True
    try:
        writer(path, prompt)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("이미지 파일이 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        return make_result(PROVIDER, CAPABILITY, status="failed", output=None,
                           message=f"이미지 생성 실패: {e}")

    output = {"path": _rel(path), "type": "image", "mock": is_mock, "prompt": prompt}
    return make_result(PROVIDER, CAPABILITY, status="success", output=output,
                       message="이미지 생성 완료." if not is_mock else "mock 이미지 생성 완료.")


# 하네스/파이프라인이 주입할 기본 핸들러 (request -> result)
handler = generate


if __name__ == "__main__":
    import json

    from provider_sdk import make_request

    req = make_request(PROVIDER, CAPABILITY, prompt="달빛 아래 토끼")
    print(json.dumps(generate(req), ensure_ascii=False, indent=2))
