# Edge TTS 페이로드를 받아 실제 mp3 음성을 합성해 output/audio 에 저장하고 표준 결과를 반환하는 Edge TTS Executor
"""
Edge TTS Executor (Sprint 10)

입력: Provider Adapter 페이로드. 반드시 provider="Edge TTS", action="text_to_speech".

음성 정책.
  - 엔진: edge-tts
  - 목소리: ko-KR-SunHiNeural
  - 속도: -5%
  - 출력 형식: mp3

책임.
  - Edge TTS 를 실행해 실제 음성 파일을 만든다.
  - output/audio/ 아래에 저장한다.
  - 표준 JSON 결과를 반환한다.

Edge TTS 만 구현한다. 다른 공급자(Google Flow / Higgsfield / Nano Banana / Magnific / FFmpeg)는 실행하지 않는다.
합성 백엔드는 synth 인자로 주입 가능하다. 기본은 실제 edge-tts. 테스트는 가짜 백엔드로 네트워크 없이 검증한다.
출력 스키마: schemas/edge_tts_result_schema.json
Sprint 1~9 파일은 수정하지 않는다.
"""

import hashlib
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "audio")

DEFAULT_VOICE = "ko-KR-SunHiNeural"
DEFAULT_RATE = "-5%"


def _edge_tts_synth(text, voice, rate, path):
    """실제 edge-tts 합성. edge-tts 는 마이크로소프트 온라인 TTS 를 사용한다(무료)."""
    import asyncio

    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice, rate=rate).save(path)

    asyncio.run(_go())


def _rel(path):
    """가능하면 프로젝트 루트 기준 posix 상대 경로로 표기."""
    try:
        return os.path.relpath(path, _ROOT).replace(os.sep, "/")
    except ValueError:
        return path


def _result(status, output_path, voice, rate, message):
    return {
        "provider": "Edge TTS",
        "action": "text_to_speech",
        "status": status,
        "output_path": output_path,
        "format": "mp3",
        "voice": voice,
        "rate": rate,
        "message": message,
    }


def run(payload, synth=None, output_dir=None):
    """
    Edge TTS 페이로드 → 실제 mp3 합성 결과.
    provider/action 이 Edge TTS/text_to_speech 가 아니면 거부한다 (다른 공급자 실행 안 함).
    합성 실패는 status="failed" 로 반환한다.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload 는 dict 여야 한다.")
    if payload.get("provider") != "Edge TTS" or payload.get("action") != "text_to_speech":
        raise ValueError("Edge TTS Executor 는 provider='Edge TTS', action='text_to_speech' 만 처리한다.")

    params = payload.get("parameters") or {}
    voice = params.get("voice", DEFAULT_VOICE)
    rate = params.get("rate", DEFAULT_RATE)
    text = payload.get("prompt")

    if not isinstance(text, str) or not text.strip():
        return _result("failed", None, voice, rate, "합성할 텍스트(prompt)가 없다.")

    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    name = "tts_" + hashlib.md5(text.encode("utf-8")).hexdigest()[:10] + ".mp3"
    path = os.path.join(out_dir, name)

    synth = synth or _edge_tts_synth
    try:
        synth(text, voice, rate, path)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("음성 파일이 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        return _result("failed", None, voice, rate, f"Edge TTS 합성 실패: {e}")

    return _result("success", _rel(path), voice, rate, "Edge TTS 음성 합성 완료.")


if __name__ == "__main__":
    import json
    import sys

    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "안녕하세요. 말리 동화 테스트 음성입니다."
    payload = {
        "provider": "Edge TTS", "action": "text_to_speech", "prompt": text,
        "parameters": {"engine": "edge-tts", "voice": DEFAULT_VOICE, "rate": DEFAULT_RATE, "cost": "free"},
    }
    print(json.dumps(run(payload), ensure_ascii=False, indent=2))
