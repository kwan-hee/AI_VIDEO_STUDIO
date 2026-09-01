# 50 AI 플레이리스트 자동 제작

Claude Code 를 오케스트레이터로, Abocado AI MCP 를 생성기로, Python + FFmpeg 를
실행기로 써서 **플레이리스트 영상 한 편**을 만드는 파이프라인.

- 사용자 인터페이스: `.claude/skills/playlist-builder|playlist-manager|playlist-studio`
- 실행기: `playlist_studio/` 패키지 (`python -m playlist_studio`)
- 테스트: `tests/playlist/`

## 역할 분리

| 주체 | 하는 일 | 하지 않는 일 |
|---|---|---|
| Claude Code (스킬) | 대화, 판단, 가사·제목 작성, 승인 게이트, MCP 호출 | 파일 가공, 인코딩 |
| Abocado MCP | 음악 생성, 이미지 생성, (선택) STT | 편집, 병합 |
| `playlist_studio` CLI | 상태 관리, 검사, 정규화, 병합, 정렬, 자막, 썸네일, 렌더, QA | **MCP 호출 (일절 안 함)** |

CLI 는 어떤 MCP 도 부르지 않는다. 유료 생성은 전부 스킬이 사용자 승인을 받아
수행하고, 그 **결과만** CLI 에 기록한다. 그래서 CLI 단독으로는 크레딧이 절대 소모되지 않는다.

## 설치

```bash
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

FFmpeg 는 별도 설치가 필요하다.

- Windows: `winget install Gyan.FFmpeg` 또는 [ffmpeg.org](https://ffmpeg.org/download.html) 빌드를 PATH 에 추가
- macOS: `brew install ffmpeg`
- Debian/Ubuntu: `sudo apt install ffmpeg`

**libass 가 포함된 빌드**여야 ASS 자막을 태울 수 있다. `doctor` 가 확인해 준다.
PATH 에 넣기 어려우면 환경변수 `FFMPEG_BINARY` / `FFPROBE_BINARY` 로 경로를 지정한다.

```bash
python -m playlist_studio doctor
```

## 빠른 시작

```bash
# 0. 환경 검사
python -m playlist_studio doctor

# 1. 유료 생성 전 필수 - 합성 자산으로 전 과정 검증 (크레딧 0)
python -m playlist_studio selftest --tracks 3 --seconds 30

# 2. 실제 작업 시작 (Claude Code 안에서)
/playlist-builder
```

## 웹 대시보드 (핸드폰·태블릿·다른 PC)

터미널을 열지 않고 브라우저 하나로 전 과정을 조종한다.

```bash
python -m playlist_studio serve
```

Windows 는 `대시보드_실행.bat` 를 두 번 클릭해도 된다.
실행하면 터미널에 두 개의 주소가 뜬다.

```
이 PC에서       http://127.0.0.1:8765/?t=xxxxxxxx
같은 Wi-Fi 기기  http://192.168.0.12:8765/?t=xxxxxxxx   ← 핸드폰에 이 주소를 입력
```

주소 끝의 `?t=...` 는 접속 열쇠다. **이게 없으면 아무 API 도 응답하지 않는다.**
한 번 접속하면 브라우저가 기억하므로 다음부터는 주소만 넣어도 된다.
iPhone·Android 모두 "홈 화면에 추가" 하면 앱처럼 열린다.

### 화면 구성

| 화면 | 하는 일 |
|---|---|
| 홈 | 환경 상태, 플레이리스트 목록과 진행률, 새로 만들기, 전체 점검 |
| 설정 | 마법사 질문을 **한 번에 하나씩** 큰 버튼으로 |
| 단계 | 9단계 진행표 + "다음 할 일" 카드 + 단계별 실행 버튼 |
| 곡 | 곡 목록, 그 자리에서 재생, 제목·주제·가사 편집 |
| 결과물 | 최종 영상 재생, 썸네일 미리보기, 유튜브 제목·설명·챕터·태그 복사 |
| QA | 검사 결과, 확인이 필요한 항목만 먼저 |

### 무엇이 되고 무엇이 안 되는가

- **서버는 CLI 만 실행한다.** MCP 를 부르지 않으므로 이 화면을 아무리 눌러도
  **크레딧이 소모되지 않는다.**
- 실행 가능한 명령은 CLI 하위 명령으로 화이트리스트가 걸려 있다.
  임의의 셸 명령은 실행되지 않는다.
- 유료 생성(음악·이미지)은 Claude 가 해야 한다. 대시보드는 그 단계에서
  **"Claude 에 붙여넣기"** 버튼으로 지시문을 클립보드에 넣어 준다.
  Claude 가 만들어 준 결과 URL 을 다시 대시보드에 붙여넣으면 파일로 가져온다.
- 렌더링은 서버가 있는 PC 에서 돈다. **PC 가 꺼져 있으면 아무것도 안 된다.**
  핸드폰은 조종기이지 렌더링 머신이 아니다.

### 밖에서 접속하려면

같은 Wi-Fi 가 아니면 기본적으로 접속되지 않는다(그게 안전하다).
집 밖에서 쓰려면 터널을 하나 띄운다. 셋 중 하나면 충분하다.

| 방법 | 명령 | 특징 |
|---|---|---|
| Tailscale | 두 기기에 설치 후 로그인 | 가장 안전. 내 기기끼리만 보인다. 무료 |
| Cloudflare Tunnel | `cloudflared tunnel --url http://localhost:8765` | 임시 공개 주소. 계정 없이도 가능 |
| ngrok | `ngrok http 8765` | 간단. 무료 플랜은 주소가 매번 바뀐다 |

⚠️ 공개 주소로 열 때는 반드시 `?t=` 토큰을 유지하고, 그 주소를 남에게 보내지 않는다.
`--no-token` 은 집 안 네트워크에서만 쓴다.

### 옵션

```bash
python -m playlist_studio serve --port 9000        # 포트 변경
python -m playlist_studio serve --host 127.0.0.1   # 이 PC 에서만 (외부 차단)
python -m playlist_studio serve --token 내암호      # 토큰 고정 (즐겨찾기 하기 좋다)
python -m playlist_studio serve --open             # 브라우저 자동 실행
```

## 폴더 구조

```
studio/channels/001_<채널slug>/
  CHANNEL.md  channel.json
  playlists/001_<플레이리스트slug>/
    workspace.json          상태 머신 + 산출물 sha256 레지스트리
    playlist.yaml           설정 마법사 답변
    sonic_dna.json          공통 음악 DNA
    visual_dna.json         공통 비주얼 DNA
    tracks.json             곡별 계획 · job id · 해시 · 상태
    generation_ledger.json  중복 결제 방지 원장
    timing.json             곡 시작 시각 · 음량 · 싱크 리포트
    lyrics/ audio/ images/ subs/ meta/ video/ qa/ work/
```

경로는 JSON 안에 **POSIX 상대경로**로만 저장한다. Windows 에서 만든 프로젝트를
macOS 에서 열어도 같은 파일을 가리킨다.

## 상태 머신

`INIT → CHANNEL_READY → PLAN_READY → LYRICS_READY → PILOT_READY → PILOT_APPROVED
→ BATCH_GENERATED → VISUALS_READY → ALIGNED → METADATA_READY → RENDERED → VERIFIED`

- 단계가 **성공한 뒤에만** 앞으로 간다. 실패하면 그 자리에 머물고 오류가 기록된다.
- 되돌리기는 명시적일 때만 (`pilot-reject`).
- 재실행하면 `workspace.json` 의 sha256 을 재계산해 **정상인 산출물은 재사용**하고
  없거나 손상된 것만 다시 만든다.

## 안전장치

| 위험 | 장치 |
|---|---|
| 같은 곡을 두 번 결제 | `generation_ledger.json` — fingerprint(모델+프롬프트+가사) 잠금. `submit-payload --claim` 이 재제출을 차단 |
| 승인 없이 결제 | `cost` 가 곡 수·단가·총액·실시간 잔액·부족액을 표로 출력. 스킬이 명시적 승인 요구 |
| 마음에 안 드는 곡을 전곡 생성 | 파일럿 게이트 — `pilot-approve` 전에는 나머지를 만들지 않음 |
| 넘긴 가사와 로컬 가사가 다름 | 정규화 sha256 대조. 불일치면 제출 거부 |
| 실존 아티스트 모방 | 프롬프트·가사에서 "in the style of" 류 표현 자동 거부 |
| 손상된 음원이 영상에 들어감 | ffprobe + 무음 비율 검사. 통과 못 하면 병합에서 제외 |
| 손상된 중간 렌더가 재사용됨 | 세그먼트를 ffprobe 로 실측(해상도·코덱·길이) 후에만 재사용 |
| 이미지 AI 가 그린 깨진 글자 | 프롬프트에 글자 금지 명시. 모든 텍스트는 Pillow/ASS 로 로컬 합성 |
| 썸네일 글자 잘림 | 자동 줄바꿈·축소 후에도 안 되면 `overflow` 로 QA 실패 |
| 비밀정보 유출 | CLI 는 API 키·토큰을 읽지도 쓰지도 않는다. `rights.json` 에는 job id 와 크레딧 수치만 |
| 의도치 않은 공개 | 업로드 기능 자체가 없다. 파일 생성까지만 |

## 출력 규격

- 영상: 1920×1080 / 30fps / H.264 (high@4.1) / yuv420p / faststart
- 오디오: AAC 256kbps 48kHz 스테레오
- 음량: -14 LUFS (integrated), True Peak -1dB 이하
- 썸네일: 1280×720 PNG (2MB 초과 시 JPEG 병행)
- 자막: SRT(보관) + ASS(렌더 — 현재 가사 강조, 다음 줄 미리보기, 곡 카드, 인트로)

## 가사 싱크 정확도

`align` 은 방식을 숨기지 않는다.

| 방식 | 조건 | 300ms 목표 |
|---|---|---|
| `whisper` | faster-whisper 설치 + 모델 다운로드 가능 | 만족 가능 |
| `srt` | 외부 ASR SRT 제공 (`--srt-dir`) | 만족 가능 |
| `estimate` | 위 둘 다 없음 | **보장 안 됨** — QA 가 경고를 남긴다 |

`whisper`·`srt` 는 인식 결과를 **원문 가사에 되맞춘다.** ASR 오타는 타이밍만 쓰고
화면에는 항상 원문이 나간다. 인식 못 한 줄은 보간하고 `interpolated` 로 표시한다.

## 명령 목록

```
doctor  selftest  serve
channel-new  channel-list  playlist-new  list
config-status  config-set  config-show
plan  dna-show  dna-set
track-set  track-lyrics  lyrics-validate  lyrics-collect
cost  submit-payload  ledger-show  ledger-release  track-import
pilot-status  pilot-approve  pilot-reject  batch-status
visual-prompts  image-import  thumbnail  visuals-done
build-audio  align  subtitles  metadata  render  qa
status  resume  verify  clean
```

모든 명령에 `--json` 을 붙이면 기계가 읽을 수 있는 JSON 이 나온다.

## 테스트

```bash
.venv/bin/python -m pytest tests/playlist -q       # 단위 + 통합 (ffmpeg 사용)
.venv/bin/python -m playlist_studio selftest       # 전 과정 실행 (크레딧 0)
```

## 참고

- Abocado 뮤직 모델·단가는 코드 안에 스냅샷으로만 들어 있다
  (`playlist_studio/cost.py`). **승인 화면 전에는 반드시 MCP `abocado_music` 과
  `abocado_get_credits` 로 재조회해 `--unit-credits` / `--balance` 로 덮어쓴다.**
- YouTube 제목 100자 / 설명 5000자 / 태그 합계 500자 / 썸네일 2MB 한도를 QA 가 검사한다.
  ([YouTube 도움말](https://support.google.com/youtube/answer/72431))
- 챕터는 첫 줄이 `0:00` 이어야 인식된다.
  ([YouTube 챕터 안내](https://support.google.com/youtube/answer/9884579))
- 음량 목표 -14 LUFS 는 스트리밍 플랫폼의 일반적인 정규화 기준을 따른 것이다.
  ([EBU R128](https://tech.ebu.ch/publications/r128))
