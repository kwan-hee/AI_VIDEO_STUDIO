# post.json 작성법

집필 결과를 이 구조로 정리하면, `scripts/build_post.py`가 복붙용 본문 텍스트와 완성형 HTML을 한 번에 만든다. 두 결과물이 같은 데이터에서 나오므로 내용이 어긋날 일이 없다.

완성된 예시는 `assets/example-post.json`에 있다. 처음 작성한다면 그 파일을 복사해 값만 바꾸는 편이 빠르다.

```bash
python3 <스킬경로>/scripts/build_post.py post.json --outdir outputs/
```

---

## 최상위 구조

| 필드 | 필수 | 설명 |
|---|---|---|
| `slug` | 권장 | 출력 파일 이름. 영문 소문자와 붙임표를 쓴다. 없으면 책 제목에서 만든다 |
| `book` | 필수 | 도서 서지 정보 |
| `axis` | 권장 | 이 리뷰가 붙잡은 질문 한 문장 |
| `titles` | 필수 | 제목 후보 3개와 추천 인덱스 |
| `meta` | 필수 | 메타 설명, 키워드, 해시태그 |
| `images` | 권장 | 수집한 이미지 목록 |
| `body` | 필수 | 본문 블록의 배열 |
| `fact_check` | 권장 | 검증한 사실과 출처 |
| `sources` | 선택 | 참고 자료 목록 |
| `unverified` | 선택 | 확인하지 못해 글에서 뺀 정보 |

---

## book

확인된 항목만 채운다. 비워 두면 출력에서 자동으로 빠진다.

```json
"book": {
  "title": "싯다르타",
  "original_title": "Siddhartha: Eine indische Dichtung",
  "author": "헤르만 헤세 (Hermann Hesse)",
  "translator": "박병덕 옮김",
  "publisher": "민음사",
  "published_kr": "2002년",
  "published_original": "1922년 독일",
  "pages": "184쪽",
  "genre": "독일 문학, 성장 소설",
  "awards": "저자 1946년 노벨문학상 수상"
}
```

`published_kr`과 `published_original`은 반드시 구분한다. 두 연도를 섞어 적는 실수가 가장 흔하다.

---

## titles

```json
"titles": {
  "options": ["정보형 제목", "질문형 제목", "대비형 제목"],
  "recommended": 2,
  "reason": "주 키워드가 앞에 있으면서 클릭 동기가 가장 강합니다."
}
```

`recommended`는 0부터 세는 인덱스다. 위 예시에서 2는 세 번째 제목을 뜻한다. HTML에는 세 후보가 모두 실리고 추천 항목에 표시가 붙으므로, 사용자가 다른 제목을 골라 쓸 수 있다.

---

## meta

```json
"meta": {
  "description": "검색 결과에 노출되는 80~100자 설명",
  "keywords": ["싯다르타", "헤르만 헤세", "독후감"],
  "hashtags": ["싯다르타", "헤르만헤세", "고전소설추천"],
  "key_sentences": ["글을 대표하는 문장 2~3개"]
}
```

`keywords`에 적은 단어는 스크립트가 본문에서 몇 번 등장하는지 세어 HTML의 메타 정보 탭에 표시한다. 주 키워드가 5회 미만이면 배치를 다시 점검한다. 해시태그는 `#` 없이 적어도 출력 시 자동으로 붙는다.

---

## images

```json
"images": [
  {"no": 1, "caption": "헤르만 헤세의 소설 싯다르타 표지",
   "url": "https://...", "source": "민음사 도서 페이지",
   "position": "도입부 아래"},
  {"no": 2, "caption": "작가 헤르만 헤세", "url": "https://...",
   "source": "Wikimedia Commons", "license": "Public Domain",
   "position": "저자 배경 섹션 뒤"}
]
```

`no`는 본문에서 참조하는 번호다. `body`의 이미지 블록이 이 번호를 가리키며, 없는 번호를 참조하면 스크립트가 오류로 알려 준다. 캡션에는 책 제목이나 저자명을 자연스럽게 넣는다. 네이버가 캡션 텍스트도 수집하기 때문이다.

---

## body

본문은 블록의 배열이다. 각 블록은 `type`으로 구분한다.

| type | 필드 | 출력 |
|---|---|---|
| `p` | `text` | 일반 문단 |
| `h3` | `text` | 소제목 |
| `quote` | `text`, `attr`(선택) | 인용 상자 |
| `callout` | `text` | 💡 표시가 붙는 정리 상자 |
| `image` | `ref` | `[ 이미지 N 삽입 ]` 안내와 캡션 |
| `info` | `rows` | 표 형태의 정보 상자 |
| `divider` | — | 구분선 |

```json
"body": [
  {"type": "p", "text": "도입 문단"},
  {"type": "image", "ref": 1},
  {"type": "h3", "text": "헤세가 무너져 있던 시기에 쓴 소설"},
  {"type": "p", "text": "본문 문단"},
  {"type": "quote", "text": "진리는 가르칠 수 없다.", "attr": "소설의 주제를 요약한 문장"},
  {"type": "callout", "text": "한 줄 정리 — ..."}
]
```

문단 하나를 지나치게 길게 쓰지 않는다. 모바일에서 한 문단이 열 줄을 넘기면 읽히지 않으므로, 3~5줄 분량에서 블록을 나눈다.

---

## fact_check와 unverified

```json
"fact_check": [
  {"item": "원서 출간", "value": "1922년 독일", "source": "https://..."}
],
"unverified": ["국내 누적 판매 부수는 공식 자료를 찾지 못해 넣지 않았습니다."]
```

`fact_check`는 HTML의 사실 확인 탭에 표로 실린다. `unverified`는 같은 탭 아래쪽에 경고 상자로 표시되며, 사용자에게 보고할 때 그대로 옮기면 된다.

---

## 스크립트가 알려 주는 것

실행하면 본문 글자 수(공백 포함), 소제목 수, 섹션별 길이, 이미지와 해시태그 개수를 출력한다. 그리고 아래에 해당하면 점검 항목을 함께 알려 준다.

- 본문이 2,000자 미만인 경우
- 소제목이 3개 미만이거나, 섹션이 400자 미만인 경우
- 이미지가 2건 미만이거나 URL·출처·캡션이 빠진 경우
- 해시태그가 10개 미만인 경우
- "살펴보겠습니다", "알아보도록", "결론적으로" 같은 기계적 표현이 남아 있는 경우
- `fact_check`가 비어 있는 경우

점검 항목은 HTML 상단에도 표시되므로, 사용자에게 전달하기 전에 모두 해소한다.
