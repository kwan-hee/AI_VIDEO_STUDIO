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
![Tests](https://img.shields.io/badge/tests-403_passed-brightgreen)
![License](https://img.shields.io/badge/license-Private-lightgrey)
</p>

</div>
## 📚 Table of Contents

- Features
- Architecture
- Installation
- Configuration
- Environment Variables
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
├── pipeline/           # 멀티씬 제작 파이프라인
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
403 passed
```

---

# 📄 라이선스

Private Project
