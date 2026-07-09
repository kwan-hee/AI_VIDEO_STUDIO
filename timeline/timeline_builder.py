# 실행 계획과 등록된 에셋으로 미디어 타임라인만 구성하는 Timeline Builder (FFmpeg/외부호출 없음)
"""
Timeline Builder (Sprint 12)

입력.
  - execution_plan: Execution Planner 출력 {project, steps:[{order, step, ...}]}
  - assets: Asset Manager 출력 리스트 [{asset_id, type, ...}, ...]

책임.
  - 타임라인만 구성한다. FFmpeg 실행 없음. 외부 API 없음. 미디어 생성 없음.
  - 각 타임라인 항목: asset_id, asset_type, start_time, end_time, duration, layer.

레이어.
  - visual : image, video (한 트랙에 순차 배치)
  - audio  : audio (별도 트랙, 0초부터 순차)
  - story / thumbnail 은 타임라인 대상이 아니다(제외).

배치 규칙.
  - 각 레이어는 0초에서 시작, 항목을 순차로 이어 붙인다(start = 직전 항목 end).
  - 시각 항목 순서: 실행 계획의 step 순서 → 그 안에서는 등록 순서.
  - duration 은 실측하지 않는다(미디어 미접근). durations 로 지정, 없으면 타입별 기본값.

출력 스키마: schemas/timeline_schema.json
Sprint 1~11 파일은 수정하지 않는다.
"""

# 타임라인에 올라가는 에셋 타입만
TIMELINE_TYPES = {"image", "video", "audio"}

# 에셋 타입 → 레이어
LAYER_OF = {"image": "visual", "video": "visual", "audio": "audio"}

# 배치 순서 고정: visual 먼저, audio 다음
LAYERS = ("visual", "audio")

# 타입별 기본 재생 길이(초). 실측 아님, 지정 없을 때의 placeholder.
DEFAULT_DURATIONS = {"image": 5.0, "video": 10.0, "audio": 8.0}

# 에셋 타입 → 실행 계획 step 이름 (audio 는 계획상 voice 단계)
_TYPE_TO_STEP = {"image": "image", "video": "video", "audio": "voice"}


def _validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("execution_plan 은 dict 여야 한다.")
    for k in ("project", "steps"):
        if k not in plan:
            raise ValueError(f"execution_plan 에 {k} 가 필요하다.")
    if not isinstance(plan["steps"], list):
        raise ValueError("execution_plan.steps 는 list 여야 한다.")


def _validate_assets(assets):
    if not isinstance(assets, list):
        raise ValueError("assets 는 list 여야 한다.")
    for a in assets:
        if not isinstance(a, dict) or "asset_id" not in a or "type" not in a:
            raise ValueError("각 asset 은 asset_id 와 type 을 가진 dict 여야 한다.")


def _duration_for(asset, durations):
    asset_id = asset["asset_id"]
    if asset_id in durations:
        d = durations[asset_id]
    else:
        d = DEFAULT_DURATIONS[asset["type"]]
    if isinstance(d, bool) or not isinstance(d, (int, float)) or d <= 0:
        raise ValueError(f"duration 은 양수여야 한다: {asset_id}={d!r}")
    return float(d)


def build_timeline(execution_plan, assets, durations=None):
    """
    실행 계획 + 등록 에셋 → 미디어 타임라인.
    배치만 한다. 실행/호출/미디어 없음. 입력을 변형하지 않는다.
    """
    _validate_plan(execution_plan)
    _validate_assets(assets)
    durations = durations or {}

    # 계획 step → 최초 order (같은 step 이 여러 번이면 첫 등장 순서 사용)
    step_order = {}
    for s in execution_plan["steps"]:
        step_order.setdefault(s.get("step"), s.get("order"))
    _fallback = len(step_order) + 1

    # 타임라인 대상 에셋만 뽑고 (계획순서, 등록순서) 키를 붙인다
    items = []
    for reg_idx, a in enumerate(assets):
        if a["type"] not in TIMELINE_TYPES:
            continue
        plan_idx = step_order.get(_TYPE_TO_STEP[a["type"]], _fallback)
        items.append((plan_idx, reg_idx, a))

    # 레이어별로 나눠 0초부터 순차 배치
    entries = []
    for layer in LAYERS:
        layer_items = [it for it in items if LAYER_OF[it[2]["type"]] == layer]
        layer_items.sort(key=lambda it: (it[0], it[1]))
        cursor = 0.0
        for _plan_idx, _reg_idx, a in layer_items:
            dur = _duration_for(a, durations)
            start = round(cursor, 3)
            end = round(cursor + dur, 3)
            entries.append({
                "asset_id": a["asset_id"],
                "asset_type": a["type"],
                "start_time": start,
                "end_time": end,
                "duration": round(dur, 3),
                "layer": layer,
            })
            cursor = end

    total = round(max((e["end_time"] for e in entries), default=0.0), 3)
    return {
        "project": execution_plan["project"],
        "entries": entries,
        "total_duration": total,
    }


if __name__ == "__main__":
    import json
    import os
    import sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(_ROOT, "planner"))
    sys.path.insert(0, os.path.join(_ROOT, "assets"))
    from asset_manager import AssetManager

    plan = {
        "project": "malli",
        "steps": [
            {"order": 1, "step": "story"},
            {"order": 2, "step": "image"},
            {"order": 3, "step": "video"},
            {"order": 4, "step": "voice"},
        ],
    }
    mgr = AssetManager()
    mgr.register("image", "Nano Banana", "output/image/01.png")
    mgr.register("video", "Higgsfield", "output/video/02.mp4")
    mgr.register("audio", "Edge TTS", "output/audio/03.mp3")
    print(json.dumps(build_timeline(plan, mgr.list_assets()), ensure_ascii=False, indent=2))
