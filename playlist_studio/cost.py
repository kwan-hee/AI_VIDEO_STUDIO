"""크레딧 견적.

여기 담긴 카탈로그는 Abocado MCP `abocado_music` / `abocado_list_models` 응답을
그대로 옮겨 적은 **스냅샷**이다. 단가는 바뀔 수 있으므로, 실제 승인 화면을
띄우기 전에 스킬이 반드시 MCP 로 재조회해 `--unit-credits` 로 덮어써야 한다.
이 파일 값만 믿고 결제하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SNAPSHOT_TAKEN_AT = "2026-09-01"
SNAPSHOT_SOURCE = "MCP abocado_music (mode=music)"

MUSIC_MODELS: dict[str, dict[str, Any]] = {
    "se-music-v26-t2a": {
        "display": "Popcorn 2.0 Pro", "credits": 240, "lyrics_mode": "manual",
        "prompt_min": 10, "prompt_max": 2000, "lyrics_max": 3500,
        "lyrics_field": "lyrics",
        "structure_tags": ["Intro", "Verse", "Pre Chorus", "Chorus", "Post Chorus",
                           "Bridge", "Outro", "Interlude", "Hook", "Break", "Solo",
                           "Inst", "Transition", "Build Up"],
        "note": "가사 필수(비인스트루멘탈). 구조 태그 14종으로 편곡 제어.",
    },
    "se-music-v25-t2a": {
        "display": "Popcorn 2.0", "credits": 240, "lyrics_mode": "auto_or_manual",
        "prompt_min": 1, "prompt_max": 2000, "lyrics_max": 3500,
        "lyrics_field": "lyrics",
        "structure_tags": ["Intro", "Verse", "Pre Chorus", "Chorus", "Bridge",
                           "Outro", "Interlude", "Hook", "Break", "Solo", "Inst"],
        "note": "가사를 주지 않으면 자동 생성되지만 결과로 회수할 수 없다. 이 프로젝트는 항상 가사를 직접 준다.",
    },
    "se-motion-music-t2a": {
        "display": "Popcorn 1.0", "credits": 48, "lyrics_mode": "manual",
        "prompt_min": 10, "prompt_max": 300, "lyrics_max": 3000,
        "lyrics_field": "lyrics_prompt",
        "structure_tags": ["Intro", "Verse", "Chorus", "Bridge", "Outro"],
        "note": "prompt 가 300자 제한이라 DNA 를 압축해서 넣는다. 최저가.",
    },
    "se-lyria3-pro-t2a": {
        "display": "Lyria 3 Pro", "credits": 128, "lyrics_mode": "prompt_merged",
        "prompt_min": 1, "prompt_max": 2000, "lyrics_max": 0,
        "lyrics_field": None,
        "structure_tags": [],
        "note": "가사 필드가 없다. prompt 안에 'Lyrics:' 섹션으로 병합하며 합계 2000자.",
    },
    "se-lyria3-t2a": {
        "display": "Lyria 3", "credits": 64, "lyrics_mode": "prompt_merged",
        "prompt_min": 1, "prompt_max": 2000, "lyrics_max": 0,
        "lyrics_field": None,
        "structure_tags": [],
        "note": "가사 필드가 없다. prompt 안에 'Lyrics:' 섹션으로 병합하며 합계 2000자.",
    },
}

DEFAULT_MUSIC_MODEL = "se-music-v26-t2a"
DEFAULT_IMAGE_MODEL = "se-gpt-image-2-t2i"


class UnknownModel(ValueError):
    pass


def model_spec(key: str) -> dict[str, Any]:
    spec = MUSIC_MODELS.get(key)
    if spec is None:
        raise UnknownModel(
            f"모르는 뮤직 모델: {key}. 사용 가능: {', '.join(MUSIC_MODELS)} "
            f"(최신 목록은 MCP abocado_music 으로 확인)"
        )
    return spec


@dataclass
class Estimate:
    model: str
    display: str
    unit_credits: int
    track_count: int
    already_done: int
    to_generate: int
    total_credits: int
    balance: int | None
    shortfall: int
    source: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    def table(self) -> str:
        lines = [
            "| 항목 | 값 |",
            "|---|---|",
            f"| 모델 | {self.display} (`{self.model}`) |",
            f"| 곡당 크레딧 | {self.unit_credits} cr |",
            f"| 계획 곡 수 | {self.track_count} 곡 |",
            f"| 이미 생성됨 | {self.already_done} 곡 (재생성 안 함) |",
            f"| **이번에 생성할 곡** | **{self.to_generate} 곡** |",
            f"| **총 예상 크레딧** | **{self.total_credits} cr** |",
        ]
        if self.balance is None:
            lines.append("| 현재 잔액 | 조회 안 됨 — 승인 전에 MCP `abocado_get_credits` 로 반드시 확인 |")
        else:
            lines.append(f"| 현재 잔액 | {self.balance} cr |")
            if self.shortfall > 0:
                lines.append(f"| **부족액** | **{self.shortfall} cr 부족** |")
            else:
                lines.append(f"| 생성 후 잔액 | {self.balance - self.total_credits} cr |")
        lines.append(f"| 단가 출처 | {self.source} |")
        return "\n".join(lines)


def estimate(model: str, track_count: int, *, already_done: int = 0,
             balance: int | None = None, unit_credits: int | None = None) -> Estimate:
    spec = model_spec(model)
    unit = int(unit_credits) if unit_credits is not None else int(spec["credits"])
    source = ("사용자/스킬이 MCP 조회값으로 지정"
              if unit_credits is not None
              else f"코드 내 스냅샷 ({SNAPSHOT_TAKEN_AT}, {SNAPSHOT_SOURCE}) — 승인 전 재조회 필요")
    to_gen = max(0, int(track_count) - int(already_done))
    total = to_gen * unit
    shortfall = max(0, total - balance) if balance is not None else 0
    return Estimate(
        model=model, display=spec["display"], unit_credits=unit,
        track_count=int(track_count), already_done=int(already_done),
        to_generate=to_gen, total_credits=total, balance=balance,
        shortfall=shortfall, source=source,
    )
