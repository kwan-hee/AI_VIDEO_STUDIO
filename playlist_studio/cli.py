"""명령줄 진입점.

Claude Code 스킬은 이 CLI 만 호출한다. 이 CLI 는 MCP 를 직접 부르지 않는다.
유료 생성은 스킬이 사용자 승인을 받아 MCP 로 수행하고, 결과를 여기에 기록한다.

    python -m playlist_studio <명령> [옵션]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any

from . import audio as A
from . import align as AL
from . import channels as CH
from . import cost as CO
from . import dna as DNA
from . import env as ENV
from . import fonts as FN
from . import lyrics as LY
from . import metadata as MD
from . import qa as QA
from . import render as RD
from . import subtitles as SB
from . import testkit as TK
from . import tracks as TR
from . import visuals as VS
from . import wizard as WZ
from .ledger import Ledger, fingerprint
from .paths import ProjectPaths, find_project, iter_projects, studio_root
from .state import STEPS, Workspace
from .util import (ensure_dir, hhmmss, now_iso, read_json, rel_posix,
                   sha256_file, write_json, write_text)

OUT_JSON = False


def emit(human: str, data: Any = None) -> None:
    if OUT_JSON:
        print(json.dumps(data if data is not None else {"message": human},
                         ensure_ascii=False, indent=2))
    else:
        print(human)


def die(msg: str, code: int = 2) -> None:
    if OUT_JSON:
        print(json.dumps({"error": msg}, ensure_ascii=False, indent=2))
    else:
        print(f"오류: {msg}", file=sys.stderr)
    raise SystemExit(code)


# ---------------------------------------------------------------- 프로젝트 로딩
class Ctx:
    def __init__(self, project: str):
        self.paths: ProjectPaths = find_project(project)
        self.ws: Workspace = Workspace.load(self.paths)
        self.config: dict = WZ.load_config(self.paths.config)
        self._tracks: list[dict] | None = None

    @property
    def tracks(self) -> list[dict]:
        if self._tracks is None:
            self._tracks = TR.load_tracks(self.paths.tracks)
        return self._tracks

    def save_tracks(self) -> None:
        TR.save_tracks(self.paths.tracks, self.tracks)
        # tracks.json 은 단계마다 갱신되는 작업 파일이다. 저장할 때마다 해시를
        # 다시 등록하지 않으면 `verify` 가 정상 갱신을 '손상' 으로 오판한다.
        try:
            self.ws.register(self.paths.tracks, kind="plan")
        except FileNotFoundError:
            pass

    def save_config(self) -> None:
        WZ.save_config(self.paths.config, self.config)

    @property
    def sonic(self) -> dict:
        d = read_json(self.paths.sonic_dna, None)
        if d is None:
            die("sonic_dna.json 이 없습니다. 먼저 `plan` 을 실행하세요.")
        return d

    @property
    def visual(self) -> dict:
        d = read_json(self.paths.visual_dna, None)
        if d is None:
            die("visual_dna.json 이 없습니다. 먼저 `plan` 을 실행하세요.")
        return d

    @property
    def ledger(self) -> Ledger:
        return Ledger.load(self.paths.ledger)

    @property
    def timing(self) -> dict:
        return read_json(self.paths.root / "timing.json", {}) or {}

    def save_timing(self, data: dict) -> None:
        write_json(self.paths.root / "timing.json", data)


# ================================================================ 명령들
def cmd_doctor(a) -> None:
    d = ENV.doctor()
    emit(ENV.report_markdown(d), d)
    if not d["ready"]:
        raise SystemExit(1)


# ---------------------------------------------------------------- 채널
def cmd_channel_new(a) -> None:
    info = CH.create_channel(a.name, genre=a.genre or "", concept=a.concept or "")
    emit(f"채널 생성: {info['dirname']}\n  이름: {info['name']}\n"
         f"  경로: {studio_root() / 'channels' / info['dirname']}", info)


def cmd_channel_list(a) -> None:
    chans = CH.list_channels()
    if not chans:
        emit("채널이 없습니다. `channel-new` 로 만드세요.", {"channels": []})
        return
    lines = ["| 채널 | 이름 | 플레이리스트 | 상태 |", "|---|---|---|---|"]
    for c in chans:
        if c["playlists"]:
            for p in c["playlists"]:
                lines.append(f"| `{c['dirname']}` | {c['name']} | `{p['dirname']}` | {p['state']} |")
        else:
            lines.append(f"| `{c['dirname']}` | {c['name']} | — | — |")
    emit("\n".join(lines), {"channels": chans})


def cmd_playlist_new(a) -> None:
    paths, meta = CH.create_playlist(a.channel, a.title)
    project_id = f"{meta['channel_dirname']}/{meta['playlist_dirname']}"
    ws = Workspace.create(paths, project_id, meta)
    cfg = {"channel": meta["channel_dirname"], "playlist_title": a.title,
           "channel_slug": meta["channel_slug"], "playlist_slug": meta["playlist_slug"],
           "created_at": now_iso()}
    WZ.save_config(paths.config, cfg)
    ws.step_done("channel", f"채널 {meta['channel_dirname']} 아래 생성")
    ws.advance("CHANNEL_READY", "플레이리스트 폴더 생성")
    CH.refresh_channel_md(paths.root.parent.parent)
    emit(f"플레이리스트 생성: {project_id}\n  경로: {paths.root}\n"
         f"  다음: `config-status --project {project_id}` 로 남은 질문을 확인하세요.",
         {"project": project_id, "path": str(paths.root), **meta})


# ---------------------------------------------------------------- 설정 마법사
def cmd_config_status(a) -> None:
    c = Ctx(a.project)
    nxt = WZ.next_questions(c.config, limit=a.limit)
    missing = WZ.missing_questions(c.config)
    warns = WZ.validate(c.config)
    data = {
        "answered": len(WZ.QUESTIONS) - len(missing),
        "total": len(WZ.QUESTIONS),
        "missing": [q.key for q in missing],
        "next": [{"key": q.key, "label": q.label, "kind": q.kind,
                  "choices": list(q.choices), "hint": q.hint, "default": q.default}
                 for q in nxt],
        "warnings": warns,
        "config": c.config,
    }
    if not missing:
        human = ("설정이 모두 채워졌습니다.\n\n" + WZ.summary_table(c.config))
    else:
        human = [f"남은 질문 {len(missing)}개 / 전체 {len(WZ.QUESTIONS)}개", "", "다음에 물을 것:"]
        for q in nxt:
            ch = f"  선택지: {', '.join(q.choices)}" if q.choices else ""
            df = f"  (기본값 {q.default})" if q.default is not None else ""
            human.append(f"- **{q.label}** (`{q.key}`){df}\n{ch}\n  {q.hint}")
        human = "\n".join(human)
    if warns:
        human += "\n\n경고:\n" + "\n".join(f"- {w}" for w in warns)
    emit(human, data)


def cmd_config_set(a) -> None:
    c = Ctx(a.project)
    changed = {}
    for pair in a.kv:
        if "=" not in pair:
            die(f"key=value 형식이어야 합니다: {pair}")
        k, v = pair.split("=", 1)
        try:
            c.config[k] = WZ.coerce(k, v)
        except ValueError as e:
            die(str(e))
        changed[k] = c.config[k]
    c.save_config()
    missing = WZ.missing_questions(c.config)
    emit(f"저장: {changed}\n남은 질문 {len(missing)}개"
         + (f" ({', '.join(q.key for q in missing[:4])}…)" if missing else " — 모두 완료"),
         {"changed": changed, "missing": [q.key for q in missing],
          "warnings": WZ.validate(c.config)})


def cmd_config_show(a) -> None:
    c = Ctx(a.project)
    emit(WZ.summary_table(c.config), c.config)


# ---------------------------------------------------------------- 2단계: 계획
def cmd_plan(a) -> None:
    c = Ctx(a.project)
    missing = WZ.missing_questions(c.config)
    blocking = [q.key for q in missing if q.key != "thumbnail_concept"]
    if blocking and not a.force:
        die(f"설정이 덜 채워졌습니다: {', '.join(blocking)} "
            f"(썸네일 콘셉트는 6단계에서 정해도 됩니다. 무시하려면 --force)")

    c.ws.step_start("plan")
    try:
        sonic = DNA.build_sonic_dna(c.config)
        visual = DNA.build_visual_dna(c.config)
        write_json(c.paths.sonic_dna, sonic)
        write_json(c.paths.visual_dna, visual)

        existing = {t["index"]: t for t in c.tracks}
        plan = TR.build_plan(c.config, sonic)
        if existing and not a.reset:
            # 이미 만들어진 곡의 정보는 보존한다 (재실행 안전)
            for t in plan:
                old = existing.get(t["index"])
                if old and old.get("status") not in (None, "planned"):
                    t.update({k: old[k] for k in
                              ("title", "subtitle", "lyrical_theme", "lyrics_path",
                               "lyrics_sha256", "provider", "provider_job_id",
                               "prompt_fingerprint", "credit_cost", "output_path",
                               "sha256", "duration_seconds", "status", "music_prompt")
                              if k in old})
                elif old:
                    for k in ("title", "subtitle", "lyrical_theme"):
                        if old.get(k):
                            t[k] = old[k]
        c._tracks = plan
        c.save_tracks()
        c.ws.register(c.paths.sonic_dna, kind="plan")
        c.ws.register(c.paths.visual_dna, kind="plan")
        c.ws.register(c.paths.tracks, kind="plan")
        c.ws.step_done("plan", f"{len(plan)}곡 계획")
        c.ws.advance("PLAN_READY", f"{len(plan)}곡")
    except Exception as e:
        c.ws.step_failed("plan", str(e))
        raise

    emit(f"계획 완료 — {len(c.tracks)}곡\n\n{TR.summary_table(c.tracks)}\n\n"
         f"sonic_dna: `{c.paths.sonic_dna.name}` / visual_dna: `{c.paths.visual_dna.name}`\n"
         f"다음: 각 곡의 제목·부제·주제를 `track-set` 으로 채우고 `track-lyrics` 로 가사를 넣으세요.",
         {"tracks": c.tracks, "sonic_dna": sonic, "visual_dna": visual})


def cmd_dna_show(a) -> None:
    c = Ctx(a.project)
    s, v = c.sonic, c.visual
    human = ["## sonic_dna", "", "| 항목 | 값 |", "|---|---|"]
    for k, val in s.items():
        human.append(f"| {k} | {val} |")
    human += ["", "## 공통 프롬프트 문단", "", "```", DNA.dna_paragraph(s), "```",
              "", "## visual_dna", "", "| 항목 | 값 |", "|---|---|"]
    for k, val in v.items():
        human.append(f"| {k} | {val} |")
    emit("\n".join(human), {"sonic_dna": s, "visual_dna": v,
                            "sonic_paragraph": DNA.dna_paragraph(s),
                            "visual_paragraph": DNA.visual_paragraph(v)})


def cmd_dna_set(a) -> None:
    """파일럿 승인이 거절됐을 때 DNA 속성을 바꾼다."""
    c = Ctx(a.project)
    s = c.sonic
    changed = {}
    for pair in a.kv:
        if "=" not in pair:
            die(f"key=value 형식이어야 합니다: {pair}")
        k, v = pair.split("=", 1)
        if k not in s:
            die(f"sonic_dna 에 없는 항목: {k}. 가능: {', '.join(sorted(s))}")
        DNA.check_no_artist(v)
        s[k] = v
        changed[k] = v
    write_json(c.paths.sonic_dna, s)
    c.ws.register(c.paths.sonic_dna, kind="plan")
    emit(f"sonic_dna 수정: {changed}\n"
         f"주의: 이 변경으로 곡을 다시 생성하면 **곡당 크레딧이 추가로 차감**됩니다.",
         {"changed": changed, "sonic_dna": s})


# ---------------------------------------------------------------- 3단계: 가사
def cmd_track_set(a) -> None:
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, a.index)
    changed = {}
    for pair in a.kv:
        if "=" not in pair:
            die(f"key=value 형식이어야 합니다: {pair}")
        k, v = pair.split("=", 1)
        if k not in ("title", "subtitle", "lyrical_theme", "bpm", "mood",
                     "intro_lead", "target_duration", "energy_level", "structure"):
            die(f"수정할 수 없는 항목: {k}")
        DNA.check_no_artist(v)
        t[k] = int(v) if k in ("bpm", "target_duration", "energy_level") else v
        changed[k] = t[k]
    t["updated_at"] = now_iso()
    c.save_tracks()
    emit(f"트랙 {a.index:02d} 수정: {changed}", {"track": t})


def cmd_track_lyrics(a) -> None:
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, a.index)
    if a.file:
        text = Path(a.file).read_text(encoding="utf-8-sig")
    elif a.text:
        text = a.text
    else:
        text = sys.stdin.read()
    try:
        LY.save_track_lyrics(c.paths, t, text)
    except (LY.LyricsError, DNA.PromptPolicyError) as e:
        die(str(e))
    c.save_tracks()
    c.ws.register(c.paths.root / t["lyrics_path"], kind="lyrics")
    emit(f"트랙 {a.index:02d} 가사 저장: {t['lyrics_path']}\n"
         f"  해시 {t['lyrics_sha256'][:16]}  줄 {len(LY.sung_lines(text))}개",
         {"track": t})


def cmd_lyrics_validate(a) -> None:
    c = Ctx(a.project)
    r = LY.validate_set(c.paths, c.tracks)
    human = [f"검사한 곡: {r['checked']}/{len(c.tracks)}"]
    if r["errors"]:
        human += ["", "❌ 오류 (해결해야 다음 단계로 갈 수 있습니다):"]
        human += [f"- {e}" for e in r["errors"]]
    if r["warnings"]:
        human += ["", "⚠️ 경고:"] + [f"- {w}" for w in r["warnings"]]
    if not r["errors"] and not r["warnings"]:
        human.append("모든 검사 통과.")
    emit("\n".join(human), r)
    if r["errors"]:
        raise SystemExit(1)


def cmd_lyrics_collect(a) -> None:
    c = Ctx(a.project)
    r = LY.validate_set(c.paths, c.tracks)
    if r["errors"] and not a.force:
        die("가사 검사에 오류가 있습니다. `lyrics-validate` 로 확인하세요. "
            "(무시하려면 --force)")
    c.ws.step_start("lyrics")
    p = LY.write_lyrics_all(c.paths, c.tracks, c.config)
    c.ws.register(p, kind="lyrics")
    for t in c.tracks:
        if t.get("lyrics_path"):
            c.ws.register(c.paths.root / t["lyrics_path"], kind="lyrics")
    c.ws.step_done("lyrics", f"{len(c.tracks)}곡")
    c.ws.advance("LYRICS_READY", f"{len(c.tracks)}곡 가사 확정")
    emit(f"가사 모음 작성: {p}\n곡 {len(c.tracks)}개, 상태 -> LYRICS_READY",
         {"path": str(p), "validation": r})


# ---------------------------------------------------------------- 크레딧 / 제출
def cmd_cost(a) -> None:
    c = Ctx(a.project)
    model = a.model or c.config.get("music_model") or CO.DEFAULT_MUSIC_MODEL
    done = len(c.ledger.done_indices()) if not a.ignore_done else 0
    est = CO.estimate(model, len(c.tracks) or int(c.config.get("track_count", 0)),
                      already_done=done, balance=a.balance,
                      unit_credits=a.unit_credits)
    warn = ""
    if a.balance is None:
        warn = ("\n\n⚠️ 잔액을 넘기지 않았습니다. 승인 화면에는 반드시 MCP "
                "`abocado_get_credits` 의 실제 잔액을 넣어 다시 실행하세요:\n"
                f"  `cost --project {a.project} --model {model} --balance <잔액> "
                f"--unit-credits <단가>`")
    elif est.shortfall > 0:
        warn = (f"\n\n❌ 크레딧이 {est.shortfall} 부족합니다. 곡 수를 줄이거나 "
                f"더 저렴한 모델을 쓰세요. (Popcorn 1.0 = 48cr/곡)")
    emit("## 크레딧 견적\n\n" + est.table() + warn, est.to_dict())


def cmd_submit_payload(a) -> None:
    """MCP abocado_generate_audio 에 넣을 인자를 만든다. 제출은 스킬이 한다."""
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, a.index)
    model = a.model or c.config.get("music_model") or CO.DEFAULT_MUSIC_MODEL

    ok, why = LY.verify_lyrics_hash(c.paths, t)
    instrumental = c.config.get("vocal_mode") == "instrumental"
    lyrics = ""
    if not instrumental:
        if not ok:
            die(f"가사 대조 실패: {why}. 제출 전에 반드시 통과해야 합니다.")
        lyrics = LY.load_track_lyrics(c.paths, t)

    try:
        payload = TR.build_music_prompt(t, c.sonic, model, lyrics)
    except (ValueError, DNA.PromptPolicyError) as e:
        die(str(e))

    fp = fingerprint(model, payload["prompt"], lyrics, payload["options"])
    led = c.ledger
    prev = led.get(fp)
    if prev and prev.get("status") in ("claimed", "done") and not a.force:
        emit(f"⛔ 중복 생성 차단\n\n트랙 {a.index:02d} 는 같은 모델·프롬프트·가사로 "
             f"이미 {prev['status']} 상태입니다.\n"
             f"  job_id: {prev.get('provider_job_id') or '(제출 직후, 미기록)'}\n"
             f"  시각: {prev.get('claimed_at')}\n"
             f"  크레딧: {prev.get('credits')}\n\n"
             f"다시 만들려면 프롬프트나 가사를 바꾸거나, 실패한 건이면 "
             f"`ledger-release --project {a.project} --index {a.index}` 로 해제하세요.",
             {"blocked": True, "reason": "duplicate", "existing": prev})
        raise SystemExit(3)

    spec = CO.model_spec(model)
    credits = a.unit_credits if a.unit_credits is not None else spec["credits"]
    if a.claim:
        allowed, rec = led.claim(fp, track_index=a.index, model=model,
                                 credits=credits, note=t.get("title", ""))
        if not allowed and not a.force:
            die("원장 잠금 실패 (동시 실행?)")
        t["prompt_fingerprint"] = fp
        t["provider"] = model
        t["music_prompt"] = payload["prompt"]
        t["credit_cost"] = credits
        t["status"] = "submitted"
        t["updated_at"] = now_iso()
        c.save_tracks()

    mcp_args = {"model": model, "prompt": payload["prompt"],
                "title": payload["title"]}
    if payload["options"]:
        mcp_args["options"] = payload["options"]

    human = [
        f"## 트랙 {a.index:02d} 제출 페이로드 — {t.get('title') or '(제목 없음)'}",
        "",
        f"- 모델: `{model}` ({spec['display']}) — {credits} cr",
        f"- 프롬프트 {payload['prompt_chars']}/{payload['prompt_limit']}자",
        f"- 가사 {len(lyrics)}자, 해시 `{(t.get('lyrics_sha256') or '')[:16]}`",
        f"- fingerprint `{fp[:16]}`",
        f"- 원장 claim: {'예 (제출 준비 완료)' if a.claim else '아니오 (미리보기)'}",
        "",
        "MCP `abocado_generate_audio` 인자:",
        "```json",
        json.dumps(mcp_args, ensure_ascii=False, indent=2),
        "```",
    ]
    if not a.claim:
        human.append(f"\n실제 제출 전에 `--claim` 을 붙여 다시 실행해 중복 생성을 막으세요.")
    emit("\n".join(human), {"mcp_tool": "abocado_generate_audio", "arguments": mcp_args,
                            "fingerprint": fp, "credits": credits,
                            "claimed": bool(a.claim), "track": t})


def cmd_ledger_release(a) -> None:
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, a.index)
    fp = t.get("prompt_fingerprint")
    if not fp:
        die(f"트랙 {a.index} 에 fingerprint 가 없습니다. 아직 제출한 적이 없습니다.")
    led = c.ledger
    try:
        led.release(fp, a.reason or "사용자 요청")
    except ValueError as e:
        die(str(e))
    t["status"] = "lyrics_ready"
    t["provider_job_id"] = ""
    c.save_tracks()
    emit(f"트랙 {a.index:02d} 원장 해제. 다시 제출할 수 있습니다.\n"
         f"주의: 재제출하면 크레딧이 다시 차감됩니다.", {"track": t})


def cmd_ledger_show(a) -> None:
    c = Ctx(a.project)
    led = c.ledger
    entries = list(led.data["entries"].values())
    lines = ["| 트랙 | 모델 | 상태 | job_id | 크레딧 |", "|---|---|---|---|---|"]
    for e in sorted(entries, key=lambda x: (x.get("track_index") or 0)):
        lines.append(f"| {e.get('track_index')} | {e.get('model')} | {e.get('status')} | "
                     f"`{e.get('provider_job_id') or '—'}` | {e.get('credits')} |")
    lines.append("")
    lines.append(f"**실제 차감 합계(완료 건): {led.total_credits_spent()} cr**")
    emit("\n".join(lines), {"entries": entries, "spent": led.total_credits_spent()})


# ---------------------------------------------------------------- 결과 수집
def _download(url: str, dst: Path, timeout: int = 300) -> Path:
    ensure_dir(dst.parent)
    req = urllib.request.Request(url, headers={"User-Agent": "playlist-studio/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dst, "wb") as fh:
        shutil.copyfileobj(r, fh)
    return dst


def cmd_track_import(a) -> None:
    """MCP 가 돌려준 결과 URL(또는 로컬 파일)을 프로젝트로 가져온다."""
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, a.index)
    ext = a.ext or (Path(a.src.split("?")[0]).suffix.lstrip(".") or "mp3")
    dst = c.paths.track_audio_raw(a.index, ext)
    try:
        if a.src.startswith(("http://", "https://")):
            _download(a.src, dst)
        else:
            src = Path(a.src)
            if not src.exists():
                die(f"파일이 없습니다: {src}")
            ensure_dir(dst.parent)
            shutil.copy2(src, dst)
    except Exception as e:
        die(f"가져오기 실패: {e}")

    info = A.validate(dst, min_seconds=a.min_seconds,
                      expect_seconds=t.get("target_duration"))
    t["output_path"] = rel_posix(dst, c.paths.root)
    t["sha256"] = sha256_file(dst)
    t["duration_seconds"] = round(info.duration, 3)
    t["generated_at"] = now_iso()
    if a.job_id:
        t["provider_job_id"] = a.job_id
    if a.credit_cost is not None:
        t["credit_cost"] = a.credit_cost
    if a.test:
        t["is_test"] = True
    t["status"] = "verified" if info.ok else "failed"
    t["updated_at"] = now_iso()
    c.save_tracks()
    c.ws.register(dst, kind="audio", meta={"track_index": a.index})

    if a.job_id and t.get("prompt_fingerprint"):
        led = c.ledger
        if led.get(t["prompt_fingerprint"]):
            led.complete(t["prompt_fingerprint"], provider_job_id=a.job_id,
                         credits=t.get("credit_cost"), output_path=t["output_path"])

    status = "✅ 정상" if info.ok else "❌ " + "; ".join(info.issues)
    emit(f"트랙 {a.index:02d} 가져오기 완료\n"
         f"  파일: {t['output_path']}\n"
         f"  길이 {info.duration:.1f}s / {info.codec} {info.sample_rate}Hz "
         f"{info.channels}ch\n"
         f"  sha256 {t['sha256'][:16]}\n"
         f"  검사: {status}\n"
         f"  재생: `{'start' if sys.platform=='win32' else 'open/xdg-open'} \"{dst}\"`",
         {"track": t, "audio": info.to_dict()})
    if not info.ok:
        raise SystemExit(1)


# ---------------------------------------------------------------- 4단계: 파일럿
def cmd_pilot_status(a) -> None:
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, 1)
    p = c.paths.root / t["output_path"] if t.get("output_path") else None
    info = A.validate(p, min_seconds=15) if p and p.exists() else None
    human = [f"## 파일럿 (트랙 01) — {t.get('title') or '(제목 없음)'}", ""]
    if info is None:
        human.append("아직 음원이 없습니다. `submit-payload --index 1 --claim` 으로 "
                     "제출 인자를 만들고, MCP 로 생성한 뒤 `track-import` 하세요.")
    else:
        human += [
            f"- 파일: `{t['output_path']}`",
            f"- 길이: {info.duration:.1f}s (목표 {t.get('target_duration')}s)",
            f"- 코덱: {info.codec} {info.sample_rate}Hz {info.channels}ch",
            f"- 검사: {'✅ 정상' if info.ok else '❌ ' + '; '.join(info.issues)}",
            f"- 무음 비율: {A.silence_ratio(p)*100:.0f}%",
            "",
            f"재생: `{'start' if sys.platform == 'win32' else 'xdg-open'} \"{p}\"`",
            "",
            "들어 보신 뒤 하나를 고르세요:",
            "- **승인** → `pilot-approve`",
            "- **수정** → `dna-set` 으로 sonic_dna 속성을 바꾼 뒤 재생성 (크레딧 추가 차감)",
            "- **재생성** → `ledger-release --index 1` 후 다시 제출 (크레딧 추가 차감)",
        ]
    emit("\n".join(human), {"track": t, "audio": info.to_dict() if info else None,
                            "state": c.ws.state})


def cmd_pilot_approve(a) -> None:
    c = Ctx(a.project)
    t = TR.get_track(c.tracks, 1)
    if not t.get("output_path"):
        die("파일럿 음원이 없습니다.")
    p = c.paths.root / t["output_path"]
    info = A.validate(p, min_seconds=15)
    if not info.ok and not a.force:
        die(f"파일럿 음원 검사 실패: {'; '.join(info.issues)} (무시하려면 --force)")
    c.ws.step_done("pilot", f"사용자 승인 ({now_iso()})")
    c.ws.set_flag("pilot_approved_at", now_iso())
    c.ws.advance("PILOT_READY", "파일럿 생성 완료")
    c.ws.advance("PILOT_APPROVED", "사용자가 승인함")
    emit(f"파일럿 승인됨. 이제 나머지 {len(c.tracks)-1}곡을 생성할 수 있습니다.\n"
         f"먼저 `cost --project {a.project} --balance <실제잔액>` 으로 총액을 "
         f"사용자에게 보이고 승인을 받으세요.",
         {"state": c.ws.state, "remaining": len(c.tracks) - 1})


def cmd_pilot_reject(a) -> None:
    c = Ctx(a.project)
    c.ws.reset_to("LYRICS_READY", a.reason or "파일럿 거절")
    emit(f"파일럿 거절 기록. 상태 -> LYRICS_READY\n"
         f"`dna-set` 으로 sonic_dna 를 조정하거나 가사를 고친 뒤 다시 제출하세요.\n"
         f"⚠️ 재생성은 곡당 크레딧이 다시 차감됩니다.", {"state": c.ws.state})


# ---------------------------------------------------------------- 5단계
def cmd_batch_status(a) -> None:
    c = Ctx(a.project)
    pending = [t["index"] for t in c.tracks if t.get("status") != "verified"]
    done = [t["index"] for t in c.tracks if t.get("status") == "verified"]
    if not pending:
        c.ws.step_done("batch", f"{len(done)}곡 완료")
        c.ws.advance("BATCH_GENERATED", f"{len(done)}곡")
    emit(TR.summary_table(c.tracks) +
         f"\n\n완료 {len(done)}곡 / 남음 {len(pending)}곡 {pending}\n"
         f"상태: {c.ws.state}",
         {"done": done, "pending": pending, "state": c.ws.state,
          "tracks": c.tracks})


# ---------------------------------------------------------------- 6단계: 비주얼
def cmd_visual_prompts(a) -> None:
    c = Ctx(a.project)
    v = c.visual
    out: dict[str, Any] = {"image_model_suggestion": CO.DEFAULT_IMAGE_MODEL}
    human = ["## 이미지 생성 프롬프트", "",
             "⚠️ 이미지 AI 에는 글자를 그리게 하지 않습니다. 제목·곡명은 전부 "
             "로컬에서 합성합니다.", ""]

    if a.kind in ("all", "thumbnail"):
        human.append("### 썸네일 후보 4개")
        human.append("")
        human.append(VS.concept_menu())
        human.append("")
        thumbs = {}
        for k in ("A", "B", "C", "D"):
            p = VS.thumbnail_prompt(v, k, c.config)
            thumbs[k] = p
            human.append(f"**{k}**\n```\n{p}\n```\n")
        out["thumbnail_prompts"] = thumbs

    if a.kind in ("all", "intro"):
        p = VS.intro_prompt(v, c.config)
        out["intro_prompt"] = p
        human.append(f"### 인트로\n```\n{p}\n```\n")

    if a.kind in ("all", "bg"):
        bgs = {}
        human.append("### 곡별 배경")
        for t in c.tracks:
            if a.index and t["index"] != a.index:
                continue
            p = VS.track_bg_prompt(v, t, c.config)
            bgs[t["index"]] = p
            human.append(f"**{t['index']:02d}. {t.get('title') or ''}**\n```\n{p}\n```\n")
        out["bg_prompts"] = bgs

    emit("\n".join(human), out)


def cmd_image_import(a) -> None:
    c = Ctx(a.project)
    role = a.role
    if role == "bg":
        if not a.index:
            die("--role bg 는 --index 가 필요합니다.")
        dst = c.paths.track_bg(a.index)
    elif role == "intro":
        dst = c.paths.intro_image
    elif role == "thumb-candidate":
        if not a.slot:
            die("--role thumb-candidate 는 --slot 1..4 가 필요합니다.")
        dst = c.paths.thumb_candidate(a.slot)
    else:
        die(f"알 수 없는 role: {role}")

    try:
        if a.src.startswith(("http://", "https://")):
            _download(a.src, dst)
        else:
            src = Path(a.src)
            if not src.exists():
                die(f"파일이 없습니다: {src}")
            ensure_dir(dst.parent)
            shutil.copy2(src, dst)
    except Exception as e:
        die(f"가져오기 실패: {e}")

    try:
        from PIL import Image
        with Image.open(dst) as im:
            w, h = im.size
            fmt = im.format
    except Exception as e:
        die(f"이미지를 열 수 없습니다: {e}")

    recs = read_json(c.paths.images / "images.json", {"items": []})
    recs["items"] = [r for r in recs["items"]
                     if not (r.get("role") == role and r.get("index") == a.index
                             and r.get("slot") == a.slot)]
    recs["items"].append({
        "role": role, "index": a.index, "slot": a.slot,
        "path": rel_posix(dst, c.paths.root), "sha256": sha256_file(dst),
        "width": w, "height": h, "format": fmt,
        "provider": a.provider or "", "provider_job_id": a.job_id or "",
        "credit_cost": a.credit_cost or 0, "prompt": a.prompt or "",
        "generated_at": now_iso(), "is_test": bool(a.test),
    })
    write_json(c.paths.images / "images.json", recs)
    c.ws.register(dst, kind="image", meta={"role": role, "index": a.index})
    emit(f"이미지 저장: {rel_posix(dst, c.paths.root)}  ({w}x{h} {fmt})",
         {"path": str(dst), "width": w, "height": h})


def cmd_thumbnail(a) -> None:
    c = Ctx(a.project)
    concept = (a.concept or c.config.get("thumbnail_concept") or "A").upper()
    slot = {"A": 1, "B": 2, "C": 3, "D": 4}.get(concept, 1)
    src = Path(a.background) if a.background else c.paths.thumb_candidate(slot)
    if not src.exists():
        die(f"썸네일 배경 이미지가 없습니다: {src}\n"
            f"`visual-prompts --kind thumbnail` 로 프롬프트를 얻어 4장을 생성한 뒤 "
            f"`image-import --role thumb-candidate --slot {slot} --src <url>` 하세요.")

    lang = c.config.get("thumbnail_language", "ko")
    fc = FN.resolve(lang)
    if not fc.ok:
        emit(f"⚠️ {lang} 폰트 경고: {fc.note}", None) if not OUT_JSON else None

    total = c.timing.get("total_duration") or 0
    mins = int(round(total / 60)) if total else 0
    default_sub = (f"{c.config.get('situation','')} · {len(c.tracks)}곡"
                   + (f" {mins}분" if mins else ""))
    info = VS.compose_thumbnail(
        src, c.paths.thumbnail,
        title=a.title or c.config.get("playlist_title") or "",
        subtitle=a.subtitle if a.subtitle is not None else default_sub,
        badge=a.badge or (c.config.get("genre") or "").upper(),
        preset=c.config.get("visual_preset", "black-gray-red"),
        language=lang, font=fc)
    c.ws.register(c.paths.thumbnail, kind="thumbnail")
    c.config["thumbnail_concept"] = concept
    c.save_config()
    write_json(c.paths.images / "thumbnail_info.json", info)

    human = [f"썸네일 생성: {c.paths.thumbnail}",
             f"  콘셉트 {concept} / 폰트 {info['font']} / {info['bytes']:,} bytes",
             f"  제목 {info['title_size']}px: {info.get('title_lines')}",
             f"  텍스트 이탈: {'❌ ' + info.get('overflow_reason','') if info['overflow'] else '✅ 없음'}"]
    if info.get("jpeg_path"):
        human.append(f"  2MB 초과 → JPEG 도 저장: {info['jpeg_path']}")
    emit("\n".join(human), info)


def cmd_visuals_done(a) -> None:
    c = Ctx(a.project)
    missing = []
    for t in c.tracks:
        if not c.paths.track_bg(t["index"]).exists():
            missing.append(f"배경 {t['index']:02d}")
    if not c.paths.thumbnail.exists():
        missing.append("대표 썸네일")
    if not c.paths.intro_image.exists():
        missing.append("인트로 이미지")
    if missing and not a.force:
        die(f"아직 없는 이미지: {', '.join(missing)}")
    c.ws.step_done("visuals", f"배경 {len(c.tracks)}장 + 썸네일 + 인트로")
    c.ws.advance("VISUALS_READY", "이미지 준비 완료")
    emit(f"VISUALS_READY. {'(경고: ' + ', '.join(missing) + ')' if missing else ''}",
         {"state": c.ws.state, "missing": missing})


# ---------------------------------------------------------------- 7단계: 병합·정렬
def cmd_build_audio(a) -> None:
    c = Ctx(a.project)
    c.ws.step_start("align", "음원 병합")
    usable, skipped = [], []
    for t in sorted(c.tracks, key=lambda x: x["index"]):
        rel = t.get("output_path")
        if not rel:
            skipped.append((t["index"], "음원 없음"))
            continue
        src = c.paths.root / rel
        info = A.validate(src, min_seconds=a.min_seconds)
        if not info.ok:
            skipped.append((t["index"], "; ".join(info.issues)))
            continue
        dst = c.paths.track_audio_norm(t["index"])
        if not (a.reuse and c.ws.reusable(dst)):
            A.normalize(src, dst)
            c.ws.register(dst, kind="audio_norm", meta={"track_index": t["index"]})
        usable.append((t, dst))

    if not usable:
        c.ws.step_failed("align", "쓸 수 있는 음원이 없습니다")
        die("정규화를 통과한 음원이 하나도 없습니다.")

    r = A.concat([d for _, d in usable], c.paths.master_wav, crossfade=a.crossfade)
    c.ws.register(c.paths.master_wav, kind="audio_master")

    loud = A.measure_loudness(c.paths.master_wav)
    timing = {
        "generated_at": now_iso(),
        "crossfade": r["crossfade"],
        "total_duration": r["duration"],
        "expected_duration": r["expected_duration"],
        "loudness": loud,
        "tracks": [
            {"index": t["index"], "title": t.get("title", ""),
             "subtitle": t.get("subtitle", ""),
             "start": s, "duration": d, "end": round(s + d, 3),
             "norm_path": rel_posix(p, c.paths.root),
             "source_path": t.get("output_path", "")}
            for (t, p), s, d in zip(usable, r["track_starts"], r["track_durations"])
        ],
        "skipped": [{"index": i, "reason": why} for i, why in skipped],
    }
    c.save_timing(timing)

    human = [f"병합 완료: {c.paths.master_wav.name}",
             f"  전체 {hhmmss(r['duration'], force_hours=True)} ({r['duration']:.2f}s), "
             f"크로스페이드 {r['crossfade']:g}s",
             f"  음량 {loud['input_i']:.2f} LUFS / True Peak {loud['input_tp']:.2f} dB",
             "", "| # | 시작 | 길이 | 제목 |", "|---|---|---|---|"]
    for t in timing["tracks"]:
        human.append(f"| {t['index']:02d} | {hhmmss(t['start'])} | {t['duration']:.1f}s | {t['title']} |")
    if skipped:
        human += ["", "⚠️ 제외된 곡:"] + [f"- {i:02d}: {why}" for i, why in skipped]
    emit("\n".join(human), timing)


def cmd_align(a) -> None:
    c = Ctx(a.project)
    timing = c.timing
    if not timing.get("tracks"):
        die("먼저 `build-audio` 로 음원을 병합하세요.")

    method = a.method
    if method == "auto":
        method = "whisper" if AL.whisper_available() else "estimate"
        if a.srt_dir:
            method = "srt"

    all_lines: list[AL.TimedLine] = []
    per_track: list[dict] = []
    for entry in timing["tracks"]:
        idx = entry["index"]
        t = TR.get_track(c.tracks, idx)
        try:
            body = LY.load_track_lyrics(c.paths, t)
            ref = LY.sung_lines(body)
        except LY.LyricsError:
            ref = []
        if not ref:
            per_track.append({"index": idx, "lines": 0, "method": "none"})
            continue

        used = method
        lines: list[AL.TimedLine] = []
        if method == "srt":
            srt_file = Path(a.srt_dir) / f"{idx:02d}.srt"
            if srt_file.exists():
                segs = AL.parse_srt(srt_file.read_text(encoding="utf-8-sig"))
                lines = AL.align_with_reference(segs, ref, track_start=entry["start"],
                                                track_index=idx, source="srt")
            else:
                used = "estimate"
        elif method == "whisper":
            try:
                segs = AL.whisper_segments(
                    c.paths.root / entry["norm_path"],
                    model_size=a.whisper_model,
                    language=(c.config.get("lyrics_language") or "ko").split("+")[0])
                lines = AL.align_with_reference(segs, ref, track_start=entry["start"],
                                                track_index=idx, source="whisper")
            except Exception as e:
                emit(f"⚠️ 트랙 {idx:02d} whisper 실패 → 추정 배분으로 대체: {str(e)[:200]}",
                     None) if not OUT_JSON else None
                used = "estimate"

        if not lines:
            used = "estimate"
            lines = AL.estimate_lines(ref, track_start=entry["start"],
                                      duration=entry["duration"], track_index=idx)
        all_lines.extend(lines)
        per_track.append({"index": idx, "lines": len(lines), "method": used})

    if not all_lines:
        c.ws.step_failed("align", "정렬할 가사가 없습니다")
        die("정렬할 가사가 없습니다.")

    effective = "estimate" if all(p["method"] == "estimate" for p in per_track
                                  if p["method"] != "none") else method
    report = AL.timing_report(all_lines, effective)
    write_json(c.paths.subs / "alignment.json",
               {"method": effective, "requested": a.method, "per_track": per_track,
                "report": report,
                "lines": [l.to_dict() for l in all_lines]})

    timing["report"] = report
    timing["last_subtitle_end"] = round(max(l.end for l in all_lines), 3)
    c.save_timing(timing)
    c.ws.register(c.paths.subs / "alignment.json", kind="alignment")
    emit(f"정렬 완료 — 방식 `{effective}`, {len(all_lines)}줄\n"
         f"  {report['accuracy_claim']}\n"
         f"  마지막 자막 {timing['last_subtitle_end']:.2f}s / 전체 {timing['total_duration']:.2f}s",
         {"report": report, "per_track": per_track,
          "last_subtitle_end": timing["last_subtitle_end"]})


def cmd_subtitles(a) -> None:
    c = Ctx(a.project)
    al = read_json(c.paths.subs / "alignment.json", None)
    if al is None:
        die("먼저 `align` 을 실행하세요.")
    lines = [AL.TimedLine(**d) for d in al["lines"]]
    timing = c.timing
    cards = [SB.TrackCard(t["index"], t.get("title") or f"Track {t['index']}",
                          t.get("subtitle", ""), t["start"], t["end"])
             for t in timing.get("tracks", [])]

    lang = c.config.get("subtitle_language", "ko")
    fc = FN.resolve(lang)
    intro = None
    if a.intro_seconds > 0:
        total = timing.get("total_duration", 0)
        intro = (0.6, a.intro_seconds - 0.4,
                 c.config.get("playlist_title") or "",
                 f"{len(cards)}곡 · {hhmmss(total)}")

    SB.write_srt(c.paths.srt, lines)
    SB.write_ass(c.paths.ass, lines,
                 preset=c.config.get("visual_preset", "black-gray-red"),
                 font=fc.family, font_size=a.font_size, cards=cards,
                 intro=intro)
    c.ws.register(c.paths.srt, kind="subtitle")
    c.ws.register(c.paths.ass, kind="subtitle")
    c.ws.step_done("align", f"{len(lines)}줄, 방식 {al['method']}")
    c.ws.advance("ALIGNED", f"자막 {len(lines)}줄")
    emit(f"자막 생성\n  SRT: {c.paths.srt}\n  ASS: {c.paths.ass}\n"
         f"  폰트: {fc.family} ({'OK' if fc.ok else '⚠️ ' + fc.note})\n"
         f"  줄 {len(lines)}개, 곡 카드 {len(cards)}개",
         {"srt": str(c.paths.srt), "ass": str(c.paths.ass),
          "font": fc.family, "font_ok": fc.ok, "lines": len(lines)})


# ---------------------------------------------------------------- 8단계
def cmd_metadata(a) -> None:
    c = Ctx(a.project)
    timing = c.timing
    if not timing.get("tracks"):
        die("먼저 `build-audio` 를 실행하세요.")
    order = [TR.get_track(c.tracks, e["index"]) for e in timing["tracks"]]
    for t, e in zip(order, timing["tracks"]):
        t["duration_seconds"] = e["duration"]
    starts = [e["start"] for e in timing["tracks"]]
    imgs = read_json(c.paths.images / "images.json", {"items": []})["items"]

    r = MD.write_all(c.paths, c.config, order, starts,
                     channel_name=(c.ws.data.get("channel") or {}).get("channel_name", ""),
                     total_seconds=timing.get("total_duration", 0),
                     plan_note=a.plan_note or "",
                     image_records=imgs)
    for name in r["files"]:
        c.ws.register(c.paths.meta / name, kind="metadata")
    c.ws.step_done("metadata", f"제목 {r['title_chars']}자")
    c.ws.advance("METADATA_READY", "메타데이터 생성")
    emit(f"메타데이터 생성 ({c.paths.meta})\n"
         f"  제목({r['title_chars']}/100자): {r['title']}\n"
         f"  설명 {r['description_chars']}자, 챕터 {r['chapters_count']}개, "
         f"태그 {len(r['tags'])}개 ({r['tags_chars']}/500자)\n"
         f"  rights.json 항목 {len(order) + len(imgs)}건\n"
         f"  ⚠️ 업로드는 자동으로 하지 않습니다. 파일을 확인하고 직접 올리세요.", r)


# ---------------------------------------------------------------- 9단계
def cmd_render(a) -> None:
    c = Ctx(a.project)
    timing = c.timing
    if not timing.get("tracks"):
        die("먼저 `build-audio` 를 실행하세요.")
    if not c.paths.master_wav.exists():
        die("병합 음원이 없습니다.")

    c.ws.step_start("render")
    prog = (lambda m: print(m, flush=True)) if not OUT_JSON else None
    try:
        segs = []
        for e in timing["tracks"]:
            img = c.paths.track_bg(e["index"])
            if not img.exists():
                die(f"배경 이미지가 없습니다: {img}")
            segs.append(RD.Segment(e["index"], img, e["duration"]))

        bg = c.paths.work / "background.mp4"
        if not (a.reuse and c.ws.reusable(bg)):
            RD.build_background(segs, bg, c.paths.work, reuse=a.reuse,
                                preset=a.preset, crf=a.crf, grain=a.grain,
                                progress=prog)
            c.ws.register(bg, kind="work")

        waves = c.paths.work / "waves.mp4"
        if not (a.reuse and c.ws.reusable(waves)):
            if prog:
                prog("  파형 렌더 중")
            RD.build_waveform(c.paths.master_wav, waves,
                              preset_key=c.config.get("visual_preset", "black-gray-red"))
            c.ws.register(waves, kind="work")

        audio_src = c.paths.master_wav
        RD.compose_final(bg, waves, audio_src, c.paths.ass, c.paths.final_mp4,
                         intro_image=c.paths.intro_image if c.paths.intro_image.exists() else None,
                         intro_seconds=a.intro_seconds, crf=a.final_crf,
                         preset=a.final_preset, progress=prog)
        c.ws.register(c.paths.final_mp4, kind="video")
    except Exception as e:
        c.ws.step_failed("render", str(e))
        raise

    v = RD.probe_video(c.paths.final_mp4)
    c.ws.advance("RENDERED", f"{v['duration']:.1f}s")
    emit(f"렌더 완료: {c.paths.final_mp4}\n"
         f"  {v['width']}x{v['height']} {v['fps']} {v['video_codec']}/{v['pix_fmt']} "
         f"+ {v['audio_codec']} {v['audio_sample_rate']}Hz\n"
         f"  길이 {hhmmss(v['duration'], force_hours=True)} "
         f"(영상 {v['video_duration']:.2f}s / 오디오 {v['audio_duration']:.2f}s)\n"
         f"  faststart: {'예' if v['has_faststart'] else '아니오'}\n"
         f"  크기 {c.paths.final_mp4.stat().st_size/1024/1024:.1f} MB", v)


def cmd_qa(a) -> None:
    c = Ctx(a.project)
    thumb_info = read_json(c.paths.images / "thumbnail_info.json", None)
    r = QA.run_qa(c.paths, config=c.config, tracks=c.tracks,
                  timing=c.timing, thumbnail_info=thumb_info, workspace=c.ws)
    md = QA.report_markdown(r)
    write_text(c.paths.qa_report_md, md)
    write_json(c.paths.qa_report_json, r)
    c.ws.register(c.paths.qa_report_md, kind="qa")
    c.ws.register(c.paths.qa_report_json, kind="qa")
    if r["verdict"] == QA.FAIL:
        c.ws.step_failed("render", f"QA 실패 {r['counts']['fail']}건")
    else:
        c.ws.step_done("render", f"QA {r['verdict']}")
        c.ws.advance("VERIFIED", f"QA {r['verdict']}")
    emit(md, r)
    if r["verdict"] == QA.FAIL:
        raise SystemExit(1)


# ---------------------------------------------------------------- 상태 / 정리
def cmd_status(a) -> None:
    c = Ctx(a.project)
    lines = [f"# {c.config.get('playlist_title') or c.paths.root.name}", "",
             f"- 경로: `{c.paths.root}`",
             f"- 상태: **{c.ws.state}**",
             f"- 갱신: {c.ws.data.get('updated_at')}", "",
             "| 단계 | 이름 | 상태 | 비고 |", "|---|---|---|---|"]
    icon = {"done": "✅", "running": "🔄", "failed": "❌", "pending": "⬜"}
    for s in STEPS:
        st = c.ws.data["steps"].get(s["key"], {})
        note = st.get("error") or st.get("note") or ""
        lines.append(f"| {s['n']} | {s['title']} | {icon.get(st.get('status','pending'),'⬜')} "
                     f"{st.get('status','pending')} | {str(note)[:80]} |")
    nxt = c.ws.first_incomplete_step()
    lines += ["", f"다음 할 일: **{nxt['n']}. {nxt['title']}**" if nxt else "", ""]
    if c.tracks:
        lines += [TR.summary_table(c.tracks), ""]
    v = c.ws.verify_all()
    lines.append(f"산출물 {len(v['ok'])}/{v['total']} 정상"
                 + (f" — 손상 {[b['path'] for b in v['broken']]}" if v["broken"] else ""))
    led = c.ledger
    lines.append(f"차감 크레딧 누적: {led.total_credits_spent()} cr")
    emit("\n".join(lines),
         {"state": c.ws.state, "steps": c.ws.data["steps"], "next": nxt,
          "artifacts": v, "credits_spent": led.total_credits_spent(),
          "tracks": c.tracks, "config": c.config})


def cmd_verify(a) -> None:
    c = Ctx(a.project)
    v = c.ws.verify_all()
    lines = [f"등록 산출물 {v['total']}건 — 정상 {len(v['ok'])} / 손상 {len(v['broken'])}"]
    if v["broken"]:
        lines += ["", "손상/누락:"] + [f"- {b['path']} ({b['reason']})" for b in v["broken"]]
        if a.repair:
            for b in v["broken"]:
                c.ws.drop_artifact(c.paths.root / b["path"])
            lines.append("\n손상 항목을 레지스트리에서 제거했습니다. 해당 단계를 "
                         "다시 실행하면 그 파일만 새로 만듭니다.")
    emit("\n".join(lines), v)
    if v["broken"] and not a.repair:
        raise SystemExit(1)


def cmd_resume(a) -> None:
    c = Ctx(a.project)
    nxt = c.ws.first_incomplete_step()
    v = c.ws.verify_all()
    hints = {
        "channel": "playlist-new",
        "plan": f"config-status --project {a.project} → config-set → plan",
        "lyrics": f"track-set / track-lyrics → lyrics-validate → lyrics-collect",
        "pilot": f"cost --balance <잔액> → submit-payload --index 1 --claim → "
                 f"(MCP 생성) → track-import --index 1 → pilot-status → pilot-approve",
        "batch": f"cost → submit-payload --index N --claim → track-import --index N "
                 f"→ batch-status",
        "visuals": f"visual-prompts → image-import → thumbnail → visuals-done",
        "align": f"build-audio → align → subtitles",
        "metadata": "metadata",
        "render": "render → qa",
    }
    lines = [f"현재 상태: **{c.ws.state}**"]
    if v["broken"]:
        lines.append(f"⚠️ 손상된 산출물 {len(v['broken'])}건: "
                     f"{[b['path'] for b in v['broken']]}")
        lines.append(f"  `verify --project {a.project} --repair` 후 해당 단계를 다시 실행하세요.")
    if nxt is None:
        lines.append("모든 단계 완료. `qa` 로 최종 검증만 다시 하면 됩니다.")
    else:
        failed = [s for s in STEPS if c.ws.step_status(s["key"]) == "failed"]
        if failed:
            f = failed[0]
            lines.append(f"❌ 실패한 단계: {f['n']}. {f['title']} — "
                         f"{c.ws.data['steps'][f['key']].get('error','')[:200]}")
        lines.append(f"이어서 할 단계: **{nxt['n']}. {nxt['title']}**")
        lines.append(f"실행: `{hints.get(nxt['key'], nxt['key'])}`")
    emit("\n".join(lines), {"state": c.ws.state, "next": nxt, "artifacts": v})


def cmd_list(a) -> None:
    rows = ["| 프로젝트 | 상태 | 곡 | 갱신 |", "|---|---|---|---|"]
    data = []
    for p in iter_projects():
        ws = read_json(p.workspace, {})
        tr = TR.load_tracks(p.tracks)
        key = f"{p.root.parent.parent.name}/{p.root.name}"
        rows.append(f"| `{key}` | {ws.get('state','?')} | {len(tr)} | {ws.get('updated_at','')} |")
        data.append({"project": key, "path": str(p.root), "state": ws.get("state"),
                     "tracks": len(tr), "updated_at": ws.get("updated_at")})
    emit("\n".join(rows) if data else "프로젝트가 없습니다.", {"projects": data})


def cmd_clean(a) -> None:
    c = Ctx(a.project)
    removed = []
    if a.work and c.paths.work.exists():
        n = sum(1 for _ in c.paths.work.rglob("*") if _.is_file())
        for f in sorted(c.paths.work.rglob("*"), reverse=True):
            c.ws.drop_artifact(f)
        shutil.rmtree(c.paths.work)
        ensure_dir(c.paths.work)
        removed.append(f"work/ ({n}개 파일)")
    if a.norm and c.paths.audio_norm.exists():
        n = len(list(c.paths.audio_norm.glob("*.wav")))
        for f in c.paths.audio_norm.glob("*.wav"):
            c.ws.drop_artifact(f)
            f.unlink()
        removed.append(f"audio/norm/ ({n}개 파일)")
    emit("정리: " + (", ".join(removed) if removed else "(대상 없음)\n"
         "  --work 중간 렌더 파일, --norm 정규화 음원"), {"removed": removed})


# ---------------------------------------------------------------- 셀프테스트
def cmd_serve(a) -> None:
    """웹 대시보드를 띄운다. 핸드폰·다른 PC 브라우저에서 접속할 수 있다."""
    from .webapp import serve
    serve(host=a.host, port=a.port,
          token=("" if a.no_token else a.token),
          open_browser=a.open)


def cmd_selftest(a) -> None:
    """합성 음원·이미지로 파이프라인 전체를 검증한다. 크레딧을 쓰지 않는다."""
    from .selftest import run_selftest
    r = run_selftest(name=a.name, tracks=a.tracks, seconds=a.seconds,
                     keep=a.keep, verbose=not OUT_JSON)
    emit(r["report"], r)
    if not r["ok"]:
        raise SystemExit(1)


# ================================================================ 파서
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m playlist_studio",
        description="AI 플레이리스트 자동 제작 파이프라인")
    p.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    sub = p.add_subparsers(dest="cmd", required=True)

    def proj(sp):
        sp.add_argument("--project", required=True,
                        help="채널/플레이리스트 slug 또는 폴더 경로")
        return sp

    sub.add_parser("doctor", help="환경 검사").set_defaults(fn=cmd_doctor)

    s = sub.add_parser("channel-new", help="새 채널 만들기")
    s.add_argument("--name", required=True)
    s.add_argument("--genre", default="")
    s.add_argument("--concept", default="")
    s.set_defaults(fn=cmd_channel_new)

    sub.add_parser("channel-list", help="채널 목록").set_defaults(fn=cmd_channel_list)
    sub.add_parser("list", help="플레이리스트 목록").set_defaults(fn=cmd_list)

    s = sub.add_parser("playlist-new", help="새 플레이리스트 만들기")
    s.add_argument("--channel", required=True)
    s.add_argument("--title", required=True)
    s.set_defaults(fn=cmd_playlist_new)

    s = proj(sub.add_parser("config-status", help="다음에 물을 질문"))
    s.add_argument("--limit", type=int, default=2)
    s.set_defaults(fn=cmd_config_status)

    s = proj(sub.add_parser("config-set", help="설정 저장 (key=value ...)"))
    s.add_argument("kv", nargs="+")
    s.set_defaults(fn=cmd_config_set)

    proj(sub.add_parser("config-show")).set_defaults(fn=cmd_config_show)

    s = proj(sub.add_parser("plan", help="sonic_dna/visual_dna/tracks.json 생성"))
    s.add_argument("--force", action="store_true")
    s.add_argument("--reset", action="store_true", help="기존 트랙 정보를 버린다")
    s.set_defaults(fn=cmd_plan)

    proj(sub.add_parser("dna-show")).set_defaults(fn=cmd_dna_show)
    s = proj(sub.add_parser("dna-set", help="sonic_dna 속성 변경 (재생성 시 크레딧 추가)"))
    s.add_argument("kv", nargs="+")
    s.set_defaults(fn=cmd_dna_set)

    s = proj(sub.add_parser("track-set", help="트랙 제목/부제/주제 등"))
    s.add_argument("--index", type=int, required=True)
    s.add_argument("kv", nargs="+")
    s.set_defaults(fn=cmd_track_set)

    s = proj(sub.add_parser("track-lyrics", help="트랙 가사 저장"))
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--file")
    s.add_argument("--text")
    s.set_defaults(fn=cmd_track_lyrics)

    proj(sub.add_parser("lyrics-validate")).set_defaults(fn=cmd_lyrics_validate)
    s = proj(sub.add_parser("lyrics-collect", help="lyrics_all.md 작성 + LYRICS_READY"))
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_lyrics_collect)

    s = proj(sub.add_parser("cost", help="크레딧 견적"))
    s.add_argument("--model")
    s.add_argument("--balance", type=int, help="MCP abocado_get_credits 의 실제 잔액")
    s.add_argument("--unit-credits", type=int, help="MCP 로 확인한 곡당 단가")
    s.add_argument("--ignore-done", action="store_true")
    s.set_defaults(fn=cmd_cost)

    s = proj(sub.add_parser("submit-payload", help="MCP 제출 인자 생성 (+중복 차단)"))
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--model")
    s.add_argument("--unit-credits", type=int)
    s.add_argument("--claim", action="store_true", help="원장에 잠금 (실제 제출 직전)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_submit_payload)

    s = proj(sub.add_parser("ledger-release", help="실패한 생성 건 해제"))
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_ledger_release)

    proj(sub.add_parser("ledger-show")).set_defaults(fn=cmd_ledger_show)

    s = proj(sub.add_parser("track-import", help="생성 결과(URL/파일)를 가져온다"))
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--src", required=True)
    s.add_argument("--job-id")
    s.add_argument("--credit-cost", type=int)
    s.add_argument("--ext")
    s.add_argument("--min-seconds", type=float, default=20.0)
    s.add_argument("--test", action="store_true", help="테스트 자산으로 표시")
    s.set_defaults(fn=cmd_track_import)

    proj(sub.add_parser("pilot-status")).set_defaults(fn=cmd_pilot_status)
    s = proj(sub.add_parser("pilot-approve"))
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_pilot_approve)
    s = proj(sub.add_parser("pilot-reject"))
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_pilot_reject)

    proj(sub.add_parser("batch-status")).set_defaults(fn=cmd_batch_status)

    s = proj(sub.add_parser("visual-prompts", help="이미지 프롬프트 생성"))
    s.add_argument("--kind", choices=("all", "thumbnail", "bg", "intro"), default="all")
    s.add_argument("--index", type=int)
    s.set_defaults(fn=cmd_visual_prompts)

    s = proj(sub.add_parser("image-import"))
    s.add_argument("--role", required=True,
                   choices=("bg", "intro", "thumb-candidate"))
    s.add_argument("--src", required=True)
    s.add_argument("--index", type=int)
    s.add_argument("--slot", type=int)
    s.add_argument("--provider", default="")
    s.add_argument("--job-id", default="")
    s.add_argument("--credit-cost", type=int, default=0)
    s.add_argument("--prompt", default="")
    s.add_argument("--test", action="store_true")
    s.set_defaults(fn=cmd_image_import)

    s = proj(sub.add_parser("thumbnail", help="대표 썸네일 합성 (1280x720)"))
    s.add_argument("--concept", choices=("A", "B", "C", "D"))
    s.add_argument("--background")
    s.add_argument("--title")
    s.add_argument("--subtitle")
    s.add_argument("--badge")
    s.set_defaults(fn=cmd_thumbnail)

    s = proj(sub.add_parser("visuals-done"))
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_visuals_done)

    s = proj(sub.add_parser("build-audio", help="정규화 + 병합"))
    s.add_argument("--crossfade", type=float, default=1.5)
    s.add_argument("--min-seconds", type=float, default=20.0)
    s.add_argument("--reuse", action="store_true", default=True)
    s.add_argument("--no-reuse", dest="reuse", action="store_false")
    s.set_defaults(fn=cmd_build_audio)

    s = proj(sub.add_parser("align", help="가사 타이밍 정렬"))
    s.add_argument("--method", choices=("auto", "whisper", "srt", "estimate"),
                   default="auto")
    s.add_argument("--srt-dir", help="곡별 SRT 폴더 (01.srt, 02.srt ...)")
    s.add_argument("--whisper-model", default="small")
    s.set_defaults(fn=cmd_align)

    s = proj(sub.add_parser("subtitles", help="SRT + ASS 생성"))
    s.add_argument("--font-size", type=int, default=58)
    s.add_argument("--intro-seconds", type=float, default=6.0)
    s.set_defaults(fn=cmd_subtitles)

    s = proj(sub.add_parser("metadata"))
    s.add_argument("--plan-note", default="", help="생성 당시 플랜 (rights.json 기록)")
    s.set_defaults(fn=cmd_metadata)

    s = proj(sub.add_parser("render", help="최종 MP4"))
    s.add_argument("--intro-seconds", type=float, default=6.0)
    s.add_argument("--preset", default="veryfast", help="세그먼트 인코딩 프리셋")
    s.add_argument("--crf", type=int, default=20)
    s.add_argument("--final-preset", default="medium")
    s.add_argument("--final-crf", type=int, default=19)
    s.add_argument("--grain", type=int, default=7)
    s.add_argument("--reuse", action="store_true", default=True)
    s.add_argument("--no-reuse", dest="reuse", action="store_false")
    s.set_defaults(fn=cmd_render)

    proj(sub.add_parser("qa")).set_defaults(fn=cmd_qa)
    proj(sub.add_parser("status")).set_defaults(fn=cmd_status)
    proj(sub.add_parser("resume")).set_defaults(fn=cmd_resume)

    s = proj(sub.add_parser("verify", help="산출물 해시 검증"))
    s.add_argument("--repair", action="store_true")
    s.set_defaults(fn=cmd_verify)

    s = proj(sub.add_parser("clean"))
    s.add_argument("--work", action="store_true")
    s.add_argument("--norm", action="store_true")
    s.set_defaults(fn=cmd_clean)

    s = sub.add_parser("serve", help="웹 대시보드 실행 (핸드폰에서 접속 가능)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="0.0.0.0",
                   help="0.0.0.0 이면 같은 Wi-Fi 의 다른 기기에서도 접속 가능")
    s.add_argument("--token", default=None,
                   help="접속 토큰 직접 지정 (기본: 실행할 때마다 새로 생성)")
    s.add_argument("--no-token", action="store_true",
                   help="토큰 없이 연다. 신뢰할 수 있는 망에서만 쓰세요")
    s.add_argument("--open", action="store_true", help="브라우저를 자동으로 연다")
    s.set_defaults(fn=cmd_serve)

    s = sub.add_parser("selftest", help="합성 자산으로 전체 파이프라인 검증 (무료)")
    s.add_argument("--name", default="selftest")
    s.add_argument("--tracks", type=int, default=3)
    s.add_argument("--seconds", type=float, default=30.0)
    s.add_argument("--keep", action="store_true", help="끝나도 폴더를 지우지 않는다")
    s.set_defaults(fn=cmd_selftest)

    return p


def main(argv: list[str] | None = None) -> int:
    global OUT_JSON
    parser = build_parser()
    a = parser.parse_args(argv)
    OUT_JSON = bool(a.json)
    try:
        a.fn(a)
    except SystemExit:
        raise
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as e:
        die(f"{type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
