# 생성된 에셋을 등록·조회하는 Asset Manager (레지스트리 전용, 미디어 생성·외부 호출 없음)
"""
Asset Manager (Sprint 11)

책임.
  - 생성된 모든 에셋을 등록한다.
  - 조회/필터를 제공한다.

지원 에셋 타입: story, image, video, audio, thumbnail.

각 에셋은 다음을 포함한다.
  asset_id, type, provider, path, status, created_at

외부 API 없음. 미디어 생성 없음. FFmpeg 실행 없음. 레지스트리 전용(인메모리).
에셋 스키마: schemas/asset_schema.json
Sprint 1~10 파일은 수정하지 않는다.
"""

from datetime import datetime, timezone

ASSET_TYPES = {"story", "image", "video", "audio", "thumbnail"}
ASSET_STATUSES = {"pending", "ready", "failed"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class AssetManager:
    """생성된 에셋의 인메모리 레지스트리. 아무것도 실행하지 않는다."""

    def __init__(self):
        self._assets = []
        self._by_id = {}
        self._counter = 0

    def register(self, type, provider, path, status="ready", asset_id=None, created_at=None):
        """
        에셋 하나를 등록한다. 등록된 에셋 dict 를 반환한다.
        미디어를 만들지 않는다. path 는 이미 존재하는(또는 예정된) 경로 문자열일 뿐이다.
        """
        if type not in ASSET_TYPES:
            raise ValueError(f"지원하지 않는 에셋 타입: {type}")
        if status not in ASSET_STATUSES:
            raise ValueError(f"지원하지 않는 상태: {status}")

        if asset_id is None:
            self._counter += 1
            asset_id = f"{type}_{self._counter:04d}"
        if asset_id in self._by_id:
            raise ValueError(f"중복 asset_id: {asset_id}")

        asset = {
            "asset_id": asset_id,
            "type": type,
            "provider": provider,
            "path": path,
            "status": status,
            "created_at": created_at or _now_iso(),
        }
        self._assets.append(asset)
        self._by_id[asset_id] = asset
        return asset

    def get(self, asset_id):
        """asset_id 로 조회. 없으면 None."""
        return self._by_id.get(asset_id)

    def list_assets(self, type=None, status=None):
        """타입/상태로 필터. 인자 없으면 전체."""
        out = self._assets
        if type is not None:
            out = [a for a in out if a["type"] == type]
        if status is not None:
            out = [a for a in out if a["status"] == status]
        return list(out)

    def count(self):
        return len(self._assets)

    def to_dict(self):
        return {"assets": list(self._assets)}


if __name__ == "__main__":
    import json

    mgr = AssetManager()
    mgr.register("story", None, "output/text/01_script.txt")
    mgr.register("image", "Nano Banana", "output/image/02_image.png")
    mgr.register("video", "Higgsfield", "output/video/03_video.mp4")
    mgr.register("audio", "Edge TTS", "output/audio/04_voice.mp3")
    mgr.register("thumbnail", "Nano Banana", "output/image/05_thumb.png")
    print(json.dumps(mgr.to_dict(), ensure_ascii=False, indent=2))
