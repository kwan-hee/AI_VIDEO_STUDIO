# execution_logger 의 구조화 이벤트 생성·run_id/seq 추적·인메모리/JSONL 기록·검증·스키마 준수를 확인하는 테스트
"""Execution Logger 단위 테스트. 이벤트는 schemas/execution_log_schema.json 으로 검증. 실행 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "logging"))

from execution_logger import ExecutionLogger  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "execution_log_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)

FIXED_TS = "2026-07-09T00:00:00+00:00"


def _clock():
    return FIXED_TS


def _assert_valid(ev):
    errs = sorted(_VALIDATOR.iter_errors(ev), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


# --- 기본 이벤트 생성 ---

def test_run_start_event():
    lg = ExecutionLogger(run_id="run_abc", clock=_clock)
    ev = lg.run_start()
    assert ev["run_id"] == "run_abc"
    assert ev["seq"] == 1
    assert ev["timestamp"] == FIXED_TS
    assert ev["event_type"] == "run_start"
    _assert_valid(ev)


def test_provider_call_event_fields():
    lg = ExecutionLogger(run_id="r1", clock=_clock)
    ev = lg.provider_call(step="image", provider="Nano Banana",
                          capability="generate_image", status="success",
                          attempt=1, message="ok")
    assert ev["step"] == "image"
    assert ev["provider"] == "Nano Banana"
    assert ev["capability"] == "generate_image"
    assert ev["status"] == "success"
    assert ev["attempt"] == 1
    _assert_valid(ev)


def test_retry_failure_output_end_events():
    lg = ExecutionLogger(run_id="r1", clock=_clock)
    r = lg.retry(provider="Higgsfield", attempt=2, message="재시도")
    f = lg.failure(step="video", provider="Higgsfield", message="다운")
    o = lg.output(output_path="output/final/x.mp4", message="완료")
    e = lg.run_end(status="success")
    assert r["event_type"] == "retry" and r["attempt"] == 2
    assert f["event_type"] == "failure" and f["status"] == "failed"
    assert o["event_type"] == "output" and o["output_path"] == "output/final/x.mp4"
    assert e["event_type"] == "run_end" and e["status"] == "success"
    for ev in (r, f, o, e):
        _assert_valid(ev)


# --- run_id / seq 추적 ---

def test_run_id_constant_and_seq_monotonic():
    lg = ExecutionLogger(run_id="fixed", clock=_clock)
    lg.run_start()
    lg.provider_call(step="image", provider="Nano Banana",
                     capability="generate_image", status="success")
    lg.run_end(status="success")
    evs = lg.events()
    assert all(e["run_id"] == "fixed" for e in evs)
    assert [e["seq"] for e in evs] == [1, 2, 3]


def test_auto_run_id_generated_nonempty():
    lg = ExecutionLogger(clock=_clock)
    assert isinstance(lg.run_id, str) and len(lg.run_id) > 0
    ev = lg.run_start()
    assert ev["run_id"] == lg.run_id


# --- 인메모리 ---

def test_in_memory_events_accumulate():
    lg = ExecutionLogger(run_id="r", clock=_clock)
    lg.run_start()
    lg.output(output_path="a.mp4")
    assert len(lg.events()) == 2
    # events() 는 복사본
    lg.events().clear()
    assert len(lg.events()) == 2


# --- JSONL 파일 기록 ---

def test_jsonl_file_logging():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "logs", "run.jsonl")
        lg = ExecutionLogger(run_id="r", jsonl_path=p, clock=_clock)
        lg.run_start()
        lg.provider_call(step="image", provider="Nano Banana",
                         capability="generate_image", status="success")
        lg.run_end(status="success")
        with open(p, encoding="utf-8") as f:
            lines = [json.loads(ln) for ln in f if ln.strip()]
        assert len(lines) == 3
        assert lines == lg.events()
        for ev in lines:
            _assert_valid(ev)


def test_to_jsonl_matches_events():
    lg = ExecutionLogger(run_id="r", clock=_clock)
    lg.run_start()
    lg.run_end(status="failed")
    parsed = [json.loads(ln) for ln in lg.to_jsonl().splitlines()]
    assert parsed == lg.events()


# --- 검증/거부 ---

def test_invalid_event_type_rejected():
    lg = ExecutionLogger(run_id="r", clock=_clock)
    try:
        lg.log_event("explode")
    except ValueError:
        return
    raise AssertionError("알 수 없는 event_type 이 거부되지 않음")


def test_invalid_provider_rejected():
    lg = ExecutionLogger(run_id="r", clock=_clock)
    try:
        lg.provider_call(step="image", provider="DALL-E",
                         capability="generate_image", status="success")
    except ValueError:
        return
    raise AssertionError("알 수 없는 provider 가 거부되지 않음")


def test_invalid_status_rejected():
    lg = ExecutionLogger(run_id="r", clock=_clock)
    try:
        lg.run_end(status="running")
    except ValueError:
        return
    raise AssertionError("알 수 없는 status 가 거부되지 않음")


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
