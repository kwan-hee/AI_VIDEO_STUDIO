# 30 의사결정 트리 (Decision Tree)

이 문서는 AIOS가 워크플로를 고르기 전에 거치는 판단 과정을 정의한다.
실행이 아니라 사고 과정이다. 코드 없음, 워크플로 실행 없음.

입력 형식은 [40_REQUEST_SPEC.md](40_REQUEST_SPEC.md), 정책 근거는
[02_AI_ROUTER_POLICY.md](02_AI_ROUTER_POLICY.md) · [03_COST_POLICY.md](03_COST_POLICY.md) ·
[06_MAGNIFIC_POLICY.md](06_MAGNIFIC_POLICY.md)를 따른다.

---

## 0. 전체 판단 순서

```
요청 도착
  │
  1) 요청 분류      → 무슨 콘텐츠인가
  │
  2) 산출물 판별    → 무엇을 만드나 (영상/썸네일/블로그)
  │
  3) 플랫폼 선택    → 어떤 엔진으로 만드나
  │
  4) 품질·예산 반영 → 얼마나 좋게, 얼마 안에
  │
  5) Magnific 판단  → 품질 향상 넣을 지점 있나
  │
  → 워크플로 선택 (이 문서 범위 밖)
```

---

## 1. 요청 분류 — 무슨 콘텐츠인가

`content_category`가 지정되면 그대로 쓴다.
`auto`이거나 없으면 주제로 판별한다.

```
요청 주제
  │
  ├─ 동화·이야기·캐릭터·교훈 신호 ─────────→ STORY (말리 동화)
  │
  ├─ 야구 용어·규칙·KBO·선수 신호 ─────────→ BASEBALL (야구백과사전)
  │
  ├─ "썸네일" 단독 요청 / thumbnail_only ──→ THUMBNAIL
  │
  ├─ "블로그"·"포스팅"·글 텍스트 요청 ─────→ BLOG
  │
  └─ 판별 실패 ───────────────────────────→ 사람에게 확인 요청
```

- STORY / BASEBALL: 영상 파이프라인.
- THUMBNAIL: 이미지 단건 파이프라인.
- BLOG: 텍스트 파이프라인. 영상 엔진 미사용.

---

## 2. 산출물 판별 — 무엇을 만드나

```
분류 결과
  │
  ├─ STORY ────→ output=video 기본. 요청이 image/thumbnail이면 해당만.
  ├─ BASEBALL ─→ output=video 기본. 요청이 image/thumbnail이면 해당만.
  ├─ THUMBNAIL → output=thumbnail 고정.
  └─ BLOG ─────→ output=text 고정. 엔진 선택 단계 건너뜀.
```

BLOG는 3단계(플랫폼 선택)와 5단계(Magnific)를 건너뛴다.
THUMBNAIL은 영상 엔진 선택을 건너뛴다.

---

## 3. 플랫폼 선택 — 어떤 엔진으로

영상 산출물에만 적용한다.

```
영상 엔진 선택
  │
  ├─ STORY (말리 동화)
  │     ├─ 1순위: Google Flow
  │     └─ Flow 불가/실패 → Higgsfield
  │
  └─ BASEBALL (야구백과사전)
        ├─ 1순위: Higgsfield
        └─ Higgsfield 불가/실패 → Google Flow
```

이미지 생성 엔진은 콘텐츠 무관하게 기본 Nano Banana.

```
이미지 엔진
  └─ 기본: Nano Banana
        └─ 품질 향상 필요 지점 → Magnific 후처리 (5단계 판단)
```

---

## 4. 품질·예산 반영 — 얼마나 좋게, 얼마 안에

품질과 예산이 충돌하면 사람에게 우선순위를 묻는다.

```
quality_level × budget_level
  │
  ├─ draft ──────→ 최소 비용. Magnific 미적용. 폴백 엔진도 저비용 우선.
  │
  ├─ standard ───→ 균형. Magnific는 정책 지점만. (기본값)
  │
  └─ premium ────→ 품질 우선. Magnific 정책 지점 + 핵심 장면 확대.
        │
        └─ budget=low 와 동시? → 충돌. 사람 확인.
```

예산 등급별.

```
budget
  ├─ low ──────→ 유료 향상 최소화. Magnific 적용 지점 최소화 검토.
  ├─ standard ─→ 정책대로.
  └─ high ─────→ 상한 완화. 품질 판단을 우선.
```

---

## 5. Magnific 사용 판단 — 어디에 넣나

Magnific는 모든 이미지에 쓰지 않는다. 지정 지점에서만.

```
Magnific 적용?
  │
  ├─ 대상 지점인가?
  │     ├─ 썸네일 ──────────────────── 예
  │     ├─ 말리 동화 첫 장면 ────────── 예
  │     ├─ 말리 동화 마지막 장면 ────── 예
  │     ├─ 야구백과 오프닝 장면 ─────── 예
  │     ├─ 야구백과 핵심 장면 ───────── 예
  │     └─ 그 외 일반 장면 ─────────── 아니오
  │
  ├─ 예 → 품질/예산 게이트 통과?
  │     ├─ draft ────→ 건너뜀 (미적용)
  │     ├─ standard ─→ 적용
  │     └─ premium ──→ 적용 + 확대
  │
  └─ 아니오 → Nano Banana 이미지에서 바로 영상 생성으로 진행
```

일반 장면은 Magnific 없이 Nano Banana → 영상 엔진으로 직행한다.

---

## 6. 엔진 사용 요약

| 상황 | 사용 엔진 |
|------|----------|
| 말리 동화 영상 | Flow (1순위) → Higgsfield (폴백) |
| 야구백과 영상 | Higgsfield (1순위) → Flow (폴백) |
| 모든 이미지 기본 | Nano Banana |
| 썸네일 품질 향상 | Magnific |
| 말리 첫·마지막 장면 | Magnific |
| 야구백과 오프닝·핵심 장면 | Magnific |
| 일반 장면 | Magnific 미적용, 바로 영상화 |
| 음성 | Hedra |
| 자막 | Whisper |
| 최종 합성 | FFmpeg |

---

## 7. 판단 원칙

1. 분류 → 산출물 → 플랫폼 → 품질·예산 → Magnific 순서를 지킨다.
2. 폴백은 1순위 엔진이 불가하거나 실패할 때만 쓴다.
3. Magnific는 지정 지점에서만, 품질·예산 게이트를 통과할 때만.
4. 충돌(예: premium + low)은 임의 결정하지 않고 사람에게 올린다.
5. 판별 실패도 임의 진행하지 않고 사람에게 확인한다.
