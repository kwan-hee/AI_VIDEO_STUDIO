# local_executor.execute_local() 의 모의 결과 형식·확장자·안전성·스키마 준수를 검증하는 테스트
"""Local Executor 단위 테스트. 결과는 schemas/local_execution_result_schema.json 으로 검증."""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("executors", "execution", "adapters", "planner", "orchestrator", "generator", "selector", "analyzer"):
    sys.path.insert(0, os.path.join(_ROOT, _sub))

from local_executor import execute_local  # noqa: E402
from execution_manager import build_queue  # noqa: E402
from orchestrator import orchestrate  # noqa: E402
from execution_planner import plan_execution  # noqa: E402
from provider_adapter import build_payloads  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "local_execution_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

RESULT_KEYS = {"order", "step", "provider", "action", "status", "output_path", "message"}


def _queue(request, topic=None):
    combined = orchestrate(request, topic=topic)
    plan = plan_execution(combined)
    return build_queue(plan, build_payloads(plan, combined["prompts"]))


def _assert_valid(out):
    errs = sorted(_VALIDATOR.iter_errors(out), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _assert_result_shape(r):
    assert set(r.keys()) == RESULT_KEYS, f"결과 키 불일치: {r.keys()}"


# --- 카테고리별 시뮬레이션 ---

def test_baseball_mock_success():
    out = execute_local(_queue("보크 규칙 설명 영상", topic="보크"))
    assert out["project"] == "baseball"
    by = {r["step"]: r for r in out["results"]}
    assert all(r["status"] == "success" for r in out["results"])
    # 확장자 검증
    assert by["script"]["output_path"].endswith(".txt")     # 내부 텍스트
    assert by["image"]["output_path"].endswith(".png")
    assert by["video"]["output_path"].endswith(".mp4")
    assert by["voice"]["output_path"].endswith(".mp3")
    assert by["thumbnail"]["output_path"].endswith(".png")
    assert by["edit"]["output_path"].endswith(".mp4")
    for r in out["results"]:
        _assert_result_shape(r)
    _assert_valid(out)


def test_malli_providers_in_results():
    out = execute_local(_queue("말리가 달님을 만난 날", topic="달님"))
    by = {r["step"]: r for r in out["results"]}
    assert by["video"]["provider"] == "Google Flow"
    assert by["image"]["provider"] == "Nano Banana"
    _assert_valid(out)


def test_blog_internal_txt_and_thumbnail_png():
    out = execute_local(_queue("국민연금 블로그 작성", topic="국민연금"))
    by = {r["step"]: r for r in out["results"]}
    assert by["outline"]["output_path"].endswith(".txt")
    assert by["article"]["output_path"].endswith(".txt")
    assert by["thumbnail"]["output_path"].endswith(".png")
    assert all(r["provider"] is None for r in out["results"])
    _assert_valid(out)


def test_unknown_empty():
    out = execute_local(_queue("unknown input"))
    assert out["results"] == []
    _assert_valid(out)


# --- 실패 주입 ---

def test_fail_injection():
    out = execute_local(_queue("보크 규칙 설명 영상", topic="보크"), fail_orders=[3])
    by = {r["order"]: r for r in out["results"]}
    assert by[3]["status"] == "failed"
    assert by[3]["output_path"] is None
    assert by[1]["status"] == "success"
    _assert_valid(out)


# --- 안전성: 실제 미디어/파일 없음 ---

def test_no_real_file_written():
    out = execute_local(_queue("보크 규칙 영상", topic="보크"))
    for r in out["results"]:
        if r["output_path"]:
            abs_path = os.path.join(_ROOT, r["output_path"])
            assert not os.path.exists(abs_path), f"실제 파일이 생성됨: {r['output_path']}"


def test_no_execution_markers():
    out = execute_local(_queue("보크 규칙 영상", topic="보크"))
    banned = {"response", "url", "job_id", "api_call", "ffmpeg", "browser"}
    for r in out["results"]:
        assert banned.isdisjoint(set(r.keys()))


def test_input_queue_not_mutated():
    q = _queue("보크 규칙 영상", topic="보크")
    states_before = [it["state"] for it in q.items]
    execute_local(q)
    states_after = [it["state"] for it in q.items]
    assert states_before == states_after, "입력 큐 상태가 변경됨"


def test_accepts_dict_form():
    q = _queue("보크 규칙 영상", topic="보크")
    out_obj = execute_local(q)
    out_dict = execute_local(q.to_dict())
    assert out_obj == out_dict


def test_all_categories_schema():
    for req in ["말리 동화", "보크 규칙 영상", "야구 썸네일", "블로그 글 써줘", "아무거나"]:
        _assert_valid(execute_local(_queue(req)))


def test_bad_input_rejected():
    for bad in [None, "x", 3, [], {}, {"project": "malli"}]:
        try:
            execute_local(bad)
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
