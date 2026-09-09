---
description: CLEAN에서 INFO로 수렴하는 4초 영상 프롬프트를 쓴다. 크레딧을 쓰지 않는다
---

# /video-prompts

승인된 CLEAN·INFO 쌍과 `manifests/IMAGE_SEQUENCE.md` 를 근거로
`prompts/VIDEO_GENERATION_PROMPTS.md` 를 쓴다.

자산 역할을 지킨다.

- **CLEAN**: 진짜 첫 프레임. 장면 형상·카메라 프레이밍·조명·재질의 출처
- **INFO**: 최종 그래픽 내용·라벨·수치·배치·색의 목표 참조

INFO 를 첫 프레임으로 쓰지 않는다. 평면 판처럼 움직이게 하지 않는다.
CLEAN 에서 출발해 그래픽이 실제 장면 위에 단계적으로 지어지다가
마지막 프레임에서 INFO 에 수렴하게 한다.

AGENTS.md 의 4초 구성 타이밍표를 그대로 적용한다.

장면마다 다음을 명시한다.

- CLEAN 원본 ID / INFO 목표 ID / 출력 파일명
- 카메라 이동: 시작 위치, 방향, 접근 대상, 최종 위치. 5~15도 범위의 한 번만
- 기준점 위치
- 그래픽이 지어지는 순서

`"anchor dot"` 대신 `"small marker dot"` 으로 쓴다.
`"dynamic camera movement"` 처럼 추상적으로 쓰지 않는다. 구체적으로 적는다.

**여기서 멈춘다.** 승인 뒤에 `/generate-video` 로 넘어간다.
