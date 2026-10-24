# 오르골 자장가 배경음 합성 (외부 음원 없이 numpy 로 생성)
import wave
import numpy as np

SR = 44100
DUR = 24.0
BEAT = 0.6          # 3/4 박자, 한 마디 1.8초
START = 0.6

NOTE = {n: 440 * 2 ** ((i - 9) / 12 + o - 4)
        for o in range(2, 7) for i, n0 in enumerate("C C# D D# E F F# G G# A A# B".split())
        for n in [f"{n0}{o}"]}
CHORD = {"C": ["C3", "G3", "E4"], "Am": ["A2", "E3", "C4"], "F": ["F2", "C3", "A3"],
         "G": ["G2", "D3", "B3"], "Em": ["E3", "B3", "G4"]}
SONG = [("C", ["E5", "D5", "C5"]), ("Am", ["E5", "A5", "G5"]), ("F", ["F5", "E5", "C5"]),
        ("G", ["D5", None, "G4"]), ("C", ["E5", "G5", "C6"]), ("Em", ["B5", "G5", "E5"]),
        ("F", ["A5", "G5", "F5"]), ("G", ["D5", "E5", "F5"]), ("Am", ["E5", "C5", "A4"]),
        ("F", ["C5", "F5", "A5"]), ("C", ["G5", "E5", "C5"]), ("G", ["D5", "B4", "G4"]),
        ("C", ["C5", None, None])]

out = np.zeros(int(SR * DUR) + SR)
t_all = np.arange(len(out)) / SR


def add(sig, at, gain):
    i = int(at * SR)
    n = min(len(sig), len(out) - i)
    out[i:i + n] += sig[:n] * gain


def music_box(f, length=2.4):
    t = np.arange(int(SR * length)) / SR
    env = np.exp(-t * 2.6) * (1 - np.exp(-t * 400))
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 4) \
        + 0.18 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t * 12)
    return s * env


def pad(freqs, length):
    t = np.arange(int(SR * length)) / SR
    env = np.minimum(1, t / 0.6) * np.minimum(1, (length - t) / 0.8)
    s = sum(np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2.003 * f * t) for f in freqs)
    return s * env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.3 * t))


for m, (ch, mel) in enumerate(SONG):
    t0 = START + m * BEAT * 3
    add(pad([NOTE[n] for n in CHORD[ch]], BEAT * 3 + 0.5), t0, 0.05)
    add(music_box(NOTE[CHORD[ch][0]] * 2, 2.0), t0, 0.22)
    for b, n in enumerate(mel):
        if n:
            add(music_box(NOTE[n]), t0 + b * BEAT, 0.42)

# 윙크 순간 반짝이는 차임
WINK = 17.6
for k, n in enumerate(["C6", "E6", "G6", "C7" if "C7" in NOTE else "B6", "E6"]):
    f = NOTE.get(n, NOTE["C6"] * 2)
    add(music_box(f, 1.6), WINK + k * 0.07, 0.22)

out = out[:int(SR * DUR)]
fade = np.ones_like(out)
fade[:int(SR * 1.0)] = np.linspace(0, 1, int(SR * 1.0))
fade[-int(SR * 1.5):] = np.linspace(1, 0, int(SR * 1.5))
out *= fade
out = out / np.max(np.abs(out)) * 0.7
st = np.stack([out, np.roll(out, int(SR * 0.012))], axis=1)  # 약간의 스테레오 폭
with wave.open("audio/music.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print("ok")
