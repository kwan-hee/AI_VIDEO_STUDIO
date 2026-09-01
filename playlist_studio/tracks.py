"""tracks.json - 트랙 계획과 모델별 프롬프트 조립.

공통 sonic_dna 위에 트랙별로 BPM / 감정 / 인트로 악기 / 서사 / 에너지 /
구조 변형만 얹는다. 이 6개 축만 흔들어도 같은 앨범처럼 들리면서 곡이
서로 겹치지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cost import model_spec
from .dna import (INTRO_LEADS, MOOD_ARCS, STRUCTURE_VARIANTS, check_no_artist,
                  dna_paragraph)
from .util import now_iso, read_json, slugify, write_json

TRACK_FIELDS = (
    "index", "title", "subtitle", "bpm", "mood", "intro_lead", "lyrical_theme",
    "target_duration", "music_prompt", "lyrics_path", "provider",
    "provider_job_id", "credit_cost", "output_path", "sha256", "status",
)

STATUSES = ("planned", "lyrics_ready", "submitted", "downloaded",
            "verified", "failed", "rejected")


# ---------------------------------------------------------------- 계획 생성
def _spread(lo: int, hi: int, n: int, arc: str) -> list[int]:
    """BPM 을 정서 곡선에 맞게 분배. 같은 값이 연속되지 않게 살짝 흔든다."""
    lo, hi = int(lo), int(hi)
    if hi < lo:
        lo, hi = hi, lo
    if n == 1:
        return [(lo + hi) // 2]
    span = hi - lo
    out: list[int] = []
    for i in range(n):
        t = i / (n - 1)
        if arc in ("warm-to-calm", "night-deepening"):
            t = 1.0 - t
        elif arc == "flat-calm":
            t = 0.35 + 0.3 * ((i % 3) / 2.0)
        base = lo + span * t
        jitter = (-2, 1, -1, 2, 0)[i % 5]
        out.append(int(round(max(lo, min(hi, base + jitter)))))
    return out


def _mood_sequence(arc: str, n: int) -> list[str]:
    seq = MOOD_ARCS.get(arc) or MOOD_ARCS["calm-to-warm"]
    if n <= len(seq):
        # 곡 수가 적으면 앞뒤 끝점을 유지하며 균등 추출
        idx = [round(i * (len(seq) - 1) / max(1, n - 1)) for i in range(n)]
        return [seq[i] for i in idx]
    return [seq[round(i * (len(seq) - 1) / (n - 1))] for i in range(n)]


def _energy_sequence(arc: str, n: int) -> list[int]:
    if arc in ("warm-to-calm", "night-deepening"):
        return [max(1, round(6 - 4 * i / max(1, n - 1))) for i in range(n)]
    if arc == "flat-calm":
        return [2 + (i % 2) for i in range(n)]
    return [max(1, round(2 + 4 * i / max(1, n - 1))) for i in range(n)]


def build_plan(config: dict, sonic_dna: dict) -> list[dict]:
    n = int(config.get("track_count", 8))
    if n < 1:
        raise ValueError("곡 수는 1 이상이어야 합니다.")
    genre = config.get("genre", "lofi")
    arc = config.get("mood_arc", "calm-to-warm")
    bpms = _spread(config.get("bpm_min", 70), config.get("bpm_max", 90), n, arc)
    moods = _mood_sequence(arc, n)
    energies = _energy_sequence(arc, n)
    leads = INTRO_LEADS.get(genre) or INTRO_LEADS["lofi"]
    target = int(config.get("track_seconds", 180))

    tracks: list[dict] = []
    for i in range(n):
        idx = i + 1
        tracks.append({
            "index": idx,
            "title": "",                       # Claude 가 채운다
            "subtitle": "",
            "bpm": bpms[i],
            "mood": moods[i],
            "intro_lead": leads[i % len(leads)],
            "lyrical_theme": "",               # Claude 가 채운다
            "energy_level": energies[i],
            "structure": STRUCTURE_VARIANTS[i % len(STRUCTURE_VARIANTS)],
            "target_duration": target,
            "music_prompt": "",
            "lyrics_path": "",
            "lyrics_sha256": "",
            "provider": "",
            "provider_job_id": "",
            "prompt_fingerprint": "",
            "credit_cost": 0,
            "output_path": "",
            "sha256": "",
            "duration_seconds": None,
            "status": "planned",
            "updated_at": now_iso(),
        })
    return tracks


# ---------------------------------------------------------------- 프롬프트 조립
def _variation_sentence(track: dict) -> str:
    bits = [
        f"Tempo {track['bpm']} BPM.",
        f"Mood: {track['mood']}.",
        f"Opens with {track['intro_lead']}.",
        f"Energy level {track['energy_level']} out of 10.",
        f"Form: {track['structure']}.",
    ]
    if track.get("lyrical_theme"):
        bits.append(f"Narrative: {track['lyrical_theme']}.")
    return " ".join(bits)


def _compact_dna(dna: dict, budget: int) -> str:
    """짧은 프롬프트만 받는 모델(Popcorn 1.0, 300자)용 압축 DNA."""
    core = f"{dna['subgenre'] or dna['genre']}, {dna['instrumentation'].split(',')[0].strip()}"
    core += f", {dna['drum_pattern'].split(',')[0].strip()}"
    if dna.get("vocal_gender") != "none":
        core += f", {dna['vocal_gender']} vocal"
    else:
        core += ", instrumental"
    core += ", no real-artist imitation"
    return core[:budget]


def build_music_prompt(track: dict, dna: dict, model: str, lyrics: str = "") -> dict:
    """모델 규약에 맞춘 제출 페이로드를 만든다.

    반환: {"model", "prompt", "options", "title", "lyrics_for_fingerprint"}
    실제 제출은 스킬이 MCP `abocado_generate_audio` 로 한다. 이 함수는
    글자수 제한과 필드 배치만 책임진다.
    """
    spec = model_spec(model)
    pmax, pmin = int(spec["prompt_max"]), int(spec["prompt_min"])
    variation = _variation_sentence(track)
    instrumental = dna.get("vocal_gender") == "none"

    options: dict[str, Any] = {}
    lyrics = (lyrics or "").strip()

    if spec["lyrics_mode"] == "prompt_merged":
        # Lyria 계열: 가사를 prompt 안에 병합, 합계 pmax
        head = f"{dna_paragraph(dna)} {variation}"
        if instrumental or not lyrics:
            prompt = head[:pmax]
        else:
            reserve = min(len(lyrics) + 10, max(300, pmax // 2))
            head = head[: max(pmin, pmax - reserve - 12)]
            prompt = f"{head}\n\nLyrics:\n{lyrics}"[:pmax]
        if instrumental:
            options["negative_prompt"] = "vocals, singing, vocal chops, spoken word"
    else:
        # Popcorn 계열: 가사는 별도 필드
        if pmax <= 400:
            prompt = f"{_compact_dna(dna, pmax - len(variation) - 2)} {variation}"[:pmax]
        else:
            prompt = f"{dna_paragraph(dna)} {variation}"[:pmax]
        if instrumental:
            options["is_instrumental"] = True
        else:
            if not lyrics:
                raise ValueError(
                    f"{spec['display']} 는 가사가 필요합니다. 3단계(가사 작성)를 먼저 끝내세요."
                )
            field_name = spec["lyrics_field"]
            lmax = int(spec["lyrics_max"])
            if len(lyrics) > lmax:
                raise ValueError(
                    f"가사가 {len(lyrics)}자로 {spec['display']} 한도 {lmax}자를 넘습니다. "
                    f"트랙 {track['index']} 가사를 줄이세요."
                )
            options[field_name] = lyrics

    if len(prompt) < pmin:
        prompt = (prompt + " " + dna_paragraph(dna))[:pmax]
    check_no_artist(prompt)
    check_no_artist(lyrics)

    return {
        "model": model,
        "prompt": prompt,
        "options": options,
        "title": track.get("title") or f"Track {track['index']:02d}",
        "lyrics_for_fingerprint": lyrics,
        "prompt_chars": len(prompt),
        "prompt_limit": pmax,
    }


# ---------------------------------------------------------------- 저장/조회
def load_tracks(path: Path) -> list[dict]:
    data = read_json(path, None)
    if data is None:
        return []
    if isinstance(data, dict):
        return data.get("tracks", [])
    return data


def save_tracks(path: Path, tracks: list[dict]) -> Path:
    return write_json(path, {"schema_version": 1, "updated_at": now_iso(),
                             "count": len(tracks), "tracks": tracks})


def get_track(tracks: list[dict], index: int) -> dict:
    for t in tracks:
        if int(t["index"]) == int(index):
            return t
    raise KeyError(f"트랙 {index} 이(가) 없습니다. (1..{len(tracks)})")


def track_slug(track: dict) -> str:
    return slugify(track.get("title") or f"track-{track['index']:02d}",
                   fallback=f"track-{track['index']:02d}", max_len=32)


def summary_table(tracks: list[dict]) -> str:
    rows = ["| # | 제목 | BPM | 감정 | 인트로 | 상태 | 길이 |", "|---|---|---|---|---|---|---|"]
    for t in tracks:
        dur = t.get("duration_seconds")
        rows.append(
            f"| {t['index']:02d} | {t.get('title') or '—'} | {t['bpm']} | {t['mood']} | "
            f"{t['intro_lead'][:24]} | {t['status']} | "
            f"{('%.1fs' % dur) if dur else '—'} |"
        )
    return "\n".join(rows)
