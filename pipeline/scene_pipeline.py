# story.json 의 모든 씬을 순서대로 이미지·영상·나레이션·합성까지 처리하는 멀티씬 제작 파이프라인 오케스트레이터
"""
Multi-Scene Production Pipeline (Phase 8)

목적.
  - 단일 씬 파이프라인을 story.json 의 전체 씬으로 확장한다.
  - 씬마다: 이미지(Nano Banana) → 영상(Higgsfield MCP) → 나레이션(Edge TTS) → 합성(FFmpeg).

설계 원칙.
  - 기존 provider/executor/composer 를 재사용한다. provider 로직을 복제하지 않는다.
  - 각 단계는 주입 가능한 콜러블(steps)이다. 기본은 mock, real 은 명시적으로만.
  - 이미 유효한 산출물은 overwrite=True 가 아니면 건너뛴다(중복 provider 호출 없음).
  - 한 씬이 실패하면 파이프라인을 안전하게 멈춘다(이후 씬 미처리).
  - 씬별 상태/에러를 기록한다.
  - 전체 씬을 이어붙이지 않는다. 업로드하지 않는다.

아키텍처 메모.
  - 이 모듈은 별도 프로세스라 에이전트의 MCP 세션에 직접 접근할 수 없다.
  - 실 Higgsfield 영상은 make_mcp_writer 로 만든 writer 를 mcp_video_writer 로 주입받거나,
    에이전트가 미리 만들어 둔 유효한 영상 파일을 '기존 유효 자산'으로 소비한다(skip 경로).
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _p in (_ROOT, os.path.join(_ROOT, "providers"), os.path.join(_ROOT, "executors"),
           os.path.join(_ROOT, "composer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_MP4_FTYP = b"ftyp"
_MP3_SIGS = (b"ID3",)


# ---------------------------------------------------------------------------
# 경로/검증
# ---------------------------------------------------------------------------

def scene_paths(out_root, n):
    """씬 번호 n(1-base) 의 표준 산출 경로."""
    tag = f"scene_{n:03d}"
    return {
        "image": os.path.join(out_root, "images", f"{tag}.png"),
        "video": os.path.join(out_root, "videos", f"{tag}.mp4"),
        "audio": os.path.join(out_root, "audio", f"{tag}.mp3"),
        "final": os.path.join(out_root, "final", f"{tag}_final.mp4"),
    }


def _nonempty(path):
    return bool(path) and os.path.exists(path) and os.path.getsize(path) > 0


def valid_png(path):
    return _nonempty(path) and open(path, "rb").read(8) == _PNG_SIG


def valid_mp4(path):
    if not _nonempty(path):
        return False
    return open(path, "rb").read(12)[4:8] == _MP4_FTYP


def valid_mp3(path):
    if not _nonempty(path):
        return False
    head = open(path, "rb").read(3)
    return head in _MP3_SIGS or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)


_VALIDATORS = {"image": valid_png, "video": valid_mp4, "audio": valid_mp3, "final": valid_mp4}


# ---------------------------------------------------------------------------
# 기본 단계(steps): 기존 provider 재사용 래퍼. real=False 는 오프라인 placeholder.
# ---------------------------------------------------------------------------

def _ensure_dir(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _mock_image_step(scene, out_path, **_):
    _ensure_dir(out_path)
    with open(out_path, "wb") as f:
        f.write(_PNG_SIG + b"\x00" * 32)


def _mock_video_step(scene, image_path, out_path, **_):
    _ensure_dir(out_path)
    with open(out_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42mock" + b"\x00" * 16)


def _mock_tts_step(scene, out_path, **_):
    _ensure_dir(out_path)
    with open(out_path, "wb") as f:
        f.write(b"ID3" + b"\x00" * 64)


def _mock_compose_step(scene, video_path, audio_path, out_path, **_):
    _ensure_dir(out_path)
    with open(out_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypisommock" + b"\x00" * 16)


def _real_image_step(scene, out_path, **_):
    """Nano Banana provider 재사용. scene.image_prompt 로 실 이미지 생성 후 out_path 로 이동."""
    from nano_banana_provider import generate, PROVIDER, CAPABILITY
    from provider_sdk import make_request
    _ensure_dir(out_path)
    req = make_request(PROVIDER, CAPABILITY, prompt=scene["image_prompt"])
    res = generate(req, output_dir=os.path.dirname(out_path), real=True)
    if res["status"] != "success":
        raise RuntimeError(res["message"])
    src = os.path.join(_ROOT, res["output"]["path"])
    if os.path.abspath(src) != os.path.abspath(out_path):
        os.replace(src, out_path)


def _real_tts_step(scene, out_path, **_):
    """Edge TTS executor 재사용. scene.narration 으로 실 mp3 생성 후 out_path 로 이동."""
    from edge_tts_executor import run, DEFAULT_VOICE, DEFAULT_RATE
    _ensure_dir(out_path)
    payload = {"provider": "Edge TTS", "action": "text_to_speech", "prompt": scene["narration"],
               "parameters": {"engine": "edge-tts", "voice": DEFAULT_VOICE, "rate": DEFAULT_RATE}}
    res = run(payload, output_dir=os.path.dirname(out_path))
    if res["status"] != "success":
        raise RuntimeError(res["message"])
    src = os.path.join(_ROOT, res["output_path"])
    if os.path.abspath(src) != os.path.abspath(out_path):
        os.replace(src, out_path)


def _make_real_video_step(mcp_video_writer):
    """
    실 Higgsfield 영상 단계. Higgsfield provider 의 writer-injection 을 재사용한다.
    mcp_video_writer(=make_mcp_writer 결과) 가 주입되지 않으면, 실 영상은 이 프로세스에서
    직접 생성할 수 없으므로 명확히 실패한다(에이전트가 미리 만든 유효 영상은 skip 경로로 소비).
    """
    def _step(scene, image_path, out_path, **_):
        if mcp_video_writer is None:
            raise RuntimeError(
                "실 Higgsfield 영상은 MCP writer 주입 또는 미리 준비된 유효 영상 파일이 필요하다. "
                "(별도 프로세스는 에이전트 MCP 세션에 직접 접근 불가)")
        from higgsfield_provider import generate, PROVIDER, CAPABILITY
        from provider_sdk import make_request
        _ensure_dir(out_path)
        req = make_request(PROVIDER, CAPABILITY, prompt=scene["video_prompt"], inputs=[image_path])
        res = generate(req, output_dir=os.path.dirname(out_path), writer=mcp_video_writer)
        if res["status"] != "success":
            raise RuntimeError(res["message"])
        src = os.path.join(_ROOT, res["output"]["path"])
        if os.path.abspath(src) != os.path.abspath(out_path):
            os.replace(src, out_path)
    return _step


def _real_compose_step(scene, video_path, audio_path, out_path, **_):
    """
    합성: 영상 위에 나레이션을 최종 오디오로 얹는다. 나레이션이 길면 마지막 프레임을 고정(clone)해
    영상을 늘리고 나레이션을 자르지 않는다. H.264/AAC/yuv420p/+faststart, 원본 해상도 유지.
    ffmpeg 바이너리 해석은 기존 composer 를 재사용한다(중복 없음).
    """
    import re
    import subprocess

    from ffmpeg_composer import ffmpeg_binary
    ff = ffmpeg_binary()
    if not ff:
        raise RuntimeError("로컬 ffmpeg 를 찾을 수 없다.")
    _ensure_dir(out_path)

    def _dur(f):
        err = subprocess.run([ff, "-hide_banner", "-i", f], capture_output=True, text=True).stderr
        m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
        if not m:
            return None
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)

    vdur, adur = _dur(video_path), _dur(audio_path)
    fc = None
    if vdur is not None and adur is not None:
        if adur > vdur:  # 오디오가 길다 → 영상 마지막 프레임 고정으로 연장
            fc = f"[0:v]tpad=stop_mode=clone:stop_duration={adur - vdur + 1:.3f}[v]"
        elif vdur > adur:  # 영상이 길다 → 오디오를 무음으로 패딩
            fc = None  # 아래에서 apad 로 처리
    args = [ff, "-y", "-i", video_path, "-i", audio_path]
    if fc:
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "1:a:0"]
    elif vdur is not None and adur is not None and vdur > adur:
        args += ["-filter_complex", "[1:a]apad[a]", "-map", "0:v:0", "-map", "[a]"]
    else:
        args += ["-map", "0:v:0", "-map", "1:a:0"]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", "-shortest", out_path]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 합성 실패: {r.stderr[-500:]}")


def default_steps(real=False, mcp_video_writer=None):
    """실행 모드에 맞는 기본 단계 집합. mock 이 기본, real 은 명시적."""
    if not real:
        return {"image": _mock_image_step, "video": _mock_video_step,
                "tts": _mock_tts_step, "compose": _mock_compose_step}
    return {"image": _real_image_step, "video": _make_real_video_step(mcp_video_writer),
            "tts": _real_tts_step, "compose": _real_compose_step}


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------

def _run_step(kind, out_key, validator, call, paths, overwrite):
    """단계 하나 실행(+skip 판정). 반환: (status_dict, ok)."""
    out_path = paths[out_key]
    if not overwrite and validator(out_path):
        return {"status": "skipped", "path": out_path, "error": None}, True
    try:
        call(out_path)
        if not validator(out_path):
            raise RuntimeError(f"{kind} 산출물이 유효하지 않다: {out_path}")
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "path": None, "error": f"{type(e).__name__}: {e}"}, False
    return {"status": "generated", "path": out_path, "error": None}, True


def process_scene(scene, out_root, steps, overwrite=False):
    """한 씬을 이미지→영상→나레이션→합성 순서로 처리. 첫 실패에서 멈춘다."""
    n = scene["scene_number"]
    paths = scene_paths(out_root, n)
    record = {"scene_number": n, "steps": {}, "status": "success"}

    order = [
        ("image", "image", _VALIDATORS["image"],
         lambda o: steps["image"](scene, o)),
        ("video", "video", _VALIDATORS["video"],
         lambda o: steps["video"](scene, paths["image"], o)),
        ("tts", "audio", _VALIDATORS["audio"],
         lambda o: steps["tts"](scene, o)),
        ("compose", "final", _VALIDATORS["final"],
         lambda o: steps["compose"](scene, paths["video"], paths["audio"], o)),
    ]
    for kind, out_key, validator, call in order:
        st, ok = _run_step(kind, out_key, validator, call, paths, overwrite)
        record["steps"][kind] = st
        if not ok:
            record["status"] = "failed"
            record["failed_step"] = kind
            break
    return record


def run_pipeline(story_path, out_root, real=False, overwrite=False,
                 steps=None, mcp_video_writer=None, stop_on_failure=True):
    """
    story.json 의 모든 씬을 순서대로 처리한다.
    real=False(기본) 은 오프라인 mock. real=True 는 기존 provider 재사용.
    반환: {"status", "scenes":[record...], (실패 시)"failed_scene"}.
    """
    import json
    with open(story_path, encoding="utf-8") as f:
        story = json.load(f)
    scenes = sorted(story["scenes"], key=lambda s: s["scene_number"])
    steps = steps or default_steps(real=real, mcp_video_writer=mcp_video_writer)

    report = {"status": "success", "scenes": []}
    for scene in scenes:
        rec = process_scene(scene, out_root, steps, overwrite=overwrite)
        report["scenes"].append(rec)
        if rec["status"] != "success":
            report["status"] = "failed"
            report["failed_scene"] = rec["scene_number"]
            if stop_on_failure:
                break
    return report


if __name__ == "__main__":
    import json
    import sys as _sys
    real = "--real" in _sys.argv
    overwrite = "--overwrite" in _sys.argv
    rep = run_pipeline(os.path.join(_ROOT, "output", "malli", "story.json"),
                       os.path.join(_ROOT, "output", "malli"),
                       real=real, overwrite=overwrite)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
