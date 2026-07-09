# 모든 실공급자가 따를 공통 인터페이스(capability 매핑 + 표준 request/result 헬퍼 + 검증)를 정의하는 Provider SDK
"""
Provider SDK Layer (Phase 3 / Step 1)

목적.
  - Nano Banana / Google Flow / Higgsfield / Magnific 등 실공급자 구현 전,
    모든 공급자가 공유할 공통 인터페이스를 먼저 확정한다.

책임.
  - 공통 request 형식을 정의한다.
  - 공통 result 형식을 정의한다.
  - 공급자별 capability 매핑을 제공한다.
  - 표준 request/result 생성 헬퍼를 제공한다.
  - 미지원 공급자 / 공급자가 지원하지 않는 capability 를 검증·거부한다.

실공급자 호출 없음. 미디어 생성 없음. Sprint 1~13 동작 미수정.
capability 이름은 기존 Provider Adapter 의 action 값과 정렬한다.
스키마: schemas/provider_sdk_schema.json (definitions.request / definitions.result)
"""

# 지원 공급자 (기존 어댑터/셀렉터와 동일 표기)
PROVIDERS = ["Nano Banana", "Google Flow", "Higgsfield", "Magnific", "Edge TTS", "FFmpeg"]

# 전체 capability (기존 어댑터 action 과 정렬)
CAPABILITIES = ["generate_image", "generate_video", "enhance_image", "text_to_speech", "compose"]

# 공급자 → 지원 capability
PROVIDER_CAPABILITIES = {
    "Nano Banana": ["generate_image"],
    "Google Flow": ["generate_video"],
    "Higgsfield": ["generate_video"],
    "Magnific": ["enhance_image"],
    "Edge TTS": ["text_to_speech"],
    "FFmpeg": ["compose"],
}

# result 상태 (실행 전이므로 기본은 pending)
RESULT_STATUSES = ["success", "failed", "pending"]


def _validate_provider(provider):
    if provider not in PROVIDER_CAPABILITIES:
        raise ValueError(f"지원하지 않는 공급자: {provider}")


def _validate_capability(provider, capability):
    """capability 자체가 알려진 값인지 + 그 공급자가 지원하는지 검증."""
    if capability not in CAPABILITIES:
        raise ValueError(f"알 수 없는 capability: {capability}")
    if capability not in PROVIDER_CAPABILITIES[provider]:
        raise ValueError(f"{provider} 는 capability 를 지원하지 않는다: {capability}")


def supports(provider, capability):
    """공급자가 해당 capability 를 지원하면 True. 미지원 공급자면 False."""
    return capability in PROVIDER_CAPABILITIES.get(provider, [])


def capabilities_of(provider):
    """공급자의 capability 목록. 미지원 공급자면 ValueError."""
    _validate_provider(provider)
    return list(PROVIDER_CAPABILITIES[provider])


def make_request(provider, capability, prompt=None, parameters=None, inputs=None):
    """
    표준 공급자 request 를 만든다. 검증 후 dict 반환.
    미지원 공급자 / 공급자가 지원 않는 capability 는 ValueError.
    아무것도 실행하지 않는다.
    """
    _validate_provider(provider)
    _validate_capability(provider, capability)
    return {
        "provider": provider,
        "capability": capability,
        "prompt": prompt,
        "parameters": dict(parameters) if parameters else {},
        "inputs": list(inputs) if inputs else [],
    }


def make_result(provider, capability, status="pending", output=None, message=""):
    """
    표준 공급자 result 를 만든다. 검증 후 dict 반환.
    실행 전 기본 status 는 pending. 잘못된 공급자/capability/status 는 ValueError.
    """
    _validate_provider(provider)
    _validate_capability(provider, capability)
    if status not in RESULT_STATUSES:
        raise ValueError(f"잘못된 status: {status}")
    return {
        "provider": provider,
        "capability": capability,
        "status": status,
        "output": output,
        "message": message,
    }


if __name__ == "__main__":
    import json

    demo = {
        "providers": PROVIDERS,
        "capabilities": PROVIDER_CAPABILITIES,
        "sample_request": make_request("Nano Banana", "generate_image", prompt="달을 그린다"),
        "sample_result": make_result("Nano Banana", "generate_image", status="pending"),
    }
    print(json.dumps(demo, ensure_ascii=False, indent=2))
