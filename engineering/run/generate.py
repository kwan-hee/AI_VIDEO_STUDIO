#!/usr/bin/env python3
# 승인된 장면 목록을 제출용 페이로드로 바꾼다. 이 스크립트 자체는 호출하지 않는다.
"""
사용법:
    python3 run/generate.py [장면_목록.json]

출력된 JSON 을 Higgsfield generate_video_batch 의 requests 로 그대로 넘긴다.
sound=off 가 이미 들어 있다. 지우면 초당 단가가 1.75 로 오른다.
"""

import json
import sys

from _common import latest_scene_file  # noqa: E402

from kling.kling_pipeline import (  # noqa: E402
    KlingPipelineError,
    build_payloads,
    build_plan,
    format_report,
)


def main():
    args = sys.argv[1:]
    path = args[0] if args else latest_scene_file()
    if not path:
        print("장면 목록 파일을 찾지 못했다.", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as f:
        spec = json.load(f)

    try:
        plan = build_plan(spec.get("project", "untitled"), spec["scenes"], budget=spec.get("budget"))
    except KlingPipelineError as exc:
        print(f"계획 수립 실패: {exc}", file=sys.stderr)
        return 1

    print(format_report(plan), file=sys.stderr)
    print("--- 아래 JSON 을 generate_video_batch 의 requests 로 넘긴다 ---", file=sys.stderr)

    requests = [
        {"index": p["index"], "params": {**p["params"], "use_unlim": False}}
        for p in build_payloads(plan)
    ]
    print(json.dumps(requests, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
