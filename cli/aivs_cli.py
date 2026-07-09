# AI_VIDEO_STUDIO 터미널 인터페이스(run/providers/status). argparse 기반, 기본 mock, 실 provider 미호출
"""
AI_VIDEO_STUDIO CLI (Phase 5 / Step 6)

명령.
  - aivs run <project_config_path> [--request TEXT]  : 프로젝트 설정 로드 후 파이프라인 실행(mock)
  - aivs providers [--config PATH]                   : 설정된 공급자와 모드 표시
  - aivs status                                      : 시스템 상태 표시

책임.
  - 프로젝트 설정을 로드한다.
  - 기존 파이프라인을 실행한다(중복 로직 없음, pipeline_runner 호출).
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
for _sub in ("config", "pipeline"):
    _p = os.path.join(_ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from project_config import load_project_config, project_name, project_description, output_directory  # noqa: E402
from provider_config import (  # noqa: E402
    load_config, provider_mode, KNOWN_PROVIDERS, KNOWN_CAPABILITIES,
)
from pipeline_runner import run_pipeline  # noqa: E402

# 파이프라인 상태 → 종료 코드
_EXIT = {"success": 0, "partial": 0, "needs_clarification": 2, "failed": 1, "empty": 1}


def _result(command, status, exit_code, summary):
    return {"command": command, "status": status, "exit_code": exit_code, "summary": summary}


def run_command(config_path, request=None, composer_runner=None):
    """프로젝트 설정 로드 → 파이프라인 실행 → (종료코드, 구조화 결과)."""
    cfg = load_project_config(path=config_path)
    req = request or project_description(cfg) or project_name(cfg)
    out_root = output_directory(cfg)

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
            code, result = run_command(args.project_config_path, request=args.request)
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
