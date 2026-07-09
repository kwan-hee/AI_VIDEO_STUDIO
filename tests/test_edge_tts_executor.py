# edge_tts_executor.run() 의 합성 결과·경로·거부 규칙·스키마 준수를 검증하는 테스트 (합성은 가짜 백엔드로 대체)
"""Edge TTS Executor 단위 테스트. 네트워크 없이 가짜 synth 로 검증. 결과는 schemas/edge_tts_result_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("executors", "adapters", "planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

import edge_tts_executor as EX  # noqa: E402
from edge_tts_executor import run  # noqa: E402
from orchestrator import orchestrate  # noqa: E402
from execution_planner import plan_execution  # noqa: E402
from provider_adapter import build_payloads  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "edge_tts_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

_TMP = os.path.join(_ROOT, "output", "audio", "_test_tmp")


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _fake_synth(text, voice, rate, path):
    # 네트워크 없이 더미 mp3 바이트 기록
    with open(path, "wb") as f:
        f.write(b"ID3fake-mp3-bytes")


def _fail_synth(text, voice, rate, path):
    raise RuntimeError("네트워크 없음")


def _payload(text="안녕하세요 테스트", voice="ko-KR-SunHiNeural", rate="-5%"):
    return {
        "provider": "Edge TTS", "action": "text_to_speech", "prompt": text,
        "parameters": {"engine": "edge-tts", "voice": voice, "rate": rate, "cost": "free"},
    }


def _cleanup():
    if os.path.isdir(_TMP):
        for f in os.listdir(_TMP):
            os.remove(os.path.join(_TMP, f))
        os.rmdir(_TMP)


# --- 성공 합성 ---

def test_success_creates_mp3():
    try:
        r = run(_payload("말리가 달님을 만났다"), synth=_fake_synth, output_dir=_TMP)
        assert r["status"] == "success"
        assert r["output_path"].endswith(".mp3")
        assert r["format"] == "mp3"
        assert r["voice"] == "ko-KR-SunHiNeural"
        assert r["rate"] == "-5%"
        # 실제 파일 생성 확인
        files = os.listdir(_TMP)
        assert len(files) == 1 and files[0].endswith(".mp3")
        assert os.path.getsize(os.path.join(_TMP, files[0])) > 0
        _assert_valid(r)
    finally:
        _cleanup()


def test_default_output_dir_is_output_audio():
    # output_dir 미지정 시 output/audio 아래에 저장
    text = "기본 경로 테스트 고유문자열 xyzzy"
    r = run(_payload(text), synth=_fake_synth)
    try:
        assert r["status"] == "success"
        assert r["output_path"].startswith("output/audio/")
        abs_path = os.path.join(_ROOT, r["output_path"])
        assert os.path.exists(abs_path)
    finally:
        abs_path = os.path.join(_ROOT, r["output_path"])
        if os.path.exists(abs_path):
            os.remove(abs_path)


def test_deterministic_filename():
    r1 = run(_payload("같은 텍스트"), synth=_fake_synth, output_dir=_TMP)
    r2 = run(_payload("같은 텍스트"), synth=_fake_synth, output_dir=_TMP)
    try:
        assert r1["output_path"] == r2["output_path"]  # 같은 텍스트 → 같은 파일명
    finally:
        _cleanup()


# --- 실패/거부 ---

def test_empty_prompt_failed():
    r = run(_payload(""), synth=_fake_synth, output_dir=_TMP)
    assert r["status"] == "failed"
    assert r["output_path"] is None
    _assert_valid(r)
    _cleanup()


def test_synth_failure_reported():
    r = run(_payload("실패 테스트"), synth=_fail_synth, output_dir=_TMP)
    assert r["status"] == "failed"
    assert r["output_path"] is None
    assert "실패" in r["message"]
    _assert_valid(r)
    _cleanup()


def test_rejects_non_edge_tts_provider():
    for bad in [
        {"provider": "Higgsfield", "action": "generate_video", "prompt": "x", "parameters": {}},
        {"provider": "Nano Banana", "action": "generate_image", "prompt": "x", "parameters": {}},
        {"provider": "Edge TTS", "action": "generate_video", "prompt": "x", "parameters": {}},
    ]:
        try:
            run(bad, synth=_fake_synth, output_dir=_TMP)
        except ValueError:
            continue
        raise AssertionError(f"비-EdgeTTS 페이로드가 거부되지 않음: {bad}")
    _cleanup()


def test_bad_input_rejected():
    for bad in [None, "x", 3, []]:
        try:
            run(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


# --- 통합: 어댑터 페이로드에서 ---

def test_integration_from_adapter_payload():
    combined = orchestrate("보크 규칙 설명 영상", topic="보크")
    plan = plan_execution(combined)
    payloads = build_payloads(plan, combined["prompts"])
    tts = next(p for p in payloads["payloads"] if p["provider"] == "Edge TTS")
    assert tts["action"] == "text_to_speech"
    r = run(tts, synth=_fake_synth, output_dir=_TMP)
    try:
        assert r["status"] == "success"
        _assert_valid(r)
    finally:
        _cleanup()


# --- 실제 백엔드 연결 확인 (네트워크 없이) ---

def test_default_synth_is_real_edge_tts():
    import edge_tts  # 설치 확인
    assert EX._edge_tts_synth is not None
    assert callable(EX._edge_tts_synth)
    assert edge_tts is not None


# --- 옵트인 실제 합성 (RUN_REAL_TTS=1 일 때만) ---

def test_real_synthesis_optional():
    if os.environ.get("RUN_REAL_TTS") != "1":
        return  # 네트워크 의존, 기본 건너뜀
    r = run(_payload("실제 합성 테스트입니다"), output_dir=_TMP)
    try:
        assert r["status"] == "success"
        assert os.path.getsize(os.path.join(_ROOT, r["output_path"]) if not os.path.isabs(r["output_path"]) else r["output_path"]) > 0
    finally:
        _cleanup()


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
