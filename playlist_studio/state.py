"""workspace.json - 상태 머신 + 산출물 레지스트리.

핵심 규칙
  1. 상태는 단계가 *성공한 뒤에만* 전진한다.
  2. 산출물은 sha256 과 함께 등록된다. 다시 실행하면 해시를 재검증해
     정상인 것은 재사용하고, 없거나 손상된 것만 다시 만든다.
  3. 상태 전이는 history 에 append-only 로 남는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .paths import ProjectPaths
from .util import now_iso, read_json, rel_posix, sha256_file, write_json

SCHEMA_VERSION = 1

# 순서가 곧 진행도. 앞의 상태는 뒤 상태의 전제조건이다.
STATES: tuple[str, ...] = (
    "INIT",
    "CHANNEL_READY",
    "PLAN_READY",
    "LYRICS_READY",
    "PILOT_READY",
    "PILOT_APPROVED",
    "BATCH_GENERATED",
    "VISUALS_READY",
    "ALIGNED",
    "METADATA_READY",
    "RENDERED",
    "VERIFIED",
)

STATE_INDEX = {s: i for i, s in enumerate(STATES)}

# 9단계 <-> 상태 매핑 (playlist-studio 스킬이 표시하는 진행표)
STEPS: tuple[dict[str, Any], ...] = (
    {"n": 1, "key": "channel",   "title": "채널 만들기",                    "reaches": "CHANNEL_READY"},
    {"n": 2, "key": "plan",      "title": "플레이리스트 설정",              "reaches": "PLAN_READY"},
    {"n": 3, "key": "lyrics",    "title": "전체 가사 작성",                 "reaches": "LYRICS_READY"},
    {"n": 4, "key": "pilot",     "title": "파일럿 첫 곡 생성 및 승인",      "reaches": "PILOT_APPROVED"},
    {"n": 5, "key": "batch",     "title": "나머지 곡 생성",                 "reaches": "BATCH_GENERATED"},
    {"n": 6, "key": "visuals",   "title": "썸네일 · 곡별 배경 이미지",      "reaches": "VISUALS_READY"},
    {"n": 7, "key": "align",     "title": "음원 병합 · 가사 타이밍 정렬",   "reaches": "ALIGNED"},
    {"n": 8, "key": "metadata",  "title": "인트로 · 제목 · 설명 · 챕터",    "reaches": "METADATA_READY"},
    {"n": 9, "key": "render",    "title": "최종 렌더링 및 QA",              "reaches": "VERIFIED"},
)

STEP_BY_KEY = {s["key"]: s for s in STEPS}


class StateError(RuntimeError):
    pass


def _blank(project_id: str, channel: dict | None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "channel": channel or {},
        "state": "INIT",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "history": [{"state": "INIT", "at": now_iso(), "note": "workspace 생성"}],
        "steps": {s["key"]: {"status": "pending", "at": None, "note": "", "error": ""} for s in STEPS},
        "artifacts": {},
        "flags": {},
    }


@dataclass
class Workspace:
    paths: ProjectPaths
    data: dict

    # ---------------- 생성 / 로드 ----------------
    @classmethod
    def create(cls, paths: ProjectPaths, project_id: str, channel: dict | None = None) -> "Workspace":
        paths.mkdirs()
        ws = cls(paths, _blank(project_id, channel))
        ws.save()
        return ws

    @classmethod
    def load(cls, paths: ProjectPaths) -> "Workspace":
        data = read_json(paths.workspace)
        if data is None:
            raise FileNotFoundError(f"workspace.json 이 없습니다: {paths.workspace}")
        # 구버전 보정
        data.setdefault("steps", {})
        for s in STEPS:
            data["steps"].setdefault(s["key"], {"status": "pending", "at": None, "note": "", "error": ""})
        data.setdefault("artifacts", {})
        data.setdefault("flags", {})
        data.setdefault("history", [])
        return cls(paths, data)

    @classmethod
    def load_or_create(cls, paths: ProjectPaths, project_id: str, channel: dict | None = None) -> "Workspace":
        try:
            return cls.load(paths)
        except FileNotFoundError:
            return cls.create(paths, project_id, channel)

    def save(self) -> None:
        self.data["updated_at"] = now_iso()
        write_json(self.paths.workspace, self.data)

    # ---------------- 상태 ----------------
    @property
    def state(self) -> str:
        return self.data.get("state", "INIT")

    def rank(self, state: str | None = None) -> int:
        return STATE_INDEX[state or self.state]

    def at_least(self, state: str) -> bool:
        return self.rank() >= STATE_INDEX[state]

    def require(self, state: str, what: str = "") -> None:
        if not self.at_least(state):
            raise StateError(
                f"선행 상태가 부족합니다. 필요: {state} / 현재: {self.state}"
                + (f" ({what})" if what else "")
            )

    def advance(self, state: str, note: str = "") -> None:
        """단계 성공 후에만 호출. 뒤로 가지 않는다(이미 더 진행됐으면 유지)."""
        if state not in STATE_INDEX:
            raise StateError(f"알 수 없는 상태: {state}")
        if STATE_INDEX[state] > self.rank():
            self.data["state"] = state
            self.data["history"].append({"state": state, "at": now_iso(), "note": note})
        self.save()

    def reset_to(self, state: str, note: str = "") -> None:
        """되돌리기(예: 파일럿 재생성). 명시 호출 전용."""
        if state not in STATE_INDEX:
            raise StateError(f"알 수 없는 상태: {state}")
        self.data["state"] = state
        self.data["history"].append({"state": state, "at": now_iso(), "note": f"reset: {note}"})
        target = STATE_INDEX[state]
        for s in STEPS:
            if STATE_INDEX[s["reaches"]] > target:
                self.data["steps"][s["key"]] = {"status": "pending", "at": None, "note": "", "error": ""}
        self.save()

    # ---------------- 단계 ----------------
    def step_start(self, key: str, note: str = "") -> None:
        self.data["steps"][key] = {"status": "running", "at": now_iso(), "note": note, "error": ""}
        self.save()

    def step_done(self, key: str, note: str = "") -> None:
        self.data["steps"][key] = {"status": "done", "at": now_iso(), "note": note, "error": ""}
        self.save()

    def step_failed(self, key: str, error: str) -> None:
        prev = self.data["steps"].get(key, {})
        self.data["steps"][key] = {
            "status": "failed", "at": now_iso(),
            "note": prev.get("note", ""), "error": str(error)[:2000],
        }
        self.save()

    def step_status(self, key: str) -> str:
        return self.data["steps"].get(key, {}).get("status", "pending")

    def first_incomplete_step(self) -> dict | None:
        for s in STEPS:
            if self.step_status(s["key"]) != "done":
                return s
        return None

    # ---------------- 산출물 ----------------
    def register(self, path: Path, *, kind: str = "file", meta: dict | None = None) -> dict:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"등록할 산출물이 없습니다: {path}")
        key = rel_posix(path, self.paths.root)
        rec = {
            "kind": kind,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "registered_at": now_iso(),
        }
        if meta:
            rec["meta"] = meta
        self.data["artifacts"][key] = rec
        self.save()
        return rec

    def register_many(self, paths: Iterable[Path], *, kind: str = "file") -> list[dict]:
        out = [self.register(p, kind=kind) for p in paths]
        return out

    def artifact(self, path: Path) -> dict | None:
        return self.data["artifacts"].get(rel_posix(Path(path), self.paths.root))

    def verify_artifact(self, path: Path) -> tuple[bool, str]:
        """(정상여부, 사유)"""
        path = Path(path)
        rec = self.artifact(path)
        if rec is None:
            return False, "미등록"
        if not path.exists():
            return False, "파일 없음"
        if path.stat().st_size != rec.get("bytes"):
            return False, "크기 불일치"
        if sha256_file(path) != rec.get("sha256"):
            return False, "해시 불일치"
        return True, "ok"

    def verify_all(self) -> dict:
        ok, bad = [], []
        for key in sorted(self.data["artifacts"]):
            p = self.paths.root / key
            good, why = self.verify_artifact(p)
            (ok if good else bad).append({"path": key, "reason": why})
        return {"ok": ok, "broken": bad, "total": len(ok) + len(bad)}

    def drop_artifact(self, path: Path) -> None:
        self.data["artifacts"].pop(rel_posix(Path(path), self.paths.root), None)
        self.save()

    def reusable(self, path: Path) -> bool:
        """재실행 시 이 산출물을 그대로 쓸 수 있는가."""
        return self.verify_artifact(path)[0]

    # ---------------- 플래그 ----------------
    def flag(self, name: str, default: Any = None) -> Any:
        return self.data["flags"].get(name, default)

    def set_flag(self, name: str, value: Any) -> None:
        self.data["flags"][name] = value
        self.save()
