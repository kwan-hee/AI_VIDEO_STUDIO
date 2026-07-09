# Provider SDK request 를 받아 원본 이미지를 보정/업스케일(현재는 안전 mock)하고 SDK result 를 반환하는 Magnific Provider
"""
Magnific Provider (Phase 3 / Provider 3)

목적.
  - Provider SDK / Provider Harness 를 실제 Magnific 공급자 모듈에 연결한다.
  - Magnific 는 이미지 생성 이후 보정/업스케일에 쓰인다. 원본 이미지가 필요하다.

책임.
  - capability: enhance_image 지원.
  - 표준 Provider SDK request 를 받는다. (원본 이미지는 request.inputs[0])
  - 표준 Provider SDK result 를 반환한다.
  - 보정/모의 이미지를 output/enhanced/ 아래에 저장한다.

현재 실 Magnific 실행은 미가용 → 안전 mock 을 먼저 구현한다.
실 실행이 준비되면 writer 인자로 실제 보정 백엔드를 주입한다(기본은 mock writer).

다른 공급자(생성/영상/음성/합성)는 호출하지 않는다. 기존 Sprint 동작 미수정.
결과 스키마: schemas/magnific_result_schema.json (Provider SDK result 형식 준수)
"""

import hashlib
import os

from provider_sdk import make_result

PROVIDER = "Magnific"
CAPABILITY = "enhance_image"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "enhanced")

# mock 보정 이미지 바이트(PNG 시그니처 + 표식). 실 보정 아님, 배관 검증용 placeholder.
_MOCK_BYTES = b"\x89PNG\r\n\x1a\nmagnific-mock"

# 실 실행 옵트인 환경변수. "1" 일 때만 실 백엔드를 시도한다(기본은 mock).
_REAL_ENV = "MAGNIFIC_REAL"


def _mock_writer(path, source):
    """실 공급자 없이 placeholder 보정 이미지 파일을 기록한다."""
    with open(path, "wb") as f:
        f.write(_MOCK_BYTES)


def _real_writer(path, source):
    """
    실 이미지 보정 백엔드로 파일을 기록한다(옵트인 전용). source 는 원본 이미지 경로.
    실 백엔드(SDK/API)가 연결되어 있지 않으면 RuntimeError 를 올려
    generate 가 status=failed 로 보고하게 한다. 실 백엔드가 준비되면 여기서 호출하도록 교체한다.
    """
    try:
        import magnific_sdk  # 실 백엔드(선택 설치). 미설치 시 ImportError.
    except ImportError as e:
        raise RuntimeError(
            "실 Magnific 백엔드가 연결되어 있지 않다. "
            f"({_REAL_ENV}=1 옵트인했으나 SDK/API 미연결)"
        ) from e
    magnific_sdk.enhance_image(source=source, out_path=path)  # pragma: no cover


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
    Provider SDK request → 원본 이미지 보정 후 SDK result.
    원본 이미지(inputs[0])가 필요하다. 기본은 mock writer 로 output/enhanced/ 에 저장.
    실 실행은 옵트인 전용이다. real=True 또는 환경변수 MAGNIFIC_REAL=1 일 때만 실 백엔드를 시도한다.
    writer 를 직접 주입하면 그 writer 가 최우선이다(테스트/커스텀 백엔드).
    request 오류는 ValueError. 원본 누락/보정 실패는 status="failed".
    """
    _validate_request(request)

    inputs = request.get("inputs") or []
    source = inputs[0] if inputs else None
    if not source:
        return make_result(PROVIDER, CAPABILITY, status="failed", output=None,
                           message="원본 이미지 입력이 없다. (inputs[0] 필요)")

    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    key = hashlib.md5(source.encode("utf-8")).hexdigest()[:10]
    path = os.path.join(out_dir, f"magnific_{key}.png")

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
        writer(path, source)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("보정 이미지가 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        return make_result(PROVIDER, CAPABILITY, status="failed", output=None,
                           message=f"이미지 보정 실패: {e}")

    output = {"path": _rel(path), "type": "image", "mock": is_mock, "source": source}
    return make_result(PROVIDER, CAPABILITY, status="success", output=output,
                       message="mock 이미지 보정 완료." if is_mock else "이미지 보정 완료.")


# 하네스/파이프라인이 주입할 기본 핸들러 (request -> result)
handler = generate


if __name__ == "__main__":
    import json

    from provider_sdk import make_request

    req = make_request(PROVIDER, CAPABILITY, inputs=["output/images/01.png"])
    print(json.dumps(generate(req), ensure_ascii=False, indent=2))
