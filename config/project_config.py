# 프로젝트 전체 설정(project/providers/voice/video/timeline/output)을 단일 파일/딕트에서 로드·검증하고 헬퍼를 제공하는 Project Configuration Layer
"""
Project Configuration Layer (Phase 5 / Step 3)

목적.
  - 프로젝트 전체를 단일 설정 파일로 구성한다.

책임.
  - 프로젝트 설정을 로드한다(JSON 기본, PyYAML 있으면 YAML).
  - 스키마로 검증한다.
  - 헬퍼 API 를 제공한다.
  - Provider Configuration Layer 와 자연스럽게 연결한다(같은 provider 키, 표시명 매핑 재사용).

공급자를 실행하지 않는다. 외부 API 없음. 설정 로드/조회만.
사용자 설정은 DEFAULT_PROJECT_CONFIG 에 deep-merge 되어 누락 필드는 안전 기본을 유지한다.
스키마: schemas/project_config_schema.json
Provider Router / Workflow Engine / 기존 Provider 는 수정하지 않는다.
"""

import copy
import json
import os

from jsonschema import Draft7Validator

from provider_config import provider_display_name  # Provider Configuration Layer 연동

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "project_config_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)
_VALIDATOR = Draft7Validator(_SCHEMA)

# 프로젝트 provider 역할 → capability (참고용 매핑)
ROLES = ["image", "enhance", "video", "tts", "compose"]

# 안전 기본. 기존 관례와 정렬(edge voice, 1280x720, mp4).
DEFAULT_PROJECT_CONFIG = {
    "project": {
        "name": "AI_VIDEO_STUDIO",
        "description": "",
        "output_directory": "output",
    },
    "providers": {
        "image": "nano_banana",
        "enhance": "magnific",
        "video": "higgsfield",
        "tts": "edge_tts",
        "compose": "ffmpeg",
    },
    "voice": {
        "speaker": "ko-KR-SunHiNeural",
        "rate": "-5%",
    },
    "video": {
        "resolution": "1280x720",
        "fps": 30,
        "aspect_ratio": "16:9",
    },
    "timeline": {
        "default_transition": "none",
        "default_duration": 5.0,
    },
    "output": {
        "format": "mp4",
        "overwrite": False,
    },
}


def _validate(cfg):
    errs = sorted(_VALIDATOR.iter_errors(cfg), key=str)
    if errs:
        raise ValueError("프로젝트 설정 스키마 위반: " + "; ".join(e.message for e in errs))


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


def _merge(user):
    """사용자 설정을 DEFAULT 에 한 단계 deep-merge. 알 수 없는 키/타입은 그대로 두어 검증에서 걸리게 한다."""
    merged = copy.deepcopy(DEFAULT_PROJECT_CONFIG)
    if not isinstance(user, dict):
        raise ValueError("설정은 dict 여야 한다.")
    for k, v in user.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def load_project_config(path=None, data=None):
    """
    프로젝트 설정을 로드·병합·검증해 dict 로 반환한다.
    data > path > DEFAULT 순. 누락 필드는 안전 기본을 유지한다.
    스키마 위반은 ValueError. 아무것도 실행하지 않는다.
    """
    if data is not None:
        cfg = _merge(data)
    elif path is not None:
        cfg = _merge(_read_file(path))
    else:
        cfg = copy.deepcopy(DEFAULT_PROJECT_CONFIG)
    _validate(cfg)
    return cfg


# --- 헬퍼 API ---

def project_name(config):
    return config["project"]["name"]


def project_description(config):
    return config["project"]["description"]


def output_directory(config):
    return config["project"]["output_directory"]


def provider_for(config, role):
    """역할(image/enhance/video/tts/compose)의 provider 키. 알 수 없는 role 은 ValueError."""
    if role not in ROLES:
        raise ValueError(f"알 수 없는 provider 역할: {role}")
    return config["providers"][role]


def provider_display_for(config, role):
    """역할의 provider 를 SDK 표시명으로. Provider Configuration Layer 매핑 재사용."""
    return provider_display_name(provider_for(config, role))


def voice_settings(config):
    return dict(config["voice"])


def video_settings(config):
    return dict(config["video"])


def timeline_settings(config):
    return dict(config["timeline"])


def output_settings(config):
    return dict(config["output"])


if __name__ == "__main__":
    cfg = load_project_config()
    demo = {
        "project": cfg["project"],
        "providers_display": {r: provider_display_for(cfg, r) for r in ROLES},
        "voice": voice_settings(cfg),
        "video": video_settings(cfg),
    }
    print(json.dumps(demo, ensure_ascii=False, indent=2))
