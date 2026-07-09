# 공급자 모드(mock/real/disabled/local)와 라우팅 정책을 설정 파일/딕트에서 로드·검증하고 조회 헬퍼를 제공하는 Provider Configuration Layer
"""
Provider Configuration Layer (Phase 5 / Step 2)

목적.
  - 코드 수정 없이 설정으로 공급자를 mock / real / disabled 로 전환한다.

책임.
  - 설정을 파일(JSON, 선택적으로 YAML) 또는 딕트에서 로드한다.
  - 공급자 모드(mock/real/disabled/local)를 지원한다.
  - primary / backup 라우팅 정책을 지원한다.
  - 모드 조회/라우팅 조회 헬퍼를 제공한다.

공급자를 실행하지 않는다. 외부 API 없음. 설정 로드/조회만.
설정이 없으면 안전 기본(DEFAULT_CONFIG: 전부 mock, ffmpeg local)을 쓴다.
스키마: schemas/provider_config_schema.json
"""

import copy
import json
import os

from jsonschema import Draft7Validator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "provider_config_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)
_VALIDATOR = Draft7Validator(_SCHEMA)

# 설정 키(snake) → SDK 표시명
_DISPLAY = {
    "nano_banana": "Nano Banana",
    "magnific": "Magnific",
    "higgsfield": "Higgsfield",
    "google_flow": "Google Flow",
    "edge_tts": "Edge TTS",
    "ffmpeg": "FFmpeg",
}
KNOWN_PROVIDERS = list(_DISPLAY.keys())
KNOWN_CAPABILITIES = [
    "generate_image", "enhance_image", "generate_video", "text_to_speech", "compose",
]

# 안전 기본: 전부 mock, ffmpeg 는 local. 라우팅은 기본 정책.
DEFAULT_CONFIG = {
    "providers": {
        "nano_banana": {"mode": "mock"},
        "magnific": {"mode": "mock"},
        "higgsfield": {"mode": "mock"},
        "google_flow": {"mode": "mock"},
        "edge_tts": {"mode": "mock"},
        "ffmpeg": {"mode": "local"},
    },
    "routing": {
        "generate_image": {"primary": "nano_banana"},
        "enhance_image": {"primary": "magnific"},
        "generate_video": {"primary": "higgsfield", "backup": "google_flow"},
        "text_to_speech": {"primary": "edge_tts"},
        "compose": {"primary": "ffmpeg"},
    },
}


def _validate(cfg):
    errs = sorted(_VALIDATOR.iter_errors(cfg), key=str)
    if errs:
        raise ValueError("설정 스키마 위반: " + "; ".join(e.message for e in errs))


def _read_file(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if ext == ".json":
        return json.loads(text)
    if ext in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise ValueError("YAML 설정을 읽으려면 PyYAML 이 필요하다. JSON 을 쓰거나 PyYAML 설치.") from e
        return yaml.safe_load(text)
    raise ValueError(f"지원하지 않는 설정 확장자: {ext} (.json / .yaml)")


def load_config(path=None, data=None):
    """
    설정을 로드·검증해 dict 로 반환한다.
    data 딕트가 있으면 그것을, path 파일이 있으면 파일을, 둘 다 없으면 DEFAULT_CONFIG 를 쓴다.
    스키마 위반은 ValueError. 아무것도 실행하지 않는다.
    """
    if data is not None:
        cfg = copy.deepcopy(data)
    elif path is not None:
        cfg = _read_file(path)
    else:
        cfg = copy.deepcopy(DEFAULT_CONFIG)
    _validate(cfg)
    return cfg


def _check_provider_key(key):
    if key not in _DISPLAY:
        raise ValueError(f"알 수 없는 provider 키: {key}")


def _check_capability(capability):
    if capability not in KNOWN_CAPABILITIES:
        raise ValueError(f"알 수 없는 capability: {capability}")


def provider_mode(config, provider_key):
    """공급자의 모드. 설정에 없으면 안전 기본 'mock'. 알 수 없는 키는 ValueError."""
    _check_provider_key(provider_key)
    entry = (config.get("providers") or {}).get(provider_key)
    if not entry:
        return "mock"
    return entry.get("mode", "mock")


def is_real(config, provider_key):
    return provider_mode(config, provider_key) == "real"


def is_mock(config, provider_key):
    return provider_mode(config, provider_key) == "mock"


def is_disabled(config, provider_key):
    return provider_mode(config, provider_key) == "disabled"


def routing_primary(config, capability):
    """capability 의 primary 공급자 키. 정책에 없으면 None. 알 수 없는 capability 는 ValueError."""
    _check_capability(capability)
    route = (config.get("routing") or {}).get(capability)
    return route.get("primary") if route else None


def routing_backup(config, capability):
    """capability 의 backup 공급자 키(없으면 None)."""
    _check_capability(capability)
    route = (config.get("routing") or {}).get(capability)
    return route.get("backup") if route else None


def routing_candidates(config, capability, include_disabled=False):
    """
    capability 의 우선순위 후보 키 목록 [primary, backup?].
    기본은 disabled 공급자를 제외한다(failover 친화). include_disabled=True 면 그대로 둔다.
    """
    _check_capability(capability)
    order = [routing_primary(config, capability), routing_backup(config, capability)]
    order = [p for p in order if p]
    if include_disabled:
        return order
    return [p for p in order if not is_disabled(config, p)]


def provider_display_name(provider_key):
    """설정 키 → SDK 표시명. 알 수 없는 키는 ValueError."""
    _check_provider_key(provider_key)
    return _DISPLAY[provider_key]


if __name__ == "__main__":
    cfg = load_config()
    demo = {
        "modes": {k: provider_mode(cfg, k) for k in KNOWN_PROVIDERS},
        "routing": {c: routing_candidates(cfg, c) for c in KNOWN_CAPABILITIES},
    }
    print(json.dumps(demo, ensure_ascii=False, indent=2))
