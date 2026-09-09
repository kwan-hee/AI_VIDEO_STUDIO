#!/usr/bin/env python3
# 하저터널 Kling 클립을 내려받아 한 편으로 합친다. CDN 접근이 가능한 환경에서 실행한다.
"""
사용법:
    python3 scripts/compose_river_tunnel.py [결과_JSON] [출력_폴더]

기본값은 output/river_tunnel/result.json 과 output/river_tunnel 이다.
모든 클립이 같은 규격(720x1280, 9:16)이므로 재인코딩 없이 이어 붙인다.
"""

import json
import os
import subprocess
import sys
import urllib.request

DEFAULT_RESULT = os.path.join("output", "river_tunnel", "result.json")


def load_clips(result_path):
    with open(result_path, encoding="utf-8") as f:
        data = json.load(f)
    return sorted(data["clips"], key=lambda c: c["order"])


def download(clip, out_dir):
    path = os.path.join(out_dir, f"{clip['key']}.mp4")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"이미 있음: {clip['key']}.mp4")
        return path
    print(f"내려받는 중: {clip['key']}.mp4")
    urllib.request.urlretrieve(clip["url"], path)
    return path


def write_concat_list(clips, out_dir):
    list_path = os.path.join(out_dir, "concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for clip in clips:
            f.write(f"file '{clip['key']}.mp4'\n")
    return list_path


def compose(list_path, out_dir):
    final = os.path.join(out_dir, "river_tunnel_final.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final],
        check=True,
    )
    return final


def main():
    result_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESULT
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(result_path)
    os.makedirs(out_dir, exist_ok=True)

    clips = load_clips(result_path)
    for clip in clips:
        download(clip, out_dir)

    final = compose(write_concat_list(clips, out_dir), out_dir)
    total = sum(c["duration"] for c in clips)
    print(f"\n완성: {final}")
    print(f"장면 {len(clips)}개 / 총 {total}초 / 차감 {sum(c['cost'] for c in clips)} 크레딧")


if __name__ == "__main__":
    main()
