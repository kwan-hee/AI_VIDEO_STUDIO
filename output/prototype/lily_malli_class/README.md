# 말리의 동화나라 클래스 — 클로드 단독 재현본

원본 `Lily_Malli_Fairytale_Class_Final.mp4`(힉스필드 제작, 23초, 세로)의 콘티를
외부 이미지·영상 생성 도구 없이 코드만으로 다시 그린 버전이다.

| 시간 | 원본 장면 | 재현 방식 |
|---|---|---|
| 0~5초 | 수채화 초원, 릴리와 말리가 하늘을 본 뒤 걷기 시작 | SVG 하늘·구름·풀잎, 걷기 동작 |
| 5~11초 | 달리는 사이 노을, 성 등장, 불꽃놀이 | 하늘 색 전환, 성이 지평선에서 떠오름, 불꽃 입자 |
| 11~18초 | 릴리와 말리 클로즈업, 놀람 → 웃음 → 볼을 맞대고 웃음 | 정면 캐릭터, 표정 3단계, 불꽃 빛 깜빡임 |
| 18~23초 | 크림색 화면 + "말리의 동화나라 클래스" | 같은 문구와 페이드 |

| 파일 | 역할 |
|---|---|
| `scene.html` | 전체 장면과 애니메이션. 브라우저로 열면 재생된다. |
| `render.js` | 1080x1920, 24fps 로 프레임을 캡처해 mp4 를 만든다. |
| `audio/make_music.py` | 오르골 왈츠 + 성 등장 차임 + 불꽃 소리를 합성한다. |
| `lily_malli_class_claude.mp4` | 결과물. |
| `compare_original_vs_claude.mp4` | 원본과 나란히 비교한 영상. |

```bash
python3 audio/make_music.py
node render.js scene.html video silent.mp4 24
ffmpeg -i silent.mp4 -i audio/music.wav -c:v copy -c:a aac -shortest lily_malli_class_claude.mp4
```
