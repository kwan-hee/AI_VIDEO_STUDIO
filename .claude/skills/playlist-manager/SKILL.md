---
name: playlist-manager
description: 플레이리스트 채널과 프로젝트 폴더를 관리한다. 사용자가 "새 채널 만들어줘", "채널 목록 보여줘", "플레이리스트 목록", "지금 어디까지 했지", "이어서 하자", "폴더 정리해줘", "파일 검증해줘"라고 할 때 사용한다. 채널 생성, 채널 번호·slug 부여, CHANNEL.md 와 workspace.json 관리, 현재 단계·실패 단계 표시, 산출물 해시 확인, 중단된 단계부터 재개를 담당한다.
---

# playlist-manager — 채널 · 상태 · 재개

폴더와 상태를 책임진다. 음악·이미지 생성은 하지 않는다.
호출 형식은 `python -m playlist_studio <명령>` (가상환경이면 그 안의 python).

## 1. 새 채널 만들기

먼저 이름과 장르를 묻는다. 한 번에 하나씩.

```
python -m playlist_studio channel-new --name "로파이 밤 채널" --genre lofi --concept "야근·새벽 공부용 로파이"
```

- **채널 번호**는 `001`, `002` … 로 자동 부여된다. 사용자가 정하지 않는다.
- **slug** 는 한글을 로마자로 음차해 만든다 (`로파이 밤 채널` → `ropai-bam-chaeneol`).
  파일시스템 안전 문자만 남기고, 이미 있으면 `-2` 를 붙인다.
- `CHANNEL.md`(사람이 읽는 문서)와 `channel.json`(기계용)이 함께 생긴다.
- 원본 한글 이름은 두 파일에 그대로 보존되므로 slug 가 음차되어도 정보가 사라지지 않는다.

## 2. 새 플레이리스트 만들기

```
python -m playlist_studio playlist-new --channel 001_ropai-bam-chaeneol --title "비 오는 날 창가에서"
```

`workspace.json`(상태 `INIT` → `CHANNEL_READY`)과 `playlist.yaml`(빈 설정)이 생긴다.
출력에 나오는 프로젝트 경로를 이후 모든 명령의 `--project` 로 쓴다.
`--project` 에는 전체 경로, `<채널dir>/<플레이리스트dir>`, 또는 유일하면 플레이리스트 slug 만 줘도 된다.

## 3. 목록 보기

```
python -m playlist_studio channel-list      # 채널 + 그 아래 플레이리스트 + 상태
python -m playlist_studio list              # 플레이리스트만, 상태·곡 수·갱신 시각
```

표를 그대로 보여준다.

## 4. 현재 단계와 실패 단계

```
python -m playlist_studio status --project <프로젝트>
```

나오는 것:

- 현재 상태 (`INIT` … `VERIFIED` 12단계 중 하나)
- 9단계 진행표 — ✅ done / 🔄 running / ❌ failed / ⬜ pending
- **실패한 단계는 오류 메시지가 비고란에 그대로 남는다.** 이걸 사용자에게 전달한다.
- 트랙별 제목·BPM·감정·상태·길이
- 산출물 해시 검증 요약
- 누적 차감 크레딧

## 5. 완료 파일의 존재와 해시 확인

```
python -m playlist_studio verify --project <프로젝트>
```

`workspace.json` 에 등록된 모든 산출물을 열어 **크기와 sha256 을 재계산**한다.
- 정상 → 다시 만들지 않고 재사용한다.
- 없음 / 크기 불일치 / 해시 불일치 → 손상으로 보고한다.

손상된 것을 다시 만들려면:

```
python -m playlist_studio verify --project <프로젝트> --repair
```

레지스트리에서 손상 항목만 지운다. 그 뒤 해당 단계를 다시 실행하면 **그 파일만** 새로 만든다.
이미 정상인 파일은 건드리지 않는다. **음원은 다시 생성하지 않는다** — 원장이 막는다.

## 6. 중단된 단계부터 재개

```
python -m playlist_studio resume --project <프로젝트>
```

출력에 다음이 들어 있다:

- 현재 상태
- 손상된 산출물이 있으면 그 목록과 복구 명령
- 실패한 단계가 있으면 그 오류
- **이어서 할 단계**와 실행할 CLI 명령

재개 원칙:

1. Claude Code 가 꺼졌거나 컴퓨터가 재부팅돼도 `workspace.json` 만 있으면 이어진다.
2. 상태는 **단계가 성공한 뒤에만** 앞으로 간다. 실패하면 그 자리에 머문다.
3. 되돌리기는 명시적일 때만 한다 (`pilot-reject` 등). 자동으로 되돌리지 않는다.
4. 재개 시 이미 생성된 음원은 **절대 다시 생성하지 않는다.** `generation_ledger.json` 이
   같은 모델·프롬프트·가사 조합을 기억하고 있다가 재제출을 차단한다.

## 7. 원장 확인 — 크레딧이 어디에 쓰였나

```
python -m playlist_studio ledger-show --project <프로젝트>
```

트랙별 모델·상태·job id·크레딧과 완료 건 합계가 나온다.
실패한 생성 건을 다시 시도해야 하면:

```
python -m playlist_studio ledger-release --project <프로젝트> --index 3 --reason "생성 실패"
```

⚠️ 해제 후 재제출하면 **크레딧이 다시 차감된다.** 사용자에게 반드시 알린다.
이미 `done` 인 건은 해제되지 않는다 (프롬프트를 바꿔야 한다).

## 8. 폴더 정리

```
python -m playlist_studio clean --project <프로젝트> --work    # 중간 렌더 파일 (work/)
python -m playlist_studio clean --project <프로젝트> --norm    # 정규화 음원 (audio/norm/)
```

- `--work` 는 배경 세그먼트·파형 등 재생성 가능한 중간물을 지운다. 다음 렌더가 느려질 뿐 손실은 없다.
- `--norm` 은 정규화 WAV 를 지운다. `build-audio` 를 다시 돌리면 복구된다.
- **원본 음원(`audio/raw/`), 가사, 이미지, 최종 MP4 는 이 명령이 건드리지 않는다.**
  이것들을 지우면 크레딧을 다시 써야 하므로, 지우려면 사용자가 직접 하도록 안내한다.

## 9. 상태 값의 뜻

| 상태 | 뜻 |
|---|---|
| `INIT` | workspace 만 생김 |
| `CHANNEL_READY` | 채널·플레이리스트 폴더 준비 |
| `PLAN_READY` | 설정 완료, sonic_dna·visual_dna·tracks.json 생성 |
| `LYRICS_READY` | 전 곡 가사 작성·중복 검사 통과 |
| `PILOT_READY` | 파일럿 첫 곡 생성·검사 통과 |
| `PILOT_APPROVED` | 사용자가 들어보고 승인 — **여기 전에는 나머지 곡을 만들지 않는다** |
| `BATCH_GENERATED` | 전 곡 생성·검사 완료 |
| `VISUALS_READY` | 배경·썸네일·인트로 이미지 준비 |
| `ALIGNED` | 음원 병합 + SRT/ASS 생성 |
| `METADATA_READY` | 제목·설명·챕터·태그·rights.json |
| `RENDERED` | 최종 MP4 생성 |
| `VERIFIED` | QA 통과 |

## 10. 하지 않는 것

- 유료 생성을 직접 하지 않는다 (playlist-studio 소관).
- 사용자 확인 없이 파일을 지우지 않는다.
- `output_path` 가 가리키는 원본 음원을 자동으로 삭제하지 않는다.
- 상태를 임의로 앞당기지 않는다. 단계가 실제로 성공해야 넘어간다.
