# 상위 저장소의 Kling 파이프라인을 불러오기 위한 공통 경로 설정.
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)                 # engineering/
REPO = os.path.dirname(STUDIO)                 # 저장소 루트
OUTPUT = os.path.join(STUDIO, "output")

if REPO not in sys.path:
    sys.path.insert(0, REPO)


def latest_scene_file():
    """가장 최근에 수정된 장면 목록 파일을 찾는다."""
    if not os.path.isdir(OUTPUT):
        return None
    files = [
        os.path.join(OUTPUT, f)
        for f in os.listdir(OUTPUT)
        if f.endswith("_scenes.json")
    ]
    return max(files, key=os.path.getmtime) if files else None
