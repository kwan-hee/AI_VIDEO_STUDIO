# execution_manager 의 큐 구성·상태 전이·순서 관리·스키마 준수를 검증하는 테스트
"""Execution Manager 단위 테스트. 큐는 schemas/execution_queue_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("execution", "adapters", "planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

from execution_manager import build_queue, ExecutionQueue  # noqa: E402
from orchestrator import orchestrate  # noqa: E402
from execution_planner import plan_execution  # noqa: E402
from provider_adapter import build_payloads  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "execution_queue_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _queue(request, topic=None):
    combined = orchestrate(request, topic=topic)
    plan = plan_execution(combined)
    adapters_out = build_payloads(plan, combined["prompts"])
    return build_queue(plan, adapters_out)


def _assert_valid(q):
    errs = sorted(_VALIDATOR.iter_errors(q.to_dict()), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _states(q):
    return [it["state"] for it in q.items]


# --- 큐 구성 ---

def test_baseball_queue_build():
    q = _queue("보크 규칙 설명 영상", topic="보크")
    steps = [it["step"] for it in q.items]
    assert steps == ["script", "image", "video", "voice", "thumbnail", "edit"]
    # 첫 단계 ready, 나머지 pending
    assert _states(q) == ["ready", "pending", "pending", "pending", "pending", "pending"]
    # 내부 단계(script)는 payload 없음, provider 단계는 payload 있음
    by = {it["step"]: it for it in q.items}
    assert by["script"]["payload"] is None and by["script"]["provider"] is None
    assert by["image"]["provider"] == "Nano Banana" and by["image"]["payload"] is not None
    assert by["video"]["provider"] == "Higgsfield"
    _assert_valid(q)


def test_malli_queue_video_provider():
    q = _queue("말리가 달님을 만난 날", topic="달님")
    by = {it["step"]: it for it in q.items}
    assert by["video"]["provider"] == "Google Flow"
    assert by["story"]["payload"] is None
    _assert_valid(q)


def test_blog_all_internal():
    q = _queue("국민연금 블로그 작성", topic="국민연금")
    assert [it["step"] for it in q.items] == ["outline", "article", "thumbnail"]
    assert all(it["provider"] is None and it["payload"] is None for it in q.items)
    _assert_valid(q)


def test_unknown_empty_queue():
    q = _queue("unknown input")
    assert q.items == []
    assert q.ready_steps() == []
    assert q.is_done() is True  # 빈 큐는 완료로 간주
    _assert_valid(q)


# --- 상태 전이 ---

def test_initial_first_ready_rest_pending():
    q = _queue("보크 규칙 영상", topic="보크")
    assert q.items[0]["state"] == "ready"
    assert all(it["state"] == "pending" for it in q.items[1:])


def test_sequential_progression():
    q = _queue("보크 규칙 영상", topic="보크")
    # 순서대로 start→complete 하면 다음이 ready 로 승격
    for it in list(q.items):
        assert q._find(it["order"])["state"] == "ready"
        q.start(it["order"])
        assert q._find(it["order"])["state"] == "running"
        q.complete(it["order"])
        assert q._find(it["order"])["state"] == "completed"
    assert q.is_done() is True
    assert all(it["state"] == "completed" for it in q.items)


def test_fail_stops_promotion():
    q = _queue("보크 규칙 영상", topic="보크")
    first = q.items[0]["order"]
    q.start(first)
    q.fail(first)
    assert q.items[0]["state"] == "failed"
    # 실패 시 다음 단계는 승격되지 않는다
    assert q.items[1]["state"] == "pending"


def test_invalid_transition_rejected():
    q = _queue("보크 규칙 영상", topic="보크")
    order = q.items[0]["order"]
    # pending 이 아닌 ready 에서 complete 로 바로 못 감
    try:
        q.complete(order)  # ready -> completed 불가
    except ValueError:
        pass
    else:
        raise AssertionError("잘못된 전이가 허용됨")
    # pending 단계를 바로 start 불가
    try:
        q.start(q.items[1]["order"])  # pending -> running 불가
    except ValueError:
        return
    raise AssertionError("pending 에서 start 가 허용됨")


def test_only_one_ready_at_a_time():
    q = _queue("보크 규칙 영상", topic="보크")
    assert len(q.ready_steps()) == 1
    o = q.items[0]["order"]
    q.start(o)
    q.complete(o)
    assert len(q.ready_steps()) == 1  # 다음 하나만 ready


# --- 안전성 ---

def test_nothing_executed():
    # 큐 생성만으로는 어떤 상태도 진행되지 않는다 (첫 ready 외 전부 pending)
    q = _queue("보크 규칙 영상", topic="보크")
    assert "running" not in _states(q)
    assert "completed" not in _states(q)


def test_all_categories_schema():
    for req in ["말리 동화", "보크 규칙 영상", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _assert_valid(_queue(req))


def test_project_mismatch_rejected():
    c1 = orchestrate("보크 규칙 영상", topic="보크")
    plan = plan_execution(c1)
    c2 = orchestrate("말리 동화", topic="달님")
    other = build_payloads(plan_execution(c2), c2["prompts"])  # malli payloads
    try:
        build_queue(plan, other)  # baseball plan + malli adapter
    except ValueError:
        return
    raise AssertionError("project 불일치가 거부되지 않음")


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, {"project": "malli"}]:
        try:
            build_queue(bad, bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
