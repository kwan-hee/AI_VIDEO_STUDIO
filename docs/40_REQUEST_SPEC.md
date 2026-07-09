# 40 요청 규격 (Request Spec)

이 문서는 AIOS로 들어오는 모든 작업이 따라야 하는 표준 요청 형식을 정의한다.
AIOS 전체의 입력 계약이다. 이 규격을 벗어난 요청은 Router가 거부하거나 보정한다.

상위 문서는 [00_AIOS_BLUEPRINT.md](00_AIOS_BLUEPRINT.md)이며, 충돌 시 청사진이 우선한다.
구현이 아니라 계약 정의다. 코드 없음.

---

## 1. 요청 개요

- 사용자는 최소한 주제만 입력한다.
- 나머지 필드는 생략하면 AIOS가 기본값으로 판단한다.
- 필수 필드가 없으면 요청은 무효다.

---

## 2. 필수 필드 (Required)

| 필드 | 의미 | 예시 |
|------|------|------|
| `topic` | 만들 콘텐츠의 주제. 유일한 절대 필수. | "보크 규칙 설명" |

주제 하나만 있으면 요청은 성립한다.
나머지는 모두 선택이며, 없으면 AIOS가 자동 판단한다.

---

## 3. 선택 필드 (Optional)

| 필드 | 의미 | 없을 때 처리 |
|------|------|------------|
| `content_category` | 콘텐츠 분류. | AIOS가 주제로 자동 판별 |
| `task_type` | 수행할 작업 종류. | `full_pipeline` |
| `output_type` | 원하는 산출물. | 카테고리 기본값 |
| `quality_level` | 품질 등급. | `standard` |
| `budget_level` | 예산 등급. | `standard` |
| `title` | 지정 제목. | AIOS가 생성 |
| `reference` | 참고 자료·이미지·링크. | 없음 |
| `deadline` | 마감 요구. | 없음 |
| `notes` | 사람 지시·주의사항. | 없음 |

---

## 4. 지원 작업 종류 (Task Types)

| 값 | 의미 |
|----|------|
| `full_pipeline` | 기획부터 최종 합성까지 전체 실행. 기본값. |
| `image_only` | 이미지 생성까지만. |
| `video_only` | 이미지→영상 생성까지. |
| `voice_only` | 음성 생성만. |
| `subtitle_only` | 자막 생성만. |
| `composite_only` | 기존 소재로 최종 합성만. |
| `thumbnail_only` | 썸네일만 생성. |

---

## 5. 콘텐츠 분류 (Content Categories)

| 값 | 의미 | 기본 영상 엔진 |
|----|------|--------------|
| `malli` | 말리 동화. | Google Flow (폴백 Higgsfield) |
| `baseball` | 야구백과사전. | Higgsfield (폴백 Flow) |
| `auto` | 미지정. 주제로 자동 판별. | 판별 후 결정 |

새 카테고리는 이 문서 개정으로만 추가한다.

---

## 6. 산출물 종류 (Output Types)

| 값 | 의미 |
|----|------|
| `video` | 완성 영상. 기본값. |
| `image` | 이미지 단건 또는 세트. |
| `thumbnail` | 썸네일 이미지. |
| `audio` | 음성 파일. |
| `subtitle` | 자막 파일. |

---

## 7. 품질 등급 (Quality Levels)

| 값 | 의미 | Magnific |
|----|------|----------|
| `draft` | 빠른 확인용. 최저 비용. | 미적용 |
| `standard` | 기본 품질. 기본값. | 정책 지점만 적용 |
| `premium` | 최고 품질. | 정책 지점 + 핵심 장면 확대 적용 |

Magnific 적용 지점은 [06_MAGNIFIC_POLICY.md](06_MAGNIFIC_POLICY.md)를 따른다.

---

## 8. 예산 등급 (Budget Levels)

| 값 | 의미 |
|----|------|
| `low` | 비용 최우선. 유료 향상 최소화. |
| `standard` | 비용·품질 균형. 기본값. |
| `high` | 품질 최우선. 비용 상한 완화. |

비용 판단은 [03_COST_POLICY.md](03_COST_POLICY.md)를 따른다.

---

## 9. 검증 규칙 (Validation Rules)

1. `topic`이 비어 있으면 요청은 무효. 즉시 거부한다.
2. 선택 필드 값은 위 표의 허용값만 인정한다. 벗어나면 거부한다.
3. `content_category`가 없거나 `auto`면 AIOS가 주제로 판별한다. 판별 실패 시 사람에게 확인 요청.
4. `task_type`이 요구하는 소재가 없으면 (예: `composite_only`인데 소재 없음) 거부한다.
5. `quality_level`이 `premium`이고 `budget_level`이 `low`면 충돌. 사람에게 우선순위 확인.
6. 지정되지 않은 선택 필드는 기본값으로 채운다.
7. 최종 승인 권한은 언제나 사람에게 있다. AIOS는 요청을 실행하되 결과는 사람이 승인한다.

---

## 10. 최소 요청 예시 (형식 참고용, 구현 아님)

가장 짧은 유효 요청.

```
topic: "인필드 플라이 규칙"
```

이 경우 AIOS는 카테고리를 `baseball`로 판별하고,
`full_pipeline` / `video` / `standard` / `standard` 기본값으로 실행한다.
