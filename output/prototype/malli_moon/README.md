# 말리가 달님을 만난 날 — 시제품 장면 (클로드 단독 제작)

외부 이미지·영상 생성 도구(Higgsfield, Google Flow 등) 없이 코드만으로 만든 24초 장면이다.

| 파일 | 역할 |
|---|---|
| `scene.html` | SVG 로 그린 장면 + 타임라인 애니메이션. 브라우저로 열면 바로 재생된다. |
| `render.js` | Playwright 로 프레임을 캡처해 ffmpeg 로 mp4 를 만든다. |
| `audio/make_music.py` | numpy 로 오르골 자장가 배경음(`music.wav`)을 합성한다. |
| `add_voice.py` | Edge TTS 내레이션을 합성해 영상에 입힌다(인터넷 필요). |
| `malli_moon_prototype.mp4` | 자막 + 배경음 버전 결과물 (1920x1080, 24fps). |

## 다시 만들기

```bash
python3 audio/make_music.py
node render.js scene.html video silent.mp4 24
ffmpeg -i silent.mp4 -i audio/music.wav -c:v copy -c:a aac -shortest malli_moon_prototype.mp4
python3 add_voice.py   # 내레이션 버전 → malli_moon_voiced.mp4
```

말리의 외형(갈색 단발, 별 머리핀, 하늘색 물방울 잠옷)은 시제품용 임시 설정이다.
