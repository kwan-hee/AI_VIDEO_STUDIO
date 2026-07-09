# capability 와 라우팅 정책으로 적절한 공급자를 선택(실행 없음)하는 Provider Router
"""
Provider Router (Phase 4 / Step 1)

목적.
  - capability 와 라우팅 정책에 따라 적절한 공급자를 선택한다.

책임.
  - Provider SDK capability 를 이용해 요청을 라우팅한다.
  - primary / backup 공급자 선택을 지원한다.
  - 공급자를 실행하지 않고 선택 결과만 반환한다.
  - failover 를 지원한다(exclude 로 실패한 공급자를 건너뛴다).
  - 라우팅 정책을 한 곳에 모은다.

공급자 실행 없음. 외부 API 없음. 미디어 생성 없음. 기존 Provider 구현 미수정.
출력 스키마: schemas/provider_router_schema.json
"""

import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "providers"))

from provider_sdk import CAPABILITIES, supports

# 기본 라우팅 정책: capability -> 후보 공급자 (순서 = 우선순위, [0]=primary, [1]=backup ...)
ROUTING_POLICY = {
    "generate_image": ["Nano Banana"],
    "enhance_image": ["Magnific"],
    "generate_video": ["Higgsfield", "Google Flow"],
    "text_to_speech": ["Edge TTS"],
    "compose": ["FFmpeg"],
}


def _validate_capability(capability):
    if capability not in CAPABILITIES:
        raise ValueError(f"알 수 없는 capability: {capability}")
    if capability not in ROUTING_POLICY:
        raise ValueError(f"라우팅 정책에 없는 capability: {capability}")


def candidates_for(capability):
    """capability 의 우선순위 후보 목록(정책 순서)."""
    _validate_capability(capability)
    return list(ROUTING_POLICY[capability])


def route(capability, exclude=None):
    """
    capability -> 라우팅 정책에 따른 공급자 선택.
    선택만 한다. 실행/호출/미디어 없음.
    exclude: 이미 실패해 건너뛸 공급자 목록(failover). 남은 첫 후보를 선택한다.
    후보가 모두 제외되면 selected=None.
    """
    _validate_capability(capability)
    candidates = list(ROUTING_POLICY[capability])
    skip = set(exclude or [])

    selected = next((p for p in candidates if p not in skip), None)

    return {
        "capability": capability,
        "primary": candidates[0],
        "backup": candidates[1] if len(candidates) > 1 else None,
        "candidates": candidates,
        "selected": selected,
    }


# 모듈 로드 시 정책이 SDK capability 와 일치하는지 최소 자기검증
assert set(ROUTING_POLICY.keys()) == set(CAPABILITIES), "라우팅 정책이 SDK capability 와 불일치"
for _cap, _cands in ROUTING_POLICY.items():
    for _p in _cands:
        assert supports(_p, _cap), f"정책 오류: {_p} 는 {_cap} 미지원"


if __name__ == "__main__":
    import json

    demo = {cap: route(cap) for cap in ROUTING_POLICY}
    demo["failover_video"] = route("generate_video", exclude=["Higgsfield"])
    print(json.dumps(demo, ensure_ascii=False, indent=2))
