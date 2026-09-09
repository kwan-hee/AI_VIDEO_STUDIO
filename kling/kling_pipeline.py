# Kling 3.0 단일 엔진 전용 영상 파이프라인. 장면 목록을 받아 비용을 산출하고 실행 페이로드를 만든다.
"""
Kling-Only Pipeline (Sprint 12)

입력: 장면 목록 (scene dict 리스트).
      키: key, prompt, duration, start_image, end_image

책임.
  1. 영상 엔진을 Kling 3.0 하나로 고정한다. 다른 엔진은 거부한다.
  2. 제출 전에 크레딧 비용을 산출한다.
  3. 길이 상한과 예산 상한을 강제한다.
  4. 중복 장면을 탐지해 경고한다.
  5. 구조화 dict 만 반환한다. 외부 API 호출 없음.

단가 근거.
  Higgsfield 거래 내역과 생성 이력을 초 단위로 대조해 확인한 실측값이다.
    Kling v3.0 : 5초 -> 6.25 / 6초 -> 7.50 / 7초 -> 8.75  => 초당 1.25
    Wan 3.0    : 5초 -> 8.75 / 6초 -> 10.50 / 7초 -> 12.25 => 초당 1.75
  같은 길이에서 Kling 이 28.6% 저렴하다.

출력 스키마: schemas/kling_plan_schema.json
Sprint 1~5 파일은 수정하지 않는다.
"""

import re

# --- 고정 상수. 이 파이프라인은 Kling 3.0 외 엔진을 쓰지 않는다. ---

ENGINE = "kling3_0"
ENGINE_LABEL = "Kling v3.0"
CREDITS_PER_SECOND = 1.25

# 비교용. 정책 문서와 보고서에서 절감액을 계산할 때 쓴다.
WAN_CREDITS_PER_SECOND = 1.75

# 길이 정책. 숏폼 정지형 컷은 4초면 충분하고, 7초를 넘기면 초당 과금이 낭비로 돌아온다.
MIN_DURATION = 3
MAX_DURATION = 7
DEFAULT_DURATION = 5
STATIC_SHOT_DURATION = 4

ASPECT_RATIO = "9:16"
RESOLUTION = "720p"

# 중복 판정 임계값. 자카드 유사도가 이 값 이상이면 같은 정보를 두 번 전달한다고 본다.
DUPLICATE_THRESHOLD = 0.60

# 모든 프롬프트에 공통으로 들어가는 지시문. 유사도 계산에서 제외해야 실제 내용이 비교된다.
_BOILERPLATE = {
    "single", "continuous", "shot", "take", "no", "cuts", "cut", "camera", "locked",
    "off", "static", "absolutely", "movement", "zoom", "pan", "tilt", "shake", "dolly",
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "with", "into", "from",
    "is", "are", "its", "it", "that", "then", "only", "after", "while", "very", "slowly",
    "slow", "constant", "speed", "degrees", "about", "first", "frame", "end", "start",
    "image", "same", "graphics", "draw", "drawn", "overlay", "text", "letters", "logos",
    "watermark", "watermarks", "extra", "flare", "lens", "snap", "identical", "throughout",
    "stays", "stay", "perfectly", "still", "one", "two", "three", "motion", "moves", "move",
}


class KlingPipelineError(ValueError):
    """장면 정의나 예산 규칙을 어겼을 때 발생한다."""


# --- 길이와 비용 ---

def normalize_duration(seconds):
    """길이를 정책 범위 안으로 조정한다. 범위를 벗어나면 잘라 낸다."""
    if seconds is None:
        return DEFAULT_DURATION
    if not isinstance(seconds, int) or isinstance(seconds, bool):
        raise KlingPipelineError("duration 은 정수 초여야 한다.")
    return max(MIN_DURATION, min(MAX_DURATION, seconds))


def scene_cost(seconds):
    """장면 하나의 크레딧 비용."""
    return round(normalize_duration(seconds) * CREDITS_PER_SECOND, 2)


def wan_equivalent_cost(seconds):
    """같은 장면을 Wan 3.0 으로 만들었을 때의 비용. 절감액 보고용."""
    return round(normalize_duration(seconds) * WAN_CREDITS_PER_SECOND, 2)


# --- 중복 탐지 ---

def _content_tokens(prompt):
    """프롬프트에서 공통 지시문을 걷어내고 내용어만 남긴다."""
    words = re.findall(r"[a-z]+", (prompt or "").lower())
    return {w for w in words if len(w) > 2 and w not in _BOILERPLATE}


def _similarity(a, b):
    """두 토큰 집합의 자카드 유사도."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_duplicates(scenes, threshold=DUPLICATE_THRESHOLD):
    """
    같은 정보를 두 번 전달하는 장면 쌍을 찾는다.
    제거하지는 않는다. 판단은 사람이 한다.
    """
    tokens = [_content_tokens(s.get("prompt")) for s in scenes]
    found = []
    for i in range(len(scenes)):
        for j in range(i + 1, len(scenes)):
            score = _similarity(tokens[i], tokens[j])
            if score >= threshold:
                found.append({
                    "left": scenes[i].get("key", f"scene_{i}"),
                    "right": scenes[j].get("key", f"scene_{j}"),
                    "similarity": round(score, 3),
                    "refundable": scene_cost(scenes[j].get("duration")),
                })
    return found


# --- 검증 ---

def validate_scenes(scenes):
    """장면 목록의 구조를 검증한다. 엔진 지정이 섞여 있으면 거부한다."""
    if not isinstance(scenes, list) or not scenes:
        raise KlingPipelineError("scenes 는 비어 있지 않은 리스트여야 한다.")

    seen = set()
    for idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise KlingPipelineError(f"{idx}번 장면이 dict 가 아니다.")

        key = scene.get("key")
        if not key or not isinstance(key, str):
            raise KlingPipelineError(f"{idx}번 장면에 key 가 없다.")
        if key in seen:
            raise KlingPipelineError(f"장면 key 가 중복된다: {key}")
        seen.add(key)

        prompt = scene.get("prompt")
        if not prompt or not isinstance(prompt, str):
            raise KlingPipelineError(f"장면 {key} 에 prompt 가 없다.")

        # 이 파이프라인은 엔진을 고르지 않는다. 다른 엔진을 지정하면 즉시 막는다.
        engine = scene.get("engine")
        if engine is not None and engine != ENGINE:
            raise KlingPipelineError(
                f"장면 {key} 가 {engine} 을 요구한다. 이 파이프라인은 {ENGINE} 만 쓴다."
            )

        normalize_duration(scene.get("duration"))

    return True


# --- 계획 수립 ---

def build_plan(project, scenes, budget=None):
    """
    장면 목록 -> 실행 계획.
    비용을 먼저 계산하고, 예산을 넘으면 계획 자체를 만들지 않는다.
    """
    validate_scenes(scenes)

    steps = []
    total = 0.0
    total_seconds = 0
    wan_total = 0.0

    for order, scene in enumerate(scenes, start=1):
        duration = normalize_duration(scene.get("duration"))
        cost = scene_cost(duration)
        total += cost
        total_seconds += duration
        wan_total += wan_equivalent_cost(duration)

        steps.append({
            "order": order,
            "key": scene["key"],
            "engine": ENGINE,
            "duration": duration,
            "requested_duration": scene.get("duration"),
            "clamped": scene.get("duration") not in (None, duration),
            "cost": cost,
            "start_image": scene.get("start_image"),
            "end_image": scene.get("end_image"),
            "prompt": scene["prompt"],
        })

    total = round(total, 2)
    wan_total = round(wan_total, 2)

    if budget is not None and total > budget:
        raise KlingPipelineError(
            f"예상 비용 {total} 크레딧이 예산 {budget} 크레딧을 넘는다. "
            f"장면을 줄이거나 길이를 낮춰야 한다."
        )

    return {
        "project": project,
        "engine": ENGINE,
        "engine_label": ENGINE_LABEL,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "scene_count": len(steps),
        "total_seconds": total_seconds,
        "estimated_cost": total,
        "wan_equivalent_cost": wan_total,
        "saving_vs_wan": round(wan_total - total, 2),
        "budget": budget,
        "duplicates": find_duplicates(scenes),
        "steps": steps,
    }


def build_payloads(plan):
    """
    실행 계획 -> Higgsfield generate_video 인자 목록.
    준비만 한다. 호출하지 않는다.
    """
    if not isinstance(plan, dict) or "steps" not in plan:
        raise KlingPipelineError("plan 은 steps 를 가진 dict 여야 한다.")

    payloads = []
    for step in plan["steps"]:
        medias = []
        if step.get("start_image"):
            medias.append({"role": "start_image", "value": step["start_image"]})
        if step.get("end_image"):
            medias.append({"role": "end_image", "value": step["end_image"]})

        params = {
            "model": ENGINE,
            "prompt": step["prompt"],
            "duration": step["duration"],
            "aspect_ratio": ASPECT_RATIO,
        }
        if medias:
            params["medias"] = medias

        payloads.append({"index": step["order"], "key": step["key"], "params": params})

    return payloads


def format_report(plan):
    """사람이 읽을 비용 보고서. 제출 전 확인용."""
    lines = [
        f"프로젝트: {plan['project']}",
        f"엔진: {plan['engine_label']} (초당 {CREDITS_PER_SECOND} 크레딧 고정)",
        f"장면 {plan['scene_count']}개 / 총 {plan['total_seconds']}초",
        f"예상 차감: {plan['estimated_cost']} 크레딧",
        f"Wan 3.0 으로 만들 경우: {plan['wan_equivalent_cost']} 크레딧 "
        f"(절감 {plan['saving_vs_wan']})",
    ]
    clamped = [s for s in plan["steps"] if s["clamped"]]
    if clamped:
        lines.append(f"길이 조정된 장면 {len(clamped)}개:")
        for s in clamped:
            lines.append(f"  - {s['key']}: {s['requested_duration']}초 -> {s['duration']}초")
    if plan["duplicates"]:
        lines.append(f"중복 의심 {len(plan['duplicates'])}쌍:")
        for d in plan["duplicates"]:
            lines.append(
                f"  - {d['left']} vs {d['right']} (유사도 {d['similarity']}, "
                f"제거 시 {d['refundable']} 크레딧 절약)"
            )
    else:
        lines.append("중복 의심 장면 없음.")
    return "\n".join(lines)
