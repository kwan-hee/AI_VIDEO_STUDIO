"""QA - 최종 산출물이 실제로 존재하고 열리는지 확인한다.

'만들었다'가 아니라 '열어 봤다'를 기록한다. 각 항목은 PASS / WARN / FAIL 로
판정하고, FAIL 이 하나라도 있으면 VERIFIED 로 넘어가지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Sequence

from . import audio as A
from .align import TimedLine
from .paths import ProjectPaths
from .render import probe_video
from .state import Workspace
from .util import hhmmss, now_iso, read_json, read_text, sha256_file

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    data: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


def _exists(name: str, path: Path, *, min_bytes: int = 1,
            required: bool = True) -> Check:
    p = Path(path)
    if not p.exists():
        return Check(name, FAIL if required else WARN, f"없음: {p}")
    n = p.stat().st_size
    if n < min_bytes:
        return Check(name, FAIL if required else WARN, f"너무 작음: {n} bytes")
    return Check(name, PASS, f"{n:,} bytes", {"path": str(p), "bytes": n})


def run_qa(paths: ProjectPaths, *, config: dict, tracks: Sequence[dict],
           timing: dict | None = None, thumbnail_info: dict | None = None,
           workspace: Workspace | None = None) -> dict:
    checks: list[Check] = []
    timing = timing or {}

    # --- 1. 곡별 음원 ---
    ok_tracks = 0
    for t in tracks:
        idx = t["index"]
        rel = t.get("output_path")
        if not rel:
            checks.append(Check(f"음원 {idx:02d}", FAIL, "output_path 가 비어 있음"))
            continue
        p = paths.root / rel
        info = A.validate(p, min_seconds=15)
        if info.ok:
            ok_tracks += 1
            checks.append(Check(f"음원 {idx:02d}", PASS,
                                f"{info.duration:.1f}s {info.codec} {info.sample_rate}Hz",
                                info.to_dict()))
        else:
            checks.append(Check(f"음원 {idx:02d}", FAIL, "; ".join(info.issues) or "검사 실패",
                                info.to_dict()))
        if t.get("sha256"):
            if p.exists() and sha256_file(p) != t["sha256"]:
                checks.append(Check(f"음원 {idx:02d} 해시", FAIL,
                                    "tracks.json 기록과 다름 (파일이 바뀌었거나 손상)"))

    # --- 2. 가사 ---
    from .lyrics import validate_set
    lyr = validate_set(paths, list(tracks))
    checks.append(Check("가사 세트", FAIL if lyr["errors"] else PASS,
                        "; ".join(lyr["errors"]) if lyr["errors"]
                        else f"{lyr['checked']}곡 검사 통과"
                             + (f" (경고 {len(lyr['warnings'])}건)" if lyr["warnings"] else ""),
                        {"errors": lyr["errors"], "warnings": lyr["warnings"]}))
    checks.append(_exists("lyrics_all.md", paths.lyrics_all, min_bytes=50))

    # --- 3. 곡별 이미지 ---
    missing_bg = [t["index"] for t in tracks if not paths.track_bg(t["index"]).exists()]
    checks.append(Check("곡별 배경 이미지", FAIL if missing_bg else PASS,
                        f"누락: {missing_bg}" if missing_bg
                        else f"{len(tracks)}장 모두 존재"))

    # --- 4. 썸네일 ---
    tc = _exists("대표 썸네일", paths.thumbnail, min_bytes=5000)
    checks.append(tc)
    if tc.status == PASS:
        try:
            from PIL import Image
            with Image.open(paths.thumbnail) as im:
                w, h = im.size
            n = paths.thumbnail.stat().st_size
            problems = []
            if (w, h) != (1280, 720):
                problems.append(f"크기 {w}x{h} (기대 1280x720)")
            if n > 2 * 1024 * 1024:
                problems.append(f"{n/1024/1024:.1f}MB — YouTube 2MB 한도 초과")
            checks.append(Check("썸네일 규격", WARN if problems else PASS,
                                "; ".join(problems) or f"1280x720, {n/1024:.0f}KB"))
        except Exception as e:
            checks.append(Check("썸네일 규격", FAIL, f"열 수 없음: {e}"))
    if thumbnail_info and thumbnail_info.get("overflow"):
        checks.append(Check("썸네일 텍스트 이탈", FAIL,
                            thumbnail_info.get("overflow_reason", "텍스트가 화면을 벗어남")))
    elif thumbnail_info:
        checks.append(Check("썸네일 텍스트 이탈", PASS,
                            f"제목 {thumbnail_info.get('title_size')}px, 화면 안에 들어감"))

    # --- 5. 자막 ---
    checks.append(_exists("SRT", paths.srt, min_bytes=20))
    checks.append(_exists("ASS", paths.ass, min_bytes=200))
    ass_text = read_text(paths.ass, "") or ""
    if ass_text:
        has_styles = "[V4+ Styles]" in ass_text and "Style: Active" in ass_text
        n_events = ass_text.count("\nDialogue:")
        checks.append(Check("ASS 스타일", PASS if has_styles else FAIL,
                            f"스타일 정의 {'있음' if has_styles else '없음'}, "
                            f"이벤트 {n_events}개"))

    # --- 6. 메타데이터 ---
    for name, req in (("youtube_title.txt", True), ("youtube_description.txt", True),
                      ("chapters.txt", True), ("tags.txt", True),
                      ("generation_disclosure.txt", True), ("rights.json", True)):
        checks.append(_exists(name, paths.meta / name, min_bytes=5, required=req))
    title = (read_text(paths.meta / "youtube_title.txt", "") or "").strip()
    if title:
        checks.append(Check("제목 길이", PASS if len(title) <= 100 else FAIL,
                            f"{len(title)}자 / 100자 한도"))
    chapters = (read_text(paths.meta / "chapters.txt", "") or "").strip().splitlines()
    if chapters:
        first_ok = chapters[0].split()[0] in ("0:00", "00:00", "0:00:00")
        checks.append(Check("챕터 형식",
                            PASS if (first_ok and len(chapters) >= 3) else WARN,
                            f"{len(chapters)}개, 첫 줄 {'00:00 시작' if first_ok else '00:00 아님 — YouTube 가 인식 못 함'}"))
    rights = read_json(paths.meta / "rights.json", None)
    if rights is not None:
        n_items = len(rights.get("items", []))
        checks.append(Check("rights.json 항목", PASS if n_items else FAIL,
                            f"{n_items}건 기록"))

    # --- 7. 최종 영상 ---
    mv = _exists("최종 MP4", paths.final_mp4, min_bytes=100_000)
    checks.append(mv)
    if mv.status == PASS:
        try:
            v = probe_video(paths.final_mp4)
        except Exception as e:
            checks.append(Check("MP4 ffprobe", FAIL, f"열 수 없음: {e}"))
            v = None
        if v:
            spec_problems = []
            if (v["width"], v["height"]) != (1920, 1080):
                spec_problems.append(f"해상도 {v['width']}x{v['height']}")
            if v["video_codec"] != "h264":
                spec_problems.append(f"코덱 {v['video_codec']}")
            if v["pix_fmt"] != "yuv420p":
                spec_problems.append(f"pix_fmt {v['pix_fmt']}")
            if v["audio_codec"] != "aac":
                spec_problems.append(f"오디오 {v['audio_codec']}")
            fps = v["fps"]
            if fps not in ("30/1", "30000/1001"):
                spec_problems.append(f"fps {fps}")
            checks.append(Check("MP4 규격", FAIL if spec_problems else PASS,
                                "; ".join(spec_problems)
                                or f"1920x1080 h264 yuv420p {fps} aac", v))
            checks.append(Check("faststart", PASS if v["has_faststart"] else WARN,
                                "moov 아톰이 앞에 있음" if v["has_faststart"]
                                else "moov 가 뒤에 있음 — 웹 재생 시작이 느림"))
            drift = abs(v["video_duration"] - v["audio_duration"])
            checks.append(Check("영상·오디오 길이 일치",
                                PASS if drift <= 0.5 else (WARN if drift <= 2.0 else FAIL),
                                f"영상 {v['video_duration']:.2f}s / 오디오 "
                                f"{v['audio_duration']:.2f}s (차이 {drift:.2f}s)"))
            exp = timing.get("total_duration")
            if exp:
                d2 = abs(v["duration"] - exp)
                checks.append(Check("병합 음원 길이와 일치",
                                    PASS if d2 <= 1.0 else WARN,
                                    f"MP4 {v['duration']:.2f}s / 병합 음원 {exp:.2f}s "
                                    f"(차이 {d2:.2f}s)"))
            # 자막이 영상 밖으로 나가지 않는지
            last_end = timing.get("last_subtitle_end")
            if last_end:
                checks.append(Check("자막 범위",
                                    PASS if last_end <= v["duration"] + 0.5 else FAIL,
                                    f"마지막 자막 {last_end:.2f}s / 영상 {v['duration']:.2f}s"))

    # --- 8. 정렬 품질 ---
    if timing.get("report"):
        rep = timing["report"]
        checks.append(Check("가사 싱크 방식",
                            PASS if rep.get("meets_300ms_target") else WARN,
                            f"{rep.get('method')} — {rep.get('accuracy_claim','')}", rep))

    # --- 9. 산출물 해시 ---
    if workspace is not None:
        v = workspace.verify_all()
        checks.append(Check("산출물 해시 검증",
                            PASS if not v["broken"] else FAIL,
                            f"{len(v['ok'])}/{v['total']} 정상"
                            + (f", 손상: {[b['path'] for b in v['broken']]}" if v["broken"] else ""),
                            v))

    n_fail = sum(1 for c in checks if c.status == FAIL)
    n_warn = sum(1 for c in checks if c.status == WARN)
    return {
        "generated_at": now_iso(),
        "project": paths.root.name,
        "playlist_title": config.get("playlist_title", ""),
        "verdict": FAIL if n_fail else (WARN if n_warn else PASS),
        "counts": {"pass": len(checks) - n_fail - n_warn, "warn": n_warn, "fail": n_fail},
        "checks": [c.to_dict() for c in checks],
    }


def report_markdown(result: dict) -> str:
    icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌"}
    c = result["counts"]
    lines = [
        f"# QA 보고서 — {result.get('playlist_title') or result['project']}",
        "",
        f"- 생성: {result['generated_at']}",
        f"- 종합 판정: **{icon[result['verdict']]} {result['verdict']}**",
        f"- PASS {c['pass']} / WARN {c['warn']} / FAIL {c['fail']}",
        "",
        "| | 항목 | 결과 |",
        "|---|---|---|",
    ]
    for chk in result["checks"]:
        detail = str(chk.get("detail", "")).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {icon[chk['status']]} | {chk['name']} | {detail} |")
    if c["fail"]:
        lines += ["", "## 실패 항목", ""]
        for chk in result["checks"]:
            if chk["status"] == FAIL:
                lines.append(f"- **{chk['name']}** — {chk.get('detail','')}")
    if c["warn"]:
        lines += ["", "## 경고 항목", ""]
        for chk in result["checks"]:
            if chk["status"] == WARN:
                lines.append(f"- {chk['name']} — {chk.get('detail','')}")
    return "\n".join(lines) + "\n"
