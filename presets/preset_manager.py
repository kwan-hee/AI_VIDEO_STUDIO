# 승인된 영상 프리셋을 로드·검증·동결(hash/version)하고 매니페스트 메타를 제공하는 Preset Manager
"""
Approved Preset Manager

목적.
  - 품질검증으로 승인된 style/character/camera/motion 설정을 안전하게 동결(freeze)한다.
  - 프로덕션은 승인·동결된 프리셋만 재사용한다. 변경은 명시적 override 필요.

책임.
  - presets/approved/*.yaml 로드·검증.
  - status: approved 인 프리셋만 동결 대상으로 인정.
  - 프리셋 버전 + 안전한(비밀 아님) hash 계산 → 실행 매니페스트에 기록할 메타 제공.
  - 승인 프리셋 로드를 로그로 남긴다(alias/이름/버전만, 자격증명 없음).
  - 지원되지 않는 모델 파라미터를 발명하지 않는다: 알려진 필드만 통과.

이 모듈은 공급자를 실행하지 않는다. 계정/이메일/자격증명을 다루지 않는다.
"""

import hashlib
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APPROVED_DIR = os.path.join(_ROOT, "presets", "approved")

# 저장 허용 필드(실 Higgsfield MCP 옵션 + 프로젝트 영상 설정 + 창작 의도).
# provider 실 파라미터: model, resolution, aspect_ratio, duration, fps, mode, bitrate_mode, generate_audio, output_format
# 참조/일관성·창작 의도: camera_motion, motion_strength, character_consistency, reference_image, negative_prompt, seed_behavior, quality_level
# (미지원 모델 파라미터는 넣지 않는다. 의도 필드는 프롬프트/모델선택에 반영되는 상위 개념이다.)
_ALLOWED_FIELDS = {
    "provider", "model", "resolution", "aspect_ratio", "duration", "fps",
    "mode", "bitrate_mode", "generate_audio", "output_format",
    "camera_motion", "motion_strength", "character_consistency",
    "reference_image", "negative_prompt", "seed_behavior", "quality_level",
    "motion_style",
}
# 절대 프리셋에 있으면 안 되는 키(계정/자격증명 유출 방지).
_FORBIDDEN_KEYS = {"email", "account", "token", "api_key", "apikey", "cookie",
                   "credential", "credentials", "secret", "password", "oauth"}


class PresetError(Exception):
    """프리셋 로드/검증/승인 오류."""


def _read_yaml_or_json(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if ext in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise PresetError("YAML 프리셋을 읽으려면 PyYAML 필요.") from e
        return yaml.safe_load(text)
    if ext == ".json":
        return json.loads(text)
    raise PresetError(f"지원하지 않는 프리셋 확장자: {ext}")


def _scan_forbidden(node, where="preset"):
    """계정/자격증명 계열 키가 프리셋에 없는지 재귀 검사."""
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in _FORBIDDEN_KEYS:
                raise PresetError(f"프리셋에 금지 키 '{k}' 발견({where}) — 계정/자격증명 저장 금지.")
            _scan_forbidden(v, where=f"{where}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _scan_forbidden(v, where=f"{where}[{i}]")


def _preset_hash(preset_body):
    """정렬 JSON 기반 안전 hash(비밀 아님). 프리셋 내용이 바뀌면 hash 도 바뀐다."""
    payload = json.dumps(preset_body, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def load_preset(path, *, require_approved=True, log=None):
    """
    프리셋 파일 로드·검증·동결. 반환:
      {"name","project_type","version","hash","status","body"(허용필드만),"meta"(name/version/hash)}
    require_approved=True 면 status 가 approved 가 아니면 PresetError.
    body 는 _ALLOWED_FIELDS 로 화이트리스트된다(미지원 필드 발명 방지).
    로그는 alias/이름/버전만 남긴다.
    """
    data = _read_yaml_or_json(path)
    if not isinstance(data, dict) or "preset" not in data:
        raise PresetError("프리셋 파일 최상위에 'preset' 블록이 필요하다.")
    body = data["preset"]
    if not isinstance(body, dict):
        raise PresetError("preset 블록이 dict 가 아니다.")
    _scan_forbidden(body)

    status = str(body.get("status", "draft")).lower()
    name = body.get("name") or os.path.splitext(os.path.basename(path))[0]
    project_type = body.get("project_type")
    version = body.get("version", 1)

    if require_approved and status != "approved":
        raise PresetError(f"프리셋 '{name}' 은 승인 상태가 아니다(status={status}). 동결 불가.")

    # 허용 필드만 남긴다(미지원 파라미터 제거).
    frozen = {k: v for k, v in body.items() if k in _ALLOWED_FIELDS}
    phash = _preset_hash(frozen)
    result = {
        "name": name, "project_type": project_type, "version": version,
        "status": status, "hash": phash, "body": frozen,
        "meta": {"name": name, "version": version, "hash": phash},
    }
    if log:
        log(f"[Quality] Loaded preset: {name} v{version}")
    return result


def approved_preset_path(preset_name):
    """presets/approved/{preset_name}.yaml 경로."""
    return os.path.join(_APPROVED_DIR, f"{preset_name}.yaml")


def load_approved(preset_name, *, log=None):
    """이름으로 승인 프리셋 로드(presets/approved/)."""
    path = approved_preset_path(preset_name)
    if not os.path.exists(path):
        raise PresetError(f"승인 프리셋 없음: {preset_name} ({path})")
    return load_preset(path, require_approved=True, log=log)


def override_field(preset, field, value):
    """
    승인 프리셋의 한 필드를 명시적으로 override 한다(hash 재계산).
    변경은 명시적 호출로만 일어난다(기본 동결). 반환: 새 프리셋 dict.
    """
    if field not in _ALLOWED_FIELDS:
        raise PresetError(f"override 불가 필드(미지원): {field}")
    new_body = dict(preset["body"])
    new_body[field] = value
    new_hash = _preset_hash(new_body)
    out = dict(preset)
    out["body"] = new_body
    out["hash"] = new_hash
    out["meta"] = {"name": preset["name"], "version": preset["version"], "hash": new_hash}
    out["overridden"] = True
    return out


if __name__ == "__main__":
    for n in ("malli_video", "baseball_dictionary_video"):
        try:
            p = load_approved(n, log=print)
            print(json.dumps(p["meta"], ensure_ascii=False))
        except PresetError as e:
            print(f"(스킵) {n}: {e}")
