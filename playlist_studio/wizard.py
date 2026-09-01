"""설정 마법사 - playlist.yaml.

한 번에 많이 묻지 않기 위해 질문을 순서가 있는 목록으로 정의하고,
`next_questions()` 가 *아직 답하지 않은* 것만 앞에서부터 돌려준다.
Claude(스킬)는 이 목록을 받아 한 번에 1~2개씩 사용자에게 묻는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

from .util import ensure_dir, read_text


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    kind: str                      # choice | multi | int | text | range
    choices: tuple[str, ...] = ()
    hint: str = ""
    default: Any = None
    depends_on: str | None = None  # 이 키가 특정 값일 때만 묻는다
    depends_value: Any = None


# 사양이 정한 순서 그대로.
QUESTIONS: tuple[Question, ...] = (
    Question("channel", "채널", "text",
             hint="기존 채널 slug 또는 새 채널 이름"),
    Question("genre", "장르", "choice",
             choices=("lofi", "jazz", "citypop", "ballad", "ambient", "acoustic",
                      "rnb", "synthwave", "classical-crossover", "worship"),
             hint="플레이리스트 전체를 관통하는 큰 장르"),
    Question("subgenre", "세부 장르", "text",
             hint="예: lofi -> jazzy lofi / chillhop / tape-warm lofi"),
    Question("purpose", "플레이리스트 목적", "choice",
             choices=("집중", "휴식", "수면", "감성몰입", "드라이브", "카페BGM", "운동"),
             hint="청취자가 얻어갈 결과"),
    Question("situation", "청취 상황", "choice",
             choices=("공부", "야근", "새벽운전", "비오는날", "가을저녁",
                      "카페", "취침전", "산책"),
             hint="구체적 장면 - 썸네일/설명문에도 재사용된다"),
    Question("vocal_mode", "보컬 또는 연주곡", "choice",
             choices=("vocal", "instrumental", "mixed"),
             default="vocal"),
    Question("lyrics_language", "가사 언어", "choice",
             choices=("ko", "en", "ja", "ko+en"), default="ko",
             depends_on="vocal_mode", depends_value=("vocal", "mixed")),
    Question("subtitle_language", "자막 언어", "choice",
             choices=("ko", "en", "ja", "ko+en"), default="ko",
             hint="가사 언어와 다르게 둘 수 있다"),
    Question("track_count", "곡 수", "int", default=8,
             hint="권장 6~12. 곡 수 x 단가 = 총 크레딧"),
    Question("track_seconds", "곡별 목표 길이(초)", "int", default=180,
             hint="모델이 정확히 맞춰주지는 않는다. 목표값"),
    Question("total_seconds", "전체 목표 길이(초)", "int", default=1440,
             hint="곡 수 x 곡 길이와 크게 어긋나면 경고한다"),
    Question("bpm_min", "BPM 하한", "int", default=70),
    Question("bpm_max", "BPM 상한", "int", default=90),
    Question("mood_arc", "전체 정서 변화", "choice",
             choices=("calm-to-warm", "warm-to-calm", "flat-calm",
                      "melancholy-to-hope", "night-deepening"),
             default="calm-to-warm",
             hint="곡 순서대로 감정을 어떻게 끌고 갈지"),
    Question("visual_preset", "비주얼 프리셋", "choice",
             choices=("black-gray-red", "warm-film", "cold-neon", "paper-grain"),
             default="black-gray-red"),
    Question("thumbnail_language", "썸네일 언어", "choice",
             choices=("ko", "en", "ko+en"), default="ko"),
    Question("thumbnail_concept", "썸네일 콘셉트", "choice",
             choices=("A", "B", "C", "D"),
             hint="후보 4개를 생성한 뒤 고른다. 이 값은 6단계에서 확정"),
)

QUESTION_BY_KEY = {q.key: q for q in QUESTIONS}

# 마법사 밖에서 채워지는 파생/운영 키 (미응답으로 세지 않는다)
DERIVED_KEYS = {
    "playlist_title", "playlist_slug", "channel_slug", "music_model",
    "image_model", "created_at", "notes",
}


def _applicable(q: Question, answers: dict) -> bool:
    if q.depends_on is None:
        return True
    val = answers.get(q.depends_on)
    if val is None:
        return False  # 선행 질문을 아직 안 했으면 이 질문도 아직 아님
    want = q.depends_value
    if isinstance(want, (tuple, list, set)):
        return val in want
    return val == want


def load_config(path: Path) -> dict:
    raw = read_text(path)
    if raw is None:
        return {}
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(f"playlist.yaml 형식이 잘못되었습니다: {path}")
    return data


def save_config(path: Path, data: dict) -> Path:
    ensure_dir(Path(path).parent)
    ordered: dict[str, Any] = {}
    for q in QUESTIONS:              # 질문 순서대로 정렬해 사람이 읽기 쉽게
        if q.key in data:
            ordered[q.key] = data[q.key]
    for k in sorted(data):
        if k not in ordered:
            ordered[k] = data[k]
    text = yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False, default_flow_style=False)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    return Path(path)


def missing_questions(answers: dict) -> list[Question]:
    out = []
    for q in QUESTIONS:
        if not _applicable(q, answers):
            continue
        if answers.get(q.key) in (None, ""):
            out.append(q)
    return out


def next_questions(answers: dict, limit: int = 2) -> list[Question]:
    """아직 답하지 않은 질문을 순서대로 최대 limit 개."""
    return missing_questions(answers)[:limit]


def coerce(key: str, value: Any) -> Any:
    q = QUESTION_BY_KEY.get(key)
    if q is None:
        return value
    if q.kind == "int":
        return int(str(value).strip())
    if q.kind == "choice":
        v = str(value).strip()
        if q.choices and v not in q.choices:
            raise ValueError(f"{key} 허용값: {', '.join(q.choices)} (받은 값: {v})")
        return v
    return str(value).strip()


def validate(answers: dict) -> list[str]:
    """치명적이지 않은 경고 목록. 빈 리스트면 문제 없음."""
    warn: list[str] = []
    tc = answers.get("track_count")
    ts = answers.get("track_seconds")
    tot = answers.get("total_seconds")
    if tc and ts and tot:
        est = int(tc) * int(ts)
        if abs(est - int(tot)) > max(120, int(tot) * 0.25):
            warn.append(
                f"곡 수 x 곡 길이 = {est}초 인데 전체 목표는 {tot}초 입니다. "
                f"({abs(est - int(tot))}초 차이) 곡 수나 길이를 조정하세요."
            )
    lo, hi = answers.get("bpm_min"), answers.get("bpm_max")
    if lo and hi and int(lo) > int(hi):
        warn.append(f"BPM 하한({lo})이 상한({hi})보다 큽니다.")
    if answers.get("vocal_mode") == "instrumental" and answers.get("lyrics_language"):
        warn.append("연주곡인데 가사 언어가 설정되어 있습니다. 가사는 자막용으로만 쓰입니다.")
    if tc and int(tc) > 20:
        warn.append(f"곡 수 {tc} 는 크레딧 소모가 큽니다. 승인 화면에서 총액을 반드시 확인하세요.")
    return warn


def summary_table(answers: dict) -> str:
    rows = ["| 항목 | 값 |", "|---|---|"]
    for q in QUESTIONS:
        if not _applicable(q, answers):
            continue
        v = answers.get(q.key)
        rows.append(f"| {q.label} | {'—' if v in (None, '') else v} |")
    return "\n".join(rows)
