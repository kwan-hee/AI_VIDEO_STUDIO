#!/usr/bin/env python3
# 장면 목록의 비용과 중복을 산출한다. 크레딧을 쓰지 않는다.
"""
사용법:
    python3 run/estimate.py [장면_목록.json] [--duplicates-only]

인자를 생략하면 output/ 안의 가장 최근 *_scenes.json 을 쓴다.
"""

import json
import sys

from _common import latest_scene_file  # noqa: E402

from kling.kling_pipeline import (  # noqa: E402
    CREDITS_PER_SECOND,
    SOUND,
    KlingPipelineError,
    build_plan,
    find_duplicates,
)


def load(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if "scenes" not in spec:
        raise KlingPipelineError(f"{path} 에 scenes 키가 없다.")
    return spec


def report_duplicates(scenes):
    dups = find_duplicates(scenes)
    if not dups:
        print("중복 의심 장면 없음.")
        return 0
    total = 0.0
    print(f"중복 의심 {len(dups)}쌍:")
    for d in dups:
        total += d["refundable"]
        print(f"  - {d['left']} vs {d['right']}")
        print(f"      유사도 {d['similarity']}, 하나를 빼면 {d['refundable']} 크레딧 절약")
    print(f"  전부 정리하면 {round(total, 2)} 크레딧 절약.")
    print("  의도된 대비는 중복이 아니다. 지우기 전에 서사에 구멍이 생기는지 확인한다.")
    return total


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dup_only = "--duplicates-only" in sys.argv

    path = args[0] if args else latest_scene_file()
    if not path:
        print("장면 목록 파일을 찾지 못했다. output/ 에 *_scenes.json 을 두거나 경로를 지정한다.")
        return 1

    spec = load(path)
    scenes = spec["scenes"]

    if dup_only:
        report_duplicates(scenes)
        return 0

    try:
        plan = build_plan(spec.get("project", "untitled"), scenes, budget=spec.get("budget"))
    except KlingPipelineError as exc:
        print(f"계획 수립 실패: {exc}")
        return 1

    print(f"파일: {path}")
    print(f"주제: {plan['project']} / 장면 {plan['scene_count']}개 / 총 {plan['total_seconds']}초")
    print(f"엔진: Kling 3.0 (sound={SOUND}, 초당 {CREDITS_PER_SECOND})")
    print(f"예상 차감: {plan['estimated_cost']} 크레딧")
    print(f"Wan 3.0 으로 만들 경우: {plan['wan_equivalent_cost']} (절감 {plan['saving_vs_wan']})")

    clamped = [s for s in plan["steps"] if s["clamped"]]
    if clamped:
        print(f"길이 조정 {len(clamped)}건:")
        for s in clamped:
            print(f"  - {s['key']}: {s['requested_duration']}초 -> {s['duration']}초")

    print()
    report_duplicates(scenes)
    print()
    print("승인하시면 /generate-video 로 제출합니다. 승인 전에는 크레딧이 차감되지 않습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
