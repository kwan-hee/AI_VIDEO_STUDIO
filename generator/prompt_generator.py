# Task Analyzer/Provider Selector 출력을 받아 능력별 프롬프트 텍스트를 조립하는 Prompt Generator
"""
Prompt Generator (Sprint 3)

입력.
  - task_analysis          : Sprint 1 Task Analyzer JSON (project, content_type, required_tasks, ...)
  - provider_recommendation: Sprint 2 Provider Selector JSON (project, providers)
  - topic (선택)           : 실제 주제 문자열. 없으면 "{subject}" 자리표시자 사용.

책임.
  - 프롬프트만 생성한다. AI 호출 없음. 공급자 실행 없음. 미디어 생성 없음.
  - 프롬프트 종류: story / image / video / voice / thumbnail.
  - 구조화 JSON 반환.

출력 스키마: schemas/prompt_schema.json
Sprint 1, Sprint 2 파일은 수정하지 않는다.
"""

# project 별 이미지 스타일 / 낭독 톤
STYLE = {
    "malli": "따뜻한 손그림 동화책",
    "baseball": "선명한 스포츠 일러스트",
    "thumbnail": "강한 대비의 클릭 유도",
}
TONE = {
    "malli": "부드럽고 다정한",
    "baseball": "또렷하고 활기찬",
}

VIDEO_CONTENT_TYPES = {"story_video", "explainer_video"}


def _validate_inputs(task_analysis, provider_recommendation):
    if not isinstance(task_analysis, dict) or not isinstance(provider_recommendation, dict):
        raise ValueError("두 입력은 모두 dict 여야 한다.")
    for key in ("project", "content_type", "required_tasks"):
        if key not in task_analysis:
            raise ValueError(f"task_analysis 에 {key} 가 필요하다.")
    if "providers" not in provider_recommendation:
        raise ValueError("provider_recommendation 에 providers 가 필요하다.")
    if task_analysis["project"] != provider_recommendation.get("project"):
        raise ValueError("두 입력의 project 가 일치하지 않는다.")


def _empty_prompts():
    return {
        "story_prompt": None,
        "image_prompt": None,
        "video_prompt": None,
        "voice_prompt": None,
        "thumbnail_prompt": None,
    }


def _story_text(project, subject):
    if project == "malli":
        return (f"[말리 동화 대본] 주제 '{subject}'. {STYLE['malli']}풍의 "
                f"3막(도입·전개·마무리) 내레이션 대본. 말리 캐릭터 톤 유지, "
                f"어린이 대상, 교훈 한 줄로 마무리.")
    # baseball
    return (f"[야구백과 해설 대본] 주제 '{subject}'. 초보자도 이해할 3~5분 설명 대본. "
            f"정의 → 유래 → KBO 사례 → 핵심 정리 순서.")


def generate_prompts(task_analysis, provider_recommendation, topic=None):
    """
    작업 분석 + 공급자 추천 → 능력별 프롬프트.
    프롬프트만 만든다. 실행/호출 없음. 입력을 변형하지 않는다.
    """
    _validate_inputs(task_analysis, provider_recommendation)

    project = task_analysis["project"]
    content_type = task_analysis["content_type"]
    providers = provider_recommendation["providers"]
    subject = topic.strip() if isinstance(topic, str) and topic.strip() else "{subject}"

    prompts = _empty_prompts()

    # story: 영상 콘텐츠(동화/해설)는 대본 프롬프트가 필요하다. 공급자 없음(작가 계층).
    if content_type in VIDEO_CONTENT_TYPES:
        prompts["story_prompt"] = {
            "provider": None,
            "text": _story_text(project, subject),
        }

    style = STYLE.get(project, "기본")

    # image
    if providers.get("image"):
        prompts["image_prompt"] = {
            "provider": providers["image"],
            "text": (f"[{providers['image']} 이미지] 주제 '{subject}', {style} 스타일. "
                     f"일관된 캐릭터와 구도 유지."),
        }

    # video (primary 공급자로 프롬프트, backup 은 폴백 안내)
    video = providers.get("video")
    if video:
        prompts["video_prompt"] = {
            "provider": video["primary"],
            "text": (f"[{video['primary']} 영상] 이미지를 기반으로 '{subject}' 장면을 "
                     f"자연스러운 카메라 무빙으로 애니메이션화. 실패 시 {video['backup']} 폴백."),
        }

    # voice
    if providers.get("voice"):
        tone = TONE.get(project, "자연스러운")
        prompts["voice_prompt"] = {
            "provider": providers["voice"],
            "text": (f"[{providers['voice']} 음성] 대본을 {tone} 톤으로 낭독. "
                     f"자연스러운 호흡과 강세."),
        }

    # thumbnail: image_enhancement 대상에 thumbnail 이 있거나 thumbnail project 일 때
    ie = providers.get("image_enhancement")
    thumb_needed = (ie and "thumbnail" in ie.get("targets", [])) or project == "thumbnail"
    if thumb_needed and providers.get("image"):
        text = (f"[{providers['image']} 썸네일] '{subject}' 핵심을 한눈에. "
                f"{style} 스타일, 큰 제목 텍스트 여백 확보.")
        if ie and "thumbnail" in ie.get("targets", []):
            text += f" {ie['provider']}로 화질 향상."
        prompts["thumbnail_prompt"] = {
            "provider": providers["image"],
            "text": text,
        }

    return {"project": project, "prompts": prompts}


if __name__ == "__main__":
    import json
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "인필드 플라이"
    ta = {
        "project": "baseball", "content_type": "explainer_video",
        "required_tasks": ["image_generation", "video_generation",
                           "voice_generation", "subtitle_generation", "composition"],
        "needs_clarification": False,
    }
    pr = {
        "project": "baseball",
        "providers": {
            "image": "Nano Banana",
            "video": {"primary": "Higgsfield", "backup": "Google Flow"},
            "voice": "Edge TTS",
            "editing": "FFmpeg",
            "image_enhancement": {"provider": "Magnific", "targets": ["thumbnail", "opening_scene"]},
        },
    }
    print(json.dumps(generate_prompts(ta, pr, topic), ensure_ascii=False, indent=2))
