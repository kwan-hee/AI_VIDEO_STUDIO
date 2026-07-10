# Provider SDK request 를 받아 영상을 생성(현재는 안전 mock)하고 SDK result 를 반환하는 Higgsfield Provider
"""
Higgsfield Provider (Phase 3 / Provider 2)

목적.
  - Provider SDK / Provider Harness 를 실제 Higgsfield 공급자 모듈에 연결한다.
  - Higgsfield 는 기본 영상 생성 공급자다. (백업 공급자는 이 모듈에서 호출하지 않는다.)

책임.
  - capability: generate_video 지원.
  - 표준 Provider SDK request 를 받는다.
  - 표준 Provider SDK result 를 반환한다.
  - 생성/모의 영상을 output/videos/ 아래에 저장한다.

현재 실 Higgsfield 실행은 미가용 → 안전 mock 을 먼저 구현한다.
실 실행이 준비되면 writer 인자로 실제 생성 백엔드를 주입한다(기본은 mock writer).

다른 공급자(이미지/음성/보정/합성)는 호출하지 않는다. 기존 Sprint 동작 미수정.
결과 스키마: schemas/higgsfield_result_schema.json (Provider SDK result 형식 준수)
"""

import base64
import hashlib
import os
import time

from provider_sdk import make_result

PROVIDER = "Higgsfield"
CAPABILITY = "generate_video"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "videos")

# mock 영상 바이트(MP4 ftyp 박스 + 표식). 실 렌더링 아님, 배관 검증용 placeholder.
_MOCK_BYTES = b"\x00\x00\x00\x18ftypmp42higgsfield-mock"

# 실 실행 옵트인 환경변수. "1" 일 때만 실 백엔드를 시도한다(기본은 mock).
_REAL_ENV = "HIGGSFIELD_REAL"


def _mock_writer(path, prompt):
    """실 공급자 없이 placeholder 영상 파일을 기록한다."""
    with open(path, "wb") as f:
        f.write(_MOCK_BYTES)


def _real_writer(path, prompt):
    """
    실 영상 생성 백엔드로 파일을 기록한다(옵트인 전용).
    실 백엔드(SDK/API/MCP)가 연결되어 있지 않으면 RuntimeError 를 올려
    generate 가 status=failed 로 보고하게 한다. 실 백엔드가 준비되면 여기서 호출하도록 교체한다.
    """
    try:
        import higgsfield_sdk  # 실 백엔드(선택 설치). 미설치 시 ImportError.
    except ImportError as e:
        raise RuntimeError(
            "실 Higgsfield 백엔드가 연결되어 있지 않다. "
            f"({_REAL_ENV}=1 옵트인했으나 SDK/API/MCP 미연결)"
        ) from e
    higgsfield_sdk.generate_video(prompt=prompt, out_path=path)  # pragma: no cover


def _rel(path):
    try:
        return os.path.relpath(path, _ROOT).replace(os.sep, "/")
    except ValueError:
        return path


def _validate_request(request):
    if not isinstance(request, dict):
        raise ValueError("request 는 dict 여야 한다.")
    if request.get("provider") != PROVIDER:
        raise ValueError(f"이 provider 는 {PROVIDER} 전용이다: {request.get('provider')}")
    if request.get("capability") != CAPABILITY:
        raise ValueError(f"지원 capability 는 {CAPABILITY} 뿐이다: {request.get('capability')}")


def generate(request, output_dir=None, writer=None, real=None):
    """
    Provider SDK request → 영상 생성 후 SDK result.
    기본은 mock writer 로 placeholder 영상을 output/videos/ 에 저장한다.
    실 실행은 옵트인 전용이다. real=True 또는 환경변수 HIGGSFIELD_REAL=1 일 때만 실 백엔드를 시도한다.
    writer 를 직접 주입하면 그 writer 가 최우선이다(테스트/커스텀 백엔드).
    request 오류는 ValueError. 생성 실패는 status="failed".
    """
    _validate_request(request)

    prompt = request.get("prompt")
    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    key = hashlib.md5((prompt or "").encode("utf-8")).hexdigest()[:10]
    path = os.path.join(out_dir, f"higgsfield_{key}.mp4")

    # 모드 결정: 주입 writer > 실 옵트인 > mock(기본)
    if real is None:
        real = os.environ.get(_REAL_ENV) == "1"
    if writer is not None:
        is_mock = False
    elif real:
        writer, is_mock = _real_writer, False
    else:
        writer, is_mock = _mock_writer, True
    try:
        writer(path, prompt)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            raise RuntimeError("영상 파일이 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(path) and os.path.getsize(path) == 0:
            os.remove(path)
        return make_result(PROVIDER, CAPABILITY, status="failed", output=None,
                           message=f"영상 생성 실패: {e}")

    output = {"path": _rel(path), "type": "video", "mock": is_mock, "prompt": prompt}
    return make_result(PROVIDER, CAPABILITY, status="success", output=output,
                       message="mock 영상 생성 완료." if is_mock else "영상 생성 완료.")


# ---------------------------------------------------------------------------
# 실 백엔드: Higgsfield MCP writer-injection 어댑터
# ---------------------------------------------------------------------------
# 이 provider 는 별도 프로세스로 실행되어 에이전트의 MCP 세션에 직접 접근할 수 없다.
# 그래서 실 생성 로직(업로드→생성→폴링→다운로드→검증)은 여기 provider 안에 두고,
# MCP 도구 호출 transport(mcp_call)만 외부에서 주입받는다.
#   mcp_call(tool_name: str, arguments: dict) -> dict
# 에이전트는 이 mcp_call 로 실제 mcp__..._Higgsfield__* 도구를 호출하도록 배선한다.
# 테스트는 mcp_call/http 를 mock 으로 주입해 네트워크 없이 어댑터를 검증한다.
#
# 확인된 MCP 계약(입력 인자 스키마 기준. 응답 필드명은 방어적으로 파싱한다).
#   media_upload   {filename, content_type}      -> presigned upload_url + 식별 토큰
#   media_confirm  {식별 토큰}                    -> 확정 media_id
#   generate_video {params:{model, prompt, medias:[{role, value:media_id}]}} -> job id
#   job_status     {jobId}                        -> status / video_url / (width,height,duration)

_MODEL_ENV = "HIGGSFIELD_MODEL"          # 실 모델 id (하드코딩 금지, env/인자로 주입)
_ROLE_ENV = "HIGGSFIELD_VIDEO_ROLE"      # 소스 이미지 media role
_DEFAULT_ROLE = "start_image"
_MP4_FTYP = b"ftyp"
_TERMINAL_OK = ("completed", "succeeded", "success", "done", "ready")
_TERMINAL_BAD = ("failed", "error", "canceled", "cancelled", "rejected")
_CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".webp": "image/webp", ".gif": "image/gif"}


def _looks_like_mp4(data):
    """MP4(ISO BMFF) 시그니처 검사. 4~8바이트 위치의 ftyp 박스 존재 + 최소 길이."""
    return isinstance(data, (bytes, bytearray)) and len(data) >= 12 and data[4:8] == _MP4_FTYP


def _first(d, *keys):
    """dict 에서 keys 중 처음으로 비어있지 않은 값을 반환. 없으면 None."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def _record(resp):
    """리스트/래퍼로 감싸인 응답에서 대표 레코드 하나를 꺼낸다."""
    if not isinstance(resp, dict):
        return {}
    for key in ("files", "medias", "results", "data", "items"):
        v = resp.get(key)
        if isinstance(v, list) and v:
            return v[0] if isinstance(v[0], dict) else resp
        if isinstance(v, dict):
            return v
    return resp


class _RequestsHttp:
    """실 네트워크 transport. requests 를 지연 import 한다(모듈 import 시 강제 의존 회피)."""

    def __init__(self, timeout=300):
        import requests  # noqa: F401
        self._requests = requests
        self._timeout = timeout

    def put(self, url, data, headers=None):
        resp = self._requests.put(url, data=data, headers=headers or {}, timeout=self._timeout)
        resp.raise_for_status()
        return resp

    def get_bytes(self, url):
        resp = self._requests.get(url, timeout=self._timeout)
        resp.raise_for_status()
        return resp.content


class HiggsfieldMcpAdapter:
    """
    Higgsfield MCP 계약을 provider-side 에서 순차 실행하는 어댑터.
    mcp_call/http/sleep 를 주입받아 네트워크 없이 테스트 가능하다.
    """

    def __init__(self, mcp_call, *, model=None, role=None, http=None, sleep=None,
                 poll_interval=5.0, max_wait=300.0):
        if not callable(mcp_call):
            raise ValueError("mcp_call 은 callable 이어야 한다.")
        model = model or os.environ.get(_MODEL_ENV)
        if not model:
            raise RuntimeError(
                f"실 모델 id 없음: model 인자 또는 환경변수 {_MODEL_ENV} 로 지정하라(하드코딩 금지)."
            )
        self._call = mcp_call
        self._model = model
        self._role = role or os.environ.get(_ROLE_ENV) or _DEFAULT_ROLE
        self._http = http or _RequestsHttp()
        self._sleep = sleep or time.sleep
        self._interval = poll_interval
        self._max_wait = max_wait

    # -- 1) 이미지 업로드 → media_id -------------------------------------
    def _upload_image(self, image_path):
        if not image_path or not os.path.exists(image_path):
            raise RuntimeError(f"소스 이미지 없음: {image_path}")
        fname = os.path.basename(image_path)
        ctype = _CONTENT_TYPES.get(os.path.splitext(fname)[1].lower(), "application/octet-stream")
        up = self._call("media_upload", {"filename": fname, "content_type": ctype})
        rec = _record(up)
        upload_url = _first(rec, "upload_url", "uploadUrl", "url", "put_url")
        token = _first(rec, "media_id", "mediaId", "id", "value", "token")
        if not upload_url or not token:
            raise RuntimeError(f"media_upload 응답에서 upload_url/토큰을 찾지 못함: {up}")
        with open(image_path, "rb") as f:
            self._http.put(upload_url, f.read(), headers={"Content-Type": ctype})
        confirm = self._call("media_confirm", {"media_id": token, "value": token})
        media_id = _first(_record(confirm), "media_id", "mediaId", "id", "value") or token
        return media_id

    # -- 2) 영상 생성 작업 제출 → job_id --------------------------------
    def _submit(self, prompt, media_id):
        params = {"model": self._model, "prompt": prompt,
                  "medias": [{"role": self._role, "value": media_id}]}
        resp = self._call("generate_video", {"params": params})
        job_id = _first(resp, "job_id", "jobId", "id") or _first(_record(resp), "job_id", "jobId", "id")
        if not job_id:
            raise RuntimeError(f"generate_video 응답에서 job id 를 찾지 못함: {resp}")
        return job_id

    # -- 3) 완료 폴링 → (video_url, metadata) ----------------------------
    def _poll(self, job_id):
        waited = 0.0
        while True:
            resp = self._call("job_status", {"jobId": job_id})
            status = (_first(resp, "status", "state") or "").lower()
            if status in _TERMINAL_OK:
                rec = _record(resp)
                video_url = (_first(resp, "video_url", "videoUrl", "url", "output_url")
                             or _first(rec, "video_url", "videoUrl", "url", "output_url"))
                if not video_url:
                    raise RuntimeError(f"완료 상태이나 영상 URL 없음: {resp}")
                meta = {k: (_first(resp, k) if _first(resp, k) is not None else _first(rec, k))
                        for k in ("width", "height", "duration")}
                return video_url, {k: v for k, v in meta.items() if v is not None}
            if status in _TERMINAL_BAD:
                raise RuntimeError(f"영상 생성 실패 상태: {status} ({resp})")
            wait = _first(resp, "poll_after_seconds", "poll_after", "retry_after") or self._interval
            waited += wait
            if waited > self._max_wait:
                raise RuntimeError(f"영상 생성 폴링 타임아웃({self._max_wait}s 초과).")
            self._sleep(wait)

    def generate_to_file(self, path, prompt, image_path, metadata=None):
        """전체 파이프라인 실행 후 검증된 MP4 를 path 에 기록한다. metadata dict 에 width/height/duration 채움."""
        media_id = self._upload_image(image_path)
        job_id = self._submit(prompt, media_id)
        video_url, meta = self._poll(job_id)
        data = self._http.get_bytes(video_url)
        if not _looks_like_mp4(data):
            raise RuntimeError("다운로드한 데이터가 유효한 MP4(ftyp) 컨테이너가 아니다.")
        with open(path, "wb") as f:
            f.write(data)
        if os.path.getsize(path) == 0:
            raise RuntimeError("기록된 영상 파일 크기가 0 이다.")
        if isinstance(metadata, dict):
            metadata.update(meta)
        return meta


def make_mcp_writer(mcp_call, *, image_path, model=None, role=None, http=None, sleep=None,
                    poll_interval=5.0, max_wait=300.0, metadata=None):
    """
    generate(request, writer=...) 에 주입할 writer(path, prompt) 를 만든다.
    image_path(소스 이미지)를 클로저에 바인딩하고, MCP 어댑터로 실 영상을 생성한다.
    """
    adapter = HiggsfieldMcpAdapter(mcp_call, model=model, role=role, http=http, sleep=sleep,
                                   poll_interval=poll_interval, max_wait=max_wait)

    def _writer(path, prompt):
        adapter.generate_to_file(path, prompt, image_path, metadata=metadata)

    return _writer


# 하네스/파이프라인이 주입할 기본 핸들러 (request -> result)
handler = generate


if __name__ == "__main__":
    import json

    from provider_sdk import make_request

    req = make_request(PROVIDER, CAPABILITY, prompt="달이 떠오르는 밤", inputs=["output/images/01.png"])
    print(json.dumps(generate(req), ensure_ascii=False, indent=2))
