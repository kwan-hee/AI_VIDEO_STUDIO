<div align="center">

<p align="center">
  <img src="assets/ai-video-studio-banner.png" alt="AI_VIDEO_STUDIO Banner" width="100%">
</p>
<p align="center">
  <img src="assets/logo.png" width="180">
</p>
<h1 align="center">AI_VIDEO_STUDIO</h1>

<p align="center">

End-to-End AI Video Production Platform

</p>

<p align="center">

# 🎬 AI_VIDEO_STUDIO

**End-to-end AI Video Production Pipeline powered by Claude, Gemini, Higgsfield MCP, Edge TTS and YouTube.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Claude API](https://img.shields.io/badge/Claude-API-D97757?logo=anthropic&logoColor=white)
![Gemini Image](https://img.shields.io/badge/Gemini-Image-4285F4?logo=googlegemini&logoColor=white)
![Higgsfield MCP](https://img.shields.io/badge/Higgsfield-MCP-8A2BE2)
![Edge TTS](https://img.shields.io/badge/Edge-TTS-0078D4?logo=microsoftedge&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-H.264%2FAAC-007808?logo=ffmpeg&logoColor=white)
![YouTube Upload](https://img.shields.io/badge/YouTube-Upload-FF0000?logo=youtube&logoColor=white)
![Tests](https://img.shields.io/badge/tests-439_passed-brightgreen)
![License](https://img.shields.io/badge/license-Private-lightgrey)
</p>

</div>
## 📚 Table of Contents

- Features
- Architecture
- Installation
- Configuration
- Environment Variables
- Cost-Saving Hybrid Mode
- Project Structure
- Pipeline
- Security
- Roadmap
- License

## 🚀 Quick Start

```bash
git clone <repository>

cd AI_VIDEO_STUDIO

python -m venv .venv

pip install -r requirements.txt

python main.py
```

Title
   │
   ▼
Claude Story
   │
   ▼
Gemini Image
   │
   ▼
Higgsfield Video
   │
   ▼
Edge TTS
   │
   ▼
FFmpeg Compose
   │
   ▼
YouTube Upload

assets/screenshots/

story.png

workflow.png

youtube.png

final_video.png



## 📸 Screenshots

### Workflow

![Workflow](assets/screenshots/workflow.png)

### Final Video

![Final](assets/screenshots/final_video.png)


---

AI를 활용하여 **동화 스토리 생성 → 이미지 생성 → 영상 생성 → 음성 생성 → 영상 합성 → YouTube 업로드**까지 자동으로 수행하는 프로젝트입니다.

---

# ✨ Features

- 🧠 **AI Story Generation** — Anthropic Claude 로 구조화된 동화 스토리 생성
- 🖼️ **AI Image Generation** — Google Gemini 로 장면별 이미지 생성
- 🎞️ **AI Video Generation** — Higgsfield MCP 로 이미지 → 영상 변환
- 🗣️ **AI Voice Generation** — Microsoft Edge TTS 한국어 내레이션
- 🎬 **FFmpeg Composition** — 영상 + 음성 합성(H.264 + AAC, faststart)
- 🎬 **Multi-scene Pipeline** — 전체 씬을 순서대로 자동 처리
- 💸 **Cost-Saving Hybrid Mode** — 에피소드당 AI 영상 1클립 + 나머지 FFmpeg 모션
- 📤 **Automatic YouTube Upload** — YouTube Data API v3 업로드
- 🔀 **Mock / Real Mode** — 기본 mock, 실 실행은 명시 옵트인
- ⏯️ **Resume Support** — 이미 유효한 산출물은 건너뛰고 이어서 진행
- 🔁 **Retry Manager** — 실패 재시도 처리
- 📝 **Execution Logger** — 단계별 실행 상태/에러 기록

---

# 🏗️ Architecture

```
        Title
          ↓
     Claude Story
          ↓
     Gemini Image
          ↓
   Higgsfield Video
          ↓
       Edge TTS
          ↓
        FFmpeg
          ↓
    YouTube Upload
```

---

# ⚙️ Installation

```bash
# 1. Clone repository
git clone https://github.com/kwan-hee/AI_VIDEO_STUDIO.git
cd AI_VIDEO_STUDIO

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install requirements
pip install -r requirements.txt

# 4. Configure .env (API keys)
cp .env.example .env             # 그리고 키 값을 채운다

# 5. Configure OAuth (최초 1회)
python secrets/auth_youtube.py   # 브라우저 로그인 → secrets/token.json 생성

# 6. Run pipeline
python -m pipeline.scene_pipeline --real
```

---

# 🔑 Environment Variables

| 변수 | 설명 | 필수 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude 스토리 생성 API 키 | 실 스토리 생성 시 필수 |
| `GEMINI_API_KEY` | Gemini 이미지 생성 API 키 (`GOOGLE_API_KEY` 대체 가능) | 실 이미지 생성 시 필수 |
| `HIGGSFIELD_REAL` | 실 Higgsfield 영상 생성 옵트인 (`1`) | 선택 (기본 mock) |
| `YOUTUBE_REAL` | 실 YouTube 업로드 옵트인 (`1`) | 선택 (기본 mock) |

추가 참고 — `HIGGSFIELD_MODEL`(실 영상 모델 id), `YOUTUBE_TOKEN`(OAuth 토큰 경로) 도 환경변수로 지정할 수 있습니다.

---

# 🧩 구성

## 1. Claude Story

Anthropic Claude API를 이용하여 동화 스토리를 생성합니다.

기능

- Claude API 호출
- Story JSON 생성
- Story Schema 검증
- Mock / Real 모드 지원

환경변수

```
ANTHROPIC_API_KEY
```

---

## 2. Gemini Image

Google Gemini Image API를 이용하여 장면 이미지를 생성합니다.

기능

- Scene별 이미지 생성
- PNG 저장
- 이미지 검증
- Mock / Real 모드 지원

환경변수

```
GEMINI_API_KEY
```

---

## 3. Higgsfield Video

Higgsfield MCP를 이용하여 이미지를 영상으로 변환합니다.

기능

- 이미지 업로드
- Video 생성
- MP4 다운로드
- 검증 후 저장

환경변수

```
HIGGSFIELD_MODEL
```

---

## 4. Edge TTS

Microsoft Edge TTS를 이용하여 한국어 내레이션을 생성합니다.

기능

- MP3 생성
- 음성 검증
- Scene별 저장

기본 음성

```
ko-KR-SunHiNeural
```

---

## 5. FFmpeg Composer

생성된 영상과 음성을 하나의 최종 영상으로 합성합니다.

기능

- 영상 길이 자동 연장
- 마지막 프레임 Freeze
- Audio Sync
- H.264 + AAC 출력

출력

```
output/malli/final/
```

---

## 6. YouTube Upload

YouTube Data API v3를 이용하여 영상을 업로드합니다.

기능

- OAuth 인증
- Private 업로드
- Thumbnail 업로드(선택)
- Mock / Real 모드 지원

환경변수

```
YOUTUBE_REAL=1
```

---

# 💸 Cost-Saving Hybrid Mode

AI 영상 생성 크레딧 사용량을 줄이는 제작 모드입니다.

- **hybrid_economy** — 에피소드당 프리미엄 씬 **1개만** Higgsfield(Seedance) AI 영상으로 생성하고,
  나머지 씬은 Gemini 이미지 + **FFmpeg 모션**(Ken Burns / zoom / pan / fade)으로 채웁니다.
- **image_only** — AI 영상 생성 **0회**. 전 씬을 FFmpeg 모션으로 처리합니다.
- 나레이션은 기존 Edge TTS, 합성은 기존 FFmpeg Composer 를 그대로 사용합니다.
- **자동 폴백** — Seedance 생성이 재시도 후에도 실패하면 해당 씬을 FFmpeg 모션으로 대체하고
  에피소드를 `completed_with_fallback` 상태로 계속 진행합니다(추가 AI 영상 크레딧 소모 없음).
- **재개(Resume)** — 이미 유효한 이미지·클립은 재생성하지 않으며, 프리미엄 씬 선택은
  `{output}/hybrid_state.json` 에 고정되어 재실행 시에도 바뀌지 않습니다.
- 사용량 요약은 **호출 횟수만** 보고합니다. 공급자 크레딧 단가는 변동될 수 있으므로
  고정 크레딧 값을 가정하지 않습니다(공식 사용량은 공급자 API 조회 기준).

### 설정 (YAML)

```yaml
production:
  mode: hybrid_economy          # full_video(기본) | hybrid_economy | image_only | mock

cost_control:
  max_ai_video_clips: 1         # 에피소드당 AI 영상 상한
  premium_scene_strategy: auto  # auto | first | middle | climax | manual
  preferred_scene_index: null   # manual 전략에서 사용할 씬 번호(1-base)
  allow_video_fallback_to_image: true

image_motion:
  enabled: true
  default_effect: ken_burns
  alternate_effects: [zoom_in, zoom_out, pan_left, pan_right, slow_push]
  zoom_start: 1.0
  zoom_end: 1.12
  fps: 30
  resolution: 1920x1080
  crossfade_seconds: 0.5

video_generation:
  provider: higgsfield
  model: seedance
  max_clips_per_episode: 1
```

새 섹션은 전부 선택 사항입니다. 기존 프로젝트 설정 파일은 **수정 없이** 그대로 동작합니다
(부재 시 안전 기본값, 기본 모드는 `full_video` = 기존 동작).

### CLI

```bash
# hybrid_economy 로 말리 프로젝트 실행 (CLI 옵션이 YAML 을 덮어씀)
python cli/aivs_cli.py run projects/malli.yaml --mode hybrid_economy

# AI 영상 상한 / 프리미엄 씬 전략 / 씬 직접 지정
python cli/aivs_cli.py run projects/malli.yaml --mode hybrid_economy --max-ai-video-clips 1
python cli/aivs_cli.py run projects/malli.yaml --mode hybrid_economy --premium-scene auto
python cli/aivs_cli.py run projects/malli.yaml --mode hybrid_economy --premium-scene-index 3

# AI 영상 크레딧 0 으로 전체 제작
python cli/aivs_cli.py run projects/malli.yaml --mode image_only
```

실행 로그 예시.

```
[Cost Control] Mode: hybrid_economy
[Cost Control] AI video clip limit: 1
[Cost Control] Selected premium scene: 3
[Cost Control] Remaining scenes use FFmpeg image motion

Production summary
------------------
Mode: hybrid_economy
Total scenes: 6
Image generations: 6
AI video generations requested: 1
AI video generations completed: 1
FFmpeg motion scenes: 5
AI video retries: 0
Fallback scenes: 0
YouTube upload: enabled
```

---

# 🔐 OAuth 설정 방법

## 1.

Google Cloud Console

↓

YouTube Data API v3 활성화

↓

OAuth Desktop Client 생성

↓

JSON 다운로드

↓

```
secrets/
```

폴더에 저장

예)

```
secrets/youtube_client_secret.json
```

---

## 2.

최초 1회 OAuth 실행

```
python secrets/auth_youtube.py
```

브라우저 로그인 완료 후

```
secrets/token.json
```

생성되면 이후에는 자동 인증됩니다.

---

# 🗝️ API Key 설정

Anthropic

```
ANTHROPIC_API_KEY
```

Google Gemini

```
GEMINI_API_KEY
```

또는

```
GOOGLE_API_KEY
```

---

# 📁 Project Structure

```
AI_VIDEO_STUDIO
│
├── providers/          # Nano Banana(이미지) / Higgsfield(영상) 공급자
├── executors/          # Edge TTS 실행기
├── composer/           # FFmpeg 합성 + 최종 영화 합성기
├── motion/             # 정지 이미지 → FFmpeg 모션 클립 (hybrid mode)
├── pipeline/           # 멀티씬 제작 파이프라인 + hybrid 모드 파이프라인
├── uploader/           # YouTube 업로더
├── config/             # 프로젝트/공급자 설정
├── schemas/            # JSON 스키마
├── output/             # 생성 산출물 (git 제외)
├── tests/              # 테스트
├── secrets/            # OAuth 자격증명 (git 제외)
│     ├── youtube_client_secret.json
│     └── token.json
│
├── README.md
└── .gitignore
```

---

# 🛡️ Security

`secrets/` 안의 모든 파일은 **절대 커밋하지 않습니다.**

GitHub에 업로드하지 않는 대상

```
secrets/
token.json
youtube_client_secret.json
```

`.gitignore`

```
secrets/
output/
```

> ⚠️ OAuth `token.json` 은 refresh 토큰을 포함합니다. 유출 시 즉시 Google Cloud Console 에서 자격증명을 폐기하세요.

---

# 🗺️ Roadmap

### Version 1.0
- Story
- Image
- Video
- Voice
- Compose

### Version 2.0
- YouTube Upload
- Thumbnail Upload
- SEO Metadata

### Version 3.0
- Analytics
- Multi-channel
- Auto Optimization

---

# 🖼️ Screenshots

> 준비 중입니다. 아래는 자리표시자입니다.

| 파이프라인 실행 | 최종 영상 | YouTube 업로드 |
| :---: | :---: | :---: |
| ![pipeline](https://placehold.co/320x180?text=Pipeline+Run) | ![final](https://placehold.co/320x180?text=Final+Movie) | ![upload](https://placehold.co/320x180?text=YouTube+Upload) |

---

# ▶️ 실행 순서

1. Claude Story 생성
2. Gemini Image 생성
3. Higgsfield Video 생성
4. Edge TTS 생성
5. FFmpeg Compose
6. YouTube Private Upload

---

# 🧪 테스트

전체 테스트 실행

```
pytest
```

현재 기준

```
439 passed
```

---

# 🔁 Dual-Account Higgsfield Production

두 Higgsfield 계정을 alias 로만 다뤄 크레딧을 효율적으로 쓰면서 영상 품질을 높이는 워크플로.

- **legacy_account** — 최소 품질검증 + 초기 프로덕션에 사용. 남은 크레딧을 버리지 않고 실제 제작에 계속 쓴다.
- **production_account** — legacy 가 다음 생성 비용을 감당 못할 때만 자동 활성화. 승인·동결된 프리셋만 재사용.
- **승인 프리셋 동결** — 검증 통과한 style/character/camera/motion 설정을 `presets/approved/*.yaml` 로 동결. 프로덕션은 이 프리셋만 재사용하고, 변경은 명시적 override 필요.
- **자동 전환 조건** — 오직 확인된 크레딧 조건(사전 잔액 부족 또는 명시적 부족 오류)에서만. 실행당 **최대 1회**, 전환 후 legacy 로 되돌아가지 않는다.
- **전환하지 않는 경우** — 인증/권한 실패, 잘못된 프롬프트/설정, 모호한 타임아웃, 네트워크 오류.
- **중복 유료 생성 방지** — 재시도 전 provider job 상태를 확인하고 완료 자산/캐시를 재사용. 모호한 타임아웃 뒤에는 같은 장면을 재제출하지 않는다.
- **resume** — 완료된 클립/이미지/프리셋을 재사용하고, 페일오버 후 활성 계정을 보존한다(재개 시 legacy 회귀 없음).
- **자격증명은 리포 밖** — 이메일/OAuth 토큰/쿠키/API 키는 코드·YAML·로그·매니페스트·테스트에 절대 넣지 않는다. alias(`legacy_account`/`production_account`)만 등장한다.

## 구성 (alias 만, 자격증명 없음)

예시: `config/higgsfield_accounts.example.yaml` 참조. 실제 값은 alias·서버명·추정치뿐이며 계정 이메일을 넣지 않는다.
`starting_credit_estimate` 는 참고값이며 provider 잔액 데이터가 있으면 그것이 우선한다(추정치를 공식 잔액으로 취급하지 않는다).

## 설정 순서 (PowerShell)

```powershell
# 1) 두 Higgsfield MCP 서버를 서로 다른 이름으로, 각각 다른 계정으로 등록한다(자격증명은 노출하지 않는다).
#    두 번째 계정을 연결할 때 첫 계정 인증을 덮어쓰지 않도록 주의한다.
claude mcp list        # higgsfield_legacy 와 higgsfield_production 이 각각 보이는지 확인

# 2) 승인 프리셋 확인(무과금)
python cli/aivs_cli.py run projects/malli.yaml --quality-validation --preset malli_video
```

## 명령 (PowerShell)

```powershell
# 말리 품질검증 (무과금 — 검증 계획 출력)
python cli/aivs_cli.py run projects/malli.yaml --quality-validation --higgsfield-account legacy

# 야구백과 품질검증
python cli/aivs_cli.py run projects/baseball_dictionary.yaml --quality-validation --higgsfield-account legacy

# 말리 프로덕션 (자동 페일오버 + 재개)
python cli/aivs_cli.py run projects/malli.yaml --preset malli_video --higgsfield-account auto --resume

# 야구백과 프로덕션 (자동 페일오버 + 재개)
python cli/aivs_cli.py run projects/baseball_dictionary.yaml --preset baseball_dictionary_video --higgsfield-account auto --resume
```

> ⚠️ 라이브 자동 전환은 `higgsfield_legacy` 와 `higgsfield_production` 두 MCP 서버가 **각각 별도 계정으로 인증·등록**되어 신원이 확인되기 전까지 동작하지 않는다. 그 전에는 위 옵션이 무과금 안전 동작(프리셋 로드·검증 계획·계정 의도 로깅)만 수행한다. 현재 환경에는 `claude.ai Higgsfield` 단일 커넥터만 등록돼 있어 두 계정 동시 독립 인증이 **검증되지 않았다**.

## Troubleshooting

- **두 MCP alias 가 같은 계정으로 해석됨** — `higgsfield_legacy`·`higgsfield_production` 이 같은 OAuth 세션을 공유하면 동일 계정이 된다. 각 서버를 별도 Claude Code 프로필 또는 별도 MCP 래퍼 프로세스로 분리해 각기 다른 계정으로 인증하라. 등록 후 각 서버의 `balance` 값이 서로 다른지로 교차 확인한다(계정 신원은 로그로 남기지 않는다).
- **OAuth 세션 덮어쓰기** — 두 번째 계정 연결 시 첫 계정 인증이 덮여쓰이면 동시 이중 인증이 불가하다는 신호다. 프로필/래퍼 분리로 격리하라.
- **잔액 조회 없음** — provider balance 도구가 없으면 로컬 사용 원장 + `fallback_generation_limit` + 안전마진으로 판단하고, 명시적 부족 오류에도 전환한다. 이때 요약은 "estimate only" 로 표기되며 공식 잔액으로 위장하지 않는다.
- **모호한 타임아웃** — 원 job 상태를 먼저 확인한다. 완료면 재사용, 부족이면 전환, 불확실이면 멈춘다. 절대 곧바로 재제출하지 않는다(중복 과금 방지).
- **크레딧 오차감** — 요약에서 provider-reported 와 estimated 를 명확히 구분한다. 추정치는 절대 공식 잔액이 아니다.
- **계정 전환 후 재개** — 매니페스트의 `higgsfield_state.active_account` 가 보존되어 재개 시 legacy 로 되돌아가지 않는다.

---

# 📄 라이선스

Private Project
