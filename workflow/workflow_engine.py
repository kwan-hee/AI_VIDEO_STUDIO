# 기존 파이프라인(기획→라우팅→mock생성→에셋등록→타임라인→합성)을 하나로 엮는 통제된 Workflow Engine
"""
Workflow Engine (Phase 4 / Step 2)

목적.
  - 기존 파이프라인 컴포넌트를 하나의 재사용 워크플로 러너로 연결한다.

흐름.
  1. 요청 하나를 받는다.
  2. 기존 기획 파이프라인 실행 (Orchestrator → Execution Planner).
  3. Provider Router 로 capability 별 공급자 선택.
  4. 기존 provider 핸들러(기본 mock)로 생성.
  5. 생성물을 Asset Manager 에 등록.
  6. Timeline Builder 로 타임라인 구성.
  7. 최종 합성 결과 준비 (compose_from_timeline, mock runner).

통제된 엔진이다. 실 Google Flow / Higgsfield / Nano Banana / Magnific 호출 없음.
실 ffmpeg 실행 없음(runner 주입). 기본은 기존 mock provider. 기존 Provider 구현 미수정.
출력 스키마: schemas/workflow_result_schema.json
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("orchestrator", "planner", "routing", "providers", "assets", "timeline",
             "composer", "reliability", "logging"):
    _p = os.path.join(_ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from orchestrator import orchestrate                 # noqa: E402
from execution_planner import plan_execution         # noqa: E402
from provider_router import route                     # noqa: E402
from provider_sdk import make_request, make_result    # noqa: E402
from asset_manager import AssetManager                # noqa: E402
from timeline_builder import build_timeline           # noqa: E402
from ffmpeg_composer import compose_from_timeline      # noqa: E402
from retry_manager import run_with_retry               # noqa: E402  (Phase 7-2 신뢰성 배선)
from execution_logger import ExecutionLogger          # noqa: E402  (Phase 7-2 신뢰성 배선)

import nano_banana_provider                            # noqa: E402
import higgsfield_provider                             # noqa: E402
import google_flow_provider                            # noqa: E402
import magnific_provider                               # noqa: E402

import hashlib  # noqa: E402

# 실행 계획 step 이름 → capability (텍스트/편집 단계는 생성 대상 아님 → 제외)
STEP_CAPABILITY = {
    "image": "generate_image",
    "thumbnail": "generate_image",
    "video": "generate_video",
    "voice": "text_to_speech",
}

# 실행 계획 step 이름 → Asset Manager 에셋 타입
STEP_ASSET_TYPE = {
    "image": "image",
    "thumbnail": "thumbnail",
    "video": "video",
    "voice": "audio",
}

# capability → output 하위 디렉토리
_CAP_SUBDIR = {
    "generate_image": "images",
    "generate_video": "videos",
    "enhance_image": "enhanced",
    "text_to_speech": "audio",
}


def _rel(path):
    try:
        return os.path.relpath(path, _ROOT).replace(os.sep, "/")
    except ValueError:
        return path


def _mock_tts_handler(request, output_dir=None, writer=None):
    """SDK provider 모듈이 없는 Edge TTS 를 엔진 내부 mock 으로 처리(placeholder mp3)."""
    prompt = request.get("prompt")
    out_dir = output_dir or os.path.join(_ROOT, "output", "audio")
    os.makedirs(out_dir, exist_ok=True)
    key = hashlib.md5((prompt or "").encode("utf-8")).hexdigest()[:10]
    path = os.path.join(out_dir, f"tts_{key}.mp3")
    is_mock = writer is None
    writer = writer or (lambda p, t: open(p, "wb").write(b"ID3\x03mock-audio"))
    try:
        writer(path, prompt)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("음성 파일이 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        return make_result("Edge TTS", "text_to_speech", status="failed", output=None,
                           message=f"음성 생성 실패: {e}")
    output = {"path": _rel(path), "type": "audio", "mock": is_mock, "prompt": prompt}
    return make_result("Edge TTS", "text_to_speech", status="success", output=output,
                       message="mock 음성 생성 완료.")


# 공급자 이름 → 핸들러 (request, output_dir, writer) -> SDK result
DEFAULT_HANDLERS = {
    "Nano Banana": nano_banana_provider.generate,
    "Higgsfield": higgsfield_provider.generate,
    "Google Flow": google_flow_provider.generate,
    "Magnific": magnific_provider.generate,
    "Edge TTS": _mock_tts_handler,
}


def _mock_compose_runner(args, output_path):
    """실 ffmpeg 없이 placeholder mp4 를 기록하는 기본 합성 러너."""
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42workflow-mock")


def _resolve_prompt(prompts, key):
    if not key:
        return None
    v = prompts.get(key)
    if isinstance(v, dict):
        return v.get("text")
    if isinstance(v, str):
        return v
    return None


def _cap_dir(output_root, capability):
    if not output_root:
        return None
    return os.path.join(output_root, _CAP_SUBDIR[capability])


def run_workflow(request, output_root=None, handlers=None, composer_runner=None, exclude=None,
                 logger=None, max_attempts=1):
    """
    요청 하나 → 통제된 워크플로 결과.
    기획→라우팅→(Retry Manager로)생성→에셋등록→타임라인→합성. 실 외부호출/실 ffmpeg 없음.
    handlers: 공급자별 핸들러 오버라이드(기본 mock provider).
    exclude: capability 별 제외 공급자(failover 테스트/정책). 예: {"generate_video":["Higgsfield"]}
    logger: ExecutionLogger 주입(기본 내부 생성). run_start/provider_call/retry/failure/output/run_end 방출.
    max_attempts: Retry Manager 의 후보별 재시도 횟수(기본 1). failover 는 후보 순회로 처리.
    """
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request 는 비어 있지 않은 문자열이어야 한다.")

    handlers = {**DEFAULT_HANDLERS, **(handlers or {})}
    exclude = exclude or {}
    logger = logger or ExecutionLogger()
    logger.run_start()

    orch = orchestrate(request)
    project = orch["project"]
    prompts = orch["prompts"]

    if orch.get("needs_clarification") or project == "unknown":
        logger.run_end(status="failed", message="needs_clarification/unknown")
        return {
            "request": request, "project": project, "needs_clarification": True,
            "selections": [], "assets": [], "timeline": None, "composition": None,
        }

    plan = plan_execution(orch)
    mgr = AssetManager()
    selections = []
    last_image_path = None

    for step in plan["steps"]:
        name = step["step"]
        cap = STEP_CAPABILITY.get(name)
        if cap is None:
            continue  # story/script/outline/article/edit: 생성 대상 아님

        # 라우팅: 정책 후보(순서) 중 exclude 를 뺀 목록으로 Retry Manager 에 failover 위임
        sel = route(cap)
        excluded = set(exclude.get(cap) or [])
        candidates = [p for p in sel["candidates"] if p not in excluded]
        if not candidates:
            selections.append({"step": name, "capability": cap, "provider": None})
            logger.failure(step=name, message="사용 가능한 공급자 없음")
            continue

        text = _resolve_prompt(prompts, step.get("prompt_key")) or f"{project} {name}"
        inputs = [last_image_path] if (cap == "generate_video" and last_image_path) else []

        def _call(provider, attempt, _cap=cap, _text=text, _inputs=inputs):
            h = handlers.get(provider)
            if h is None:
                return {"status": "failed", "message": f"핸들러 없음: {provider}"}
            req = make_request(provider, _cap, prompt=_text, inputs=_inputs)
            return h(req, output_dir=_cap_dir(output_root, _cap))

        retry_res = run_with_retry(candidates, _call, max_attempts=max_attempts)

        # 시도별 이벤트: provider_call, 실패 후 다음 시도가 있으면 retry
        entries = retry_res["log"]
        for i, e in enumerate(entries):
            logger.provider_call(step=name, provider=e["provider"], capability=cap,
                                 status=e["status"], attempt=e["attempt"], message=e["message"])
            if e["status"] == "failed" and i < len(entries) - 1:
                logger.retry(provider=e["provider"], attempt=e["attempt"], message="failover/재시도")

        provider = retry_res["selected_provider"]
        selections.append({"step": name, "capability": cap, "provider": provider})

        if retry_res["status"] != "success":
            logger.failure(step=name, provider=candidates[0], message="모든 후보 실패")
            continue

        path = retry_res["result"]["output"]["path"]
        mgr.register(STEP_ASSET_TYPE[name], provider, path, status="ready")
        if name == "image":
            last_image_path = path

    assets = mgr.list_assets()
    timeline = build_timeline(plan, assets)

    composition = None
    has_visual = any(e["layer"] == "visual" for e in timeline["entries"])
    if has_visual:
        final_dir = os.path.join(output_root, "final") if output_root else None
        composition = compose_from_timeline(
            timeline, assets, output_dir=final_dir,
            runner=composer_runner or _mock_compose_runner,
        )

    composed_ok = bool(composition and composition.get("status") == "success")
    if composed_ok:
        logger.output(output_path=composition.get("output_path"))
    logger.run_end(status="success" if composed_ok else "failed")

    return {
        "request": request,
        "project": project,
        "needs_clarification": False,
        "selections": selections,
        "assets": assets,
        "timeline": timeline,
        "composition": composition,
    }


if __name__ == "__main__":
    import json

    req = sys.argv[1] if len(sys.argv) > 1 else "말리가 달님을 만난 동화 영상 만들어줘"
    print(json.dumps(run_workflow(req), ensure_ascii=False, indent=2))
