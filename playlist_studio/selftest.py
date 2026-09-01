"""셀프테스트 - 합성 음원·이미지로 파이프라인 전체를 돌린다.

크레딧을 쓰지 않는다. 유료 생성을 시작하기 전에 이 테스트가 전부
통과해야 한다. 각 단계는 실제 CLI 명령을 호출하므로, 사용자가 손으로
실행할 경로와 동일한 코드를 검증한다.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import time
import traceback
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

from . import testkit as TK
from .paths import ProjectPaths, channels_dir, find_project, studio_root
from .util import ensure_dir, hhmmss, read_json

SAMPLE_LYRICS = [
    ("창가의 새벽", "first light", "밤을 지나 아침으로 건너가는 순간",
     "[Intro]\n[Verse]\n창틀에 맺힌 물기를 손끝으로 지운다\n어제는 아직 방 안에 남아 있고\n"
     "[Pre Chorus]\n숨을 한 번 길게 내쉬면\n[Chorus]\n천천히 밝아지는 쪽으로\n"
     "몸을 조금씩 돌려 본다\n[Outro]"),
    ("두 시의 라디오", "two a.m.", "잠들지 못하는 밤의 소음",
     "[Intro]\n[Verse]\n식은 컵을 다시 데우려다 그만둔다\n주파수 사이에서 사람 목소리가 스친다\n"
     "[Chorus]\n아무도 부르지 않는 이름을\n혼자 소리 내어 불러 본다\n[Bridge]\n"
     "이 시간에만 들리는 것들이 있다\n[Outro]"),
    ("먼 길의 불빛", "far lights", "돌아가는 길에 보이는 작은 빛",
     "[Verse]\n버스는 정류장을 두 개쯤 지나쳤고\n창밖 간판들이 흐리게 번진다\n"
     "[Pre Chorus]\n어디쯤에서 내려야 할지\n[Chorus]\n멀리 켜진 불빛 하나를\n"
     "오래 바라보고 있었다\n[Outro]"),
    ("책상 위의 겨울", "desk winter", "오래 앉아 있는 사람의 온도",
     "[Verse]\n연필이 굴러가 모서리에 멈춘다\n손등이 조금 차가워졌다\n"
     "[Chorus]\n아직 끝나지 않은 문장 위에\n작은 온기를 올려 둔다\n[Outro]"),
    ("돌아오는 계단", "stairs home", "익숙한 곳으로 되돌아가는 걸음",
     "[Verse]\n세 번째 칸에서 늘 소리가 난다\n오늘도 같은 자리에서 멈춘다\n"
     "[Chorus]\n올라갈수록 조용해지는 쪽으로\n한 칸씩 나를 옮긴다\n[Outro]"),
    ("젖은 우산", "wet umbrella", "비를 털고 들어온 저녁",
     "[Verse]\n현관에 우산을 세워 둔다\n바닥에 작은 웅덩이가 생긴다\n"
     "[Chorus]\n밖에 두고 온 하루가\n천천히 마르고 있다\n[Outro]"),
]


@dataclass
class Step:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


def _run_cli(argv: list[str]) -> tuple[bool, str]:
    from . import cli
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            cli.main(argv)
        return True, buf.getvalue()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        return code == 0, buf.getvalue()
    except Exception:
        return False, buf.getvalue() + "\n" + traceback.format_exc()


def run_selftest(*, name: str = "selftest", tracks: int = 3,
                 seconds: float = 30.0, keep: bool = False,
                 verbose: bool = True) -> dict:
    tracks = max(1, min(tracks, len(SAMPLE_LYRICS)))
    steps: list[Step] = []
    log: list[str] = []
    project = ""
    root: Path | None = None

    def step(label: str, fn) -> bool:
        t0 = time.time()
        try:
            ok, out = fn()
        except Exception:
            ok, out = False, traceback.format_exc()
        dt = time.time() - t0
        steps.append(Step(label, ok, dt, out.strip()[-1500:] if not ok else ""))
        if verbose:
            print(f"  [{'OK ' if ok else 'FAIL'}] {label}  ({dt:.1f}s)", flush=True)
            if not ok:
                print("        " + (out.strip()[-800:].replace("\n", "\n        ")),
                      flush=True)
        log.append(out)
        return ok

    ch_name = f"TEST {name}"
    pl_title = f"테스트 플레이리스트 {name}"
    try:
        if verbose:
            print(f"셀프테스트 시작 — {tracks}곡 × {seconds:.0f}초 합성 음원\n", flush=True)

        # 1. 채널/플레이리스트
        ok = step("채널 생성", lambda: _run_cli(
            ["channel-new", "--name", ch_name, "--genre", "lofi",
             "--concept", "셀프테스트용. 실제 채널이 아님."]))
        if not ok:
            raise RuntimeError("채널 생성 실패")
        ch_dir = sorted(channels_dir().iterdir())[-1].name

        ok = step("플레이리스트 생성", lambda: _run_cli(
            ["playlist-new", "--channel", ch_dir, "--title", pl_title]))
        if not ok:
            raise RuntimeError("플레이리스트 생성 실패")
        # 방금 만든 채널 아래 마지막 플레이리스트
        pl_root = sorted((channels_dir() / ch_dir / "playlists").iterdir())[-1]
        root = pl_root
        project = str(pl_root)

        # 2. 설정
        step("설정 저장", lambda: _run_cli([
            "config-set", "--project", project,
            "genre=lofi", "subgenre=jazzy tape lofi", "purpose=집중",
            "situation=야근", "vocal_mode=vocal", "lyrics_language=ko",
            "subtitle_language=ko", f"track_count={tracks}",
            f"track_seconds={int(seconds)}", f"total_seconds={int(seconds*tracks)}",
            "bpm_min=70", "bpm_max=88", "mood_arc=calm-to-warm",
            "visual_preset=black-gray-red", "thumbnail_language=ko",
        ]))
        step("남은 질문 조회(마법사 재개)", lambda: _run_cli(
            ["config-status", "--project", project]))

        # 3. 계획
        step("계획 생성 (sonic_dna/visual_dna/tracks.json)", lambda: _run_cli(
            ["plan", "--project", project]))

        # 4. 가사
        def _lyrics():
            outs = []
            for i in range(tracks):
                title, sub, theme, body = SAMPLE_LYRICS[i]
                ok1, o1 = _run_cli(["track-set", "--project", project,
                                    "--index", str(i + 1),
                                    f"title={title}", f"subtitle={sub}",
                                    f"lyrical_theme={theme}"])
                ok2, o2 = _run_cli(["track-lyrics", "--project", project,
                                    "--index", str(i + 1), "--text", body])
                outs += [o1, o2]
                if not (ok1 and ok2):
                    return False, "\n".join(outs)
            return True, "\n".join(outs)
        step("가사 작성 및 저장", _lyrics)
        step("가사 중복·해시 검사", lambda: _run_cli(
            ["lyrics-validate", "--project", project]))
        step("가사 모음 작성 (LYRICS_READY)", lambda: _run_cli(
            ["lyrics-collect", "--project", project]))

        # 5. 크레딧 견적 (차감 없음)
        step("크레딧 견적 표시", lambda: _run_cli(
            ["cost", "--project", project, "--balance", "134"]))

        # 6. 중복 생성 차단 검증
        def _dup_guard():
            ok1, o1 = _run_cli(["submit-payload", "--project", project,
                                "--index", "1", "--claim"])
            if not ok1:
                return False, "첫 제출 페이로드 생성 실패\n" + o1
            ok2, o2 = _run_cli(["submit-payload", "--project", project,
                                "--index", "1", "--claim"])
            if ok2:
                return False, "두 번째 제출이 차단되지 않았습니다 (중복 과금 위험)\n" + o2
            if "중복 생성 차단" not in o2:
                return False, "차단은 됐지만 메시지가 예상과 다릅니다\n" + o2
            return True, o1 + o2
        step("중복 생성 차단 (같은 프롬프트 재제출)", _dup_guard)

        # 7. 합성 음원 주입
        stage = ensure_dir(pl_root / "work" / "_synth")

        def _audio():
            outs = []
            for i in range(1, tracks + 1):
                f = TK.synth_mp3(stage / f"{i:02d}.mp3", seconds=seconds,
                                 bpm=72 + i * 4, seed=i)
                ok, o = _run_cli(["track-import", "--project", project,
                                  "--index", str(i), "--src", str(f),
                                  "--job-id", f"TEST-JOB-{i:03d}",
                                  "--credit-cost", "0", "--test",
                                  "--min-seconds", str(max(5, seconds * 0.5))])
                outs.append(o)
                if not ok:
                    return False, "\n".join(outs)
            return True, "\n".join(outs)
        step("합성 음원 주입 + ffprobe 검사", _audio)

        step("파일럿 상태 확인", lambda: _run_cli(
            ["pilot-status", "--project", project]))
        step("파일럿 승인 게이트", lambda: _run_cli(
            ["pilot-approve", "--project", project]))
        step("배치 상태 (BATCH_GENERATED)", lambda: _run_cli(
            ["batch-status", "--project", project]))

        # 8. 이미지
        def _images():
            outs = []
            preset = "black-gray-red"
            for i in range(1, tracks + 1):
                f = TK.synth_image(stage / f"bg{i:02d}.png", preset=preset,
                                   seed=i * 5, label="TEST BG")
                ok, o = _run_cli(["image-import", "--project", project,
                                  "--role", "bg", "--index", str(i),
                                  "--src", str(f), "--test",
                                  "--provider", "synthetic"])
                outs.append(o)
                if not ok:
                    return False, "\n".join(outs)
            f = TK.synth_image(stage / "intro.png", preset=preset, seed=99,
                               label="TEST INTRO")
            ok, o = _run_cli(["image-import", "--project", project, "--role", "intro",
                              "--src", str(f), "--test", "--provider", "synthetic"])
            outs.append(o)
            for slot in range(1, 5):
                f = TK.synth_image(stage / f"th{slot}.png", preset=preset,
                                   seed=slot * 11, label="TEST THUMB")
                ok2, o2 = _run_cli(["image-import", "--project", project,
                                    "--role", "thumb-candidate", "--slot", str(slot),
                                    "--src", str(f), "--test",
                                    "--provider", "synthetic"])
                outs.append(o2)
                ok = ok and ok2
            return ok, "\n".join(outs)
        step("합성 이미지 주입 (배경·인트로·썸네일 후보 4장)", _images)

        step("썸네일 합성 (텍스트 이탈 검사 포함)", lambda: _run_cli(
            ["thumbnail", "--project", project, "--concept", "B"]))
        step("VISUALS_READY", lambda: _run_cli(
            ["visuals-done", "--project", project]))

        # 9. 병합 · 정렬 · 자막
        step("음량 정규화 + 크로스페이드 병합", lambda: _run_cli(
            ["build-audio", "--project", project, "--crossfade", "1.2",
             "--min-seconds", str(max(5, seconds * 0.5))]))
        step("가사 타이밍 정렬", lambda: _run_cli(
            ["align", "--project", project, "--method", "estimate"]))
        step("SRT + ASS 생성", lambda: _run_cli(
            ["subtitles", "--project", project, "--intro-seconds", "6"]))

        # 10. 재개 검증 - 상태를 읽어 이어갈 수 있는가
        def _resume():
            ok1, o1 = _run_cli(["status", "--project", project])
            ok2, o2 = _run_cli(["resume", "--project", project])
            ok3, o3 = _run_cli(["verify", "--project", project])
            return ok1 and ok2 and ok3, o1 + o2 + o3
        step("상태 저장·재개·해시 검증", _resume)

        # 11. 메타데이터
        step("메타데이터 + rights.json", lambda: _run_cli(
            ["metadata", "--project", project, "--plan-note", "SELFTEST (무료 합성 자산)"]))

        # 12. 렌더
        step("최종 MP4 렌더 (배경+파형+인트로+자막)", lambda: _run_cli(
            ["render", "--project", project, "--intro-seconds", "6",
             "--preset", "ultrafast", "--final-preset", "veryfast",
             "--crf", "26", "--final-crf", "24"]))

        # 13. QA
        step("QA 보고서", lambda: _run_cli(["qa", "--project", project]))

        # 14. 산출물 존재 확인
        def _artifacts():
            p = ProjectPaths(pl_root)
            need = [
                ("최종 MP4", p.final_mp4), ("SRT", p.srt), ("ASS", p.ass),
                ("썸네일", p.thumbnail), ("lyrics_all.md", p.lyrics_all),
                ("병합 음원", p.master_wav),
                ("youtube_title.txt", p.meta / "youtube_title.txt"),
                ("youtube_description.txt", p.meta / "youtube_description.txt"),
                ("chapters.txt", p.meta / "chapters.txt"),
                ("tags.txt", p.meta / "tags.txt"),
                ("rights.json", p.meta / "rights.json"),
                ("QA 보고서", p.qa_report_md),
            ]
            for i in range(1, tracks + 1):
                need.append((f"음원 {i:02d}", p.track_audio_raw(i)))
                need.append((f"배경 {i:02d}", p.track_bg(i)))
            missing = [n for n, f in need if not Path(f).exists() or Path(f).stat().st_size == 0]
            if missing:
                return False, "없거나 빈 파일: " + ", ".join(missing)
            return True, f"{len(need)}개 산출물 모두 존재"
        step("최종 산출물 존재 확인", _artifacts)

    except Exception:
        tb = traceback.format_exc()
        log.append(tb)
        steps.append(Step("셀프테스트 진행 중 예외", False, 0.0, tb[-2000:]))
        if verbose:
            print(f"  [FAIL] 셀프테스트 진행 중 예외\n{tb}", flush=True)

    qa_result = None
    video = None
    if root is not None:
        p = ProjectPaths(root)
        qa_result = read_json(p.qa_report_json, None)
        if p.final_mp4.exists():
            try:
                from .render import probe_video
                video = probe_video(p.final_mp4)
            except Exception:
                pass

    ok_all = bool(steps) and all(s.ok for s in steps)

    lines = [
        "# 셀프테스트 결과 (합성 자산 · 크레딧 미사용)",
        "",
        f"- 프로젝트: `{project}`",
        f"- 곡 수: {tracks} × {seconds:.0f}초",
        f"- 종합: **{'✅ 전부 통과' if ok_all else '❌ 실패 있음'}**",
        "",
        "| | 단계 | 소요 |",
        "|---|---|---|",
    ]
    for s in steps:
        lines.append(f"| {'✅' if s.ok else '❌'} | {s.name} | {s.seconds:.1f}s |")
    fails = [s for s in steps if not s.ok]
    if fails:
        lines += ["", "## 실패 상세", ""]
        for s in fails:
            lines += [f"### {s.name}", "```", s.detail or "(출력 없음)", "```", ""]
    if video:
        lines += [
            "", "## 최종 MP4 실측 (ffprobe)", "",
            "| 항목 | 값 |", "|---|---|",
            f"| 해상도 | {video['width']}x{video['height']} |",
            f"| fps | {video['fps']} |",
            f"| 영상 코덱 | {video['video_codec']} / {video['pix_fmt']} |",
            f"| 오디오 | {video['audio_codec']} {video['audio_sample_rate']}Hz "
            f"{video['audio_channels']}ch |",
            f"| 길이 | {hhmmss(video['duration'], force_hours=True)} "
            f"(영상 {video['video_duration']:.2f}s / 오디오 {video['audio_duration']:.2f}s) |",
            f"| faststart | {'예' if video['has_faststart'] else '아니오'} |",
        ]
    if qa_result:
        c = qa_result["counts"]
        lines += ["", f"## QA: **{qa_result['verdict']}** "
                      f"(PASS {c['pass']} / WARN {c['warn']} / FAIL {c['fail']})"]
        for chk in qa_result["checks"]:
            if chk["status"] != "PASS":
                lines.append(f"- {chk['status']} — {chk['name']}: {chk.get('detail','')}")

    if not keep and root is not None and root.exists():
        parent = root.parent.parent
        shutil.rmtree(parent, ignore_errors=True)
        lines += ["", f"테스트 채널 삭제됨: `{parent.name}` (남기려면 `--keep`)"]
    elif root is not None:
        lines += ["", f"테스트 산출물 위치: `{root}`"]

    return {
        "ok": ok_all,
        "project": project,
        "steps": [s.__dict__ for s in steps],
        "qa": qa_result,
        "video": video,
        "report": "\n".join(lines),
    }
