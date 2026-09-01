"""웹 대시보드 - 보안 경계와 요약 조립."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from playlist_studio import webapp as W


# ---------------------------------------------------------------- 화이트리스트
def test_allowed_commands_are_real_cli_subcommands():
    """오타 난 명령이 화이트리스트에 남아 있으면 버튼이 조용히 죽는다."""
    from playlist_studio.cli import build_parser
    sub = next(a for a in build_parser()._actions if a.dest == "cmd")
    real = set(sub.choices)
    unknown = W.ALLOWED - real
    assert not unknown, f"CLI 에 없는 명령: {unknown}"


def test_serve_itself_is_not_runnable_from_the_web():
    """웹에서 서버를 또 띄우지 못하게 한다."""
    assert "serve" not in W.ALLOWED


def test_slow_commands_are_all_allowed():
    assert W.SLOW <= W.ALLOWED


# ---------------------------------------------------------------- 서버 통합
@pytest.fixture()
def server(studio, monkeypatch):
    from http.server import ThreadingHTTPServer
    W.Handler.token = "tok-test"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), W.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def get(base, path, token="tok-test", raw=False):
    req = urllib.request.Request(base + path)
    if token:
        req.add_header("X-Token", token)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return (r.status, body) if raw else (r.status, json.loads(body))


def post(base, path, payload, token="tok-test"):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Token": token or ""},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_requires_token(server):
    with pytest.raises(urllib.error.HTTPError) as ex:
        get(server, "/api/bootstrap", token=None)
    assert ex.value.code == 401


def test_wrong_token_rejected(server):
    with pytest.raises(urllib.error.HTTPError) as ex:
        get(server, "/api/projects", token="wrong-token")
    assert ex.value.code == 401


def test_static_files_need_no_token(server):
    for path in ("/", "/app.css", "/app.js"):
        status, body = get(server, path, token=None, raw=True)
        assert status == 200 and len(body) > 100


@pytest.mark.parametrize("bad", [
    "rm", "bash", "serve", "doctor; rm -rf /", "", "../cli",
])
def test_arbitrary_commands_are_refused(server, bad):
    status, data = post(server, "/api/run", {"command": bad, "args": []})
    assert status == 400 and "허용되지 않은" in data["error"]


def test_args_must_be_a_list_of_scalars(server):
    status, data = post(server, "/api/run", {"command": "doctor", "args": {"a": 1}})
    assert status == 400
    status, data = post(server, "/api/run", {"command": "doctor", "args": [{"x": 1}]})
    assert status == 400


def test_path_traversal_is_blocked(server, project):
    key = W.project_key(project)
    for evil in ("../../../../etc/passwd", "/etc/passwd", "..%2f..%2fetc%2fpasswd"):
        req = f"/media?project={key}&path={urllib.request.quote(evil, safe='')}"
        try:
            status, _ = get(server, req, raw=True)
        except urllib.error.HTTPError as e:
            status = e.code
        assert status == 404, f"{evil} 이 열렸습니다"


def test_media_serves_files_inside_the_project(server, project):
    f = project.root / "meta" / "sample.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("안녕", encoding="utf-8")
    key = W.project_key(project)
    status, body = get(server, f"/media?project={key}&path=meta/sample.txt", raw=True)
    assert status == 200 and body.decode("utf-8") == "안녕"


def test_text_endpoint_returns_content(server, project):
    f = project.root / "meta" / "chapters.txt"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("0:00 첫 곡\n", encoding="utf-8")
    key = W.project_key(project)
    status, data = get(server, f"/api/text?project={key}&path=meta/chapters.txt")
    assert status == 200 and "0:00 첫 곡" in data["text"]


def test_unknown_project_is_404(server):
    """URL 은 퍼센트 인코딩으로 온다 (프론트가 encodeURIComponent 를 쓴다)."""
    with pytest.raises(urllib.error.HTTPError) as ex:
        get(server, "/api/project/" + urllib.request.quote("없는것", safe=""))
    assert ex.value.code == 404


# ---------------------------------------------------------------- 요약
def test_project_summary_shape(project):
    s = W.project_summary(project)
    assert s["key"].endswith(project.root.name)
    assert len(s["steps"]) == 9
    assert s["total_steps"] == 9
    assert s["next_step"]["key"] == "plan"        # 채널만 끝난 상태
    assert s["done_steps"] == 1
    assert isinstance(s["files"], dict)
    assert s["credits_spent"] == 0


def test_summary_marks_failed_steps(project):
    from playlist_studio.state import Workspace
    ws = Workspace.load(project)
    ws.step_failed("plan", "테스트 실패")
    s = W.project_summary(project)
    assert "플레이리스트 설정" in s["failed_steps"]
    assert s["steps"][1]["error"] == "테스트 실패"


def test_file_map_lists_only_existing_files(project):
    s = W.project_summary(project)
    assert s["files"]["final_mp4"] is None
    project.video.mkdir(parents=True, exist_ok=True)
    project.final_mp4.write_bytes(b"x" * 10)
    assert W.project_summary(project)["files"]["final_mp4"] == "video/final.mp4"


def test_lan_ip_returns_something():
    ip = W.lan_ip()
    assert ip and ip.count(".") == 3
