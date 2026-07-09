# analyze.analyze() 의 분류/판별 규칙을 검증하는 테스트
"""AI Director analyzer 테스트. 표준 라이브러리만 사용."""

from analyze import analyze


def test_baseball_video():
    r = analyze("인필드 플라이 규칙 영상 만들어줘")
    assert r["content_type"] == "baseball"
    assert r["outputs"] == ["video"]
    assert "video" in r["capabilities"]
    assert r["needs_clarification"] is False


def test_malli_story():
    r = analyze("말리가 숲에서 친구를 만나는 동화 이야기")
    assert r["content_type"] == "malli"
    assert r["outputs"] == ["video"]


def test_thumbnail_takes_precedence():
    # 야구 신호가 있어도 '썸네일' 형식 지시가 우선
    r = analyze("야구백과 보크편 썸네일")
    assert r["content_type"] == "thumbnail"
    assert r["outputs"] == ["thumbnail"]
    assert r["capabilities"] == ["image"]


def test_blog():
    r = analyze("한화 어제 경기 블로그 글 써줘")
    assert r["content_type"] == "blog"
    assert r["outputs"] == ["text"]
    assert r["capabilities"] == ["text"]


def test_quality_premium():
    assert analyze("보크 규칙 고품질 영상")["quality_level"] == "premium"


def test_quality_draft():
    assert analyze("보크 규칙 초안 빠르게")["quality_level"] == "draft"


def test_quality_default_standard():
    assert analyze("보크 규칙 영상")["quality_level"] == "standard"


def test_priority_high():
    assert analyze("보크 규칙 영상 지금 급하게")["priority"] == "high"


def test_priority_default_normal():
    assert analyze("보크 규칙 영상")["priority"] == "normal"


def test_unknown_needs_clarification():
    r = analyze("뭔가 멋진 거 만들어줘")
    assert r["content_type"] == "unknown"
    assert r["needs_clarification"] is True
    assert r["capabilities"] == []


def test_no_provider_names_leak():
    # 공급자 이름이 결과에 절대 새지 않아야 한다
    banned = {"flow", "higgsfield", "nano_banana", "nano banana", "magnific", "hedra", "whisper", "ffmpeg"}
    r = analyze("보크 규칙 영상")
    blob = str(r).lower()
    for name in banned:
        assert name not in blob


def test_empty_rejected():
    for bad in ["", "   ", None, 123]:
        try:
            analyze(bad)
        except ValueError:
            continue
        except TypeError:
            continue
        raise AssertionError(f"빈/잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"PASS {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
