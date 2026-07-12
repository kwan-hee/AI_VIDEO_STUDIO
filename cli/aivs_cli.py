# AI_VIDEO_STUDIO 터미널 인터페이스(run/providers/status). argparse 기반, 기본 mock, 실 provider 미호출
"""
AI_VIDEO_STUDIO CLI (Phase 5 / Step 6)

명령.
  - aivs run <project_config_path> [--request TEXT]  : 프로젝트 설정 로드 후 파이프라인 실행(mock)
      [--mode full_video|hybrid_economy|image_only|mock]
      [--max-ai-video-clips N] [--premium-scene STRATEGY] [--premium-scene-index N]
  - aivs providers [--config PATH]                   : 설정된 공급자와 모드 표시
  - aivs status                                      : 시스템 상태 표시

책임.
  - 프로젝트 설정을 로드한다.
  - 기존 파이프라인을 실행한다(중복 로직 없음, pipeline_runner 호출).
  - hybrid_economy / image_only 모드는 씬 기반 모드 파이프라인(hybrid_pipeline)으로 라우팅한다.
    그 외(full_video/mock/미지정)는 기존 경로 그대로다(기본 동작 불변).
  - CLI 옵션이 프로젝트 설정을 덮어쓴다(CLI > YAML).
  - 간결한 결과 요약을 출력한다.
  - 종료 코드를 반환한다.

기본은 mock 모드다. 설정이 명시적으로 real 을 켜지 않는 한 실 외부 공급자를 호출하지 않는다.
(현 파이프라인은 mock provider + mock 합성 러너를 사용한다. 기존 Provider 구현 미수정.)
argparse 만 사용한다(경량, 무거운 의존성 없음).
결과 스키마: schemas/cli_result_schema.json
"""

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("config", "pipeline", "story", "presets", "quality", "routing"):
    _p = os.path.join(_ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from project_config import (  # noqa: E402
    load_project_config, project_name, project_description, output_directory,
    production_mode, cost_control_settings, image_motion_settings, video_generation_settings,
)
from provider_config import (  # noqa: E402
    load_config, provider_mode, KNOWN_PROVIDERS, KNOWN_CAPABILITIES,
)
from pipeline_runner import run_pipeline  # noqa: E402

# 파이프라인 상태 → 종료 코드
_EXIT = {"success": 0, "partial": 0, "completed_with_fallback": 0,
         "needs_clarification": 2, "failed": 1, "empty": 1}

# 새 씬 기반 모드 파이프라인으로 라우팅하는 모드 (그 외는 기존 경로 불변)
_SCENE_MODES = ("hybrid_economy", "image_only")


def _result(command, status, exit_code, summary):
    return {"command": command, "status": status, "exit_code": exit_code, "summary": summary}


def _apply_cli_overrides(cost_control, max_clips=None, strategy=None, scene_index=None):
    """CLI 옵션 > 프로젝트 설정. index 만 주어지면 manual 전략으로 간주한다."""
    cc = dict(cost_control)
    if max_clips is not None:
        cc["max_ai_video_clips"] = max_clips
    if scene_index is not None:
        cc["preferred_scene_index"] = scene_index
        if strategy is None:
            strategy = "manual"
    if strategy is not None:
        cc["premium_scene_strategy"] = strategy
    return cc


def _ensure_story(out_root, request):
    """{out_root}/story.json 을 재사용(재개)하거나, 없으면 mock 스토리를 생성해 저장한다."""
    story_path = os.path.join(out_root, "story.json")
    if os.path.exists(story_path) and os.path.getsize(story_path) > 0:
        return story_path
    from story_generator import generate_story
    sr = generate_story(request, title=request)
    if sr["status"] != "success":
        raise ValueError(f"스토리 생성 실패: {sr.get('message')}")
    os.makedirs(out_root, exist_ok=True)
    with open(story_path, "w", encoding="utf-8") as f:
        json.dump(sr["story"], f, ensure_ascii=False, indent=2)
    return story_path


_PROJECT_TYPE_BY_PRESET = {"malli_video": "malli",
                          "baseball_dictionary_video": "baseball_dictionary"}


def _quality_validation_plan(project_type):
    """유료 생성 없이 검증 계획(상한·점검항목)만 반환한다. 안전(무과금)."""
    from quality_validation import QualityValidationSession, CHECKS  # 지연 import
    s = QualityValidationSession(project_type)
    return {"project_type": project_type, "max_validation_clips": s.clip_limit(),
            "checks": CHECKS[project_type]}


def _load_preset_safe(preset_name, log):
    """승인 프리셋을 로드·로그(무과금). meta(name/version/hash)만 반환."""
    from preset_manager import load_approved  # 지연 import
    p = load_approved(preset_name, log=log)
    return p["meta"]


def run_command(config_path, request=None, composer_runner=None, mode=None,
                max_ai_video_clips=None, premium_scene=None, premium_scene_index=None,
                higgsfield_account=None, preset=None, quality_validation=False,
                approve_preset=False, quality=None, resume=False):
    """프로젝트 설정 로드 → 파이프라인 실행 → (종료코드, 구조화 결과). CLI 옵션 > YAML.

    Higgsfield 이중계정 관련 옵션(higgsfield_account/preset/quality_validation/approve_preset)은
    **무과금 안전 동작**만 한다. 실제 유료 생성/라이브 계정 전환은 두 MCP 서버가 별도 인증으로
    등록·검증되기 전까지 배선되지 않는다(README 의 Dual-Account 섹션 참조)."""
    cfg = load_project_config(path=config_path)
    req = request or project_description(cfg) or project_name(cfg)
    out_root = output_directory(cfg)

    # --quality-validation: 검증 계획만 출력(무과금). 파이프라인 실행하지 않는다.
    if quality_validation:
        ptype = _PROJECT_TYPE_BY_PRESET.get(preset) or (
            "malli" if "malli" in (project_name(cfg) or "").lower() else "baseball_dictionary")
        plan = _quality_validation_plan(ptype)
        print(f"[Quality] Validation plan for {ptype}: max {plan['max_validation_clips']} paid clips; "
              f"checks={', '.join(plan['checks'])}")
        print("[Quality] No paid generation performed. Review each clip, then approve explicitly.")
        summary = {"request": req, "project": project_name(cfg), "status": "success",
                   "quality_validation": plan, "account_intent": higgsfield_account or "legacy"}
        return 0, _result("run", "success", 0, summary)

    # --preset / --higgsfield-account: 안전 메타 로깅(무과금).
    preset_meta = None
    if preset:
        preset_meta = _load_preset_safe(preset, log=print)
        print(f"[Quality] Loaded approved preset: {preset_meta['name']} v{preset_meta['version']} "
              f"(hash {preset_meta['hash']})")
    if higgsfield_account:
        print(f"[Higgsfield Router] Requested account policy: {higgsfield_account} "
              "(live switching inactive until two MCP servers are registered).")

    effective_mode = mode or production_mode(cfg)

    if effective_mode in _SCENE_MODES:
        from hybrid_pipeline import run_mode_pipeline
        cc = _apply_cli_overrides(cost_control_settings(cfg),
                                  max_clips=max_ai_video_clips,
                                  strategy=premium_scene,
                                  scene_index=premium_scene_index)
        story_path = _ensure_story(out_root, req)
        res = run_mode_pipeline(
            story_path, out_root, mode=effective_mode,
            cost_control=cc,
            image_motion_settings=image_motion_settings(cfg),
            video_generation=video_generation_settings(cfg),
        )
        status = res["status"]
        code = _EXIT.get(status, 1)
        summary = {
            "request": req,
            "project": project_name(cfg),
            "status": status,
            "mode": effective_mode,
            "premium_scenes": res["premium_scenes"],
            "usage": res["summary"],
        }
        return code, _result("run", status, code, summary)

    # 기존 경로(기본 동작 불변): full_video / mock / 미지정
    res = run_pipeline(req, output_root=out_root, composer_runner=composer_runner)
    status = res["status"]
    code = _EXIT.get(status, 1)
    summary = {
        "request": res["request"],
        "project": res["project"],
        "status": status,
        "asset_count": res["asset_count"],
        "providers_used": res["providers_used"],
        "final_output": res["final_output"],
    }
    return code, _result("run", status, code, summary)


def providers_command(config_path=None):
    """설정된 공급자와 모드 → (종료코드, 구조화 결과)."""
    cfg = load_config(path=config_path)
    modes = {key: provider_mode(cfg, key) for key in KNOWN_PROVIDERS}
    return 0, _result("providers", "ok", 0, {"providers": modes})


def status_command():
    """시스템 상태 → (종료코드, 구조화 결과)."""
    cfg = load_config()
    summary = {
        "ready": True,
        "default_mode": "mock",
        "providers": {key: provider_mode(cfg, key) for key in KNOWN_PROVIDERS},
        "capabilities": list(KNOWN_CAPABILITIES),
    }
    return 0, _result("status", "ok", 0, summary)


def _print_summary(result):
    """간결한 사람용 요약 출력."""
    cmd = result["command"]
    s = result["summary"]
    if cmd == "run":
        if "quality_validation" in s:  # 무과금 검증 계획 출력
            qv = s["quality_validation"]
            print(f"[run] project={s['project']} quality-validation "
                  f"max_clips={qv['max_validation_clips']} account={s['account_intent']}")
        elif "usage" in s:  # 씬 기반 모드 파이프라인 (사용량 상세는 파이프라인이 이미 출력)
            print(f"[run] project={s['project']} mode={s['mode']} status={s['status']} "
                  f"premium_scenes={s['premium_scenes']}")
        else:
            print(f"[run] project={s['project']} status={s['status']} "
                  f"assets={s['asset_count']} providers={','.join(p for p in s['providers_used'])}")
            print(f"      final_output={s['final_output']}")
    elif cmd == "providers":
        for key, mode in s["providers"].items():
            print(f"  {key:<14} {mode}")
    elif cmd == "status":
        print(f"AI_VIDEO_STUDIO ready={s['ready']} default_mode={s['default_mode']}")
        print(f"  capabilities: {', '.join(s['capabilities'])}")


def _build_parser():
    p = argparse.ArgumentParser(prog="aivs", description="AI_VIDEO_STUDIO CLI")
    sub = p.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="프로젝트 설정으로 파이프라인 실행(mock)")
    p_run.add_argument("project_config_path", help="프로젝트 설정 파일 경로(JSON/YAML)")
    p_run.add_argument("--request", default=None, help="요청 텍스트(미지정 시 설정의 description 사용)")
    p_run.add_argument("--mode", default=None,
                       choices=["full_video", "hybrid_economy", "image_only", "mock"],
                       help="제작 모드(설정의 production.mode 를 덮어씀)")
    p_run.add_argument("--max-ai-video-clips", type=int, default=None, dest="max_ai_video_clips",
                       help="에피소드당 AI 영상 클립 상한(설정을 덮어씀)")
    p_run.add_argument("--premium-scene", default=None, dest="premium_scene",
                       choices=["auto", "first", "middle", "climax", "manual"],
                       help="프리미엄 씬 선택 전략(설정을 덮어씀)")
    p_run.add_argument("--premium-scene-index", type=int, default=None, dest="premium_scene_index",
                       help="프리미엄 씬 번호(1-base). 지정 시 manual 전략으로 간주")
    # --- Higgsfield 이중계정 옵션 (무과금 안전 동작; 라이브 전환은 두 MCP 서버 등록 후) ---
    p_run.add_argument("--higgsfield-account", default=None, dest="higgsfield_account",
                       choices=["auto", "legacy", "production"],
                       help="Higgsfield 계정 정책(alias 만): auto/legacy/production")
    p_run.add_argument("--preset", default=None, dest="preset",
                       help="승인 프리셋 이름(malli_video / baseball_dictionary_video)")
    p_run.add_argument("--quality-validation", action="store_true", dest="quality_validation",
                       help="검증 계획만 출력(무과금). 최대 3클립(말리2/야구1).")
    p_run.add_argument("--approve-preset", action="store_true", dest="approve_preset",
                       help="프리셋 승인 의도 표기(명시 승인은 검증 세션에서).")
    p_run.add_argument("--quality", default=None, dest="quality",
                       help="품질 수준 힌트(예: high)")
    p_run.add_argument("--resume", action="store_true", dest="resume",
                       help="완료 자산·활성 계정을 재사용(재개). 전환 후 legacy 회귀 없음.")

    p_prov = sub.add_parser("providers", help="설정된 공급자와 모드 표시")
    p_prov.add_argument("--config", default=None, help="공급자 설정 파일 경로")

    sub.add_parser("status", help="시스템 상태 표시")
    return p


def main(argv=None):
    """CLI 진입점. 종료 코드를 반환한다."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help(sys.stderr)
        return 2

    try:
        if args.command == "run":
            code, result = run_command(
                args.project_config_path, request=args.request, mode=args.mode,
                max_ai_video_clips=args.max_ai_video_clips,
                premium_scene=args.premium_scene,
                premium_scene_index=args.premium_scene_index,
                higgsfield_account=args.higgsfield_account,
                preset=args.preset,
                quality_validation=args.quality_validation,
                approve_preset=args.approve_preset,
                quality=args.quality,
                resume=args.resume,
            )
        elif args.command == "providers":
            code, result = providers_command(config_path=args.config)
        else:  # status
            code, result = status_command()
    except (ValueError, OSError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    _print_summary(result)
    return code


if __name__ == "__main__":
    sys.exit(main())
