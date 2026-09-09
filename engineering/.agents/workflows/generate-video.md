---
description: 승인된 영상 프롬프트를 Kling 3.0으로 제출한다. 크레딧이 차감된다
---

# /generate-video

**크레딧을 차감한다.** 실행 전에 확인한다.

1. `balance` 로 잔액 확인.
2. 예상 차감액을 보고하고 승인을 받았는가. 4초 클립은 장당 5.00 크레딧이다.

페이로드는 반드시 이 형태여야 한다.

```json
{
  "model": "kling3_0",
  "prompt": "<영어 프롬프트>",
  "duration": 4,
  "aspect_ratio": "9:16",
  "sound": "off",
  "mode": "std",
  "medias": [
    { "role": "start_image", "value": "<CLEAN job id>" },
    { "role": "end_image",   "value": "<INFO job id>" }
  ]
}
```

**`"sound": "off"` 를 빼면 초당 1.75 로 올라 Wan 과 같아진다.** 절대 빼지 않는다.

`generate_video_batch` 로 한 번에 12건까지 제출하고 `jobs_wait` 로 기다린다.
전부 끝나면 `show_generation_by_ids` 로 한 번에 보여 준다.
클립마다 `job_display` 를 따로 부르지 않는다.

제출 뒤 실제 차감액을 조회해 예상과 일치하는지 확인하고 보고한다.

검수 항목.

- CLEAN 에서 시작해 INFO 로 수렴하는가
- 그래픽이 동시에 페이드인 하지 않고 순서대로 지어지는가
- 카메라가 한 번만, 절제되게 움직이는가
- 화살표 방향이 뒤집히지 않았는가
- 구조가 변형되거나 물체가 복제되지 않았는가

결함이 한 클립에만 있으면 그 클립만 다시 만든다.
원인을 확인하지 않고 같은 프롬프트를 다시 던지지 않는다.
