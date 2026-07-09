# AI_VIDEO_STUDIO - AGENTS.md

## 역할

이 프로젝트는 AI 영상 제작 자동화 시스템이다.

기존 운영 프로젝트는 절대 수정하지 않는다.
이 프로젝트는 새로운 기능을 실험하고 검증하는 R&D 프로젝트다.

## 핵심 원칙

1. 기존 PROJECT 폴더는 절대 수정하지 않는다.
2. 모든 실험은 AI_VIDEO_STUDIO 안에서만 진행한다.
3. 검증된 기능만 나중에 기존 운영 프로젝트로 이전한다.
4. AI 서비스는 역할별로 분리한다.
5. 비용과 품질을 함께 고려한다.

## 기본 AI 역할

- Claude Code: 전체 기획, 판단, 실행 지휘
- Nano Banana: 이미지 생성
- Magnific: 대표 이미지 품질 향상
- Google Flow: 말리 동화 영상 생성
- Higgsfield: 야구백과사전 영상 생성
- Hedra: 음성 생성
- Whisper: 자막 생성
- FFmpeg: 최종 영상 합성

## 플랫폼 선택 규칙

### 말리 동화

기본 영상 생성 도구는 Google Flow를 사용한다.

우선순위:

1. Google Flow
2. Higgsfield

### 야구백과사전

기본 영상 생성 도구는 Higgsfield를 사용한다.

우선순위:

1. Higgsfield
2. Google Flow

### Magnific 사용 기준

Magnific는 모든 이미지에 사용하지 않는다.

사용 대상:

- 썸네일
- 말리 동화 첫 장면
- 말리 동화 마지막 장면
- 야구백과사전 오프닝 장면
- 야구백과사전 핵심 장면

일반 장면은 Nano Banana 이미지에서 바로 영상 생성으로 넘어간다.

## 작업 시작 전 확인

작업을 시작할 때 반드시 아래 문서를 먼저 확인한다.

- docs/01_PROJECT_GOAL.md
- docs/02_AI_ROUTER_POLICY.md
- docs/03_COST_POLICY.md

말리 작업이면 추가로 확인한다.

- docs/04_MALLI_PIPELINE.md
- memory/malli_character.md

야구백과 작업이면 추가로 확인한다.

- docs/05_BASEBALL_PIPELINE.md
- memory/baseball_terms.md

## 목표

사용자는 주제만 입력한다.

Claude Code는 다음을 자동으로 판단한다.

- 어떤 콘텐츠인지
- 어떤 AI를 사용할지
- Magnific를 사용할지
- Flow를 사용할지
- Higgsfield를 사용할지
- 비용을 줄일 방법이 있는지
- 최종 결과물을 어디에 저장할지
