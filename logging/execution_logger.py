# 파이프라인 실행 이벤트(run/provider호출/재시도/실패/출력)를 구조화 기록하는 Execution Logger (인메모리 + JSONL)
"""
Execution Logger (Phase 5 / Step 5)

목적.
  - 파이프라인 실행, 공급자 호출, 재시도, 실패, 최종 출력의 구조화 로그 이벤트를 기록한다.

책임.
  - 구조화 로그 이벤트를 만든다(run_id / seq / timestamp / event_type / step / provider /
    capability / status / attempt / output_path / message).
  - run_id 를 추적한다.
  - 인메모리 로깅(테스트)과 JSONL 파일 로깅(실 실행)을 지원한다.

외부 API 없음. 미디어 생성 없음. 기존 provider / Retry Manager 미수정. 기록만 한다.
스키마: schemas/execution_log_schema.json (단일 이벤트)

주의: 이 파일이 있는 디렉토리명은 logging 이지만 파이썬 표준 logging 을 가리지 않도록
__init__.py 를 두지 않는다(패키지화 금지). 모듈 자체도 표준 logging 을 임포트하지 않는다.
"""

import json
import os
from datetime import datetime, timezone

from jsonschema import Draft7Validator

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "execution_log_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as _f:
    _SCHEMA = json.load(_f)
_VALIDATOR = Draft7Validator(_SCHEMA)

# run_id 자동 생성용 프로세스 카운터
_RUN_COUNTER = [0]

# log_event 가 허용하는 선택 필드
_OPTIONAL_FIELDS = ("step", "provider", "capability", "status", "attempt", "output_path", "message")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _gen_run_id():
    _RUN_COUNTER[0] += 1
    return f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{_RUN_COUNTER[0]:04d}"


class ExecutionLogger:
    """실행 이벤트를 구조화 기록한다. 인메모리 누적 + 선택적 JSONL 파일 추가."""

    def __init__(self, run_id=None, jsonl_path=None, clock=None):
        self.run_id = run_id or _gen_run_id()
        self.jsonl_path = jsonl_path
        self._clock = clock or _now_iso
        self._events = []
        self._seq = 0
        if jsonl_path:
            d = os.path.dirname(jsonl_path)
            if d:
                os.makedirs(d, exist_ok=True)

    def log_event(self, event_type, **fields):
        """구조화 이벤트 하나를 만들어 검증·기록하고 반환한다. output_path 는 None 도 허용."""
        self._seq += 1
        ev = {
            "run_id": self.run_id,
            "seq": self._seq,
            "timestamp": self._clock(),
            "event_type": event_type,
        }
        for k in _OPTIONAL_FIELDS:
            if k in fields and (fields[k] is not None or k == "output_path"):
                ev[k] = fields[k]

        errs = sorted(_VALIDATOR.iter_errors(ev), key=str)
        if errs:
            self._seq -= 1  # 잘못된 이벤트는 seq 를 소비하지 않는다
            raise ValueError("로그 이벤트 스키마 위반: " + "; ".join(e.message for e in errs))

        self._events.append(ev)
        if self.jsonl_path:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        return ev

    # --- 편의 메서드 ---

    def run_start(self, **kw):
        return self.log_event("run_start", **kw)

    def provider_call(self, step, provider, capability, status, attempt=None, message=None):
        return self.log_event("provider_call", step=step, provider=provider,
                              capability=capability, status=status, attempt=attempt, message=message)

    def retry(self, provider, attempt, message=None):
        return self.log_event("retry", provider=provider, attempt=attempt, message=message)

    def failure(self, step=None, provider=None, message=None):
        return self.log_event("failure", step=step, provider=provider, status="failed", message=message)

    def output(self, output_path, message=None):
        return self.log_event("output", output_path=output_path, message=message)

    def run_end(self, status, message=None):
        return self.log_event("run_end", status=status, message=message)

    # --- 조회 ---

    def events(self):
        """기록된 이벤트의 복사본."""
        return list(self._events)

    def to_jsonl(self):
        """전체 이벤트를 JSONL 문자열로."""
        return "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self._events)


if __name__ == "__main__":
    lg = ExecutionLogger(run_id="run_demo")
    lg.run_start()
    lg.provider_call(step="image", provider="Nano Banana",
                     capability="generate_image", status="success", attempt=1)
    lg.retry(provider="Higgsfield", attempt=2, message="일시 실패")
    lg.output(output_path="output/final/demo.mp4")
    lg.run_end(status="success")
    print(lg.to_jsonl())
