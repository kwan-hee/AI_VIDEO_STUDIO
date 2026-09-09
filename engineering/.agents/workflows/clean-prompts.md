---
description: CLEAN 키프레임 생성 프롬프트를 쓴다. 크레딧을 쓰지 않는다
---

# /clean-prompts

`prompts/CLEAN_KEYFRAME_PROMPTS.md` 에 장면별 프롬프트를 쓴다.

CLEAN 은 인포그래픽이 전혀 없는 순수 3D 장면이다. 다음을 담는다.

- 피사체와 재질, 구조의 실제 형상
- 카메라 각도와 구도. 세로 9:16 에 맞는 구도로 잡는다
- 조명과 색감
- **금지 문구를 반드시 넣는다**: `no text, no letters, no arrows, no labels, no graphics, no logos, no watermark`

세로 프레임에 가로형 구도를 요청하면 장면이 90도 돌아갈 수 있다.
넓은 구조를 담아야 하면 "카메라 쪽으로 비스듬히" 구도로 바꿔 요청한다.

CLEAN 은 뒤에 오는 INFO 와 영상의 기준이 되므로, 라벨이 들어갈 여백을
미리 비워 둔다. 화면 하단은 자막 영역이므로 핵심 피사체를 두지 않는다.

**여기서 멈춘다.** 프롬프트 승인 뒤에 `/generate-clean` 으로 넘어간다.
