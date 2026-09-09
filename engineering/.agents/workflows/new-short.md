---
description: 새 프로젝트를 연다. 기획서가 있으면 그것으로, 없으면 대본부터 쓴다
---

# /new-short

인자: 주제. 없으면 주제 하나만 묻는다.

## 1. 폴더를 만들고 기획서부터 찾는다

`<주제>_쇼츠/` 폴더와 하위 구조(script, clean, info, video, edit, manifests, prompts)를 만든다.

**그다음 폴더 안에 기획서 `.md` 파일이 있는지 확인한다.**

```
기획서가 있는가?
  ├─ 있다 → 2-A 로 간다. 대본을 새로 쓰지 않는다.
  └─ 없다 → 2-B 로 간다.
```

## 2-A. 기획서가 있을 때

기획실에서 뽑은 문서다. 탭 구조를 읽어 해당 파일로 옮겨 담는다.

| 기획서 탭 | 옮길 파일 |
|---|---|
| 01 대본 | `script/APPROVED_NARRATION_KR.md` |
| 02 장면 설계 | `manifests/IMAGE_SEQUENCE.md` |
| 03 키프레임 프롬프트 | `prompts/CLEAN_KEYFRAME_PROMPTS.md`, `prompts/INFOGRAPHIC_KEYFRAME_PROMPTS.md` |
| 04 영상 프롬프트 | `prompts/VIDEO_GENERATION_PROMPTS.md` |
| 05 자막 | `edit/subtitles_*.srt` |
| 06 업로드 정보 | `script/TITLE_DESCRIPTION.md` |
| 사실 확인 | `script/SOURCE.md` |

옮기면서 할 일은 세 가지뿐이다.

1. **내레이션 한 줄 = 한 장면.** 줄 수를 세어 장면 수를 확정하고
   `S01A` / `KF-01A` / `CLIP01` 식별자를 붙인다.
2. **엔진 규칙을 입힌다.** 프롬프트 내용은 그대로 두고 설정만 바꾼다.
   영상은 `kling3_0` + `sound: "off"` + 9:16, 이미지는 `nano_banana_pro` 2k.
   `"anchor dot"` 이 있으면 `"small marker dot"` 으로 바꾼다.
3. **추정 수치를 검색으로 확인한다.** 고친 값은 대본·자막·프롬프트에 일관되게 반영하고
   근거를 `script/SOURCE.md` 에 남긴다.

**프롬프트를 처음부터 다시 쓰지 않는다.** 기획서에 이미 있다.

끝나면 이렇게 보고한다.

```
기획서를 읽었습니다.
장면 <n>개 (내레이션 <n>줄), 목표 길이 <초>초
고친 수치: <없음 또는 목록>
바꾼 설정: 영상 엔진 -> kling3_0 sound=off
예상 총비용: CLEAN <n>장 + INFO <n>장 + 영상 <n>클립 = <크레딧> 크레딧
승인하시면 /generate-clean 부터 시작합니다.
```

## 2-B. 기획서가 없을 때

주제를 공학 관점에서 깊게 판다. 불확실한 수치는 검색으로 확인한다.
AGENTS.md 의 대본 논리 네 가지(중심 질문 / 핵심 메커니즘 / 보이는 물리 흐름 / 차별점)를
먼저 확정한 뒤 대본을 `script/APPROVED_NARRATION_KR.md` 에 쓴다.

**여기서 멈춘다.** 대본 승인 전에는 장면 설계도 이미지 생성도 하지 않는다.

## 3. 공통

`manifests/PROJECT_STATUS.md` 를 만들고 현재 단계를 기록한다.
