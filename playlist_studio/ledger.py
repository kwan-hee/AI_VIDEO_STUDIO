"""생성 원장 - 같은 프롬프트로 크레딧을 두 번 쓰지 않기 위한 잠금장치.

제출 직전에 `claim()` 을 호출한다. 같은 fingerprint(모델+프롬프트+가사)가
이미 원장에 있으면 BLOCK 을 돌려주고, 스킬은 제출을 중단한다.
실패한 작업은 `release()` 로 풀어야 재시도할 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .util import now_iso, read_json, sha256_text, write_json


def fingerprint(model: str, prompt: str, lyrics: str = "", options: dict | None = None) -> str:
    from .util import normalize_lyrics
    payload = "\n---\n".join([
        f"model={model}",
        f"prompt={normalize_lyrics(prompt)}",
        f"lyrics={normalize_lyrics(lyrics or '')}",
        f"options={sorted((options or {}).items())}",
    ])
    return sha256_text(payload)


@dataclass
class Ledger:
    path: Path
    data: dict

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        data = read_json(path, None)
        if data is None:
            data = {"schema_version": 1, "entries": {}}
        data.setdefault("entries", {})
        return cls(Path(path), data)

    def save(self) -> None:
        write_json(self.path, self.data)

    def get(self, fp: str) -> dict | None:
        return self.data["entries"].get(fp)

    def claim(self, fp: str, *, track_index: int, model: str, credits: int,
              note: str = "") -> tuple[bool, dict]:
        """(제출해도 되는가, 기존/신규 레코드).

        False 면 이미 이 프롬프트로 크레딧을 쓴 적이 있다는 뜻이다.
        """
        existing = self.get(fp)
        if existing and existing.get("status") in ("claimed", "done"):
            return False, existing
        rec = {
            "fingerprint": fp,
            "track_index": track_index,
            "model": model,
            "credits": credits,
            "status": "claimed",
            "provider_job_id": None,
            "claimed_at": now_iso(),
            "completed_at": None,
            "note": note,
        }
        self.data["entries"][fp] = rec
        self.save()
        return True, rec

    def complete(self, fp: str, *, provider_job_id: str, credits: int | None = None,
                 output_path: str = "") -> dict:
        rec = self.data["entries"].get(fp)
        if rec is None:
            raise KeyError(f"원장에 없는 fingerprint: {fp}")
        rec["status"] = "done"
        rec["provider_job_id"] = provider_job_id
        rec["completed_at"] = now_iso()
        if credits is not None:
            rec["credits"] = int(credits)
        if output_path:
            rec["output_path"] = output_path
        self.save()
        return rec

    def release(self, fp: str, reason: str = "") -> None:
        """실패한 claim 을 해제해 재시도를 허용한다."""
        rec = self.data["entries"].get(fp)
        if rec is None:
            return
        if rec.get("status") == "done":
            raise ValueError("이미 완료된 생성은 해제할 수 없습니다. 프롬프트를 바꾸세요.")
        rec["status"] = "released"
        rec["released_at"] = now_iso()
        rec["release_reason"] = reason
        self.save()

    def total_credits_spent(self) -> int:
        return sum(int(r.get("credits") or 0)
                   for r in self.data["entries"].values()
                   if r.get("status") == "done")

    def done_indices(self) -> set[int]:
        return {int(r["track_index"]) for r in self.data["entries"].values()
                if r.get("status") == "done" and r.get("track_index") is not None}
