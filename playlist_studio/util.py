"""공통 유틸 - 경로/해시/JSON/명령 실행.

경로는 전부 pathlib 로 다루고, JSON 에는 POSIX 상대경로만 저장한다.
(Windows / Linux / macOS 어디서 재개해도 같은 파일을 가리키게 하기 위함)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


# --------------------------------------------------------------------------
# 시간
# --------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------
# 경로
# --------------------------------------------------------------------------
def rel_posix(path: Path, root: Path) -> str:
    """root 기준 상대경로를 POSIX 문자열로. root 밖이면 절대 POSIX 경로."""
    path = Path(path)
    root = Path(root)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def from_rel(rel: str, root: Path) -> Path:
    """rel_posix 의 역변환. 절대경로가 들어오면 그대로 사용."""
    p = Path(rel)
    return p if p.is_absolute() else (Path(root) / p)


def ensure_dir(path: Path) -> Path:
    Path(path).mkdir(parents=True, exist_ok=True)
    return Path(path)


_SLUG_KEEP = re.compile(r"[^a-z0-9]+")

# 한글 -> 로마자 (국어의 로마자 표기법 근사).
# 폴더 이름을 사람이 알아볼 수 있게 만드는 것이 목적이므로 음운 변동은 적용하지 않는다.
_HANGUL_BASE = 0xAC00
_HANGUL_LAST = 0xD7A3
_CHO = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j",
        "jj", "ch", "k", "t", "p", "h")
_JUNG = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae",
         "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i")
_JONG = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l",
         "p", "l", "m", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t")


def romanize_hangul(text: str) -> str:
    """한글 음절을 로마자로. 한글이 아닌 문자는 그대로 통과시킨다."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", str(text)):
        code = ord(ch)
        if _HANGUL_BASE <= code <= _HANGUL_LAST:
            idx = code - _HANGUL_BASE
            cho, rem = divmod(idx, 588)
            jung, jong = divmod(rem, 28)
            out.append(_CHO[cho] + _JUNG[jung] + _JONG[jong])
        else:
            out.append(ch)
    return "".join(out)


def slugify(text: str, fallback: str = "item", max_len: int = 48) -> str:
    """파일시스템 안전 slug.

    한글은 로마자로 음차한다. 그 외 비ASCII(일본어·중국어 등)는 제거되므로
    전부 사라지면 fallback 을 쓴다. 원문은 CHANNEL.md 와 json 에 그대로
    남으므로 정보 손실은 없다.
    """
    text = romanize_hangul(str(text))
    norm = unicodedata.normalize("NFKD", text)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_KEEP.sub("-", ascii_only).strip("-")
    slug = slug[:max_len].strip("-")
    return slug or fallback


def safe_filename(text: str, fallback: str = "file") -> str:
    """Windows 예약문자를 제거한 파일명."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(text)).strip(" .")
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    return cleaned[:120] or fallback


# --------------------------------------------------------------------------
# 해시
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_WS = re.compile(r"[ \t\u3000]+")


def normalize_lyrics(text: str) -> str:
    """가사 비교용 정규화.

    - 유니코드 NFC
    - CRLF -> LF
    - 각 줄 양끝 공백 제거, 내부 연속 공백 1칸
    - 빈 줄 제거
    - 소문자화하지 않는다 (한글에는 무의미하고 영문 대소문자 차이는 의미가 있을 수 있음)
    """
    text = str(text).replace("\ufeff", "")          # BOM / 제로폭 공백 제거
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def lyrics_fingerprint(text: str) -> str:
    return sha256_text(normalize_lyrics(text))


# --------------------------------------------------------------------------
# JSON (원자적 쓰기)
# --------------------------------------------------------------------------
def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> Path:
    """같은 디렉터리에 임시파일을 쓰고 os.replace 로 교체 (중단 시 파손 방지)."""
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def read_text(path: Path, default: str | None = None) -> str | None:
    """텍스트 파일 읽기.

    utf-8-sig 로 읽는다. Windows PowerShell 의 `Set-Content -Encoding UTF8` 은
    파일 앞에 BOM(U+FEFF)을 붙이는데, 그대로 읽으면 첫 줄의 `[Intro]` 같은
    구조 태그가 태그로 인식되지 않는다. utf-8-sig 는 BOM 이 있으면 벗기고
    없으면 일반 UTF-8 로 읽으므로 양쪽 모두 안전하다.
    """
    path = Path(path)
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8-sig")


# --------------------------------------------------------------------------
# 외부 명령
# --------------------------------------------------------------------------
class ToolMissing(RuntimeError):
    pass


class CommandFailed(RuntimeError):
    def __init__(self, cmd: Sequence[str], returncode: int, stderr: str):
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-25:])
        super().__init__(f"명령 실패 (exit {returncode}): {' '.join(map(str, cmd))}\n{tail}")


def which(name: str) -> str | None:
    """ffmpeg/ffprobe 탐색. PATH 우선, 없으면 imageio-ffmpeg 번들, 흔한 설치 경로."""
    found = shutil.which(name)
    if found:
        return found
    if name in ("ffmpeg", "ffprobe"):
        env = os.environ.get(f"{name.upper()}_BINARY")
        if env and Path(env).exists():
            return env
        if name == "ffmpeg":
            try:  # pragma: no cover - 선택적 의존성
                import imageio_ffmpeg

                return imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
        candidates = [
            Path("C:/ffmpeg/bin") / f"{name}.exe",
            Path("C:/Program Files/ffmpeg/bin") / f"{name}.exe",
            Path.home() / "scoop" / "shims" / f"{name}.exe",
            Path("/usr/local/bin") / name,
            Path("/opt/homebrew/bin") / name,
        ]
        for c in candidates:
            if c.exists():
                return str(c)
    return None


def require(name: str) -> str:
    found = which(name)
    if not found:
        raise ToolMissing(
            f"'{name}' 을 찾을 수 없습니다. PATH 에 추가하거나 환경변수 "
            f"{name.upper()}_BINARY 로 실행파일 경로를 지정하세요."
        )
    return found


def run(cmd: Sequence[str], *, cwd: Path | None = None, timeout: int = 3600,
        check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise CommandFailed(cmd, proc.returncode, proc.stderr or proc.stdout or "")
    return proc


def ffmpeg(args: Sequence[str], *, timeout: int = 3600) -> subprocess.CompletedProcess:
    """-y -hide_banner -nostdin 을 자동으로 앞에 붙인다."""
    exe = require("ffmpeg")
    return run([exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args], timeout=timeout)


def ffprobe_json(target: Path, *, streams: bool = True, fmt: bool = True) -> dict:
    exe = require("ffprobe")
    args = [exe, "-v", "error", "-print_format", "json"]
    if streams:
        args += ["-show_streams"]
    if fmt:
        args += ["-show_format"]
    args += [str(target)]
    proc = run(args, timeout=180)
    return json.loads(proc.stdout or "{}")


# --------------------------------------------------------------------------
# 표시
# --------------------------------------------------------------------------
def hhmmss(seconds: float, *, force_hours: bool = False) -> str:
    seconds = max(0.0, float(seconds))
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h or force_hours:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    ms_total = int(round(seconds * 1000))
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    cs_total = int(round(seconds * 100))
    h, rem = divmod(cs_total, 360_000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)
