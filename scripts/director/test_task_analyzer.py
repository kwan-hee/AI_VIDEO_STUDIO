# task_analyzer.analyze_task() 의 project/단계/도구/Magnific 판단을 검증하는 테스트
"""Task Analyzer 테스트. 표준 라이브러리만 사용."""

from task_analyzer import analyze_task


def test_baseball_pipeline():
    r = analyze_task("인필드 플라이 규칙 영상 만들어줘")
    assert r["project"] == "baseball"
    assert r["content_type"] == "explainer_video"
    assert r["required_steps"][0] == "image_generation"
    assert "composition" in r["required_steps"]
    # 야구는 Higgsfield 1순위, Flow 폴백
    assert r["recommended_tools"]["video_generation"] == ["Higgsfield", "Google Flow"]
    assert r["magnific"]["needed"] is True
    assert r["magnific"]["targets"] == ["opening_scene", "key_scene"]


def test_malli_video_priority():
    r = analyze_task("말리가 숲에서 친구를 만나는 동화")
    assert r["project"] == "malli"
    assert r["content_type"] == "story_video"
    # 말리는 Flow 1순위, Higgsfield 폴백
    assert r["recommended_tools"]["video_generation"] == ["Google Flow", "Higgsfield"]
    assert r["magnific"]["targets"] == ["first_scene", "last_scene"]


def test_image_tool_is_nano_banana():
    r = analyze_task("보크 규칙 영상")
    assert r["recommended_tools"]["image_generation"] == ["Nano Banana"]


def test_voice_subtitle_composition_tools():
    r = analyze_task("보크 규칙 영상")
    assert r["recommended_tools"]["voice_generation"] == ["Hedra"]
    assert r["recommended_tools"]["subtitle_generation"] == ["Whisper"]
    assert r["recommended_tools"]["composition"] == ["FFmpeg"]


def test_thumbnail_uses_magnific():
    r = analyze_task("야구백과 보크편 썸네일")
    assert r["project"] == "thumbnail"
    assert r["content_type"] == "thumbnail_image"
    assert r["magnific"]["needed"] is True
    assert r["magnific"]["targets"] == ["thumbnail"]
    assert "quality_enhancement" in r["required_steps"]
    assert r["recommended_tools"]["quality_enhancement"] == ["Magnific"]


def test_thumbnail_draft_skips_magnific():
    r = analyze_task("야구백과 보크편 썸네일 초안 빠르게")
    assert r["project"] == "thumbnail"
    assert r["magnific"]["needed"] is False
    assert r["magnific"]["targets"] == []
    assert "quality_enhancement" not in r["required_steps"]


def test_baseball_draft_no_magnific():
    r = analyze_task("보크 규칙 영상 초안")
    assert r["quality_level"] == "draft"
    assert r["magnific"]["needed"] is False


def test_blog_text_only():
    r = analyze_task("한화 어제 경기 블로그 글 써줘")
    assert r["project"] == "blog"
    assert r["content_type"] == "blog_text"
    assert r["required_steps"] == ["text_writing"]
    assert r["recommended_tools"]["text_writing"] == ["Claude Code"]
    assert r["magnific"]["needed"] is False


def test_unknown_needs_clarification():
    r = analyze_task("뭔가 멋진 거 만들어줘")
    assert r["project"] == "unknown"
    assert r["needs_clarification"] is True
    assert r["required_steps"] == []
    assert r["recommended_tools"] == {}
    assert r["magnific"]["needed"] is False


def test_empty_rejected():
    for bad in ["", "   ", None, 42]:
        try:
            analyze_task(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"빈/잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
