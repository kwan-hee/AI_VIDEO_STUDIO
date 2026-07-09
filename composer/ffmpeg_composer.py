# 이미지·비디오·오디오와 실행 계획을 받아 로컬 FFmpeg로 최종 MP4를 합성하고 표준 결과를 반환하는 FFmpeg Composer
"""
FFmpeg Composer (Sprint 11)

입력.
  - inputs: {
        "images": [경로...],
        "videos": [경로...],
        "audio":  [경로...],
        "execution_plan": {project, steps...}  # 선택, 이름/맥락용
    }

책임.
  - 로컬 FFmpeg 로 최종 MP4 한 개를 합성한다.
  - output/final/ 아래에 저장한다.
  - 표준 JSON 결과를 반환한다.

FFmpeg 만 사용한다. 다른 공급자(Google Flow / Higgsfield / Nano Banana / Magnific)는 호출하지 않는다.
기존 미디어 파일을 입력으로 받는다(생성하지 않는다).
ffmpeg 실행 백엔드는 runner 인자로 주입 가능하다. 기본은 실제 로컬 ffmpeg.
출력 스키마: schemas/composition_result_schema.json
Sprint 1~10 파일은 수정하지 않는다.
"""

import hashlib
import os
import shutil

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT_DIR = os.path.join(_ROOT, "output", "final")


def ffmpeg_binary():
    """로컬 ffmpeg 실행 파일 경로. 없으면 None. 환경변수 → PATH → imageio-ffmpeg 순."""
    env = os.environ.get("FFMPEG_BINARY")
    if env and os.path.exists(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def ffmpeg_available():
    return ffmpeg_binary() is not None


def _build_args(images, videos, audio, output_path):
    """ffmpeg 인자 목록 생성(바이너리 제외, 끝에 output_path 포함). 비디오 우선, 없으면 이미지 슬라이드쇼."""
    audio0 = audio[0] if audio else None
    args = []

    if videos:
        for v in videos:
            args += ["-i", v]
        if audio0:
            args += ["-i", audio0]
        n = len(videos)
        if n == 1:
            args += ["-map", "0:v:0"]
            if audio0:
                args += ["-map", "1:a:0", "-c:a", "aac", "-shortest"]
            args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
        else:
            concat = "".join(f"[{i}:v:0]" for i in range(n))
            fc = f"{concat}concat=n={n}:v=1:a=0[v]"
            args += ["-filter_complex", fc, "-map", "[v]"]
            if audio0:
                args += ["-map", f"{n}:a:0", "-c:a", "aac", "-shortest"]
            args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
    elif images:
        for im in images:
            args += ["-loop", "1", "-t", "2", "-i", im]
        if audio0:
            args += ["-i", audio0]
        n = len(images)
        scale = "".join(
            f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1[s{i}];" for i in range(n))
        concat = "".join(f"[s{i}]" for i in range(n))
        fc = scale + f"{concat}concat=n={n}:v=1:a=0[v]"
        args += ["-filter_complex", fc, "-map", "[v]"]
        if audio0:
            args += ["-map", f"{n}:a:0", "-c:a", "aac", "-shortest"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", output_path]
    else:
        raise ValueError("합성에 필요한 이미지 또는 비디오가 없다.")

    return args


def _default_runner(args, output_path):
    """실제 로컬 ffmpeg 실행."""
    import subprocess

    binary = ffmpeg_binary()
    if not binary:
        raise RuntimeError("로컬 ffmpeg 를 찾을 수 없다. (PATH / FFMPEG_BINARY / imageio-ffmpeg)")
    subprocess.run([binary, "-y", *args], check=True, capture_output=True, timeout=300)


def _result(status, output_path, images, videos, audio, message):
    return {
        "provider": "FFmpeg",
        "action": "compose",
        "status": status,
        "output_path": output_path,
        "format": "mp4",
        "inputs_used": {"images": len(images), "videos": len(videos), "audio": len(audio)},
        "message": message,
    }


def _rel(path):
    try:
        return os.path.relpath(path, _ROOT).replace(os.sep, "/")
    except ValueError:
        return path


def compose(inputs, output_dir=None, runner=None):
    """
    이미지/비디오/오디오 + 실행 계획 → 최종 MP4.
    로컬 ffmpeg 만 사용. 다른 공급자 호출 없음. 기존 파일만 받는다.
    실패는 status="failed" 로 반환한다.
    """
    if not isinstance(inputs, dict):
        raise ValueError("inputs 는 dict 여야 한다.")

    images = list(inputs.get("images") or [])
    videos = list(inputs.get("videos") or [])
    audio = list(inputs.get("audio") or [])
    plan = inputs.get("execution_plan") or {}
    project = plan.get("project", "final")

    if not images and not videos:
        raise ValueError("영상 합성에는 최소 하나의 이미지 또는 비디오가 필요하다.")

    missing = [f for f in (images + videos + audio) if not os.path.exists(f)]
    if missing:
        return _result("failed", None, images, videos, audio,
                       f"입력 파일 없음: {missing}")

    out_dir = output_dir or _DEFAULT_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    key = hashlib.md5("|".join(images + videos + audio).encode("utf-8")).hexdigest()[:10]
    output_path = os.path.join(out_dir, f"{project}_{key}.mp4")

    runner = runner or _default_runner
    try:
        args = _build_args(images, videos, audio, output_path)
        runner(args, output_path)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("최종 MP4 가 생성되지 않았다.")
    except Exception as e:  # noqa: BLE001
        if os.path.exists(output_path) and os.path.getsize(output_path) == 0:
            os.remove(output_path)
        return _result("failed", None, images, videos, audio, f"FFmpeg 합성 실패: {e}")

    return _result("success", _rel(output_path), images, videos, audio, "최종 MP4 합성 완료.")


if __name__ == "__main__":
    import json
    import sys

    # 데모: 인자로 비디오/오디오 경로. 없으면 사용법.
    if len(sys.argv) < 2:
        print(json.dumps({"ffmpeg_available": ffmpeg_available(),
                          "binary": ffmpeg_binary(),
                          "usage": "ffmpeg_composer.py <video> [audio]"}, ensure_ascii=False, indent=2))
    else:
        vids = [sys.argv[1]]
        auds = [sys.argv[2]] if len(sys.argv) > 2 else []
        print(json.dumps(compose({"videos": vids, "audio": auds}), ensure_ascii=False, indent=2))
