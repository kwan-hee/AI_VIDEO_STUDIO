# 실행 계획 단계를 {provider, action, prompt, parameters} 표준 페이로드로 변환하는 Provider Adapter
"""
Provider Adapter (Sprint 6)

입력: Sprint 5 Execution Planner 출력 (project, steps[...]).
      선택: prompts (Orchestrator prompts) — prompt_key 를 실제 텍스트로 해석할 때 사용.

책임.
  - 각 실행 단계를 표준 공급자 페이로드로 변환한다.
  - 모든 공급자가 같은 표준 형식을 반환한다.

표준 페이로드는 정확히 네 키만 담는다.
  - provider
  - action
  - prompt        (텍스트 없는 공급자는 null)
  - parameters    (공급자별 세부 파라미터)

지원 공급자: Google Flow, Higgsfield, Nano Banana, Edge TTS, Magnific, FFmpeg.

외부 API 호출 없음. 미디어 생성 없음. 공급자 실행 없음. 페이로드 준비만.
출력 스키마: schemas/adapter_payload_schema.json
Sprint 1~5 파일은 수정하지 않는다.
"""


def _payload(provider, action, prompt, parameters):
    """모든 공급자가 공유하는 표준 페이로드. 정확히 네 키."""
    return {
        "provider": provider,
        "action": action,
        "prompt": prompt,
        "parameters": parameters,
    }


# --- 공급자별 어댑터. 페이로드만 준비한다. 실행/호출 없음. ---

def adapt_nano_banana(step, prompt_text):
    return _payload("Nano Banana", "generate_image", prompt_text, {
        "model": "nano-banana",
    })


def adapt_magnific(step, prompt_text):
    return _payload("Magnific", "enhance_image", None, {
        "model": "magnific",
        "mode": "enhance",
        "source_image": "<upstream_image>",
    })


def adapt_google_flow(step, prompt_text):
    return _payload("Google Flow", "generate_video", prompt_text, {
        "model": "google-flow",
        "source_image": "<upstream_image>",
        "backup": step.get("backup"),
    })


def adapt_higgsfield(step, prompt_text):
    return _payload("Higgsfield", "generate_video", prompt_text, {
        "model": "higgsfield",
        "source_image": "<upstream_image>",
        "backup": step.get("backup"),
    })


def adapt_edge_tts(step, prompt_text):
    # Edge TTS: 한국어 내레이션·스토리 음성. 무료.
    return _payload("Edge TTS", "text_to_speech", prompt_text, {
        "engine": "edge-tts",
        "voice": "ko-KR-SunHiNeural",
        "rate": "-5%",
        "cost": "free",
    })


def adapt_ffmpeg(step, prompt_text):
    return _payload("FFmpeg", "compose", None, {
        "operation": "compose",
        "inputs": ["<video>", "<voice>", "<subtitle>"],
    })


# 공급자 이름 → 어댑터 함수
ADAPTERS = {
    "Nano Banana": adapt_nano_banana,
    "Magnific": adapt_magnific,
    "Google Flow": adapt_google_flow,
    "Higgsfield": adapt_higgsfield,
    "Edge TTS": adapt_edge_tts,
    "FFmpeg": adapt_ffmpeg,
}


def _resolve_text(prompts, prompt_key):
    if prompts and prompt_key and isinstance(prompts.get(prompt_key), dict):
        return prompts[prompt_key].get("text")
    return None


def build_payloads(execution_plan, prompts=None):
    """
    실행 계획 → 표준 공급자 페이로드 목록.
    provider 가 있는 단계만 변환한다. 내부 작성 단계(story/script/outline/article)는 건너뛴다.
    외부 API 호출 없음. 준비만.
    """
    if not isinstance(execution_plan, dict):
        raise ValueError("execution_plan 은 dict 여야 한다.")
    if "project" not in execution_plan or "steps" not in execution_plan:
        raise ValueError("execution_plan 에 project 와 steps 가 필요하다.")
    if not isinstance(execution_plan["steps"], list):
        raise ValueError("steps 는 리스트여야 한다.")

    payloads = []
    for step in execution_plan["steps"]:
        provider = step.get("provider")
        if provider is None:
            continue  # 내부 작성 단계, 외부 공급자 없음
        if provider not in ADAPTERS:
            raise ValueError(f"지원하지 않는 공급자: {provider}")
        text = _resolve_text(prompts, step.get("prompt_key"))
        payloads.append(ADAPTERS[provider](step, text))

    return {"project": execution_plan["project"], "payloads": payloads}


if __name__ == "__main__":
    import json
    import os
    import sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _sub in ("planner", "orchestrator"):
        sys.path.insert(0, os.path.join(_ROOT, _sub))
    from orchestrator import orchestrate
    from execution_planner import plan_execution

    req = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "보크 규칙 설명 영상"
    combined = orchestrate(req)
    plan = plan_execution(combined)
    print(json.dumps(build_payloads(plan, combined["prompts"]), ensure_ascii=False, indent=2))
