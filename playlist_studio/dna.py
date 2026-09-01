"""sonic_dna / visual_dna - 앨범 통일감을 만드는 공통 설계도.

모든 곡은 하나의 sonic_dna 를 공유하고, 트랙별로는 정해진 축(BPM/감정/
인트로 악기/서사/에너지/구조 변형)만 바꾼다. 그래야 같은 앨범처럼 들리면서
멜로디와 가사가 반복되지 않는다.

실존 아티스트·밴드 이름은 어떤 필드에도 들어가지 않는다. 프롬프트를 만들 때
금지어 검사를 통과해야만 반환한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

from .util import now_iso

# ---------------------------------------------------------------- 장르 프리셋
GENRE_PRESETS: dict[str, dict[str, Any]] = {
    "lofi": {
        "instrumentation": "muted rhodes electric piano, nylon-string guitar, soft upright bass, brushed drum kit, tape hiss, distant vinyl crackle",
        "drum_pattern": "laid-back boom-bap groove, snare slightly behind the grid, closed hats in soft eighths, no heavy fills",
        "bass_character": "round warm upright-style bass, short sustain, sits low in the mix, walks only on chord changes",
        "harmony_mood": "major-seventh and minor-ninth voicings, gentle ii-V motion, unresolved endings that loop back",
        "mix_texture": "low-pass filtered highs, wide but soft stereo field, gentle tape saturation, no harsh transients",
        "energy_range": "2 to 4 on a 10 scale",
        "forbidden": "EDM drops, sidechain pumping, aggressive trap hi-hat rolls, loud brass stabs, heavy distortion",
    },
    "jazz": {
        "instrumentation": "acoustic piano trio, brushed drums, double bass, occasional muted trumpet, room reverb",
        "drum_pattern": "swung ride pattern, brush sweeps on snare, sparse kick, tasteful rim accents",
        "bass_character": "walking double bass, woody attack, natural decay, drives the harmonic motion",
        "harmony_mood": "extended dominant voicings, tritone substitutions, warm minor turnarounds",
        "mix_texture": "natural room ambience, minimal compression, instruments placed as if on a small stage",
        "energy_range": "3 to 5 on a 10 scale",
        "forbidden": "quantized electronic drums, synth leads, EDM structure, loudness-war mastering",
    },
    "citypop": {
        "instrumentation": "chorused electric piano, clean funk guitar with sixteenth strumming, slap-capable electric bass, gated snare, analog pad, bright saxophone accents",
        "drum_pattern": "tight sixteenth-note hi-hat pocket, backbeat snare, syncopated kick",
        "bass_character": "melodic electric bass with rounded pick attack, active but never busy",
        "harmony_mood": "major-seventh and add9 chords, bright modulations, nostalgic uplift",
        "mix_texture": "glossy eighties-style mixing, wide chorus, plate reverb on vocals, punchy but not loud",
        "energy_range": "5 to 7 on a 10 scale",
        "forbidden": "lofi tape hiss, trap drums, modern EDM risers, heavy autotune",
    },
    "ballad": {
        "instrumentation": "grand piano, sustained string section, soft acoustic guitar, subtle synth pad, restrained drum kit entering late",
        "drum_pattern": "slow half-time backbeat, brushed or soft-mallet feel, entering only after the first chorus",
        "bass_character": "long sustained fingered bass, follows the root, no fills",
        "harmony_mood": "diatonic progressions with borrowed minor-four chords, a lifted final chorus",
        "mix_texture": "vocal forward, wide strings, generous hall reverb, wide dynamic range",
        "energy_range": "2 to 6 on a 10 scale, rising across the song",
        "forbidden": "dance beats, aggressive synths, heavy percussion loops",
    },
    "ambient": {
        "instrumentation": "evolving synth pads, bowed glass textures, soft field recordings, sparse piano notes, long reverb tails",
        "drum_pattern": "no drum kit; only occasional low pulse or heartbeat-like sub hit",
        "bass_character": "sub-bass drone that moves slowly, felt more than heard",
        "harmony_mood": "suspended and modal harmony, no strong cadence, slow drift between two centers",
        "mix_texture": "very wide stereo, heavy reverb and delay, gentle high-frequency roll-off",
        "energy_range": "1 to 3 on a 10 scale",
        "forbidden": "drum loops, vocal chops, rhythmic gating, bright cymbals",
    },
    "acoustic": {
        "instrumentation": "steel-string acoustic guitar, light percussion or cajon, upright bass, occasional glockenspiel",
        "drum_pattern": "cajon and shaker groove, soft kick on one and three, no cymbals",
        "bass_character": "simple root-fifth upright bass, warm and unobtrusive",
        "harmony_mood": "open-position folk voicings, capo-bright chords, honest and simple",
        "mix_texture": "close-mic'd, dry and intimate, minimal processing, natural breath and string noise kept",
        "energy_range": "3 to 5 on a 10 scale",
        "forbidden": "synthesizers, electronic drums, heavy reverb, pitch correction artifacts",
    },
    "rnb": {
        "instrumentation": "electric piano, muted guitar skanks, deep sub bass, layered vocal harmonies, finger snaps",
        "drum_pattern": "swung sixteenth groove, crisp rimshot backbeat, ghost notes between hits",
        "bass_character": "deep rounded sub bass with slides, locks tightly with the kick",
        "harmony_mood": "lush ninth and eleventh voicings, chromatic passing chords, smooth resolutions",
        "mix_texture": "vocal-centric, warm low end, silky highs, tasteful stereo doubling",
        "energy_range": "3 to 6 on a 10 scale",
        "forbidden": "rock guitars, EDM drops, aggressive distortion",
    },
    "synthwave": {
        "instrumentation": "analog saw-lead synth, gated pad stacks, electronic drum machine, arpeggiated bass sequence",
        "drum_pattern": "steady four-on-the-floor with gated reverb snare on the backbeat",
        "bass_character": "sixteenth-note synth bass arpeggio, driving and hypnotic",
        "harmony_mood": "minor key with major lifts, sustained pads, nostalgic and cinematic",
        "mix_texture": "wide chorus, tape delay, bright but rounded highs, retro analog warmth",
        "energy_range": "5 to 7 on a 10 scale",
        "forbidden": "acoustic drum kit, folk instruments, trap hi-hats",
    },
    "classical-crossover": {
        "instrumentation": "solo piano, chamber string quartet, soft woodwind doubling, light cinematic percussion",
        "drum_pattern": "no standard kit; timpani swells and soft mallet accents only",
        "bass_character": "cello and double bass section carrying the low line",
        "harmony_mood": "romantic-era voice leading, suspensions resolving late, wide dynamic arcs",
        "mix_texture": "concert-hall ambience, natural dynamics, no compression pumping",
        "energy_range": "2 to 7 on a 10 scale",
        "forbidden": "drum machines, synth bass, electronic effects",
    },
    "worship": {
        "instrumentation": "warm piano, sustained pad, ambient electric guitar with long delay, soft kick and floor tom",
        "drum_pattern": "simple four-count with floor-tom pulses, building in the final section",
        "bass_character": "sustained root notes, supportive, never syncopated",
        "harmony_mood": "bright diatonic progressions, suspended chords resolving to major",
        "mix_texture": "spacious reverb, wide guitars, vocal centered and clear",
        "energy_range": "3 to 7 on a 10 scale, rising toward the end",
        "forbidden": "aggressive percussion, distorted leads, dance rhythms",
    },
}

VOCAL_PRESETS = {
    "ko": {
        "vocal_gender": "female",
        "vocal_range": "warm mezzo, mostly in the lower-middle register",
        "vocal_delivery": "breathy and close-mic'd, conversational phrasing, no belting, Korean lyrics",
    },
    "en": {
        "vocal_gender": "female",
        "vocal_range": "soft alto",
        "vocal_delivery": "intimate and airy, laid-back phrasing behind the beat, English lyrics",
    },
    "ja": {
        "vocal_gender": "female",
        "vocal_range": "light soprano, gentle head voice",
        "vocal_delivery": "clear and soft, precise consonants, Japanese lyrics",
    },
    "ko+en": {
        "vocal_gender": "female",
        "vocal_range": "warm mezzo",
        "vocal_delivery": "Korean verses with short English hooks, breathy and intimate",
    },
}

# 정서 곡선 - 곡 순서에 따른 (감정, 에너지) 배분
MOOD_ARCS: dict[str, list[str]] = {
    "calm-to-warm": ["still", "quiet", "gentle", "warm", "hopeful", "glowing"],
    "warm-to-calm": ["glowing", "warm", "gentle", "soft", "quiet", "still"],
    "flat-calm": ["still", "quiet", "still", "gentle", "quiet", "still"],
    "melancholy-to-hope": ["heavy", "wistful", "aching", "steadying", "lifting", "hopeful"],
    "night-deepening": ["dusk", "streetlight", "late", "quiet-hours", "deep-night", "before-dawn"],
}

INTRO_LEADS: dict[str, list[str]] = {
    "lofi": ["muted rhodes chord", "nylon guitar arpeggio", "vinyl crackle then piano",
             "soft brushed hats alone", "filtered pad swell", "single upright bass note",
             "music-box like bell", "rain field recording then keys"],
    "jazz": ["solo piano rubato phrase", "brushed snare alone", "walking bass intro",
             "muted trumpet long tone", "ride cymbal texture", "piano block chords",
             "bass and drums trading", "unaccompanied melody line"],
    "citypop": ["chorused electric piano stab", "clean funk guitar riff", "slap bass fill",
                "gated snare pickup", "bright pad swell", "saxophone lick",
                "syncopated clav figure", "filtered drum loop opening"],
    "ballad": ["single piano note", "string swell", "acoustic guitar fingerpicking",
               "soft pad with breath", "piano octaves", "cello line",
               "distant choir texture", "reversed piano into downbeat"],
    "ambient": ["long pad fade-in", "bowed glass tone", "field recording of wind",
                "sparse piano note with long tail", "sub drone rising", "granular texture",
                "reversed cymbal wash", "distant bell"],
    "acoustic": ["fingerpicked guitar figure", "shaker alone", "glockenspiel motif",
                 "strummed open chord", "upright bass pulse", "cajon groove",
                 "harmonics on guitar", "hummed melody then guitar"],
    "rnb": ["electric piano chord", "finger snaps alone", "sub bass slide",
            "layered vocal hum", "muted guitar skank", "filtered drum intro",
            "rimshot groove", "reversed vocal texture"],
    "synthwave": ["arpeggiated bass sequence", "gated pad hit", "saw lead sweep",
                  "drum machine fill", "tape-delayed stab", "filtered noise riser",
                  "octave bass pulse", "long pad fade with delay"],
    "classical-crossover": ["solo piano phrase", "string quartet swell", "woodwind line",
                            "cello melody", "harp-like piano figure", "timpani roll",
                            "unaccompanied violin", "soft piano ostinato"],
    "worship": ["ambient guitar swell", "piano single chord", "pad fade-in",
                "floor tom pulse", "delayed guitar motif", "soft organ tone",
                "piano octaves", "vocal hum then piano"],
}

STRUCTURE_VARIANTS = [
    "verse-chorus-verse-chorus-outro",
    "intro-verse-prechorus-chorus-bridge-chorus",
    "verse-chorus-verse-chorus-doublechorus",
    "instrumental-intro-verse-chorus-interlude-chorus",
    "verse-verse-chorus-bridge-chorus",
    "chorus-first, then verse-chorus-outro",
]

# 실존 인물 모방 차단.
_ARTIST_HINT = re.compile(
    r"\b(in the style of|sounds like|inspired by|à la|a la|cover of|tribute to|"
    r"like\s+[A-Z][a-z]+\s+[A-Z][a-z]+)\b", re.IGNORECASE)

NO_ARTIST_CLAUSE = (
    "Do not imitate any real, named artist, band, or specific recording. "
    "Describe the sound only through musical attributes."
)


class PromptPolicyError(ValueError):
    pass


def check_no_artist(text: str) -> None:
    m = _ARTIST_HINT.search(text or "")
    if m:
        raise PromptPolicyError(
            f"실존 아티스트 모방으로 읽힐 수 있는 표현이 있습니다: '{m.group(0)}'. "
            f"장르·악기·리듬·믹싱·정서로 바꿔 주세요."
        )


# ---------------------------------------------------------------- sonic_dna
def build_sonic_dna(config: dict) -> dict:
    genre = config.get("genre", "lofi")
    preset = GENRE_PRESETS.get(genre) or GENRE_PRESETS["lofi"]
    vocal_mode = config.get("vocal_mode", "vocal")
    lang = config.get("lyrics_language", "ko")
    vocal = dict(VOCAL_PRESETS.get(lang, VOCAL_PRESETS["ko"]))
    if vocal_mode == "instrumental":
        vocal = {"vocal_gender": "none", "vocal_range": "none",
                 "vocal_delivery": "instrumental only, no vocals, no vocal chops"}

    dna = {
        "created_at": now_iso(),
        "genre": genre,
        "subgenre": config.get("subgenre", ""),
        "instrumentation": preset["instrumentation"],
        "drum_pattern": preset["drum_pattern"],
        "bass_character": preset["bass_character"],
        "harmony_mood": preset["harmony_mood"],
        "vocal_gender": vocal["vocal_gender"],
        "vocal_range": vocal["vocal_range"],
        "vocal_delivery": vocal["vocal_delivery"],
        "mix_texture": preset["mix_texture"],
        "energy_range": preset["energy_range"],
        "forbidden": preset["forbidden"],
        "bpm_range": [int(config.get("bpm_min", 70)), int(config.get("bpm_max", 90))],
        "no_real_artist": NO_ARTIST_CLAUSE,
    }
    check_no_artist(" ".join(str(v) for v in dna.values() if isinstance(v, str)))
    return dna


def dna_paragraph(dna: dict) -> str:
    """모든 곡에 공통으로 붙는 DNA 문단."""
    parts = [
        f"Genre: {dna['genre']}" + (f" / {dna['subgenre']}" if dna.get("subgenre") else "") + ".",
        f"Instrumentation: {dna['instrumentation']}.",
        f"Drums: {dna['drum_pattern']}.",
        f"Bass: {dna['bass_character']}.",
        f"Harmony: {dna['harmony_mood']}.",
    ]
    if dna.get("vocal_gender") == "none":
        parts.append("Vocals: instrumental only, no vocals.")
    else:
        parts.append(
            f"Vocals: {dna['vocal_gender']}, {dna['vocal_range']}, {dna['vocal_delivery']}."
        )
    parts += [
        f"Mix: {dna['mix_texture']}.",
        f"Energy: {dna['energy_range']}.",
        f"Avoid: {dna['forbidden']}.",
        dna["no_real_artist"],
    ]
    return " ".join(parts)


# ---------------------------------------------------------------- visual_dna
VISUAL_PRESETS: dict[str, dict[str, str]] = {
    "black-gray-red": {
        "color_palette": "near-black background, charcoal and graphite mid-tones, one restrained crimson accent",
        "style": "cinematic photography, shallow depth of field, 35mm look",
        "lighting": "single hard key light from the side, deep falloff, practical lamp glow",
        "composition": "off-center subject, strong negative space on the left third",
        "texture": "fine film grain, slight halation around highlights",
        "accent_color": "crimson red, used on at most five percent of the frame",
        "people": "no recognizable faces; silhouettes or backs of figures only",
        "negative_space": "left third of the frame kept empty for text",
        "forbidden": "text, letters, logos, watermarks, captions, musical notation, brand marks",
    },
    "warm-film": {
        "color_palette": "amber, ochre, faded cream, warm brown shadows",
        "style": "analog film photograph, soft focus, expired-film color shift",
        "lighting": "late golden-hour sunlight through a window, long shadows",
        "composition": "wide establishing frame, subject small in the lower right",
        "texture": "heavy grain, gentle light leak on one edge",
        "accent_color": "warm orange highlight",
        "people": "no recognizable faces; distant figures only",
        "negative_space": "upper half of the frame kept open",
        "forbidden": "text, letters, logos, watermarks, captions, brand marks",
    },
    "cold-neon": {
        "color_palette": "deep navy and teal shadows, cyan and magenta neon reflections",
        "style": "night street photography, wet asphalt reflections, anamorphic feel",
        "lighting": "neon signage as the only light source, strong colored rim light",
        "composition": "leading lines down a narrow street, low camera height",
        "texture": "light rain streaks, subtle chromatic aberration",
        "accent_color": "magenta neon",
        "people": "no recognizable faces; umbrella silhouettes at distance",
        "negative_space": "top-left sky area kept dark and empty",
        "forbidden": "text, letters, signage words, logos, watermarks, brand marks",
    },
    "paper-grain": {
        "color_palette": "off-white paper, soft graphite gray, muted sage",
        "style": "minimal illustration, hand-drawn line with flat washes",
        "lighting": "flat even light, no cast shadows",
        "composition": "centered single motif with wide margins",
        "texture": "visible paper fiber, dry-brush edges",
        "accent_color": "muted terracotta",
        "people": "no faces; simplified figures without features",
        "negative_space": "generous margin on all four sides",
        "forbidden": "text, letters, logos, watermarks, captions",
    },
}

THUMBNAIL_CONCEPTS = {
    "A": "가까운 사물 클로즈업 - 창가의 컵, 이어폰, 젖은 유리 등. 얕은 심도.",
    "B": "인물 실루엣 - 뒷모습이나 그림자. 얼굴은 보이지 않는다.",
    "C": "넓은 풍경 - 밤 도시, 창밖, 텅 빈 방. 인물 없음.",
    "D": "질감 추상 - 빛 번짐, 필름 그레인, 색면. 구체적 사물 없음.",
}


def build_visual_dna(config: dict) -> dict:
    preset_key = config.get("visual_preset", "black-gray-red")
    preset = VISUAL_PRESETS.get(preset_key) or VISUAL_PRESETS["black-gray-red"]
    dna = {"created_at": now_iso(), "preset": preset_key, **preset}
    return dna


def visual_paragraph(vdna: dict) -> str:
    return " ".join([
        f"Color palette: {vdna['color_palette']}.",
        f"Style: {vdna['style']}.",
        f"Lighting: {vdna['lighting']}.",
        f"Composition: {vdna['composition']}.",
        f"Texture: {vdna['texture']}.",
        f"Accent: {vdna['accent_color']}.",
        f"People: {vdna['people']}.",
        f"Negative space: {vdna['negative_space']}.",
        f"Absolutely no {vdna['forbidden']}. The image must contain no readable characters of any script.",
    ])
