# execution_runner.run() 의 큐 처리·상태 전이·결과 요약·스키마 준수를 검증하는 테스트
"""Execution Runner 단위 테스트. 결과는 schemas/execution_result_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("runner", "execution", "adapters", "planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

from execution_runner import run  # noqa: E402
from execution_manager import build_queue  # noqa: E402
from orchestrator import orchestrate  # noqa: E402
from execution_planner import plan_execution  # noqa: E402
from provider_adapter import build_payloads  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "execution_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _queue(request, topic=None):
    combined = orchestrate(request, topic=topic)
    plan = plan_execution(combined)
    return build_queue(plan, build_payloads(plan, combined["prompts"]))


def _assert_valid(result):
    errs = sorted(_VALIDATOR.iter_errors(result), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 성공 실행 ---

def test_baseball_all_completed():
    q = _queue("보크 규칙 설명 영상", topic="보크")
    r = run(q)
    assert r["status"] == "completed"
    assert r["summary"]["total"] == 6
    assert r["summary"]["completed"] == 6
    assert r["summary"]["failed"] == 0
    assert all(s["state"] == "completed" for s in r["steps"])
    assert q.is_done() is True  # 큐 상태 갱신됨
    _assert_valid(r)


def test_malli_all_completed():
    r = run(_queue("말리가 달님을 만난 날", topic="달님"))
    assert r["status"] == "completed"
    assert r["summary"]["completed"] == r["summary"]["total"]
    _assert_valid(r)


def test_blog_internal_steps_completed():
    r = run(_queue("국민연금 블로그 작성", topic="국민연금"))
    assert r["status"] == "completed"
    assert r["summary"]["total"] == 3
    assert [s["step"] for s in r["steps"]] == ["outline", "article", "thumbnail"]
    _assert_valid(r)


def test_unknown_empty():
    r = run(_queue("unknown input"))
    assert r["status"] == "empty"
    assert r["summary"] == {"total": 0, "completed": 0, "failed": 0, "pending": 0}
    assert r["steps"] == []
    _assert_valid(r)


# --- 실패 경로 ---

def test_fail_halts_progression():
    q = _queue("보크 규칙 설명 영상", topic="보크")
    # 3번(video) 실패 주입 → 이후 단계 pending 유지
    r = run(q, fail_orders=[3])
    assert r["status"] == "failed"
    assert r["summary"]["failed"] == 1
    assert r["summary"]["completed"] == 2   # script, image
    assert r["summary"]["pending"] == 3     # voice, thumbnail, edit
    states = {s["order"]: s["state"] for s in r["steps"]}
    assert states[3] == "failed"
    assert states[4] == "pending"
    assert q.is_done() is False
    _assert_valid(r)


def test_first_step_fail():
    q = _queue("보크 규칙 영상", topic="보크")
    r = run(q, fail_orders=[1])
    assert r["status"] == "failed"
    assert r["summary"]["completed"] == 0
    assert r["summary"]["failed"] == 1
    assert r["summary"]["pending"] == r["summary"]["total"] - 1


# --- 안전성/계약 ---

def test_no_running_left_after_run():
    r = run(_queue("보크 규칙 영상", topic="보크"))
    assert all(s["state"] != "running" for s in r["steps"])


def test_no_execution_markers():
    r = run(_queue("보크 규칙 영상", topic="보크"))
    banned = {"response", "url", "job_id", "output", "media", "api_call"}
    assert banned.isdisjoint(set(r.keys()))
    for s in r["steps"]:
        assert banned.isdisjoint(set(s.keys()))


def test_all_categories_schema():
    for req in ["말리 동화", "보크 규칙 영상", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _assert_valid(run(_queue(req)))


def test_rerun_after_done_is_noop():
    q = _queue("보크 규칙 영상", topic="보크")
    r1 = run(q)
    r2 = run(q)  # 이미 완료된 큐 재실행 → 변화 없음
    assert r1 == r2


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, {"project": "malli", "queue": []}]:
        try:
            run(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"잘못된 입력이 거부되지 않음: {bad!r}")


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run_all()
