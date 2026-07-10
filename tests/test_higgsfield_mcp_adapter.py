# Higgsfield MCP writer-injection 어댑터를 mock MCP/HTTP 로 검증하는 테스트 (네트워크 없음)
"""
HiggsfieldMcpAdapter / make_mcp_writer 단위 테스트.

실 MCP/네트워크 없이 mcp_call 과 http transport 를 mock 으로 주입해
업로드→생성→폴링→다운로드→MP4 검증 파이프라인과 provider writer 주입을 확인한다.
기존 provider 테스트는 건드리지 않는다.
"""

import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "providers"))

from higgsfield_provider import (  # noqa: E402
    HiggsfieldMcpAdapter, make_mcp_writer, generate, _looks_like_mp4,
    PROVIDER, CAPABILITY,
)
from provider_sdk import make_request  # noqa: E402

_VALID_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32
_MEDIA_ID = "11111111-1111-4111-8111-111111111111"
_JOB_ID = "22222222-2222-4222-8222-222222222222"


class _FakeHttp:
    """put/get_bytes 를 기록하는 mock transport."""

    def __init__(self, video_bytes=_VALID_MP4):
        self._video = video_bytes
        self.put_calls = []

    def put(self, url, data, headers=None):
        self.put_calls.append((url, len(data), headers))

    def get_bytes(self, url):
        self.get_url = url
        return self._video


class _FakeMcp:
    """스크립트된 MCP 응답을 돌려주는 mock. 호출 순서/인자를 기록한다."""

    def __init__(self, status_sequence=None, upload=None, generate=None):
        self.calls = []
        self._status = list(status_sequence or [{"status": "completed",
                                                 "video_url": "https://x/v.mp4",
                                                 "width": 1024, "height": 576, "duration": 5}])
        self._upload = upload or {"upload_url": "https://up/put", "media_id": _MEDIA_ID}
        self._generate = generate or {"job_id": _JOB_ID}

    def __call__(self, tool, args):
        self.calls.append((tool, args))
        if tool == "media_upload":
            return self._upload
        if tool == "media_confirm":
            return {"media_id": _MEDIA_ID}
        if tool == "generate_video":
            return self._generate
        if tool == "job_status":
            return self._status.pop(0) if len(self._status) > 1 else self._status[0]
        raise AssertionError(f"예상치 못한 MCP 도구 호출: {tool}")


def _img():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "scene_001.png")
    with open(p, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return p


# --- MP4 시그니처 검증 유닛 ---

def test_looks_like_mp4():
    assert _looks_like_mp4(_VALID_MP4) is True
    assert _looks_like_mp4(b"not-an-mp4-file-bytes") is False
    assert _looks_like_mp4(b"") is False


# --- happy path: 어댑터 전체 파이프라인 ---

def test_adapter_generates_valid_mp4():
    mcp, http = _FakeMcp(), _FakeHttp()
    meta = {}
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "scene_001.mp4")
        adapter = HiggsfieldMcpAdapter(mcp, model="kling3_0_turbo", http=http, sleep=lambda _: None)
        adapter.generate_to_file(out, "달이 떠오른다", _img(), metadata=meta)
        assert os.path.exists(out) and os.path.getsize(out) > 0
        with open(out, "rb") as f:
            assert _looks_like_mp4(f.read()) is True
    # 도구 호출 순서 확인
    order = [c[0] for c in mcp.calls]
    assert order == ["media_upload", "media_confirm", "generate_video", "job_status"]
    # generate_video 인자: model/prompt/medias(media_id) 확인
    gv = next(a for t, a in mcp.calls if t == "generate_video")
    params = gv["params"]
    assert params["model"] == "kling3_0_turbo"
    assert params["prompt"] == "달이 떠오른다"
    assert params["medias"][0]["value"] == _MEDIA_ID
    assert params["medias"][0]["role"] == "start_image"
    # 업로드 바이트 PUT 되었는지
    assert http.put_calls and http.put_calls[0][1] > 0
    # metadata 채워짐
    assert meta == {"width": 1024, "height": 576, "duration": 5}


# --- 폴링: pending → completed ---

def test_adapter_polls_until_complete():
    seq = [
        {"status": "in_progress", "poll_after_seconds": 3},
        {"status": "queued", "poll_after_seconds": 2},
        {"status": "completed", "url": "https://x/v.mp4"},
    ]
    slept = []
    mcp, http = _FakeMcp(status_sequence=seq), _FakeHttp()
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "v.mp4")
        adapter = HiggsfieldMcpAdapter(mcp, model="m", http=http, sleep=slept.append)
        adapter.generate_to_file(out, "p", _img())
        assert os.path.exists(out)
    assert [c[0] for c in mcp.calls].count("job_status") == 3
    assert slept == [3, 2]  # 완료 전까지만 대기


# --- 검증 실패: 잘못된 MP4 다운로드 ---

def test_adapter_rejects_invalid_mp4():
    mcp, http = _FakeMcp(), _FakeHttp(video_bytes=b"garbage-not-mp4")
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "v.mp4")
        adapter = HiggsfieldMcpAdapter(mcp, model="m", http=http, sleep=lambda _: None)
        try:
            adapter.generate_to_file(out, "p", _img())
        except RuntimeError as e:
            assert "MP4" in str(e)
            assert not os.path.exists(out)  # 무효 → 파일 미기록
            return
    raise AssertionError("무효 MP4 가 거부되지 않음")


# --- 실패 상태 처리 ---

def test_adapter_raises_on_failed_status():
    mcp = _FakeMcp(status_sequence=[{"status": "failed"}])
    with tempfile.TemporaryDirectory() as d:
        adapter = HiggsfieldMcpAdapter(mcp, model="m", http=_FakeHttp(), sleep=lambda _: None)
        try:
            adapter.generate_to_file(os.path.join(d, "v.mp4"), "p", _img())
        except RuntimeError as e:
            assert "실패" in str(e)
            return
    raise AssertionError("failed 상태가 예외로 이어지지 않음")


# --- 업로드 응답 파싱 실패 ---

def test_adapter_upload_missing_fields():
    mcp = _FakeMcp(upload={"unexpected": True})
    with tempfile.TemporaryDirectory() as d:
        adapter = HiggsfieldMcpAdapter(mcp, model="m", http=_FakeHttp(), sleep=lambda _: None)
        try:
            adapter.generate_to_file(os.path.join(d, "v.mp4"), "p", _img())
        except RuntimeError as e:
            assert "upload_url" in str(e)
            return
    raise AssertionError("업로드 응답 파싱 실패가 예외로 이어지지 않음")


# --- 모델 id 필수 (하드코딩 금지) ---

def test_model_required():
    prev = os.environ.pop("HIGGSFIELD_MODEL", None)
    try:
        HiggsfieldMcpAdapter(lambda t, a: {}, http=_FakeHttp())
    except RuntimeError as e:
        assert "모델" in str(e)
        return
    finally:
        if prev is not None:
            os.environ["HIGGSFIELD_MODEL"] = prev
    raise AssertionError("모델 미지정이 거부되지 않음")


def test_model_from_env():
    prev = os.environ.get("HIGGSFIELD_MODEL")
    os.environ["HIGGSFIELD_MODEL"] = "seedance_2_0"
    try:
        a = HiggsfieldMcpAdapter(lambda t, arg: {}, http=_FakeHttp())
        assert a._model == "seedance_2_0"
    finally:
        if prev is None:
            os.environ.pop("HIGGSFIELD_MODEL", None)
        else:
            os.environ["HIGGSFIELD_MODEL"] = prev


# --- provider writer 주입 통합: mock=False, status=success ---

def test_make_mcp_writer_integrates_with_generate():
    mcp, http = _FakeMcp(), _FakeHttp()
    with tempfile.TemporaryDirectory() as d:
        writer = make_mcp_writer(mcp, image_path=_img(), model="kling3_0_turbo",
                                 http=http, sleep=lambda _: None)
        req = make_request(PROVIDER, CAPABILITY, prompt="장면1",
                           inputs=["output/malli/images/scene_001.png"])
        r = generate(req, output_dir=d, writer=writer)
        assert r["status"] == "success"
        assert r["output"]["mock"] is False
        assert r["output"]["type"] == "video"
        p = os.path.join(_ROOT, r["output"]["path"])
        assert os.path.exists(p) and os.path.getsize(p) > 0


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
