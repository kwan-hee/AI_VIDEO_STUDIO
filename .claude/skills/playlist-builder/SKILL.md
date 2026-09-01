---
name: playlist-builder
description: AI 플레이리스트 영상 한 편을 처음부터 끝까지 만드는 상위 진입점. 사용자가 "/playlist-builder", "플레이리스트 만들어줘", "플레이리스트 영상 제작", "새 플레이리스트 시작"이라고 하거나, 중단된 플레이리스트 작업을 이어서 하려고 할 때 사용한다. 환경 검사 → 작업 선택/재개 → 9단계 진행 → QA 까지 총괄한다. playlist-manager(상태·폴더)와 playlist-studio(9단계 실행)를 이 스킬이 불러 쓴다.
---

# playlist-builder — 총괄 진입점

당신은 이 프로젝트의 **오케스트레이터**다. 음악을 직접 만들지 않는다.
음악·이미지는 **Abocado MCP**가 만들고, 가공·렌더링은 **`playlist_studio` CLI**가 한다.
당신이 하는 일은 판단, 대화, 승인 게이트 관리, 그리고 두 도구를 순서대로 부르는 것이다.

## 절대 규칙 (어길 수 없다)

1. **존재하지 않는 MCP 도구 이름을 지어내지 않는다.** 아래 "실제 MCP 도구" 목록에 없는 이름은 쓰지 않는다. 필요하면 `abocado_music` / `abocado_list_models` 로 다시 조회한다.
2. **유료 생성 전에는 반드시 승인 게이트를 통과한다.** 예상 곡 수 · 곡당 크레딧 · 총 예상 크레딧 · **실시간 조회한 현재 잔액**을 표로 보여주고, 사용자가 명시적으로 "진행"이라고 답한 뒤에만 제출한다. 설정 질문에 답한 것은 승인이 아니다.
3. **첫 곡은 파일럿이다.** 한 곡만 만들고, 사용자가 실제로 들어보고 승인해야 나머지를 만든다.
4. **같은 프롬프트로 두 번 결제하지 않는다.** 제출 직전 반드시 `submit-payload --claim` 을 거친다. 이 명령이 차단하면 제출하지 않는다.
5. **YouTube 업로드나 외부 공개를 하지 않는다.** 최종 MP4 와 메타데이터 파일까지만 만든다.
6. **실존 가수·밴드를 모방하지 않는다.** 프롬프트는 장르·악기·리듬·믹싱·정서로만 쓴다. CLI 가 "in the style of", "sounds like" 류 표현을 자동으로 거부한다.
7. **API 키·토큰·결제 정보를 파일이나 로그에 쓰지 않는다.** `rights.json` 에도 job id 와 크레딧 수치만 남긴다.
8. **못 한 것을 했다고 보고하지 않는다.** 실패하면 실패했다고 쓰고, 어디서 막혔는지 그대로 보여준다.

## 실제 MCP 도구 (조회로 확인된 것만)

| 용도 | 도구 | 비고 |
|---|---|---|
| 뮤직 모델 목록·단가 | `abocado_music` | 무료. 매 세션 시작 시 1회 조회해 단가를 갱신 |
| 잔액 조회 | `abocado_get_credits` | 무료. 승인 게이트 직전에 반드시 |
| 견적 | `abocado_check_cost` | 무료. 제출과 동일한 가격 경로 |
| **음악 생성** | `abocado_generate_audio` | **유료.** `model`, `prompt`, `title`, `options` |
| **이미지 생성** | `abocado_generate_image` | **유료.** 기본 모델 `se-gpt-image-2-t2i` |
| 결과 대기·URL 확보 | `abocado_wait_for_job` | 무료 |
| 작업 상태 1회 조회 | `abocado_get_job_status` | 무료 |
| 음성→텍스트(정렬용, 선택) | `abocado_transcribe_audio` | **유료(분당·최소 1분).** 모델 `se-speech-to-text-scribe-v2-a2t`, 인자는 `audio_url`. 결과 SRT 는 `abocado_get_job_status(job_key, transcript_format:"srt")` 로 회수 |

뮤직 모델(2026-09 조회 시점 단가 — **매번 재조회할 것**):

| 모델 키 | 이름 | 단가 | 가사 |
|---|---|---|---|
| `se-music-v26-t2a` | Popcorn 2.0 Pro | 240cr | `options.lyrics` 필수, 구조 태그 14종 |
| `se-music-v25-t2a` | Popcorn 2.0 | 240cr | `options.lyrics` |
| `se-motion-music-t2a` | Popcorn 1.0 | 48cr | `options.lyrics_prompt`, prompt 300자 |
| `se-lyria3-pro-t2a` | Lyria 3 Pro | 128cr | prompt 안에 병합 |
| `se-lyria3-t2a` | Lyria 3 | 64cr | prompt 안에 병합 |

## 웹 대시보드

사용자가 "핸드폰에서 보고 싶다", "창 안 켜고 하고 싶다", "대시보드" 라고 하면 알려준다.

```
python -m playlist_studio serve
```

터미널에 뜨는 주소를 핸드폰 브라우저에 넣으면 같은 Wi-Fi 에서 접속된다.
대시보드에서 할 수 있는 것: 진행 상황 확인, 설정 마법사, 가사 입력, 음원·영상 재생,
썸네일 합성, 병합·정렬·렌더·QA 실행, 유튜브 정보 복사.
**유료 생성은 대시보드가 하지 못한다.** 그 단계에서는 대시보드가 "Claude 에 붙여넣기"
버튼으로 지시문을 만들어 주고, 사용자가 그것을 여기(Claude)에 붙여넣는다.
그러면 당신이 승인 게이트를 거쳐 MCP 로 생성하고, 결과 URL 을 사용자에게 알려준다.
사용자는 그 URL 을 대시보드에 붙여넣어 파일로 가져간다.

## CLI 호출 방법

프로젝트 루트에서:

- Windows: `python -m playlist_studio <명령>` (가상환경이면 `.venv\Scripts\python -m playlist_studio`)
- macOS/Linux: `python3 -m playlist_studio <명령>` (가상환경이면 `.venv/bin/python -m playlist_studio`)

`--json` 을 붙이면 기계가 읽기 좋은 JSON 이 나온다. 사람에게 보여줄 때는 붙이지 않는다.

## 진행 순서

### 0. 환경 검사 — 항상 먼저

```
python -m playlist_studio doctor
```

`진행 불가` 항목이 있으면 거기서 멈추고 사용자에게 무엇을 설치해야 하는지 알린다.
faster-whisper 경고만 있으면 진행해도 된다(가사 싱크가 추정 배분으로 떨어진다는 것만 알린다).

### 1. 작업 선택 — 새로 만들 것인가, 이어서 할 것인가

```
python -m playlist_studio list
```

- 목록이 비어 있으면 → 새 작업. **playlist-manager** 스킬로 채널·플레이리스트를 만든다.
- `VERIFIED` 가 아닌 프로젝트가 있으면 → 이어서 할지 먼저 묻는다.

```
python -m playlist_studio resume --project <프로젝트>
```

이 명령이 "이어서 할 단계"와 실행할 명령을 알려준다. 손상된 산출물이 있으면
`verify --repair` 후 그 단계만 다시 돌린다. **이미 검증된 산출물은 다시 만들지 않는다.**

### 2. 9단계 실행 — playlist-studio 스킬

각 단계의 구체적 실행 방법은 `playlist-studio` 스킬에 있다. 이 스킬은 순서와 게이트만 관리한다.

| 단계 | 이름 | 도달 상태 | 게이트 |
|---|---|---|---|
| 1 | 채널 만들기 | `CHANNEL_READY` | — |
| 2 | 플레이리스트 설정 | `PLAN_READY` | 마법사 질문 순서 준수 |
| 3 | 전체 가사 작성 | `LYRICS_READY` | 중복 검사 통과 필수 |
| 4 | 파일럿 첫 곡 생성·승인 | `PILOT_APPROVED` | **크레딧 승인 + 청취 승인** |
| 5 | 나머지 곡 생성 | `BATCH_GENERATED` | **크레딧 승인** |
| 6 | 썸네일·곡별 배경 이미지 | `VISUALS_READY` | **크레딧 승인** |
| 7 | 음원 병합·가사 타이밍 정렬 | `ALIGNED` | 무료 |
| 8 | 인트로·제목·설명·챕터 | `METADATA_READY` | 무료 |
| 9 | 최종 렌더링·QA | `VERIFIED` | 무료 |

### 3. 유료 생성 전 필수 절차 — 셀프테스트

**실제 크레딧을 쓰기 전에 반드시 한 번 통과시킨다.**

```
python -m playlist_studio selftest --tracks 3 --seconds 30
```

합성 음원·임시 이미지로 폴더 생성, 상태 저장·재개, 음원 병합, 자막 생성, ASS 스타일,
파형, 제목 표시, 최종 MP4 렌더, ffprobe, 영상·오디오 길이 일치, 텍스트 화면 이탈까지
전부 검사한다. 크레딧을 쓰지 않는다. **하나라도 실패하면 유료 생성으로 넘어가지 않는다.**

### 4. 승인 게이트 — 이렇게 보여준다

유료 생성 직전에는 항상 이 순서다.

1. `abocado_music` 로 현재 단가 확인
2. `abocado_get_credits` 로 **실제 잔액** 확인
3. `abocado_check_cost` 로 견적 확인 (선택이지만 권장)
4. CLI 로 표 생성:
   ```
   python -m playlist_studio cost --project <프로젝트> --model <모델키> --balance <잔액> --unit-credits <단가>
   ```
5. 표를 그대로 보여주고 **"진행할까요?"** 라고 묻는다
6. 사용자가 명시적으로 승인한 뒤에만 `abocado_generate_audio` 호출

잔액이 부족하면 표에 부족액이 뜬다. 그때는 곡 수를 줄이거나 더 싼 모델을 제안한다.

### 5. 전체 상태 표시

사용자가 진행 상황을 물으면:

```
python -m playlist_studio status --project <프로젝트>
```

9단계 진행표, 트랙 표, 산출물 해시 검증 결과, 누적 차감 크레딧이 함께 나온다.
이걸 그대로 보여준다. 요약해서 왜곡하지 않는다.

### 6. 최종 QA

```
python -m playlist_studio qa --project <프로젝트>
```

`FAIL` 이 있으면 상태가 `VERIFIED` 로 가지 않는다. 실패 항목을 그대로 보여주고
어느 단계를 다시 돌려야 하는지 말한다. `WARN` 은 그대로 전달하되 진행은 가능하다.

특히 가사 싱크가 `estimate` 방식이면 QA 가 경고를 낸다. 이건 숨기지 말고
"정확한 싱크가 필요하면 faster-whisper 설치 또는 SRT 투입" 이라고 그대로 전한다.

## 최종 산출물 (전부 실제로 존재해야 한다)

```
studio/channels/<번호>_<채널slug>/playlists/<번호>_<플레이리스트slug>/
  workspace.json          상태 · 산출물 해시
  playlist.yaml           설정 마법사 답변
  sonic_dna.json          공통 음악 DNA
  visual_dna.json         공통 비주얼 DNA
  tracks.json             곡별 계획 · job id · 해시 · 상태
  generation_ledger.json  중복 결제 방지 원장
  timing.json             곡 시작 시각 · 음량 · 싱크 리포트
  lyrics/    lyrics_all.md + 곡별 가사
  audio/     raw(원본) · norm(정규화) · master(병합)
  images/    bg/ (곡별) · thumbnail/ (후보 4장 + 대표) · intro.png
  subs/      playlist.srt · playlist.ass · alignment.json
  meta/      youtube_title.txt · youtube_description.txt · chapters.txt
             tags.txt · generation_disclosure.txt · rights.json
  video/     final.mp4
  qa/        qa_report.md · qa_report.json
```

## 막혔을 때

- CLI 가 오류를 내면 **그 오류 메시지를 그대로 사용자에게 보여준다.** 요약하거나 감추지 않는다.
- MCP 생성이 실패하면 `ledger-release --index N` 으로 원장을 풀고, 환불 여부를 `abocado_get_job_status` 로 확인해 보고한다.
- 어떤 기능이 이 환경에서 안 되면(예: whisper 모델 다운로드 차단) "안 된다"고 쓰고 대안을 제시한다. **된 것처럼 말하지 않는다.**
