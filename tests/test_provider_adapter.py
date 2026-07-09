# provider_adapter.build_payloads() 와 공급자별 어댑터의 {provider,action,prompt,parameters} 표준 형식을 검증하는 테스트
"""Provider Adapter 단위 테스트. 페이로드는 schemas/adapter_payload_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("adapters", "planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

import provider_adapter as PA  # noqa: E402
from provider_adapter import build_payloads, ADAPTERS  # noqa: E402
from orchestrator import orchestrate  # noqa: E402
from execution_planner import plan_execution  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "adapter_payload_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

SUPPORTED = {"Google Flow", "Higgsfield", "Nano Banana", "Edge TTS", "Magnific", "FFmpeg"}
PAYLOAD_KEYS = {"provider", "action", "prompt", "parameters"}


def _pipeline(request, topic=None):
    combined = orchestrate(request, topic=topic)
    plan = plan_execution(combined)
    return build_payloads(plan, combined["prompts"])


def _assert_valid(obj):
    errs = sorted(_VALIDATOR.iter_errors(obj), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _assert_payload(p):
    assert set(p.keys()) == PAYLOAD_KEYS, f"페이로드 키 불일치: {p.keys()}"
    assert p["provider"] in SUPPORTED
    assert isinstance(p["parameters"], dict)
    assert p["prompt"] is None or isinstance(p["prompt"], str)


# --- 지원 공급자 6종 각각 단위 테스트 ---

def test_each_supported_provider_shape():
    step = {"step": "x", "provider": "?", "backup": "Higgsfield", "prompt_key": None}
    expected_action = {
        "Nano Banana": "generate_image",
        "Magnific": "enhance_image",
        "Google Flow": "generate_video",
        "Higgsfield": "generate_video",
        "Edge TTS": "text_to_speech",
        "FFmpeg": "compose",
    }
    assert set(ADAPTERS.keys()) == SUPPORTED  # 6종 전부
    for name, fn in ADAPTERS.items():
        p = fn(step, "샘플 프롬프트")
        _assert_payload(p)
        assert p["provider"] == name
        assert p["action"] == expected_action[name]
        _assert_valid({"project": "malli", "payloads": [p]})


def test_nano_banana_carries_prompt():
    p = PA.adapt_nano_banana({"step": "image", "backup": None}, "보크 장면")
    assert p["action"] == "generate_image"
    assert p["prompt"] == "보크 장면"
    assert p["parameters"]["model"] == "nano-banana"


def test_magnific_no_prompt():
    p = PA.adapt_magnific({"step": "image", "backup": None}, None)
    assert p["prompt"] is None
    assert p["action"] == "enhance_image"


def test_google_flow_backup_param():
    p = PA.adapt_google_flow({"step": "video", "backup": "Higgsfield"}, "장면")
    assert p["parameters"]["backup"] == "Higgsfield"
    assert p["parameters"]["model"] == "google-flow"


def test_higgsfield_backup_param():
    p = PA.adapt_higgsfield({"step": "video", "backup": "Google Flow"}, "장면")
    assert p["parameters"]["backup"] == "Google Flow"


def test_hedra_script_prompt():
    p = PA.adapt_edge_tts({"step": "voice", "backup": None}, "대본 낭독")
    assert p["action"] == "text_to_speech"
    assert p["prompt"] == "대본 낭독"


def test_ffmpeg_compose():
    p = PA.adapt_ffmpeg({"step": "edit", "backup": None}, None)
    assert p["action"] == "compose"
    assert p["prompt"] is None
    assert "inputs" in p["parameters"]


# --- 파이프라인 통합: 카테고리별 ---

def test_baseball_payloads():
    out = _pipeline("보크 규칙 설명 영상", topic="보크")
    provs = [p["provider"] for p in out["payloads"]]
    assert provs == ["Nano Banana", "Higgsfield", "Edge TTS", "Nano Banana", "FFmpeg"]
    for p in out["payloads"]:
        _assert_payload(p)
    _assert_valid(out)


def test_malli_payloads():
    out = _pipeline("말리가 달님을 만난 날", topic="달님")
    provs = [p["provider"] for p in out["payloads"]]
    assert provs == ["Nano Banana", "Google Flow", "Edge TTS", "Nano Banana", "FFmpeg"]
    _assert_valid(out)


def test_thumbnail_payloads():
    out = _pipeline("건강검진 대상자 조회 썸네일", topic="건강검진")
    assert [p["provider"] for p in out["payloads"]] == ["Nano Banana", "Nano Banana"]
    _assert_valid(out)


def test_blog_no_payloads():
    out = _pipeline("국민연금 블로그 작성", topic="국민연금")
    assert out["payloads"] == []
    _assert_valid(out)


def test_unknown_no_payloads():
    out = _pipeline("unknown input")
    assert out["payloads"] == []
    _assert_valid(out)


# --- 계약/안전성 ---

def test_prompt_text_embedded():
    out = _pipeline("보크 규칙 영상", topic="인필드 플라이")
    img = next(p for p in out["payloads"] if p["action"] == "generate_image")
    assert "인필드 플라이" in img["prompt"]


def test_no_execution_markers():
    out = _pipeline("보크 규칙 영상", topic="보크")
    for p in out["payloads"]:
        banned = {"executed", "status", "response", "result", "url", "job_id", "output"}
        assert banned.isdisjoint(set(p.keys()))


def test_unsupported_provider_rejected():
    bad_plan = {"project": "malli", "steps": [
        {"order": 1, "step": "image", "provider": "DALL-E", "backup": None, "prompt_key": None}]}
    try:
        build_payloads(bad_plan)
    except ValueError:
        return
    raise AssertionError("지원하지 않는 공급자가 거부되지 않음")


def test_input_not_mutated():
    combined = orchestrate("보크 규칙 영상", topic="보크")
    plan = plan_execution(combined)
    before = json.dumps([plan, combined["prompts"]], ensure_ascii=False, sort_keys=True)
    build_payloads(plan, combined["prompts"])
    after = json.dumps([plan, combined["prompts"]], ensure_ascii=False, sort_keys=True)
    assert before == after, "입력이 변형됨"


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, {"project": "malli"}]:
        try:
            build_payloads(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
