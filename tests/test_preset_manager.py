# 승인 프리셋 로드·동결·override·금지키 검사 테스트 (계정정보 없음, 유료연산 없음)
"""
Preset Manager 테스트. 필수:
 3 승인된 말리 프리셋 동결·재사용 / 4 승인된 야구 프리셋 동결·재사용.
추가: 미승인 거부, 금지키(계정/자격증명) 거부, override 시 hash 변경, 미지원 필드 제거.
"""

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "presets"))

from preset_manager import (  # noqa: E402
    load_approved, load_preset, override_field, PresetError, _preset_hash,
)


def _log():
    lines = []
    return lines, (lambda m: lines.append(m))


# 3) 승인된 말리 프리셋 동결·재사용
def test_malli_preset_frozen_and_reused():
    lines, log = _log()
    p = load_approved("malli_video", log=log)
    assert p["status"] == "approved"
    assert p["project_type"] == "malli"
    assert p["meta"]["hash"] and len(p["meta"]["hash"]) == 12
    # 동결: 같은 파일 재로드 시 hash 동일(재사용 안정).
    p2 = load_approved("malli_video")
    assert p2["hash"] == p["hash"]
    # 로그는 이름·버전만.
    assert any("Loaded preset: malli_video v1" in ln for ln in lines)
    # 계정/이메일 관련 키가 body 에 없다.
    assert not any(k in p["body"] for k in ("email", "account", "token"))


# 4) 승인된 야구 프리셋 동결·재사용
def test_baseball_preset_frozen_and_reused():
    p = load_approved("baseball_dictionary_video")
    assert p["status"] == "approved"
    assert p["project_type"] == "baseball_dictionary"
    assert p["body"]["provider"] == "higgsfield"
    assert p["body"]["resolution"] == "1080p"
    assert "negative_prompt" in p["body"]
    p2 = load_approved("baseball_dictionary_video")
    assert p2["hash"] == p["hash"]


# 미승인 상태 거부
def test_unapproved_preset_rejected(tmp_path):
    f = tmp_path / "draft.yaml"
    f.write_text("preset:\n  status: draft\n  name: draft\n  model: m\n", encoding="utf-8")
    with pytest.raises(PresetError):
        load_preset(str(f), require_approved=True)


# 금지키(계정/자격증명) 거부
def test_forbidden_account_keys_rejected(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("preset:\n  status: approved\n  name: bad\n  email: x@y.z\n", encoding="utf-8")
    with pytest.raises(PresetError):
        load_preset(str(f), require_approved=True)


# 미지원 필드 제거(발명 금지)
def test_unsupported_fields_stripped(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text("preset:\n  status: approved\n  name: p\n  model: m\n  made_up_param: 123\n",
                 encoding="utf-8")
    p = load_preset(str(f))
    assert "model" in p["body"]
    assert "made_up_param" not in p["body"]     # 미지원 필드는 동결 대상에서 제외


# override 시 hash 변경(명시적 변경만)
def test_override_changes_hash():
    p = load_approved("malli_video")
    p2 = override_field(p, "resolution", "720p")
    assert p2["hash"] != p["hash"]
    assert p2["body"]["resolution"] == "720p"
    assert p2.get("overridden") is True
    with pytest.raises(PresetError):
        override_field(p, "made_up_param", 1)   # 미지원 필드 override 금지


def test_preset_hash_stable():
    body = {"model": "m", "resolution": "1080p"}
    assert _preset_hash(body) == _preset_hash({"resolution": "1080p", "model": "m"})  # 키순서 무관


if __name__ == "__main__":
    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
