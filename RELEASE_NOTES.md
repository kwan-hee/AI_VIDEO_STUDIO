# RELEASE NOTES

AI_VIDEO_STUDIO Sprint별 릴리스 기록.

---

## Sprint 1 — Task Analyzer (승인됨)

상태: ✅ Approved

### Sprint Goal

자연어 사용자 요청을 받아 구조화된 작업 분석 JSON을 만든다.
공급자 선택 없이, 무엇을 만들지와 어떤 작업이 필요한지만 판단한다.

### Deliverables

- `analyzer/task_analyzer.py` — 자연어 입력 → 작업 분석 dict/JSON.
- `schemas/task_schema.json` — 출력 계약 (JSON Schema draft-07, enum 고정, 추가 키 금지).
- `tests/test_task_analyzer.py` — 단위 테스트.

출력 필드.

- `project` : malli | baseball | thumbnail | blog | unknown
- `content_type` : story_video | explainer_video | thumbnail_image | blog_text | unknown
- `required_tasks` : 추상 작업 목록 (공급자 이름 없음)
- `needs_clarification` : unknown 판별 시 true

### Tests

- 11/11 통과.
- 커버리지: project별 판별, content_type, 작업 목록, 스키마 준수, 공급자 이름 미노출, 빈/잘못된 입력 거부.
- 리뷰 예시 입력 5건 검증 (`test_sprint1_sample_inputs`).

| 예시 입력 | project | content_type |
|---|---|---|
| 말리가 달님을 만난 날 | malli | story_video |
| 보크 규칙 설명 영상 | baseball | explainer_video |
| 건강검진 대상자 조회 썸네일 | thumbnail | thumbnail_image |
| 국민연금 블로그 작성 | blog | blog_text |
| unknown input | unknown | unknown |

### Definition of Done

- [x] 자연어 입력을 받는다.
- [x] project를 판별한다.
- [x] content_type을 판별한다.
- [x] 필요한 작업 목록을 생성한다.
- [x] 구조화 JSON을 출력한다. 스키마로 검증된다.
- [x] 단위 테스트 포함, 전부 통과.
- [x] 공급자 선택 없음. 외부 AI 호출 없음. 워크플로 실행 없음. 미디어 생성 없음.
- [x] 기존 PROJECT 폴더 미수정.

### Known Limitations

- 분류가 키워드 기반이다. 신호 사전에 없는 표현은 unknown으로 빠질 수 있다.
- 야구 vs 동화는 신호 수 비교로 정한다. 동점이면 baseball 우선. 애매한 문장은 오분류 가능.
- 출력에 품질 등급·우선순위가 없다. 이는 Sprint 1 범위 밖.
- `required_tasks`는 추상 단계다. 실제 장면 수·순서 세부는 포함하지 않는다.
- unknown 시 사람 확인 흐름은 플래그(`needs_clarification`)만 있고 인터랙션은 없다.

### Backlog Items

`BACKLOG.md`에서 관리. Sprint 1 관련 이월 항목.

- [ ] 키워드 분류를 넘어선 판별 정확도 개선.
- [ ] unknown 판별 시 사람 확인 인터랙션.
- [ ] 요청 검증기 — `docs/40_REQUEST_SPEC.md` 검증 규칙 코드화.
- [ ] 중복 정리 — `scripts/director/` (초기 시제품)와 `analyzer/` 정본 병존. 리팩터링 대상.
- [ ] 문서 번호 충돌 정리 (`00_`, `01_` 중복).
