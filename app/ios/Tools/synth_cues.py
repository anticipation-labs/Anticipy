"""The five cues, synthesised.

Anticipy's sound has to belong to the same object as its light: warm, quiet,
made of breath and wood rather than glass and bells. Nothing here is a chime.
Every cue fades to exact zero at both ends — a cue that clicks on its own edges
is worse than no cue.
"""
import math, random, struct, wave

SR = 44100
random.seed(1729)   # deterministic: the same bytes every build

def env(n, attack, release, curve=2.0):
    """Attack/release envelope, both ends landing exactly on zero."""
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    out = []
    for i in range(n):
        if i < a:
            v = (i / a) ** 0.7
        elif i > n - r:
            v = ((n - i) / r) ** curve
        else:
            v = 1.0
        out.append(v)
    return out

def tone(freq, n, phase=0.0):
    return [math.sin(2 * math.pi * freq * i / SR + phase) for i in range(n)]

def glide(f0, f1, n):
    """A note that moves. Phase-accumulated so it never discontinuities."""
    out, ph = [], 0.0
    for i in range(n):
        f = f0 + (f1 - f0) * (i / n) ** 0.6
        ph += 2 * math.pi * f / SR
        out.append(math.sin(ph))
    return out

def breath(n, cutoff=0.06):
    """Filtered noise. One-pole lowpass twice = the air, not the hiss."""
    out, y1, y2 = [], 0.0, 0.0
    for _ in range(n):
        x = random.uniform(-1, 1)
        y1 += cutoff * (x - y1)
        y2 += cutoff * (y1 - y2)
        out.append(y2 * 6.0)
    return out

def mix(*layers):
    n = max(len(l) for l in layers)
    out = [0.0] * n
    for l in layers:
        for i, v in enumerate(l):
            out[i] += v
    return out

def scale(sig, peak):
    m = max(abs(v) for v in sig) or 1.0
    return [v / m * peak for v in sig]

def write(name, sig, peak):
    # Remove DC bias the noise layer leaves behind. Inaudible on its own, but a
    # biased signal is a signal that can thump on somebody's hardware.
    bias = sum(sig) / len(sig)
    sig = [v - bias for v in sig]
    sig = scale(sig, peak)
    # Hard-guarantee silence at the very edges.
    for i in range(min(64, len(sig))):
        sig[i] *= i / 64
        sig[-1 - i] *= i / 64
    with wave.open(name, 'w') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, v)) * 32767)) for v in sig))
    print(f"{name:26} {len(sig)/SR*1000:6.0f} ms   peak {peak}")

# ── 1. listening opens ─────────────────────────────────────────────────────
# A rising breath: D4 to A4, a fifth, with air moving through it. The one
# moment a person must never be uncertain about, so it is the longest cue.
n = int(0.44 * SR)
e = env(n, 0.05, 0.26)
write('listen-open.wav', mix(
    [v * 0.62 * e[i] for i, v in enumerate(glide(293.66, 440.0, n))],
    [v * 0.16 * e[i] for i, v in enumerate(glide(587.32, 880.0, n))],
    [v * 0.20 * e[i] for i, v in enumerate(breath(n, 0.10))],
), peak=0.34)

# ── 2. heard ───────────────────────────────────────────────────────────────
# Near-subliminal. If you notice it twice in a row it is too loud.
n = int(0.032 * SR)
e = env(n, 0.001, 0.028, curve=3.0)
write('heard.wav', mix(
    [v * 0.5 * e[i] for i, v in enumerate(breath(n, 0.42))],
    [v * 0.3 * e[i] for i, v in enumerate(tone(2100.0, n))],
), peak=0.10)

# ── 3. listening closes ────────────────────────────────────────────────────
# The same breath, falling. Closure, not a stop — so it is softer and it lingers.
n = int(0.52 * SR)
e = env(n, 0.04, 0.38)
write('listen-close.wav', mix(
    [v * 0.62 * e[i] for i, v in enumerate(glide(440.0, 293.66, n))],
    [v * 0.14 * e[i] for i, v in enumerate(glide(880.0, 587.32, n))],
    [v * 0.18 * e[i] for i, v in enumerate(breath(n, 0.09))],
), peak=0.28)

# ── 4. needs you ───────────────────────────────────────────────────────────
# A knuckle on wood. Two thumps, the second quieter — the rhythm of somebody
# being polite about it.
def knock(amp):
    n = int(0.085 * SR)
    e = env(n, 0.0008, 0.082, curve=3.4)
    return mix(
        [v * 0.75 * e[i] * amp for i, v in enumerate(tone(118.0, n))],
        [v * 0.35 * e[i] * amp for i, v in enumerate(tone(196.0, n))],
        [v * 0.30 * e[i] * amp for i, v in enumerate(breath(n, 0.55))],
    )
gap = [0.0] * int(0.115 * SR)
write('needs-you.wav', knock(1.0) + gap + knock(0.62), peak=0.30)

# ── 5. done ────────────────────────────────────────────────────────────────
# The only cue with warmth in it. A struck wooden bowl settling: a root, then a
# fifth blooming in late, then a long decay. It resolves; it does not celebrate.
n = int(0.85 * SR)
e = env(n, 0.006, 0.70, curve=1.7)
late = [0.0 if i < 0.07 * SR else min(1.0, (i - 0.07 * SR) / (0.16 * SR)) for i in range(n)]
write('done.wav', mix(
    [v * 0.60 * e[i] for i, v in enumerate(tone(220.0, n))],
    [v * 0.26 * e[i] * late[i] for i, v in enumerate(tone(330.0, n))],
    [v * 0.10 * e[i] for i, v in enumerate(tone(440.0, n))],
    [v * 0.09 * e[i] for i, v in enumerate(breath(n, 0.20))],
), peak=0.32)
