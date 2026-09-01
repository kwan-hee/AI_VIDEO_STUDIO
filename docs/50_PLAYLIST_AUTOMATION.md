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
doctor  selftest
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
