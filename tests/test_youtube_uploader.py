# YouTube 업로더의 mock 업로드·설정 병합·요청 body·실 경로(주입 service)·옵트인 가드를 검증하는 테스트
"""YouTube Upload Pipeline 단위 테스트. 네트워크/실 자격증명 없이 검증한다."""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "uploader"))

from youtube_uploader import (  # noqa: E402
    upload, load_config, build_request_body, DEFAULT_YOUTUBE_CONFIG, _REAL_ENV,
)

_MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 16


def _video():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "malli_final.mp4")
    with open(p, "wb") as f:
        f.write(_MP4)
    return p


# --- 설정 로드/병합 ---

def test_config_defaults_when_empty():
    cfg = load_config(None)
    assert cfg["privacy"] == "private"
    assert cfg["category"] == "22"
    assert cfg["tags"] == [] and cfg["publish_time"] is None


def test_config_merge_overrides_only_given_keys():
    cfg = load_config({"title": "Malli 1화", "privacy": "unlisted", "tags": ["동화"]})
    assert cfg["title"] == "Malli 1화"
    assert cfg["privacy"] == "unlisted"
    assert cfg["tags"] == ["동화"]
    assert cfg["category"] == DEFAULT_YOUTUBE_CONFIG["category"]  # 미지정은 기본 유지


def test_config_from_json_path():
    import json
    d = tempfile.mkdtemp()
    p = os.path.join(d, "yt.json")
    json.dump({"channel": "Malli Ch", "category": "24"}, open(p, "w", encoding="utf-8"))
    cfg = load_config(p)
    assert cfg["channel"] == "Malli Ch" and cfg["category"] == "24"


# --- 요청 body 매핑 ---

def test_build_request_body_maps_fields():
    cfg = load_config({"title": "T", "description": "D", "tags": ["a", "b"],
                       "category": "22", "privacy": "public"})
    body = build_request_body(cfg)
    assert body["snippet"]["title"] == "T"
    assert body["snippet"]["description"] == "D"
    assert body["snippet"]["tags"] == ["a", "b"]
    assert body["snippet"]["categoryId"] == "22"
    assert body["status"]["privacyStatus"] == "public"
    assert "publishAt" not in body["status"]


def test_scheduled_publish_forces_private_with_publishat():
    cfg = load_config({"privacy": "public", "publish_time": "2026-08-01T09:00:00Z"})
    body = build_request_body(cfg)
    assert body["status"]["privacyStatus"] == "private"  # 예약은 private 강제
    assert body["status"]["publishAt"] == "2026-08-01T09:00:00Z"


# --- mock 업로드 ---

def test_mock_upload_success():
    v = _video()
    r = upload(v, {"title": "Malli", "privacy": "unlisted", "channel": "Malli Ch"},
               now="2026-07-10T00:00:00Z")
    assert r["status"] == "success"
    assert r["mock"] is True
    assert r["video_id"].startswith("MOCK_")
    assert r["title"] == "Malli"
    assert r["visibility"] == "unlisted"
    assert r["url"] == f"https://youtu.be/{r['video_id']}"
    assert r["upload_time"] == "2026-07-10T00:00:00Z"


def test_mock_default_when_no_optin():
    prev = os.environ.pop(_REAL_ENV, None)
    try:
        r = upload(_video(), {"title": "x"})
        assert r["mock"] is True and r["status"] == "success"
    finally:
        if prev is not None:
            os.environ[_REAL_ENV] = prev


def test_mock_thumbnail_flag():
    v = _video()
    thumb = os.path.join(os.path.dirname(v), "thumb.png")
    open(thumb, "wb").write(b"\x89PNG\r\n\x1a\n")
    r = upload(v, {"title": "x"}, thumbnail=thumb)
    assert r["thumbnail_uploaded"] is True


def test_missing_video_fails():
    r = upload("nope/malli_final.mp4", {"title": "x"})
    assert r["status"] == "failed"
    assert r["video_id"] is None


# --- 실 경로: 자격증명/서비스 없으면 실패(옵트인 가드) ---

def test_real_optin_without_service_or_creds_fails():
    r = upload(_video(), {"title": "x"}, real=True)  # service 미주입, lib/creds 없음
    assert r["status"] == "failed"
    assert r["mock"] is False
    assert "실 YouTube 업로드 실패" in r["message"]


# --- 실 경로: service 주입으로 오프라인 검증 ---

class _FakeExec:
    def __init__(self, ret):
        self._ret = ret

    def execute(self):
        return self._ret


class _FakeVideos:
    def __init__(self, rec):
        self._rec = rec

    def insert(self, part, body, media_body):
        self._rec["insert"] = {"part": part, "body": body}
        return _FakeExec({"id": "YT_REAL_123"})


class _FakeThumbs:
    def __init__(self, rec):
        self._rec = rec

    def set(self, videoId, media_body):
        self._rec["thumb_set"] = videoId
        return _FakeExec({})


class _FakeService:
    def __init__(self):
        self.rec = {}

    def videos(self):
        return _FakeVideos(self.rec)

    def thumbnails(self):
        return _FakeThumbs(self.rec)


def test_real_upload_with_injected_service():
    v = _video()
    thumb = os.path.join(os.path.dirname(v), "t.png")
    open(thumb, "wb").write(b"\x89PNG\r\n\x1a\n")
    svc = _FakeService()
    r = upload(v, {"title": "Malli", "privacy": "public", "tags": ["동화"]},
               real=True, thumbnail=thumb, service=svc)
    assert r["status"] == "success"
    assert r["mock"] is False
    assert r["video_id"] == "YT_REAL_123"
    assert r["url"] == "https://youtu.be/YT_REAL_123"
    assert r["thumbnail_uploaded"] is True
    # 요청 body 가 설정에서 옴
    assert svc.rec["insert"]["body"]["snippet"]["title"] == "Malli"
    assert svc.rec["insert"]["body"]["status"]["privacyStatus"] == "public"
    assert svc.rec["thumb_set"] == "YT_REAL_123"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
