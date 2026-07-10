# 완성된 malli_final.mp4 를 설정 기반으로 YouTube 에 업로드(기본 mock, 실 업로드는 명시 옵트인)하는 업로더
"""
YouTube Upload Pipeline (Phase 10)

목적.
  - 완성된 최종 영화(output/malli/final/malli_final.mp4)를 YouTube 에 업로드한다.
  - 제목/설명/태그/카테고리/공개범위/예약공개는 설정에서만 읽는다.

원칙.
  - 미디어를 재생성하지 않는다. 기존 최종 MP4 를 재사용한다.
  - 기본은 mock. 실 업로드는 real=True 또는 환경변수 YOUTUBE_REAL=1 로만 옵트인.
  - 실 업로드는 google-api-python-client + OAuth 자격증명이 필요하다(없으면 명확히 실패).
  - service 를 주입하면 네트워크 없이 실 경로를 테스트할 수 있다.
"""

import copy
import hashlib
import json
import os
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_ENV = "YOUTUBE_REAL"
_MP4_FTYP = b"ftyp"

# 안전 기본 설정. 사용자 설정이 deep-merge 되어 누락 필드는 기본을 유지한다.
DEFAULT_YOUTUBE_CONFIG = {
    "channel": None,               # 채널 식별(표시/기록용)
    "title": "Malli",              # 영상 제목
    "description": "",             # 설명
    "tags": [],                    # 태그 리스트
    "category": "22",              # YouTube categoryId (22 = People & Blogs)
    "privacy": "private",          # public / unlisted / private
    "publish_time": None,          # ISO8601 예약 공개 시각(있으면 private + publishAt)
}


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(source=None):
    """
    설정 로드. source 는 dict 또는 JSON 파일 경로. None 이면 기본만.
    누락 필드는 DEFAULT_YOUTUBE_CONFIG 로 채운다.
    """
    if source is None:
        override = {}
    elif isinstance(source, dict):
        override = source
    elif isinstance(source, str):
        with open(source, encoding="utf-8") as f:
            override = json.load(f)
    else:
        raise ValueError("source 는 dict, JSON 경로, 또는 None 이어야 한다.")
    return _deep_merge(DEFAULT_YOUTUBE_CONFIG, override)


def build_request_body(config):
    """설정 → YouTube videos.insert 요청 body(snippet + status)."""
    snippet = {
        "title": config["title"],
        "description": config["description"],
        "tags": list(config.get("tags") or []),
        "categoryId": str(config["category"]),
    }
    status = {"privacyStatus": config["privacy"]}
    if config.get("publish_time"):
        # 예약 공개는 private + publishAt 규칙을 따른다.
        status["privacyStatus"] = "private"
        status["publishAt"] = config["publish_time"]
    return {"snippet": snippet, "status": status}


# ---------------------------------------------------------------------------
# 검증/서비스
# ---------------------------------------------------------------------------

def _valid_mp4(path):
    if not (path and os.path.exists(path) and os.path.getsize(path) > 0):
        return False
    with open(path, "rb") as f:
        return f.read(12)[4:8] == _MP4_FTYP


def _build_service(config):
    """
    실 YouTube API 서비스 생성. google-api-python-client + OAuth 자격증명 필요.
    미설치/미설정 시 RuntimeError. (테스트는 service 를 직접 주입한다.)
    """
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise RuntimeError(
            "실 YouTube 업로드에는 google-api-python-client 가 필요하다(미설치)."
        ) from e
    token_path = (config.get("oauth") or {}).get("token") or os.environ.get("YOUTUBE_TOKEN")
    if not token_path or not os.path.exists(token_path):
        raise RuntimeError(
            "YouTube OAuth 자격증명 없음: config.oauth.token 또는 환경변수 YOUTUBE_TOKEN 필요."
        )
    creds = Credentials.from_authorized_user_file(
        token_path, ["https://www.googleapis.com/auth/youtube.upload"])
    return build("youtube", "v3", credentials=creds)


def _real_upload(video_path, config, thumbnail, service):
    """실 업로드 수행. service 미주입 시 자격증명으로 생성한다."""
    # MediaFileUpload 는 실 lib 이 있을 때만. 주입 service(테스트/오프라인)는 없어도 동작한다.
    try:
        from googleapiclient.http import MediaFileUpload
        def _media(p, resumable=False):
            return MediaFileUpload(p, chunksize=-1, resumable=resumable, mimetype="video/*")
    except ImportError:
        if service is None:
            raise  # 실 service 도 lib 도 없으면 실 업로드 불가
        def _media(p, resumable=False):
            return p  # 주입 service 는 media_body 내용을 사용하지 않는다

    service = service or _build_service(config)
    body = build_request_body(config)
    media = _media(video_path, resumable=True)
    resp = service.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    video_id = resp["id"]
    thumb_done = False
    if thumbnail and os.path.exists(thumbnail):
        service.thumbnails().set(videoId=video_id, media_body=_media(thumbnail)).execute()
        thumb_done = True
    return video_id, thumb_done


# ---------------------------------------------------------------------------
# 업로드 오케스트레이션
# ---------------------------------------------------------------------------

def upload(video_path, config=None, real=None, thumbnail=None, service=None, now=None):
    """
    최종 MP4 를 YouTube 에 업로드한다.
    기본 mock. real=True 또는 YOUTUBE_REAL=1 일 때만 실 업로드.
    반환: 검증 리포트 dict.
    """
    cfg = load_config(config)  # dict/경로/None → 기본 병합
    if real is None:
        real = os.environ.get(_REAL_ENV) == "1"
    upload_time = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = build_request_body(config=cfg)
    visibility = body["status"]["privacyStatus"]

    def result(status, video_id=None, thumb=False, message=""):
        url = f"https://youtu.be/{video_id}" if video_id else None
        return {
            "status": status,
            "video_id": video_id,
            "title": cfg["title"],
            "visibility": visibility,
            "publish_at": body["status"].get("publishAt"),
            "upload_time": upload_time,
            "thumbnail_uploaded": thumb,
            "url": url,
            "channel": cfg["channel"],
            "mock": not real,
            "message": message,
        }

    if not _valid_mp4(video_path):
        return result("failed", message=f"유효한 최종 MP4 없음: {video_path}")

    if not real:
        # mock: 실제 업로드 없이 결정적 가짜 video id.
        vid = "MOCK_" + hashlib.md5(os.path.abspath(video_path).encode()).hexdigest()[:11]
        thumb_done = bool(thumbnail and os.path.exists(thumbnail))
        return result("success", video_id=vid, thumb=thumb_done, message="mock 업로드 완료.")

    try:
        video_id, thumb_done = _real_upload(video_path, cfg, thumbnail, service)
    except Exception as e:  # noqa: BLE001
        return result("failed", message=f"실 YouTube 업로드 실패: {type(e).__name__}: {e}")
    return result("success", video_id=video_id, thumb=thumb_done, message="YouTube 업로드 완료.")


if __name__ == "__main__":
    import sys
    real = "--real" in sys.argv
    vid = os.path.join(_ROOT, "output", "malli", "final", "malli_final.mp4")
    cfg = {"title": "Malli - 용감한 토끼의 숲 모험", "tags": ["Malli", "동화", "애니메이션"],
           "privacy": "private", "channel": "Malli Channel"}
    print(json.dumps(upload(vid, cfg, real=real), ensure_ascii=False, indent=2))
