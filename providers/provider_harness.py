# 임의 공급자를 Provider SDK 인터페이스로 검증하는 재사용 테스트 하네스 (실공급자 호출/미디어 없음)
"""
Provider Test Harness (Phase 3 / Step 2)

목적.
  - 실공급자 구현 전에, 모든 공급자를 같은 인터페이스로 검증할 공통 하네스를 만든다.

입력.
  - provider: 공급자 이름 (Provider SDK 지원 목록)
  - handler:  request -> result 콜러블(선택). 미지정 시 내장 stub 사용.
              실공급자를 구현하면 그 콜러블을 주입해 같은 하네스로 검증한다.

검사 항목(CHECK_NAMES).
  - capabilities_declared          : capability 선언이 비지 않고 알려진 값인지
  - request_format                 : 각 capability 의 request 가 SDK 스키마에 맞는지
  - result_format                  : handler 결과가 result 스키마 + provider/capability 일치인지
  - unsupported_capability_rejected: 공급자가 지원 않는 capability 를 SDK 가 거부하는지
  - unsupported_provider_rejected  : 알 수 없는 공급자를 SDK 가 거부하는지

실공급자 호출 없음. 미디어 생성 없음. Sprint 1~13 미수정.
SDK: providers/provider_sdk.py, 스키마: schemas/provider_sdk_schema.json / provider_harness_schema.json
"""

import json
import os

from provider_sdk import (
    CAPABILITIES,
    make_request,
    make_result,
    capabilities_of,
    _validate_provider,
)

from jsonschema import Draft7Validator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SDK_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_sdk_schema.json")
with open(_SDK_SCHEMA_PATH, encoding="utf-8") as _f:
    _SDK_SCHEMA = json.load(_f)
_REQ_V = Draft7Validator(_SDK_SCHEMA["definitions"]["request"])
_RES_V = Draft7Validator(_SDK_SCHEMA["definitions"]["result"])

CHECK_NAMES = [
    "capabilities_declared",
    "request_format",
    "result_format",
    "unsupported_capability_rejected",
    "unsupported_provider_rejected",
]

_UNKNOWN_PROVIDER = "__nonexistent_provider__"


def _stub_handler(request):
    """실공급자 없이 인터페이스 배관만 검증하는 기본 핸들러. 항상 pending result."""
    return make_result(request["provider"], request["capability"], status="pending")


def _check(name, passed, detail=""):
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def _check_capabilities_declared(caps):
    ok = bool(caps) and all(c in CAPABILITIES for c in caps)
    return _check("capabilities_declared", ok, f"caps={caps}")


def _check_request_format(provider, caps):
    problems = []
    for c in caps:
        try:
            req = make_request(provider, c, prompt="harness")
            errs = list(_REQ_V.iter_errors(req))
            if errs:
                problems.append(f"{c}: {errs[0].message}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"{c}: {e}")
    return _check("request_format", not problems, "; ".join(problems) or "all valid")


def _check_result_format(provider, caps, handler):
    problems = []
    for c in caps:
        req = make_request(provider, c, prompt="harness")
        try:
            res = handler(req)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{c}: handler raised {e}")
            continue
        errs = list(_RES_V.iter_errors(res))
        if errs:
            problems.append(f"{c}: {errs[0].message}")
            continue
        if res["provider"] != provider or res["capability"] != c:
            problems.append(f"{c}: result 의 provider/capability 불일치")
    return _check("result_format", not problems, "; ".join(problems) or "all valid")


def _check_unsupported_capability_rejected(provider, caps):
    unsupported = [c for c in CAPABILITIES if c not in caps]
    if not unsupported:
        return _check("unsupported_capability_rejected", True, "테스트할 미지원 capability 없음")
    target = unsupported[0]
    try:
        make_request(provider, target)
    except ValueError:
        return _check("unsupported_capability_rejected", True, f"{target} 거부 확인")
    return _check("unsupported_capability_rejected", False, f"{target} 가 거부되지 않음")


def _check_unsupported_provider_rejected(caps):
    cap = caps[0] if caps else CAPABILITIES[0]
    try:
        make_request(_UNKNOWN_PROVIDER, cap)
    except ValueError:
        return _check("unsupported_provider_rejected", True, "알 수 없는 공급자 거부 확인")
    return _check("unsupported_provider_rejected", False, "알 수 없는 공급자가 거부되지 않음")


def run_harness(provider, handler=None):
    """
    공급자를 Provider SDK 인터페이스로 검증하고 구조화 리포트를 반환한다.
    검증만 한다. 실공급자 호출/미디어 생성 없음.
    미지원 공급자로 호출하면 ValueError (검증할 대상이 아님).
    """
    _validate_provider(provider)
    handler = handler or _stub_handler
    caps = capabilities_of(provider)

    checks = [
        _check_capabilities_declared(caps),
        _check_request_format(provider, caps),
        _check_result_format(provider, caps, handler),
        _check_unsupported_capability_rejected(provider, caps),
        _check_unsupported_provider_rejected(caps),
    ]

    failed = sum(1 for c in checks if not c["passed"])
    return {
        "provider": provider,
        "passed": failed == 0,
        "total": len(checks),
        "failed": failed,
        "checks": checks,
    }


if __name__ == "__main__":
    from provider_sdk import PROVIDERS

    report = {p: run_harness(p)["passed"] for p in PROVIDERS}
    print(json.dumps({"harness_pass": report}, ensure_ascii=False, indent=2))
