# aivs_cli 의 run/providers/status 명령·종료코드·구조화 결과·스키마 준수를 확인하는 테스트
"""AI_VIDEO_STUDIO CLI 단위 테스트. 결과는 schemas/cli_result_schema.json 으로 검증. 실 외부호출/실 ffmpeg 없음."""

import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "cli"))

from aivs_cli import run_command, providers_command, status_command, main  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

_SCHEMA_PATH = os.path.join(_ROOT, "schemas", "cli_result_schema.json")
with open(_SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)
Draft7Validator.check_schema(SCHEMA)
_VALIDATOR = Draft7Validator(SCHEMA)


def _assert_valid(r):
    errs = sorted(_VALIDATOR.iter_errors(r), key=str)
    assert not errs, "스키마 위반: " + "; ".join(e.message for e in errs)


def _mock_compose_runner(args, output_path):
    with open(output_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42cli-mock")


def _write_project_config(d, description="말리가 달님을 만난 동화 영상", output_dir=None):
    cfg = {
        "project": {"name": "말리동화", "description": description,
                    "output_directory": output_dir or os.path.join(d, "out")},
    }
    p = os.path.join(d, "project.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return p


# --- run ---

def test_run_command_success():
    with tempfile.TemporaryDirectory() as d:
        cfg_path = _write_project_config(d)
        code, r = run_command(cfg_path, composer_runner=_mock_compose_runner)
        assert code == 0
        assert r["command"] == "run"
        assert r["status"] == "success"
        assert r["exit_code"] == 0
        assert r["summary"]["project"] == "malli"
        assert r["summary"]["asset_count"] == 4
        assert r["summary"]["final_output"].endswith(".mp4")
        _assert_valid(r)


def test_run_command_request_override():
    with tempfile.TemporaryDirectory() as d:
        cfg_path = _write_project_config(d, description="아무거나")
        code, r = run_command(cfg_path, request="보크 규칙 설명 영상",
                              composer_runner=_mock_compose_runner)
        assert r["summary"]["project"] == "baseball"
        _assert_valid(r)


def test_run_command_unknown_needs_clarification_exit_code():
    with tempfile.TemporaryDirectory() as d:
        cfg_path = _write_project_config(d, description="zxcv asdf qwer")
        code, r = run_command(cfg_path, composer_runner=_mock_compose_runner)
        assert r["status"] == "needs_clarification"
        assert code == 2
        assert r["exit_code"] == 2
        _assert_valid(r)


# --- providers ---

def test_providers_command_default_modes():
    code, r = providers_command()
    assert code == 0
    assert r["command"] == "providers"
    assert r["status"] == "ok"
    modes = r["summary"]["providers"]
    assert modes["nano_banana"] == "mock"     # 안전 기본
    assert modes["ffmpeg"] == "local"
    _assert_valid(r)


def test_providers_command_reads_config():
    with tempfile.TemporaryDirectory() as d:
        data = {"providers": {"nano_banana": {"mode": "real"}}, "routing": {}}
        p = os.path.join(d, "providers.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        code, r = providers_command(config_path=p)
        assert r["summary"]["providers"]["nano_banana"] == "real"
        _assert_valid(r)


# --- status ---

def test_status_command():
    code, r = status_command()
    assert code == 0
    assert r["command"] == "status"
    assert r["status"] == "ok"
    assert r["summary"]["ready"] is True
    assert "capabilities" in r["summary"]
    _assert_valid(r)


# --- main 종료코드 ---

def test_main_run_exit_code():
    with tempfile.TemporaryDirectory() as d:
        cfg_path = _write_project_config(d)
        code = main(["run", cfg_path])
        assert code == 0


def test_main_providers_exit_code():
    assert main(["providers"]) == 0


def test_main_status_exit_code():
    assert main(["status"]) == 0


def test_main_no_command_returns_nonzero():
    code = main([])
    assert code != 0


def test_main_run_missing_config_nonzero():
    code = main(["run", "/nonexistent/path/project.json"])
    assert code != 0


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")


if __name__ == "__main__":
    _run()
