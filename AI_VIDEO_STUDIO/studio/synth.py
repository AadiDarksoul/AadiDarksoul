"""Procedural, royalty-free sound design (pure numpy/scipy, CPU-only, deterministic by seed).

Every generator returns mono float32 at 48 kHz unless noted. SFX registry: SFX[name](dur, rng).
"""
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

from .config import SAMPLE_RATE as SR


def t_axis(dur):
    return np.arange(int(dur * SR)) / SR


def noise(n, color="white", rng=None):
    rng = rng or np.random.default_rng(0)
    w = rng.standard_normal(n).astype(np.float32)
    if color == "white":
        return w
    f = np.fft.rfft(w)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    freqs[0] = freqs[1] if n > 1 else 1
    f /= np.sqrt(freqs) if color == "pink" else freqs
    out = np.fft.irfft(f, n).astype(np.float32)
    return out / (np.max(np.abs(out)) + 1e-9)


def band(x, lo=None, hi=None, order=4):
    if lo and hi:
        sos = butter(order, [lo, hi], btype="band", fs=SR, output="sos")
    elif lo:
        sos = butter(order, lo, btype="high", fs=SR, output="sos")
    else:
        sos = butter(order, hi, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def env_adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    sus = max(n - a - d - r, 0)
    e = np.concatenate([np.linspace(0, 1, a, endpoint=False), np.linspace(1, s, d, endpoint=False),
                        np.full(sus, s), np.linspace(s, 0, r)])
    return np.pad(e, (0, max(0, n - len(e))))[:n].astype(np.float32)


def norm(x, peak=0.9):
    m = np.max(np.abs(x)) + 1e-9
    return (x / m * peak).astype(np.float32)


def reverb(x, decay=2.5, mix=0.35, rng=None):
    """Cheap convolution reverb with an exponentially decaying noise impulse response."""
    rng = rng or np.random.default_rng(7)
    n = int(decay * SR)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-6.9 * np.arange(n) / n)
    ir = band(ir, 120, 7000, 2)
    wet = fftconvolve(x, ir)[: len(x)]
    wet = wet / (np.max(np.abs(wet)) + 1e-9) * (np.max(np.abs(x)) + 1e-9)
    return ((1 - mix) * x + mix * wet).astype(np.float32)


# ----------------------------------------------------------------------------------- generators
def wind(dur, rng=None, intensity=0.6):
    rng = rng or np.random.default_rng(1)
    n = int(dur * SR)
    x = noise(n, "pink", rng)
    t = t_axis(dur)
    gust = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + rng.uniform(0, 6)) * np.sin(2 * np.pi * 0.023 * t)
    howl = band(x, 300, 900, 2) * (0.4 + gust) + band(x, None, 400, 2) * 0.8
    return norm(howl * intensity, 0.5 * intensity)


def drone(dur, base=55.0, rng=None, dark=True):
    rng = rng or np.random.default_rng(2)
    t = t_axis(dur)
    sig = np.zeros_like(t, dtype=np.float32)
    for i, mult in enumerate([1, 1.5, 2, 2.996, 4.03]):
        det = 1 + rng.uniform(-0.004, 0.004)
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.05 + 0.03 * i) * t + i)
        sig += (np.sin(2 * np.pi * base * mult * det * t) / (i + 1) * lfo).astype(np.float32)
    if dark:
        sig += 0.2 * band(noise(len(t), "brown", rng), None, 200, 2)
    fade = np.minimum(1, np.minimum(t / 2.0, (dur - t) / 2.0).clip(0))
    return norm(sig * fade, 0.5)


def heartbeat(dur, bpm=70, rng=None):
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    beat = 60.0 / bpm
    def thump(f, length=0.12):
        tt = t_axis(length)
        return (np.sin(2 * np.pi * f * tt * (1 - tt * 2)) * np.exp(-tt * 35)).astype(np.float32)
    lub, dub = thump(55), thump(70) * 0.7
    t0 = 0.0
    while t0 < dur:
        for off, s in ((0, lub), (0.28, dub)):
            i = int((t0 + off) * SR)
            if i < n:
                out[i:i + len(s)] += s[: n - i]
        t0 += beat
    return norm(out, 0.8)


def footsteps(dur, rate=1.8, rng=None, surface="wood"):
    rng = rng or np.random.default_rng(3)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    lo, hi = (80, 1800) if surface == "wood" else (200, 6000)
    step = 1.0 / rate
    t0 = 0.05
    while t0 < dur:
        L = int(0.09 * SR)
        hit = noise(L, "white", rng) * np.exp(-np.arange(L) / (0.018 * SR))
        hit = band(hit, lo, hi, 2) * rng.uniform(0.6, 1.0)
        i = int(t0 * SR)
        out[i:i + L] += hit[: max(0, min(L, n - i))]
        t0 += step * rng.uniform(0.92, 1.08)
    return norm(reverb(out, 0.6, 0.25, rng), 0.7)


def creak(dur=1.6, rng=None):
    rng = rng or np.random.default_rng(4)
    t = t_axis(dur)
    f = 180 + 120 * np.sin(np.pi * t / dur) + 15 * rng.standard_normal(len(t)).cumsum() / np.sqrt(len(t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    # stick-slip: pulse train of the fundamental through a resonant body
    raw = (np.sin(phase) > 0.92).astype(np.float32) * (0.5 + 0.5 * np.sin(2 * np.pi * 7 * t))
    body = band(raw, 300, 2500, 2) + 0.3 * band(raw, 80, 300, 2)
    return norm(reverb(body * env_adsr(len(t), 0.1, 0.2, 0.8, 0.4), 1.2, 0.3), 0.6)


def thunder(dur=5.0, rng=None):
    rng = rng or np.random.default_rng(5)
    n = int(dur * SR)
    x = noise(n, "brown", rng)
    tt = np.arange(n) / SR
    e = np.exp(-tt / (dur * 0.35)) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 1.3 * tt)))
    crack = band(noise(int(0.25 * SR), "white", rng), 800, 6000, 2) * np.exp(-np.arange(int(0.25 * SR)) / (0.04 * SR))
    out = band(x, None, 300, 2) * e
    out[: len(crack)] += crack * 0.5
    return norm(reverb(out, 3.0, 0.4, rng), 0.95)


def stinger(dur=3.0, rng=None):
    """Dissonant orchestral-style swell into a hit (classic jump-scare)."""
    rng = rng or np.random.default_rng(6)
    t = t_axis(dur)
    swell = np.zeros_like(t, dtype=np.float32)
    for f in (233.08, 246.94, 277.18, 311.13, 466.16, 493.88):
        vib = 1 + 0.01 * np.sin(2 * np.pi * rng.uniform(4, 7) * t)
        swell += np.sign(np.sin(2 * np.pi * f * vib * t)) * 0.15
    swell = band(swell, 150, 4000, 2) * (t / dur) ** 3
    hit_at = int(dur * 0.8 * SR)
    L = len(t) - hit_at
    hit = band(noise(L, "pink", rng), 40, 3000, 2) * np.exp(-np.arange(L) / (0.25 * SR))
    hit += np.sin(2 * np.pi * 45 * np.arange(L) / SR) * np.exp(-np.arange(L) / (0.4 * SR))
    swell[hit_at:] = swell[hit_at:] * 0.2 + hit * 1.5
    return norm(reverb(swell, 2.5, 0.35, rng), 0.95)


def whispers(dur, rng=None):
    rng = rng or np.random.default_rng(8)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    t0 = 0.0
    while t0 < dur:
        L = int(rng.uniform(0.25, 0.8) * SR)
        syl = noise(L, "white", rng)
        f1 = rng.uniform(500, 1500)
        syl = band(syl, f1, f1 * 2.4, 2) * env_adsr(L, 0.05, 0.1, 0.6, 0.15)
        i = int(t0 * SR)
        out[i:i + L] += syl[: max(0, min(L, n - i))] * rng.uniform(0.3, 1)
        t0 += rng.uniform(0.2, 0.9)
    return norm(reverb(out, 2.0, 0.5, rng), 0.35)


def rain(dur, rng=None, heavy=0.6):
    rng = rng or np.random.default_rng(9)
    n = int(dur * SR)
    bed = band(noise(n, "pink", rng), 400, 9000, 2) * 0.5
    drops = (rng.random(n) > 1 - 0.0015 * heavy).astype(np.float32) * rng.uniform(0.2, 1, n)
    drops = band(drops, 1500, 9000, 2) * 3
    return norm(bed + drops, 0.45 * heavy + 0.1)


def knock(dur=1.6, count=3, rng=None):
    rng = rng or np.random.default_rng(10)
    n = int(dur * SR)
    out = np.zeros(n, np.float32)
    for k in range(count):
        L = int(0.12 * SR)
        h = band(noise(L, "white", rng), 90, 900, 2) * np.exp(-np.arange(L) / (0.02 * SR))
        h += np.sin(2 * np.pi * 120 * np.arange(L) / SR) * np.exp(-np.arange(L) / (0.03 * SR))
        i = int((0.05 + k * 0.32) * SR)
        out[i:i + L] += h[: max(0, min(L, n - i))]
    return norm(reverb(out, 1.0, 0.3, rng), 0.85)


def door_slam(dur=2.0, rng=None):
    rng = rng or np.random.default_rng(11)
    n = int(dur * SR)
    L = int(0.4 * SR)
    hit = band(noise(L, "brown", rng), 40, 1200, 2) * np.exp(-np.arange(L) / (0.08 * SR))
    out = np.zeros(n, np.float32)
    out[:L] = hit
    return norm(reverb(out, 1.8, 0.4, rng), 0.95)


def whoosh(dur=1.2, rng=None):
    rng = rng or np.random.default_rng(12)
    n = int(dur * SR)
    x = noise(n, "pink", rng)
    t = np.arange(n) / n
    e = np.sin(np.pi * t) ** 2
    lo = band(x, 200, 1200, 2) * (1 - t) + band(x, 1200, 5000, 2) * t
    return norm(lo * e, 0.7)


def riser(dur=4.0, rng=None):
    t = t_axis(dur)
    f = 80 * (2 ** (4 * t / dur))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / dur) ** 2
    s += band(noise(len(t), "white", rng), 2000, 8000, 2) * (t / dur) ** 3 * 0.3
    return norm(s, 0.7)


SFX = {
    "wind": wind, "drone": drone, "heartbeat": heartbeat, "footsteps": footsteps, "creak": creak,
    "thunder": thunder, "stinger": stinger, "whispers": whispers, "rain": rain, "knock": knock,
    "door_slam": door_slam, "whoosh": whoosh, "riser": riser,
}

AMBIENCES = {
    "haunted_house": [("drone", 0.5, {"base": 49.0}), ("wind", 0.35, {}), ("whispers", 0.12, {})],
    "forest_night": [("wind", 0.55, {"intensity": 0.5}), ("drone", 0.25, {"base": 41.2})],
    "storm": [("rain", 0.6, {}), ("wind", 0.4, {}), ("drone", 0.2, {"base": 36.7})],
    "basement": [("drone", 0.6, {"base": 32.7}), ("whispers", 0.2, {})],
    "documentary_room": [("wind", 0.08, {"intensity": 0.2})],
}


def make_sfx(name, dur, seed=0, **kw):
    if name not in SFX:
        raise KeyError(f"Unknown sfx '{name}'. Options: {sorted(SFX)}")
    fn = SFX[name]
    rng = np.random.default_rng(seed)
    import inspect
    params = inspect.signature(fn).parameters
    args = {k: v for k, v in kw.items() if k in params}
    if "rng" in params:
        args["rng"] = rng
    if "dur" in params:
        return fn(dur, **args)
    return fn(**args)


def ambience(preset, dur, seed=0):
    """Layered stereo ambience bed; slow independent L/R variation gives width."""
    if preset not in AMBIENCES:
        raise KeyError(f"Unknown ambience '{preset}'. Options: {sorted(AMBIENCES)}")
    n = int(dur * SR)
    out = np.zeros((n, 2), np.float32)
    for k, (name, gain, kw) in enumerate(AMBIENCES[preset]):
        l = make_sfx(name, dur, seed + k * 13, **kw)[:n]
        r = make_sfx(name, dur, seed + k * 13 + 1, **kw)[:n]
        out[: len(l), 0] += l * gain
        out[: len(r), 1] += r * gain
    return out
