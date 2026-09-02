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


# ---------------------------------------------------------------- 제출 인자 버튼
def _project_ready_for_payload(project):
    """가사까지 끝내고 모델을 확정한 프로젝트."""
    from playlist_studio import cli
    import io
    from contextlib import redirect_stdout

    def cli_run(argv):
        with redirect_stdout(io.StringIO()):
            try:
                cli.main(argv)
            except SystemExit:
                pass

    key = W.project_key(project)
    cli_run(["config-set", "--project", key, "genre=citypop", "subgenre=K-pop",
             "purpose=휴식", "situation=산책", "vocal_mode=vocal",
             "lyrics_language=ko", "subtitle_language=ko", "track_count=2",
             "track_seconds=180", "total_seconds=360", "bpm_min=88", "bpm_max=108",
             "mood_arc=calm-to-warm", "visual_preset=warm-film",
             "thumbnail_language=ko"])
    cli_run(["plan", "--project", key])
    cli_run(["track-set", "--project", key, "--index", "1",
             "title=첫 곡", "lyrical_theme=저녁 산책"])
    cli_run(["track-lyrics", "--project", key, "--index", "1", "--text",
             "[Verse]\n운동화 끈을 다시 묶고 문을 열어\n[Chorus]\n천천히 걸어도 돼"])
    cli_run(["track-set", "--project", key, "--index", "2",
             "title=둘째 곡", "lyrical_theme=돌아오는 길"])
    cli_run(["track-lyrics", "--project", key, "--index", "2", "--text",
             "[Verse]\n이제 그만 돌아설까 하다가\n[Chorus]\n돌아가는 길은 늘 짧아"])
    cli_run(["lyrics-collect", "--project", key])
    cli_run(["cost", "--project", key, "--model", "se-motion-music-t2a",
             "--balance", "134"])
    return key


def test_payload_button_returns_ready_to_submit_arguments(server, project):
    """② 제출 인자 만들기 가 부르는 경로. Claude 가 그대로 쓸 수 있어야 한다."""
    key = _project_ready_for_payload(project)
    status, r = post(server, "/api/query", {
        "command": "submit-payload",
        "args": ["--project", key, "--index", "1", "--claim"]})
    assert status == 200 and r["ok"] is True
    d = r["data"]
    assert d["mcp_tool"] == "abocado_generate_audio"
    assert d["arguments"]["model"] == "se-motion-music-t2a"   # ① 에서 고른 모델
    assert d["credits"] == 48
    assert d["claimed"] is True
    assert "lyrics_prompt" in d["arguments"]["options"]
    assert 10 <= len(d["arguments"]["prompt"]) <= 300          # Popcorn 1.0 한도


def test_payload_button_blocks_the_second_press(server, project):
    key = _project_ready_for_payload(project)
    args = ["--project", key, "--index", "1", "--claim"]
    post(server, "/api/query", {"command": "submit-payload", "args": args})
    status, r = post(server, "/api/query", {"command": "submit-payload", "args": args})
    assert r["ok"] is False
    assert r["data"]["blocked"] is True
    assert r["data"]["reason"] == "duplicate"


def test_release_button_unblocks_it_again(server, project):
    key = _project_ready_for_payload(project)
    args = ["--project", key, "--index", "1", "--claim"]
    post(server, "/api/query", {"command": "submit-payload", "args": args})
    status, rel = post(server, "/api/query", {
        "command": "ledger-release",
        "args": ["--project", key, "--index", "1", "--reason", "재시도"]})
    assert rel["ok"] is True
    status, again = post(server, "/api/query", {"command": "submit-payload", "args": args})
    assert again["ok"] is True and again["data"]["claimed"] is True


# ---------------------------------------------------------------- 화면 자동 갱신
def _app_js() -> str:
    from playlist_studio.webapp import WEB_DIR
    return (WEB_DIR / "app.js").read_text(encoding="utf-8")


def test_auto_refresh_is_guarded_against_wiping_open_dialogs():
    """자동 새로고침이 입력 중인 화면을 다시 그리면 붙여넣던 값이 사라진다.

    실제로 사용자가 결과 URL 을 복사해 오는 사이에 입력창이 닫히는 일이
    있었다. 가드가 지워지면 같은 문제가 재발한다.
    """
    js = _app_js()
    guard = js[js.index("setInterval("):]
    for condition in ("S.busy", "S.modalOpen", "sheet", "document.hidden",
                      "INPUT", "TEXTAREA", "SELECT"):
        assert condition in guard[:900], f"자동 새로고침 가드에 {condition} 조건이 없습니다"


def test_auto_refresh_interval_is_not_aggressive():
    js = _app_js()
    tail = js[js.index("setInterval("):]
    ms = int(tail.split("}, ")[1].split(")")[0])
    assert ms >= 60000, f"자동 새로고침이 {ms}ms 로 너무 잦습니다 (입력 시간이 부족)"


def test_modal_sets_and_clears_the_lock():
    js = _app_js()
    body = js[js.index("function modal("):js.index("function costDialog(")]
    assert "S.modalOpen = true;" in body
    assert body.count("S.modalOpen = false;") >= 2   # 취소 · 확인 양쪽
