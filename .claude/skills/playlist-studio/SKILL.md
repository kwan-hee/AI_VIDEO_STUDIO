---
name: playlist-studio
description: 플레이리스트 제작 9단계를 실제로 실행한다. 채널 만들기, 플레이리스트 설정 마법사, 전체 가사 작성, 파일럿 첫 곡 생성·승인, 나머지 곡 생성, 썸네일·곡별 배경 이미지, 음원 병합·가사 타이밍 정렬, 인트로·유튜브 제목·설명·챕터·태그, 최종 영상 렌더링·QA 를 담당한다. 사용자가 "가사 써줘", "곡 만들어줘", "썸네일 만들어줘", "영상 렌더해줘", "챕터 뽑아줘" 처럼 개별 단계를 요청할 때도 사용한다.
---

# playlist-studio — 9단계 실행

호출 형식: `python -m playlist_studio <명령> --project <프로젝트>`
(Windows 가상환경이면 `.venv\Scripts\python`, Linux/macOS 면 `.venv/bin/python`)

**당신이 직접 만드는 것은 글(가사·제목·설명)뿐이다.** 음악·이미지는 Abocado MCP,
파일 처리는 CLI 가 한다. 유료 호출 전에는 항상 승인 게이트를 통과한다.

---

## 1단계 — 채널 만들기

`playlist-manager` 스킬의 `channel-new` / `playlist-new` 를 쓴다. 여기서 반복하지 않는다.
도달 상태: `CHANNEL_READY`

---

## 2단계 — 플레이리스트 설정 (마법사)

**한 번에 많이 묻지 않는다.** 다음 명령이 "아직 답하지 않은 질문"만 순서대로 돌려준다.

```
python -m playlist_studio config-status --project <프로젝트> --limit 2
```

한 턴에 **최대 2개**만 묻는다. 선택지가 있으면 그대로 제시하고, 추천 1개를 이유와 함께 붙인다.
답을 받으면 저장한다:

```
python -m playlist_studio config-set --project <프로젝트> genre=lofi subgenre="jazzy tape lofi"
```

질문 순서 (사양 고정, 바꾸지 않는다):
채널 → 장르 → 세부 장르 → 플레이리스트 목적 → 청취 상황 → 보컬/연주곡 →
가사 언어 → 자막 언어 → 곡 수 → 곡별 목표 길이 → 전체 목표 길이 →
BPM 하한 → BPM 상한 → 전체 정서 변화 → 비주얼 프리셋 → 썸네일 언어 → 썸네일 콘셉트

- `vocal_mode=instrumental` 이면 가사 언어 질문은 자동으로 건너뛴다.
- 썸네일 콘셉트는 6단계에서 후보 4장을 본 뒤 정한다. 2단계에서는 비워 둬도 된다.
- 곡 수 × 곡 길이와 전체 목표가 크게 어긋나면 경고가 나온다. 그대로 사용자에게 전달한다.
- **다시 실행해도 이미 답한 것은 묻지 않는다.** 이게 이 명령의 핵심이다.

모든 질문이 끝나면:

```
python -m playlist_studio plan --project <프로젝트>
```

이때 만들어지는 것:

- **`sonic_dna.json`** — 모든 곡이 공유하는 음악 설계도.
  장르·세부장르 / 악기 구성 / 드럼 패턴 / 베이스 특성 / 화성·코드 분위기 /
  보컬 성별·음역·전달 방식 / 믹싱 질감 / 에너지 범위 / 금지 요소 /
  실존 아티스트 미사용 조건.
- **`visual_dna.json`** — 색상 팔레트 / 사진·일러스트 스타일 / 조명 / 구도 /
  질감 / 포인트 색상 / 인물 사용 여부 / 여백 위치 / 금지 요소.
- **`tracks.json`** — 곡별 슬롯. BPM·감정·인트로 악기·에너지·구조 변형이
  정서 곡선에 따라 자동 배분된다. **인트로 악기는 곡마다 전부 다르게** 잡힌다.

DNA 를 보고 싶으면 `dna-show --project <프로젝트>`.
파일럿 거절 후 음색을 바꿀 때만 `dna-set --project <프로젝트> vocal_delivery="..."` 를 쓴다.

도달 상태: `PLAN_READY`

---

## 3단계 — 전체 가사 작성

**당신이 직접 쓴다.** 곡마다 제목·부제·주제를 정하고 가사를 쓴다.

가사 규칙:

- 곡마다 **제목과 주제가 달라야 한다.**
- **첫 줄과 후렴이 다른 곡과 겹치면 안 된다.** (유사도 0.80 이상이면 오류)
- `[Intro] [Verse] [Pre Chorus] [Chorus] [Bridge] [Outro]` 등 구조 태그를 쓴다.
  (Popcorn 2.0 Pro 는 `[Post Chorus] [Transition] [Build Up]` 도 지원)
- 가사 언어(`lyrics_language`)와 자막 언어(`subtitle_language`)는 별개로 관리된다.
- 실존 아티스트·기존 곡 인용 금지.

곡마다 두 번 호출한다:

```
python -m playlist_studio track-set --project <프로젝트> --index 1 \
  title="창가의 새벽" subtitle="first light" lyrical_theme="밤에서 아침으로 건너가는 순간"

python -m playlist_studio track-lyrics --project <프로젝트> --index 1 --text "[Verse]
창틀에 맺힌 물기를 손끝으로 지운다
...
[Chorus]
천천히 밝아지는 쪽으로"
```

긴 가사는 파일로: `track-lyrics --index 1 --file lyrics_draft.md`

전 곡을 쓴 뒤 반드시 검사한다:

```
python -m playlist_studio lyrics-validate --project <프로젝트>
```

오류가 있으면 **고칠 때까지 다음으로 넘어가지 않는다.** 경고는 사용자에게 보여주고 판단을 맡긴다.

통과하면:

```
python -m playlist_studio lyrics-collect --project <프로젝트>
```

`lyrics/lyrics_all.md` 와 곡별 파일이 함께 저장되고, 각 가사의 정규화 해시가
`tracks.json` 에 기록된다. **이 해시가 제출 직전 다시 대조된다** — 로컬 파일과
생성에 넘긴 가사가 다르면 제출이 막힌다.

도달 상태: `LYRICS_READY`

---

## 4단계 — 파일럿 첫 곡 생성 및 승인

### 4-1. 크레딧 승인 게이트 (건너뛰지 않는다)

1. `abocado_music` 호출 → 모델 목록과 **현재 단가** 확인
2. `abocado_get_credits` 호출 → **현재 잔액** 확인
3. 표를 만든다:
   ```
   python -m playlist_studio cost --project <프로젝트> \
     --model se-music-v26-t2a --balance <잔액> --unit-credits <단가>
   ```
4. 표를 그대로 보여주고 **"파일럿 1곡을 생성할까요? (N cr 차감)"** 이라고 묻는다
5. **명시적 승인 후에만** 다음으로 간다

### 4-2. 제출 페이로드 생성 (중복 결제 차단)

```
python -m playlist_studio submit-payload --project <프로젝트> --index 1 --claim
```

이 명령이 하는 일:

- 로컬 가사 파일 ↔ `tracks.json` 해시 대조 (틀리면 중단)
- 모델 규약에 맞게 프롬프트 조립 (Popcorn 1.0 은 300자, Lyria 는 가사 병합 후 2000자)
- 실존 아티스트 표현 검사
- **fingerprint(모델+프롬프트+가사) 를 원장에 잠근다**
- `abocado_generate_audio` 에 그대로 넣을 JSON 인자를 출력

⛔ **"중복 생성 차단" 이 나오면 제출하지 않는다.** 같은 조합으로 이미 크레딧을 썼다는 뜻이다.

### 4-3. MCP 제출

출력된 JSON 인자를 **그대로** `abocado_generate_audio` 에 넣는다. 임의로 바꾸지 않는다.
완료를 기다리려면 `abocado_wait_for_job`.

### 4-4. 결과 가져오기 + 검사

```
python -m playlist_studio track-import --project <프로젝트> --index 1 \
  --src "<결과 URL>" --job-id "<job_key>" --credit-cost <차감액>
```

자동으로 하는 것: 다운로드 → ffprobe 로 길이·코덱 확인 → 무음 비율 측정 →
sha256 기록 → 원장 완료 처리 → 재생 명령 안내.

### 4-5. 사용자 청취 승인

```
python -m playlist_studio pilot-status --project <프로젝트>
```

길이·코덱·무음 비율·재생 방법이 나온다. 사용자에게 **실제로 들어보라고 하고**,
세 가지 중 하나를 고르게 한다:

| 선택 | 실행 | 비용 |
|---|---|---|
| **승인** | `pilot-approve --project <프로젝트>` | 없음 |
| **수정** | `dna-set` 으로 sonic_dna 속성 변경 → 4-1 부터 다시 | **곡당 크레딧 재차감** |
| **재생성** | `ledger-release --index 1` → 4-1 부터 다시 | **곡당 크레딧 재차감** |

수정 시 바꿀 수 있는 속성은 `dna-show` 로 보여주고 하나만 고르게 한다
(예: `vocal_delivery`, `drum_pattern`, `mix_texture`, `instrumentation`).
**재생성에 크레딧이 추가로 든다는 사실을 반드시 먼저 알린다.**

**`pilot-approve` 전에는 나머지 곡을 절대 생성하지 않는다.**

도달 상태: `PILOT_APPROVED`

---

## 5단계 — 나머지 곡 생성

1. 다시 크레딧 승인 게이트 (남은 곡 수 × 단가, 실시간 잔액)
   ```
   python -m playlist_studio cost --project <프로젝트> --balance <잔액> --unit-credits <단가>
   ```
   이미 완료된 곡은 "이미 생성됨" 으로 빠지고 남은 곡만 계산된다.
2. 곡마다 4-2 → 4-3 → 4-4 반복 (`--index 2`, `3`, …)
3. 진행 상황 확인:
   ```
   python -m playlist_studio batch-status --project <프로젝트>
   ```

중간에 끊겨도 안전하다. 다시 시작하면 완료된 곡은 원장이 막고, 남은 곡만 만든다.

도달 상태: `BATCH_GENERATED`

---

## 6단계 — 썸네일과 곡별 배경 이미지

### 6-1. 프롬프트 받기

```
python -m playlist_studio visual-prompts --project <프로젝트>
```

나오는 것: 썸네일 후보 4개 콘셉트(A/B/C/D) 프롬프트, 인트로 프롬프트, 곡별 배경 프롬프트.

**모든 프롬프트에 "글자를 그리지 말 것" 이 박혀 있다.**
제목·곡명·로고는 **전부 로컬에서 합성**한다. 이미지 AI 에게 글자를 시키지 않는다.

### 6-2. 크레딧 승인 → 생성

이미지도 유료다. `abocado_check_cost` 로 견적을 내고 잔액과 함께 보여준 뒤 승인을 받는다.
`abocado_generate_image` (기본 `se-gpt-image-2-t2i`) 로 생성한다.

### 6-3. 가져오기

```
python -m playlist_studio image-import --project <프로젝트> --role thumb-candidate --slot 1 --src "<URL>" --provider abocado --job-id "<key>" --credit-cost <액수>
python -m playlist_studio image-import --project <프로젝트> --role bg --index 1 --src "<URL>" ...
python -m playlist_studio image-import --project <프로젝트> --role intro --src "<URL>" ...
```

곡마다 배경 **최소 1장**, 썸네일 후보 **4장**, 인트로 **1장**.

### 6-4. 콘셉트 선택 → 대표 썸네일 합성

후보 4장을 사용자에게 보여주고 하나를 고르게 한다. 그 다음:

```
python -m playlist_studio thumbnail --project <프로젝트> --concept B
```

1280×720 PNG 를 만들고 제목·부제·장르 뱃지를 **로컬 폰트로 합성**한다.
글자가 화면을 벗어나면 자동으로 줄바꿈·축소하고, 그래도 안 되면 `overflow` 로 보고한다.
2MB 를 넘으면 JPEG 도 같이 저장한다 (YouTube 한도).

```
python -m playlist_studio visuals-done --project <프로젝트>
```

도달 상태: `VISUALS_READY`

---

## 7단계 — 음원 병합과 가사 타이밍 정렬

### 7-1. 정규화 + 병합

```
python -m playlist_studio build-audio --project <프로젝트> --crossfade 1.5
```

- ffprobe 로 모든 음원 검사 → **손상되거나 너무 짧은 파일은 제외하고 목록에 남긴다**
- 곡별로 `loudnorm` 2-pass → **-14 LUFS / True Peak -1dB 이하**
- `acrossfade` 로 크로스페이드 병합 (곡보다 긴 값은 자동으로 줄인다)
- `timing.json` 에 곡별 시작 시각·길이·전체 음량이 기록된다

제외된 곡이 있으면 사용자에게 그대로 알리고, 그 곡을 다시 만들지 물어본다.

### 7-2. 정렬

```
python -m playlist_studio align --project <프로젝트> --method auto
```

세 가지 방식이 있고, **어느 것을 썼는지 항상 보고된다**:

| 방식 | 조건 | 정확도 |
|---|---|---|
| `whisper` | faster-whisper 설치됨 | 원문 대조 후 300ms 목표 만족 가능 |
| `srt` | 외부 ASR SRT 를 `--srt-dir` 로 제공 | 위와 동일 경로 |
| `estimate` | 위 둘 다 없음 | **300ms 보장 안 됨** — 반드시 그렇게 말한다 |

`whisper`·`srt` 는 인식 결과를 **원문 가사에 되맞춘다**. ASR 이 "조용이 안자 있어"로
잘못 들었어도 화면에는 원문 "조용히 앉아 있어"가 나가고, 타이밍만 가져온다.
인식 못 한 줄은 앞뒤 사이에 보간하고 `interpolated` 로 표시한다.

Abocado STT 를 쓰려면 `abocado_transcribe_audio` 를 `transcript_format:"srt"` 로 호출해
곡별 SRT 를 `01.srt`, `02.srt` … 로 저장한 뒤 `--method srt --srt-dir <폴더>`.

### 7-3. 자막 생성

```
python -m playlist_studio subtitles --project <프로젝트> --intro-seconds 6
```

- **SRT** — 보관·업로드용, 순수 텍스트
- **ASS** — 렌더용. 현재 가사 강조 + 다음 줄 흐린 미리보기 + 곡 번호/제목/부제 카드 +
  인트로 타이틀. 폰트는 자막 언어에 맞춰 자동 선택된다(Windows 는 맑은 고딕 등).

도달 상태: `ALIGNED`

---

## 8단계 — 인트로 · 유튜브 제목 · 설명 · 챕터 · 태그

```
python -m playlist_studio metadata --project <프로젝트> --plan-note "<생성 당시 플랜>"
```

만들어지는 것:

| 파일 | 내용 |
|---|---|
| `youtube_title.txt` | 100자 한도 안에서 제목 + 곡 수·길이 |
| `youtube_description.txt` | 소개 + 챕터 + 곡별 설명 + 생성 고지 (5000자 한도) |
| `chapters.txt` | **첫 줄이 반드시 `0:00`** — 아니면 YouTube 가 인식하지 않는다 |
| `tags.txt` | 중복 제거, 합계 500자 한도 |
| `generation_disclosure.txt` | AI 생성 고지 |
| `rights.json` | 음악·이미지마다 제공자·생성일·플랜·프롬프트 파일·사용 권한·원본 해시 |

**쓰지 않는 문구:** 수익 보장, 저작권 보장, "저작권 문제 없음". `rights.json` 에도
"이 파일은 생성 이력 기록이며 저작권 귀속이나 수익 발생을 보장하지 않는다"고 명시된다.

**업로드는 하지 않는다.** 사용자가 직접 복사해 올리도록 파일까지만 만든다.

도달 상태: `METADATA_READY`

---

## 9단계 — 최종 영상 렌더링과 QA

```
python -m playlist_studio render --project <프로젝트> --intro-seconds 6
```

3단계로 나뉘어 있고 각 중간물은 `work/` 에 남는다. **다시 돌리면 정상인 것은 재사용한다.**

- **A. 배경** — 곡별 이미지에 느린 줌·패닝(zoompan), 필름 그레인(noise). 곡마다 방향이 다르다.
- **B. 파형** — showwaves, 하단 140px, 프리셋 색상. 검은 배경은 키아웃되어 배경이 비친다.
- **C. 합성** — 배경 + 파형 + 인트로 이미지(페이드) + ASS 자막 + AAC 오디오

출력 규격: **1920×1080 / 30fps / H.264 yuv420p / AAC 256k 48kHz / faststart**
인트로는 첫 곡 위에 5~8초 오버레이된다 (무음 구간을 넣지 않으므로 챕터가 밀리지 않는다).

느리면 `--preset ultrafast --crf 26` 으로 초안을 먼저 보여주고, 확정 후 기본값으로 다시 돌린다.

### QA

```
python -m playlist_studio qa --project <프로젝트>
```

검사 항목: 곡별 음원 유효성·해시, 가사 중복·해시, 곡별 이미지 존재, 썸네일 규격(1280×720/2MB)과
**텍스트 화면 이탈**, SRT·ASS 존재와 ASS 스타일, 메타데이터 6종, 제목 길이, 챕터 첫 줄 `0:00`,
`rights.json` 항목 수, 최종 MP4 규격(해상도·코덱·픽셀포맷·fps·오디오), faststart,
**영상·오디오 길이 일치**, 병합 음원 길이와 일치, 자막이 영상 밖으로 나가지 않는지,
가사 싱크 방식, 산출물 전체 해시 검증.

`qa/qa_report.md` 와 `qa_report.json` 이 저장된다. 보고서를 **그대로** 보여준다.
`FAIL` 이 있으면 `VERIFIED` 로 가지 않는다.

도달 상태: `VERIFIED`

---

## 유료 생성 전 셀프테스트 (필수)

```
python -m playlist_studio selftest --tracks 3 --seconds 30
```

합성 음원·임시 이미지로 위 전 과정을 돌린다. 크레딧을 쓰지 않는다.
**전부 통과한 뒤에 4단계로 간다.** 실패하면 실패 내용을 그대로 보고하고 멈춘다.

## 실패 시

- CLI 오류는 **그대로** 사용자에게 보여준다.
- MCP 생성 실패 시 `abocado_get_job_status` 로 환불 상태(`refund_pending`/`refunded`)를
  확인해 보고한 뒤, `ledger-release` 로 원장을 풀고 재시도 여부를 묻는다.
- 어느 단계에서든 `resume --project <프로젝트>` 로 이어서 할 수 있다.
