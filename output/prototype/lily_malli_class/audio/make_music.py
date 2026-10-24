# 배경음 합성: 경쾌한 오르골 왈츠 + 성이 나타날 때 차임 + 불꽃 터지는 소리 (numpy 만 사용)
import wave
import numpy as np

SR = 44100
DUR = 23.0
BEAT = 0.5
rng = np.random.default_rng(3)

NAMES = "C C# D D# E F F# G G# A A# B".split()
NOTE = {f"{n}{o}": 440 * 2 ** ((i - 9) / 12 + o - 4) for o in range(1, 8) for i, n in enumerate(NAMES)}
CH = {"F": ["F2", "C3", "A3"], "Dm": ["D2", "A2", "F3"], "Bb": ["A#1", "F2", "D3"], "C": ["C2", "G2", "E3"],
      "Gm": ["G1", "D2", "A#2"], "Am": ["A1", "E2", "C3"]}
SONG = [("F", ["A5", "C6", "A5"]), ("Bb", ["F5", "D5", "F5"]), ("C", ["E5", "G5", "C6"]), ("F", ["A5", None, "F5"]),
        ("Dm", ["D6", "C6", "A5"]), ("Bb", ["A#5", "A5", "F5"]), ("Gm", ["G5", "A5", "A#5"]), ("C", ["C6", None, None]),
        ("F", ["A5", "C6", "F6"]), ("Am", ["E6", "C6", "A5"]), ("Bb", ["D6", "A#5", "F5"]), ("C", ["G5", "A#5", "E6"]),
        ("F", ["F6", "C6", "A5"]), ("Dm", ["A5", "D6", "F6"]), ("Bb", ["F6", "D6", "A#5"]), ("F", ["A5", None, None])]

out = np.zeros(int(SR * (DUR + 2)))


def add(sig, at, gain):
    i = int(at * SR)
    n = min(len(sig), len(out) - i)
    if n > 0:
        out[i:i + n] += sig[:n] * gain


def box(f, length=2.0, decay=2.8):
    t = np.arange(int(SR * length)) / SR
    env = np.exp(-t * decay) * (1 - np.exp(-t * 500))
    return (np.sin(2 * np.pi * f * t) + .3 * np.sin(4 * np.pi * f * t) * np.exp(-t * 5)
            + .15 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t * 14)) * env


def pad(fs, length):
    t = np.arange(int(SR * length)) / SR
    env = np.minimum(1, t / .4) * np.minimum(1, (length - t) / .5)
    return sum(np.sin(2 * np.pi * f * t) + .25 * np.sin(2 * np.pi * 2.004 * f * t) for f in fs) * env


def boom(length=1.6):
    n = int(SR * length)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    low = np.convolve(noise, np.ones(60) / 60, mode="same")
    thump = np.sin(2 * np.pi * 55 * t * np.exp(-t * 3)) * np.exp(-t * 9)
    crackle = (rng.random(n) < .004) * rng.standard_normal(n) * (t > .25) * np.exp(-t * 2)
    return (low * 3 * np.exp(-t * 6) + thump * .8 + crackle * .5)


def whistle(length=.7):
    t = np.arange(int(SR * length)) / SR
    f = 900 + 1400 * t / length
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(1, t / .1) * (1 - t / length) * .3


# 1~4 마디는 오르골만, 이후 화음과 베이스가 더해진다 (16마디 x 1.5초 = 24초)
for m, (ch, mel) in enumerate(SONG):
    t0 = .3 + m * BEAT * 3
    if t0 > DUR:
        break
    full = m >= 4
    if full:
        add(pad([NOTE[n] for n in CH[ch]], BEAT * 3 + .3), t0, .045)
        add(box(NOTE[CH[ch][0]] * 2, 1.2, 4), t0, .2)
        for b in (1, 2):
            add(box(NOTE[CH[ch][1]] * 2, .5, 7), t0 + b * BEAT, .08)
            add(box(NOTE[CH[ch][2]] * 2, .5, 7), t0 + b * BEAT, .08)
    for b, n in enumerate(mel):
        if n:
            add(box(NOTE[n]), t0 + b * BEAT, .38)

# 성이 떠오를 때 반짝이는 상행 차임
for k, n in enumerate(["F5", "A5", "C6", "F6", "A6", "C7"]):
    add(box(NOTE[n], 1.8, 2.2), 5.6 + k * .09, .16)

# 불꽃: scene.html 의 FW 발사 시각과 같다
FW = [8.0, 8.5, 9.0, 9.5, 10.0, 10.4, 11.2, 11.9, 12.6, 13.2, 13.8, 14.4, 15.0, 15.6, 16.2, 16.8, 17.4, 18.0]
for i, t0 in enumerate(FW):
    near = t0 >= 11
    add(whistle(), t0, .05 if near else .03)
    add(boom(), t0 + .7, (.5 if near else .3) * (0.8 + .4 * rng.random()))

# 마무리 화음
add(pad([NOTE["F3"], NOTE["A3"], NOTE["C4"], NOTE["F4"]], 4.2), 18.9, .06)
for k, n in enumerate(["C6", "F6", "A6"]):
    add(box(NOTE[n], 3, 1.5), 19.4 + k * .15, .18)

out = out[:int(SR * DUR)]
fade = np.ones_like(out)
fade[:int(SR * .4)] = np.linspace(0, 1, int(SR * .4))
fade[-int(SR * 1.2):] = np.linspace(1, 0, int(SR * 1.2))
out *= fade
out = np.tanh(out / np.max(np.abs(out)) * 1.2) * .75
st = np.stack([out, np.roll(out, int(SR * .011))], axis=1)
with wave.open("audio/music.wav", "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype(np.int16).tobytes())
print("ok")
