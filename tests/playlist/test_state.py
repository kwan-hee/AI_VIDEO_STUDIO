"""상태 머신 · 산출물 레지스트리."""
import pytest

from playlist_studio.state import STATES, StateError, Workspace


def test_states_are_ordered_and_complete():
    assert STATES[0] == "INIT" and STATES[-1] == "VERIFIED"
    assert len(set(STATES)) == len(STATES)


def test_advance_only_moves_forward(project):
    ws = Workspace.load(project)
    ws.advance("PLAN_READY")
    ws.advance("LYRICS_READY")
    ws.advance("PLAN_READY")          # 뒤로 가는 전이는 무시된다
    assert ws.state == "LYRICS_READY"


def test_require_blocks_when_behind(project):
    ws = Workspace.load(project)
    with pytest.raises(StateError):
        ws.require("RENDERED")


def test_reset_clears_later_steps(project):
    ws = Workspace.load(project)
    ws.step_done("plan"); ws.advance("PLAN_READY")
    ws.step_done("lyrics"); ws.advance("LYRICS_READY")
    ws.step_done("pilot"); ws.advance("PILOT_APPROVED")
    ws.reset_to("LYRICS_READY", "파일럿 거절")
    assert ws.state == "LYRICS_READY"
    assert ws.step_status("lyrics") == "done"      # 이전 단계는 유지
    assert ws.step_status("pilot") == "pending"    # 이후 단계는 초기화


def test_artifact_hash_detects_tampering(project):
    ws = Workspace.load(project)
    f = project.root / "sample.txt"
    f.write_text("hello", encoding="utf-8")
    ws.register(f)
    assert ws.verify_artifact(f) == (True, "ok")
    assert ws.reusable(f)

    f.write_text("hello world", encoding="utf-8")
    ok, why = ws.verify_artifact(f)
    assert not ok and why in ("크기 불일치", "해시 불일치")
    assert not ws.reusable(f)

    f.unlink()
    assert ws.verify_artifact(f) == (False, "파일 없음")


def test_workspace_survives_reload(project):
    ws = Workspace.load(project)
    ws.set_flag("pilot_approved_at", "2026-01-01T00:00:00+00:00")
    ws.advance("PLAN_READY", "테스트")
    again = Workspace.load(project)
    assert again.state == "PLAN_READY"
    assert again.flag("pilot_approved_at").startswith("2026")
    assert any(h["state"] == "PLAN_READY" for h in again.data["history"])
