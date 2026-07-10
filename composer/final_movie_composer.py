# scene_*_final.mp4 들을 씬 번호 순으로 이어붙여 malli_final.mp4 한 편으로 만드는 최종 영화 합성기
"""
Final Movie Composer (Phase 9)

목적.
  - output/malli/final/scene_*_final.mp4 를 자동 탐지·정렬해 하나의 최종 영화로 이어붙인다.
  - 스트림 파라미터가 같으면 재인코딩 없이(-c copy) concat, 다르면 안전 재인코딩으로 폴백.
  - H.264 + AAC, +faststart 유지. 최종 결과를 검증한다.

설계.
  - ffmpeg 바이너리 해석은 기존 ffmpeg_composer 를 재사용한다(중복 없음).
  - runner/prober/validator 를 주입 가능하게 해 네트워크·ffmpeg 없이 테스트한다.
  - 새 자산을 생성하지 않는다. 기존 scene_final.mp4 만 입력으로 쓴다.
  - 다른 공급자(Claude/Nano Banana/Higgsfield/Edge TTS)를 호출하지 않는다.
"""

import glob
import os
import re
import subprocess
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys  # noqa: E402
if os.path.join(_ROOT, "composer") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "composer"))

from ffmpeg_composer import ffmpeg_binary  # noqa: E402

_SCENE_RE = re.compile(r"scene_(\d+)_final\.mp4$")
_MP4_FTYP = b"ftyp"


# ---------------------------------------------------------------------------
# 탐지/정렬/누락 검사
# ---------------------------------------------------------------------------

def discover_scenes(final_dir):
    """
    final_dir 에서 scene_*_final.mp4 를 탐지해 씬 번호 오름차순으로 반환한다.
    반환: (scenes, missing)
      scenes  = [(n, path), ...] 번호순
      missing = 1..max 중 빠진 번호 리스트(연속성 검사)
    malli_final.mp4 등 병합 산출물은 제외한다.
    """
    found = {}
    for p in glob.glob(os.path.join(final_dir, "scene_*_final.mp4")):
        m = _SCENE_RE.search(os.path.basename(p))
        if m:
            found[int(m.group(1))] = p
    scenes = [(n, found[n]) for n in sorted(found)]
    missing = []
    if scenes:
        hi = scenes[-1][0]
        missing = [i for i in range(1, hi + 1) if i not in found]
    return scenes, missing


# ---------------------------------------------------------------------------
# 프로브/검증 (기본은 실제 ffmpeg 파싱)
# ---------------------------------------------------------------------------

def _ffmpeg_info(path, ff):
    err = subprocess.run([ff, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    v = re.search(r"Video: (\w+).*?, (\d+)x(\d+)", err)
    a = re.search(r"Audio: (\w+).*?, (\d+) Hz", err)
    px = re.search(r"Video: \w+ [^,]*, (\w+)\(", err)
    dur = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err)
    d = None
    if dur:
        h, mi, s = dur.groups()
        d = int(h) * 3600 + int(mi) * 60 + float(s)
    return {
        "vcodec": v.group(1) if v else None,
        "width": int(v.group(2)) if v else None,
        "height": int(v.group(3)) if v else None,
        "pix_fmt": px.group(1) if px else None,
        "acodec": a.group(1) if a else None,
        "sample_rate": int(a.group(2)) if a else None,
        "duration": d,
        "has_video": v is not None,
        "has_audio": a is not None,
    }


def _default_prober(paths):
    ff = ffmpeg_binary()
    if not ff:
        raise RuntimeError("로컬 ffmpeg 를 찾을 수 없다.")
    return [_ffmpeg_info(p, ff) for p in paths]


def _default_validator(path):
    ff = ffmpeg_binary()
    info = _ffmpeg_info(path, ff) if ff else {}
    sig = os.path.exists(path) and os.path.getsize(path) > 0 and \
        open(path, "rb").read(12)[4:8] == _MP4_FTYP
    return {
        "mp4_signature": bool(sig),
        "has_video": info.get("has_video", False),
        "has_audio": info.get("has_audio", False),
        "duration": info.get("duration"),
        "width": info.get("width"),
        "height": info.get("height"),
        "vcodec": info.get("vcodec"),
        "acodec": info.get("acodec"),
        "ok": bool(sig and info.get("has_video") and info.get("has_audio")),
    }


def _params_uniform(probes):
    """모든 클립의 (vcodec,width,height,pix_fmt,acodec,sample_rate) 가 동일하면 True."""
    if not probes:
        return False
    keys = [(p["vcodec"], p["width"], p["height"], p["pix_fmt"], p["acodec"], p["sample_rate"])
            for p in probes]
    return all(k == keys[0] for k in keys)


# ---------------------------------------------------------------------------
# ffmpeg 인자 빌드
# ---------------------------------------------------------------------------

def _write_concat_list(paths):
    fd, listfile = tempfile.mkstemp(suffix=".txt", prefix="concat_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for p in paths:
            ap = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{ap}'\n")
    return listfile


def build_copy_args(paths, out_path, listfile):
    """무재인코딩 concat(demuxer + -c copy) 인자."""
    return ["-f", "concat", "-safe", "0", "-i", listfile,
            "-c", "copy", "-movflags", "+faststart", out_path]


def build_reencode_args(paths, out_path, target):
    """안전 재인코딩 concat. 각 입력을 target(w,h)로 스케일·패드 후 concat filter 로 합친다."""
    w, h = target
    args = []
    for p in paths:
        args += ["-i", p]
    n = len(paths)
    parts = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1[v{i}];")
        parts.append(f"[{i}:a]aresample=async=1:first_pts=0[a{i}];")
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
    fc = "".join(parts) + f"{concat_in}concat=n={n}:v=1:a=1[v][a]"
    args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-movflags", "+faststart", out_path]
    return args


def _default_runner(args):
    ff = ffmpeg_binary()
    if not ff:
        raise RuntimeError("로컬 ffmpeg 를 찾을 수 없다.")
    r = subprocess.run([ff, "-y", *args], capture_output=True, text=True, timeout=600)
    return r.returncode, r.stderr


# ---------------------------------------------------------------------------
# 오케스트레이션
# ---------------------------------------------------------------------------

def compose_movie(final_dir, out_path=None, overwrite=False,
                  runner=None, prober=None, validator=None, allow_gaps=False):
    """
    scene_*_final.mp4 → 하나의 malli_final.mp4.
    파라미터 동일 시 -c copy, 다르면 재인코딩. 실패/누락은 status='failed'.
    """
    out_path = out_path or os.path.join(final_dir, "malli_final.mp4")
    runner = runner or _default_runner
    prober = prober or _default_prober
    validator = validator or _default_validator

    def result(status, method=None, scenes=None, missing=None, message="", validation=None):
        return {"status": status, "output_path": out_path if status == "success" else None,
                "method": method, "scenes_merged": len(scenes or []),
                "scene_order": [n for n, _ in (scenes or [])],
                "missing": missing or [], "message": message, "validation": validation}

    scenes, missing = discover_scenes(final_dir)
    if not scenes:
        return result("failed", message="scene_*_final.mp4 를 찾지 못했다.")
    if missing and not allow_gaps:
        return result("failed", scenes=scenes, missing=missing,
                      message=f"씬 누락으로 병합 중단: {missing}")

    # resume: 이미 유효한 최종본이 있으면 재실행하지 않는다.
    if not overwrite and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        val = validator(out_path)
        if val.get("ok"):
            return result("success", method="skipped", scenes=scenes, missing=missing,
                          message="이미 유효한 malli_final.mp4 존재(재개).", validation=val)

    paths = [p for _, p in scenes]
    probes = prober(paths)
    uniform = _params_uniform(probes)
    target = (probes[0].get("width") or 1280, probes[0].get("height") or 720)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    method = None
    rc, err = 1, ""
    if uniform:
        method = "copy"
        listfile = _write_concat_list(paths)
        try:
            rc, err = runner(build_copy_args(paths, out_path, listfile))
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
        if rc != 0 or not validator(out_path).get("ok"):
            uniform = False  # copy 실패 → 재인코딩 폴백

    if not uniform:
        method = "reencode"
        rc, err = runner(build_reencode_args(paths, out_path, target))

    if rc != 0:
        return result("failed", method=method, scenes=scenes, missing=missing,
                      message=f"ffmpeg 병합 실패: {(err or '')[-500:]}")

    val = validator(out_path)
    if not val.get("ok"):
        return result("failed", method=method, scenes=scenes, missing=missing,
                      message="최종본 검증 실패(스트림/시그니처).", validation=val)
    return result("success", method=method, scenes=scenes, missing=missing,
                  message="최종 영화 합성 완료.", validation=val)


if __name__ == "__main__":
    import json
    d = os.path.join(_ROOT, "output", "malli", "final")
    print(json.dumps(compose_movie(d), ensure_ascii=False, indent=2))
