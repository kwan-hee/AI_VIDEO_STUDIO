# 시제품 영상에 Edge TTS 내레이션을 입힌다 (인터넷이 되는 PC 에서 실행)
#   pip install edge-tts   (ffmpeg 필요)
#   python add_voice.py   ->  malli_moon_voiced.mp4
import asyncio
import os
import subprocess

import edge_tts

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = os.path.join(HERE, "malli_moon_prototype.mp4")
MUSIC = os.path.join(HERE, "audio", "music.wav")
OUT = os.path.join(HERE, "malli_moon_voiced.mp4")

# (시작 초, 대사, 속도, 음높이)  시작 초는 scene.html 의 SUBS 와 맞춘다
LINES = [
    (1.8, "별들이 하나둘 반짝이던 밤, 말리는 좀처럼 잠이 오지 않았어요.", "-8%", "+0Hz"),
    (6.7, "그때, 언덕 너머로 동그란 달님이 살며시 떠올랐어요.", "-8%", "+0Hz"),
    (12.2, "달님, 안녕? 나랑 같이 놀래?", "-3%", "+25Hz"),
    (16.0, "그러자 달님이 반짝, 하고 윙크를 해 주었답니다.", "-8%", "+0Hz"),
]
VOICE = "ko-KR-SunHiNeural"


async def synth():
    paths = []
    for i, (_, text, rate, pitch) in enumerate(LINES):
        p = os.path.join(HERE, "audio", f"line{i + 1}.mp3")
        await edge_tts.Communicate(text, VOICE, rate=rate, pitch=pitch).save(p)
        paths.append(p)
    return paths


def main():
    paths = asyncio.run(synth())
    cmd = ["ffmpeg", "-y", "-i", VIDEO, "-i", MUSIC]
    for p in paths:
        cmd += ["-i", p]
    parts, labels = [], []
    for i, (start, *_) in enumerate(LINES):
        ms = int(start * 1000)
        parts.append(f"[{i + 2}:a]adelay={ms}|{ms},volume=1.6[v{i}]")
        labels.append(f"[v{i}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(LINES)}:normalize=0[voice]")
    parts.append("[1:a]volume=0.35[bgm]")
    parts.append("[bgm][voice]amix=inputs=2:normalize=0:duration=first[aout]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", OUT]
    subprocess.run(cmd, check=True)
    print("완료:", OUT)


if __name__ == "__main__":
    main()
