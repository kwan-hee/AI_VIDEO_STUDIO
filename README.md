# AI_VIDEO_STUDIO

AI 영상 제작 자동화 R&D 프로젝트.

## 개요

## 폴더 구조

## 시작하기

## AI 플레이리스트 자동 제작

Claude Code(오케스트레이터) + Abocado AI MCP(생성) + Python·FFmpeg(가공)로
플레이리스트 영상 한 편을 처음부터 끝까지 만든다.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playlist_studio doctor      # 환경 검사
.venv/bin/python -m playlist_studio selftest    # 전 과정 검증 (크레딧 0)
.venv/bin/python -m playlist_studio serve       # 웹 대시보드 (핸드폰에서 접속 가능)
```

Windows 는 `대시보드_실행.bat` 를 두 번 클릭하면 된다.
Claude Code 안에서는 `/playlist-builder` 로 시작한다.

자세한 내용: [docs/50_PLAYLIST_AUTOMATION.md](docs/50_PLAYLIST_AUTOMATION.md)

## 참고 문서
