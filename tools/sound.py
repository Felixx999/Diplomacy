"""Синтез звуковых файлов.

Только стандартная библиотека: волны считаются вручную и пишутся модулем
`wave`. Никаких зависимостей — как и всё остальное в проекте.

Три музыкальных слоя намеренно сделаны в одном темпе, одной
тональности и с совпадающей длиной петли. Это обязательное требование к
вертикальному наслоению: слои звучат одновременно в любом сочетании, и
если темп или тональность разойдутся, смесь развалится.

    python3 tools/sound.py
"""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SFX_DIR = ROOT / "web" / "sfx"
MUSIC_DIR = ROOT / "web" / "music"

SR_SFX = 44100
SR_MUS = 22050

# Ля минор: одна тональность на все слои, иначе они не смешаются.
A = 55.0
SCALE = {"A1": A, "C2": A * 2 ** (3 / 12), "E2": A * 2 ** (7 / 12),
         "A2": A * 2, "C3": A * 2 * 2 ** (3 / 12), "E3": A * 2 * 2 ** (7 / 12),
         "G2": A * 2 ** (10 / 12), "D3": A * 2 * 2 ** (5 / 12),
         "A3": A * 4, "F2": A * 2 ** (8 / 12)}

LOOP = 8.0      # секунд: одна петля на все слои
BPM = 60.0


def write(path: Path, samples: list[float], rate: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(s) for s in samples), default=1.0) or 1.0
    scale = 0.82 / peak
    data = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767))
                    for s in samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data)
    return path.stat().st_size


def env(i: int, n: int, attack: float, release: float) -> float:
    """Огибающая: быстрый подъём, плавный спад — иначе слышны щелчки."""
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    if i < a:
        return i / a
    if i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


def tone(freq: float, dur: float, rate: int, kind: str = "sine",
         to: float | None = None, harm: int = 1) -> list[float]:
    n = int(dur * rate)
    out = []
    phase = 0.0
    for i in range(n):
        f = freq if to is None else freq * (to / freq) ** (i / n)
        phase += 2 * math.pi * f / rate
        if kind == "sine":
            v = math.sin(phase)
        elif kind == "triangle":
            v = 2 / math.pi * math.asin(math.sin(phase))
        elif kind == "saw":
            v = 2 * ((phase / (2 * math.pi)) % 1.0) - 1
        else:
            v = 1.0 if math.sin(phase) > 0 else -1.0
        for h in range(2, harm + 1):
            v += math.sin(phase * h) / (h * 2.2)
        out.append(v * env(i, n, 0.02, 0.55))
    return out


def noise(dur: float, rate: int, rng: random.Random, cut: float = 0.25) -> list[float]:
    """Шум с простым сглаживанием — основа для щелчков и шороха."""
    n = int(dur * rate)
    out, prev = [], 0.0
    for i in range(n):
        v = rng.uniform(-1, 1)
        prev = prev + (v - prev) * cut
        out.append(prev * env(i, n, 0.005, 0.7))
    return out


def mix(*tracks: list[float]) -> list[float]:
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    return out


# --- отклики интерфейса --------------------------------------------------

def build_sfx() -> list[tuple[str, int]]:
    rng = random.Random(7)
    made = []

    def save(name: str, samples: list[float]):
        made.append((name, write(SFX_DIR / f"{name}.wav", samples, SR_SFX)))

    # сухой щелчок: короткий шум плюс низкий тон
    save("click", mix(noise(0.05, SR_SFX, rng, 0.6),
                      [v * 0.5 for v in tone(320, 0.06, SR_SFX)]))
    save("tab", mix(noise(0.04, SR_SFX, rng, 0.7),
                    [v * 0.4 for v in tone(440, 0.05, SR_SFX)]))
    save("slider", [v * 0.5 for v in noise(0.035, SR_SFX, rng, 0.8)])

    # удача и отказ: восходящий и нисходящий, без литавр
    save("good", mix(tone(SCALE["C3"], 0.22, SR_SFX, "sine", SCALE["E3"]),
                     [v * 0.4 for v in tone(SCALE["A2"], 0.22, SR_SFX)]))
    save("bad", mix(tone(SCALE["G2"], 0.34, SR_SFX, "triangle", SCALE["F2"]),
                    [v * 0.3 for v in tone(SCALE["A1"], 0.34, SR_SFX)]))

    save("notify", mix(tone(SCALE["E3"], 0.3, SR_SFX, "sine", SCALE["A3"]),
                       [v * 0.3 for v in tone(SCALE["C3"], 0.3, SR_SFX)]))
    # единственный громкий: низкий, тревожный
    save("alert", mix(tone(SCALE["A2"], 0.75, SR_SFX, "saw", SCALE["G2"], harm=3),
                      [v * 0.5 for v in tone(SCALE["A1"], 0.75, SR_SFX, "triangle")]))

    # чернильный росчерк и тяжёлая печать
    save("sign", mix([v * 0.7 for v in noise(0.20, SR_SFX, rng, 0.35)],
                     tone(SCALE["C3"], 0.35, SR_SFX, "sine", SCALE["E3"]),
                     [v * 0.5 for v in tone(SCALE["A2"], 0.40, SR_SFX)]))
    # смена месяца: глубокий удар, задаёт ритм партии
    save("turn", mix(tone(SCALE["A1"], 0.7, SR_SFX, "sine", A * 0.75, harm=2),
                     [v * 0.35 for v in tone(SCALE["E2"], 0.5, SR_SFX)],
                     [v * 0.3 for v in noise(0.10, SR_SFX, rng, 0.2)]))

    save("open", tone(SCALE["C3"], 0.14, SR_SFX, "sine", SCALE["E3"]))
    save("close", tone(SCALE["E3"], 0.12, SR_SFX, "sine", SCALE["C3"]))
    return made


# --- музыкальные слои ----------------------------------------------------

def layer_base() -> list[float]:
    """Ровный фон: медленное дыхание аккорда, ничего не происходит."""
    n = int(LOOP * SR_MUS)
    out = [0.0] * n
    for freq, amp in ((SCALE["A1"], 0.5), (SCALE["E2"], 0.32),
                      (SCALE["A2"], 0.22), (SCALE["C3"], 0.14)):
        phase = 0.0
        for i in range(n):
            phase += 2 * math.pi * freq / SR_MUS
            breath = 0.72 + 0.28 * math.sin(2 * math.pi * i / n)
            out[i] += math.sin(phase) * amp * breath
    # плавная петля: сшиваем края
    fade = int(SR_MUS * 0.4)
    for i in range(fade):
        k = i / fade
        out[i] *= k
        out[n - 1 - i] *= k
    return out


def layer_tension() -> list[float]:
    """Слой напряжения: пульс на восьмых, беспокойная терция."""
    n = int(LOOP * SR_MUS)
    out = [0.0] * n
    beat = 60.0 / BPM / 2
    steps = int(LOOP / beat)
    for s in range(steps):
        start = int(s * beat * SR_MUS)
        freq = SCALE["C3"] if s % 4 in (0, 2) else SCALE["D3"]
        pulse = tone(freq, beat * 0.85, SR_MUS, "triangle")
        for i, v in enumerate(pulse):
            if start + i < n:
                out[start + i] += v * 0.30
    phase = 0.0
    for i in range(n):
        phase += 2 * math.pi * SCALE["E2"] / SR_MUS
        out[i] += math.sin(phase) * 0.18
    fade = int(SR_MUS * 0.3)
    for i in range(fade):
        k = i / fade
        out[i] *= k
        out[n - 1 - i] *= k
    return out


def layer_crisis() -> list[float]:
    """Слой кризиса: низкий гул и редкие тяжёлые удары."""
    n = int(LOOP * SR_MUS)
    rng = random.Random(3)
    out = [0.0] * n
    for freq, amp in ((A * 0.5, 0.55), (SCALE["A1"], 0.3), (SCALE["F2"], 0.16)):
        phase = 0.0
        for i in range(n):
            phase += 2 * math.pi * freq / SR_MUS
            wob = 1.0 + 0.05 * math.sin(2 * math.pi * 0.7 * i / SR_MUS)
            out[i] += math.sin(phase * wob) * amp
    for s in (0, 3, 5):
        start = int(s * SR_MUS)
        hit = mix(tone(A * 0.75, 0.5, SR_MUS, "sine", A * 0.5),
                  [v * 0.4 for v in noise(0.12, SR_MUS, rng, 0.15)])
        for i, v in enumerate(hit):
            if start + i < n:
                out[start + i] += v * 0.35
    fade = int(SR_MUS * 0.3)
    for i in range(fade):
        k = i / fade
        out[i] *= k
        out[n - 1 - i] *= k
    return out


def build_music() -> list[tuple[str, int]]:
    return [
        ("base", write(MUSIC_DIR / "base.wav", layer_base(), SR_MUS)),
        ("tension", write(MUSIC_DIR / "tension.wav", layer_tension(), SR_MUS)),
        ("crisis", write(MUSIC_DIR / "crisis.wav", layer_crisis(), SR_MUS)),
    ]


def main() -> None:
    print("Синтез звука\n")
    print("Отклики интерфейса:")
    for name, size in build_sfx():
        print(f"  {name:<10} {size / 1024:6.1f} КБ")
    print(f"\nМузыкальные слои, петля {LOOP:.0f} с, {BPM:.0f} ударов, ля минор:")
    for name, size in build_music():
        print(f"  {name:<10} {size / 1024:6.1f} КБ")
    print("\nСлои сведены в одном темпе и тональности — смешиваются в любом "
          "сочетании.")


if __name__ == "__main__":
    main()
