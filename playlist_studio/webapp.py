"""웹 대시보드 - 핸드폰·태블릿·다른 PC 에서 브라우저로 조종한다.

설계 원칙
  - 추가 설치 없음. 파이썬 표준 라이브러리만 쓴다.
  - 서버는 CLI 를 대신 실행할 뿐이다. 스스로 MCP 를 부르지 않으므로
    이 화면에서 조작해도 **크레딧이 소모되지 않는다.**
  - 실행할 수 있는 명령은 CLI 하위 명령으로 화이트리스트를 건다.
    임의 셸 명령은 절대 실행하지 않는다.
  - 접속 토큰이 없으면 아무 API 도 응답하지 않는다.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import threading
import time
import uuid
import sys as _sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .paths import iter_projects, studio_root
from .util import read_json

WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_LOG_CHARS = 200_000
JOB_KEEP = 40

# 실행을 허용하는 CLI 하위 명령. 여기 없는 것은 거부한다.
# CLI 자체가 MCP 를 부르지 않으므로 전부 크레딧 0 이다.
ALLOWED = {
    "doctor", "selftest",
    "channel-new", "channel-list", "playlist-new", "list",
    "config-status", "config-set", "config-show",
    "plan", "dna-show", "dna-set",
    "track-set", "track-lyrics", "lyrics-validate", "lyrics-collect",
    "cost", "submit-payload", "ledger-show", "ledger-release", "track-import",
    "pilot-status", "pilot-approve", "pilot-reject", "batch-status",
    "visual-prompts", "image-import", "thumbnail", "visuals-done",
    "build-audio", "align", "subtitles", "metadata", "render", "qa",
    "status", "resume", "verify", "clean",
}

# 오래 걸리는 명령 (프론트가 진행 표시를 다르게 한다)
SLOW = {"render", "build-audio", "align", "selftest", "thumbnail"}


# ---------------------------------------------------------------- 작업 실행
class Job:
    def __init__(self, argv: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.argv = argv
        self.command = argv[0] if argv else ""
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.returncode: int | None = None
        self.log = ""
        self.lock = threading.Lock()

    def append(self, text: str) -> None:
        with self.lock:
            self.log = (self.log + text)[-MAX_LOG_CHARS:]

    def to_dict(self, with_log: bool = True) -> dict:
        with self.lock:
            log = self.log if with_log else ""
        return {
            "id": self.id, "command": self.command, "argv": self.argv,
            "running": self.finished_at is None,
            "returncode": self.returncode,
            "elapsed": round((self.finished_at or time.time()) - self.started_at, 1),
            "slow": self.command in SLOW,
            "log": log,
        }


class Runner:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.order: list[str] = []
        self.lock = threading.Lock()

    def start(self, argv: list[str]) -> Job:
        job = Job(argv)
        with self.lock:
            self.jobs[job.id] = job
            self.order.append(job.id)
            while len(self.order) > JOB_KEEP:
                self.jobs.pop(self.order.pop(0), None)
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        cmd = [sys.executable, "-m", "playlist_studio", *job.argv]
        job.append("$ " + " ".join(shlex.quote(c) for c in cmd[2:]) + "\n\n")
        try:
            env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                cwd=str(Path(__file__).resolve().parent.parent), env=env)
            assert proc.stdout is not None
            for line in proc.stdout:
                job.append(line)
            proc.wait()
            job.returncode = proc.returncode
        except Exception as e:
            job.append(f"\n[서버 오류] {type(e).__name__}: {e}\n")
            job.returncode = -1
        finally:
            job.finished_at = time.time()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def recent(self, n: int = 12) -> list[dict]:
        with self.lock:
            ids = self.order[-n:][::-1]
        return [self.jobs[i].to_dict(with_log=False) for i in ids if i in self.jobs]


RUNNER = Runner()


# ---------------------------------------------------------------- 동기 실행
def run_sync(argv: list[str], timeout: int = 90) -> dict:
    """--json 을 붙여 즉시 결과를 받는다 (조회성 명령 전용)."""
    cmd = [sys.executable, "-m", "playlist_studio", "--json", *argv]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
            cwd=str(Path(__file__).resolve().parent.parent),
            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"시간 초과 ({timeout}초)"}
    out = (proc.stdout or "").strip()
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        return {"ok": False, "error": "출력을 읽을 수 없습니다",
                "raw": (out or proc.stderr or "")[-4000:]}
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "data": data}


# ---------------------------------------------------------------- 요약 조립
STEP_TITLES = [
    "채널 만들기", "플레이리스트 설정", "전체 가사 작성",
    "파일럿 첫 곡 생성·승인", "나머지 곡 생성", "썸네일·배경 이미지",
    "음원 병합·가사 정렬", "제목·설명·챕터", "최종 렌더링·QA",
]
STEP_KEYS = ["channel", "plan", "lyrics", "pilot", "batch", "visuals",
             "align", "metadata", "render"]


def project_key(p) -> str:
    return f"{p.root.parent.parent.name}/{p.root.name}"


def project_summary(p) -> dict:
    ws = read_json(p.workspace, {}) or {}
    cfg_raw = None
    try:
        import yaml
        cfg_raw = yaml.safe_load(p.config.read_text(encoding="utf-8")) if p.config.exists() else {}
    except Exception:
        cfg_raw = {}
    tracks_doc = read_json(p.tracks, {}) or {}
    tracks = tracks_doc.get("tracks", []) if isinstance(tracks_doc, dict) else tracks_doc
    steps = ws.get("steps", {})
    done = sum(1 for k in STEP_KEYS if steps.get(k, {}).get("status") == "done")
    failed = [STEP_TITLES[i] for i, k in enumerate(STEP_KEYS)
              if steps.get(k, {}).get("status") == "failed"]
    next_i = next((i for i, k in enumerate(STEP_KEYS)
                   if steps.get(k, {}).get("status") != "done"), None)
    timing = read_json(p.root / "timing.json", {}) or {}
    qa = read_json(p.qa_report_json, None)
    return {
        "key": project_key(p),
        "path": str(p.root),
        "title": (cfg_raw or {}).get("playlist_title") or p.root.name,
        "channel": p.root.parent.parent.name,
        "state": ws.get("state", "?"),
        "updated_at": ws.get("updated_at", ""),
        "steps": [
            {"n": i + 1, "key": k, "title": STEP_TITLES[i],
             "status": steps.get(k, {}).get("status", "pending"),
             "note": steps.get(k, {}).get("note", ""),
             "error": steps.get(k, {}).get("error", "")}
            for i, k in enumerate(STEP_KEYS)
        ],
        "done_steps": done,
        "total_steps": len(STEP_KEYS),
        "failed_steps": failed,
        "next_step": None if next_i is None else
                     {"n": next_i + 1, "key": STEP_KEYS[next_i], "title": STEP_TITLES[next_i]},
        "config": cfg_raw or {},
        "tracks": tracks,
        "timing": {"total_duration": timing.get("total_duration"),
                   "tracks": timing.get("tracks", []),
                   "report": timing.get("report")},
        "qa": None if not qa else {"verdict": qa.get("verdict"),
                                   "counts": qa.get("counts"),
                                   "checks": qa.get("checks", [])},
        "files": file_map(p),
        "credits_spent": sum(
            int(e.get("credits") or 0)
            for e in (read_json(p.ledger, {}) or {}).get("entries", {}).values()
            if e.get("status") == "done"),
    }


def file_map(p) -> dict:
    def rel(path: Path) -> str | None:
        return path.relative_to(p.root).as_posix() if path.exists() else None
    out = {
        "final_mp4": rel(p.final_mp4),
        "thumbnail": rel(p.thumbnail),
        "intro": rel(p.intro_image),
        "srt": rel(p.srt),
        "ass": rel(p.ass),
        "lyrics_all": rel(p.lyrics_all),
        "qa_md": rel(p.qa_report_md),
        "master": rel(p.master_wav),
        "meta": {},
        "thumb_candidates": [],
        "backgrounds": {},
        "audio": {},
    }
    for name in ("youtube_title.txt", "youtube_description.txt", "chapters.txt",
                 "tags.txt", "generation_disclosure.txt", "rights.json"):
        r = rel(p.meta / name)
        if r:
            out["meta"][name] = r
    for i in range(1, 5):
        r = rel(p.thumb_candidate(i))
        if r:
            out["thumb_candidates"].append({"slot": i, "path": r})
    if p.images_bg.exists():
        for f in sorted(p.images_bg.glob("*.png")):
            out["backgrounds"][f.stem] = f.relative_to(p.root).as_posix()
    if p.audio_raw.exists():
        for f in sorted(p.audio_raw.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
                out["audio"][f.stem] = f.relative_to(p.root).as_posix()
    return out


def find_project_root(key: str) -> Path | None:
    for p in iter_projects():
        if project_key(p) == key or str(p.root) == key or p.root.name == key:
            return p.root
    return None


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "playlist-studio"
    token = ""

    # --- 유틸 ---
    def _json(self, data: Any, code: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, text: str, code: int = 200, ctype: str = "text/plain") -> None:
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self, q: dict) -> bool:
        if not Handler.token:
            return True
        given = (self.headers.get("X-Token")
                 or (q.get("t", [""])[0] if q else ""))
        return secrets.compare_digest(given or "", Handler.token)

    def log_message(self, fmt: str, *args) -> None:      # 콘솔을 조용히
        pass

    # --- 라우팅 ---
    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = unquote(u.path)

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
            return
        if path == "/app.css":
            self._serve_static("app.css")
            return
        if path == "/app.js":
            self._serve_static("app.js")
            return
        if path == "/favicon.ico":
            self._text("", 404)
            return

        if not self._authorized(q):
            self._json({"error": "접속 토큰이 필요합니다. 서버가 출력한 주소로 다시 들어오세요."}, 401)
            return

        if path == "/api/bootstrap":
            self._json(self._bootstrap())
        elif path == "/api/projects":
            self._json({"projects": [project_summary(p) for p in iter_projects()]})
        elif path.startswith("/api/project/"):
            key = path[len("/api/project/"):]
            root = find_project_root(key)
            if root is None:
                self._json({"error": f"프로젝트를 찾을 수 없습니다: {key}"}, 404)
                return
            from .paths import ProjectPaths
            self._json(project_summary(ProjectPaths(root)))
        elif path.startswith("/api/job/"):
            job = RUNNER.get(path[len("/api/job/"):])
            self._json(job.to_dict() if job else {"error": "없는 작업"}, 200 if job else 404)
        elif path == "/api/jobs":
            self._json({"jobs": RUNNER.recent()})
        elif path == "/api/questions":
            key = q.get("project", [""])[0]
            self._json(run_sync(["config-status", "--project", key, "--limit", "12"]))
        elif path == "/api/text":
            self._serve_text_file(q)
        elif path == "/media":
            self._serve_media(q)
        else:
            self._json({"error": "없는 경로"}, 404)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._authorized(q):
            self._json({"error": "접속 토큰이 필요합니다."}, 401)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "잘못된 요청 형식"}, 400)
            return

        path = unquote(u.path)
        if path == "/api/run":
            self._run(payload, background=True)
        elif path == "/api/query":
            self._run(payload, background=False)
        else:
            self._json({"error": "없는 경로"}, 404)

    # --- 핸들러 본체 ---
    def _bootstrap(self) -> dict:
        doc = run_sync(["doctor"], timeout=120)
        d = doc.get("data", {}) if doc.get("ok") is not None else {}
        return {
            "studio_root": str(studio_root()),
            "doctor": {
                "ready": d.get("ready", False),
                "blockers": d.get("blockers", []),
                "warnings": d.get("warnings", []),
                "ffmpeg": bool(d.get("ffmpeg", {}).get("found")),
                "ffmpeg_version": d.get("ffmpeg", {}).get("version", ""),
                "whisper": bool(d.get("packages", {}).get("faster_whisper")),
                "fonts": d.get("fonts", []),
                "platform": d.get("platform", {}),
            },
            "projects": [project_summary(p) for p in iter_projects()],
            "music_models": self._music_models(),
        }

    @staticmethod
    def _music_models() -> list[dict]:
        from .cost import MUSIC_MODELS, SNAPSHOT_TAKEN_AT
        return [{"key": k, "display": v["display"], "credits": v["credits"],
                 "note": v["note"], "snapshot": SNAPSHOT_TAKEN_AT}
                for k, v in sorted(MUSIC_MODELS.items(), key=lambda x: x[1]["credits"])]

    def _run(self, payload: dict, *, background: bool) -> None:
        cmd = str(payload.get("command", "")).strip()
        if cmd not in ALLOWED:
            self._json({"error": f"허용되지 않은 명령입니다: {cmd or '(빈 값)'}"}, 400)
            return
        raw_args = payload.get("args") or []
        if not isinstance(raw_args, list):
            self._json({"error": "args 는 배열이어야 합니다."}, 400)
            return
        args: list[str] = []
        for a in raw_args:
            if not isinstance(a, (str, int, float)):
                self._json({"error": "args 원소는 문자열이어야 합니다."}, 400)
                return
            args.append(str(a))
        argv = [cmd, *args]
        if background:
            job = RUNNER.start(argv)
            self._json({"job": job.to_dict(with_log=False)})
        else:
            self._json(run_sync(argv))

    def _resolve_in_project(self, q: dict) -> Path | None:
        key = q.get("project", [""])[0]
        rel = q.get("path", [""])[0]
        root = find_project_root(key)
        if root is None or not rel:
            return None
        target = (root / rel).resolve()
        try:
            target.relative_to(root.resolve())        # 경로 탈출 차단
        except ValueError:
            return None
        return target if target.is_file() else None

    def _serve_text_file(self, q: dict) -> None:
        target = self._resolve_in_project(q)
        if target is None:
            self._json({"error": "파일을 찾을 수 없습니다."}, 404)
            return
        if target.stat().st_size > 2_000_000:
            self._json({"error": "파일이 너무 큽니다."}, 413)
            return
        try:
            self._json({"path": q.get("path", [""])[0],
                        "text": target.read_text(encoding="utf-8-sig", errors="replace")})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _serve_media(self, q: dict) -> None:
        target = self._resolve_in_project(q)
        if target is None:
            self._text("파일 없음", 404)
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        size = target.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        partial = False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                s, e = m.group(1), m.group(2)
                if s:
                    start = min(int(s), size - 1)
                    end = min(int(e), size - 1) if e else size - 1
                elif e:                                   # 마지막 N 바이트
                    start = max(0, size - int(e))
                partial = True
        length = max(0, end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(target, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # 브라우저가 탐색바를 움직이거나 페이지를 떠나면 전송 중인 연결을
            # 그냥 끊는다. 정상 동작이므로 조용히 넘어간다.
            pass

    def _serve_static(self, name: str) -> None:
        f = WEB_DIR / name
        if not f.exists():
            self._text("웹 파일이 없습니다.", 500)
            return
        ctype = {"html": "text/html", "css": "text/css",
                 "js": "application/javascript"}[name.rsplit(".", 1)[1]]
        self._text(f.read_text(encoding="utf-8"), 200, ctype)


class QuietHTTPServer(ThreadingHTTPServer):
    """클라이언트가 끊어서 나는 예외로 화면을 어지럽히지 않는 서버.

    영상 탐색·페이지 이동 때마다 브라우저가 전송 중인 연결을 끊는데,
    기본 서버는 그때마다 traceback 을 통째로 출력한다. 정상 동작이라
    사용자에게는 오류로 보일 뿐이므로 조용히 넘긴다. 진짜 오류는 그대로 낸다.
    """

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        exc = _sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            ConnectionAbortedError, TimeoutError)):
            return
        super().handle_error(request, client_address)


# ---------------------------------------------------------------- 실행
def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def serve(host: str = "0.0.0.0", port: int = 8765, token: str | None = None,
          open_browser: bool = False) -> None:
    Handler.token = token if token is not None else secrets.token_urlsafe(9)
    httpd = QuietHTTPServer((host, port), Handler)
    ip = lan_ip()
    suffix = f"?t={Handler.token}" if Handler.token else ""
    local = f"http://127.0.0.1:{port}/{suffix}"
    remote = f"http://{ip}:{port}/{suffix}"

    line = "─" * 62
    print(f"\n{line}")
    print("  🎧  플레이리스트 스튜디오 — 웹 대시보드")
    print(line)
    print(f"  이 PC에서       {local}")
    if host in ("0.0.0.0", "::"):
        print(f"  같은 Wi-Fi 기기  {remote}")
        print(f"                  ↑ 핸드폰 브라우저에 이 주소를 그대로 입력하세요")
    print(f"\n  스튜디오 폴더    {studio_root()}")
    print(f"  중지            Ctrl+C")
    print(f"{line}\n")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(local)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        httpd.server_close()
