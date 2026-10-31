"""Procedural cinematic score generator (CPU, deterministic, royalty-free).

Moods: horror, suspense, sad, documentary, epic, mystery. Output: stereo float32 @ 48 kHz.
For higher-quality generative music, MusicGen (facebookresearch/audiocraft) can replace this
on a GPU machine - see PRODUCTION_WORKFLOWS.md.
"""
import numpy as np

from .config import SAMPLE_RATE as SR
from .synth import band, env_adsr, noise, norm, reverb

NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def root_midi(key):
    return 45 + NOTE[key.rstrip("m")]  # around A2


MOODS = {
    #            bpm, scale intervals,     progression (scale degrees), motif density, colour
    "horror":      (60, [0, 2, 3, 5, 7, 8, 11], [0, 5, 3, 6], 0.25, "dark"),
    "suspense":    (84, [0, 2, 3, 5, 7, 8, 10], [0, 0, 5, 4], 0.5, "pulse"),
    "mystery":     (72, [0, 2, 3, 5, 7, 8, 10], [0, 3, 5, 4], 0.35, "dark"),
    "sad":         (66, [0, 2, 3, 5, 7, 8, 10], [0, 5, 2, 6], 0.4, "warm"),
    "documentary": (80, [0, 2, 4, 5, 7, 9, 11], [0, 4, 5, 3], 0.45, "warm"),
    "epic":        (96, [0, 2, 3, 5, 7, 8, 10], [0, 5, 2, 6], 0.6, "pulse"),
}


def _pad(freqs, n, rng, bright=1200):
    t = np.arange(n) / SR
    s = np.zeros(n, np.float32)
    for f in freqs:
        for det in (-0.006, 0.0, 0.007):
            ph = rng.uniform(0, 2 * np.pi)
            # band-limited-ish saw via a few harmonics
            for h in range(1, 7):
                s += (np.sin(2 * np.pi * f * (1 + det) * h * t + ph * h) / h).astype(np.float32) * 0.08
    s = band(s, None, bright, 2)
    return s * env_adsr(n, 0.8, 0.5, 0.8, 0.9)


def _piano(f, dur, rng):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * f * h * t) * np.exp(-t * (1.6 + h * 0.9)) / h ** 1.2 for h in range(1, 6))
    s *= np.minimum(1, t / 0.004)
    return s.astype(np.float32)


def score(mood="horror", dur=60.0, key="Am", seed=0, intensity_curve=None):
    """Return stereo music of length dur. intensity_curve: optional fn(t_norm)->0..1."""
    if mood not in MOODS:
        raise KeyError(f"Unknown mood '{mood}'. Options: {sorted(MOODS)}")
    bpm, scale, prog, density, colour = MOODS[mood]
    rng = np.random.default_rng(seed)
    n = int(dur * SR)
    L = np.zeros(n, np.float32)
    R = np.zeros(n, np.float32)
    beat = 60.0 / bpm
    bar = beat * 4
    root = root_midi(key)

    def deg(d, octave=0):
        return root + scale[d % len(scale)] + 12 * (d // len(scale) + octave)

    # Chords: 2 bars each
    chord_len = bar * 2
    t0, ci = 0.0, 0
    while t0 < dur:
        d = prog[ci % len(prog)]
        notes = [deg(d, 1), deg(d + 2, 1), deg(d + 4, 1)]
        if colour == "dark":
            notes.append(deg(d, 1) + 1)  # minor-second cluster for unease
        seg = int(min(chord_len + 1.0, dur - t0) * SR)
        if seg > SR * 0.2:
            p = _pad([hz(m) for m in notes], seg, rng, 900 if colour == "dark" else 1800)
            i = int(t0 * SR)
            L[i:i + seg] += p * 0.9
            R[i:i + seg] += np.roll(p, int(0.011 * SR)) * 0.9
            # bass
            tb = np.arange(seg) / SR
            bass = np.sin(2 * np.pi * hz(deg(d, -1)) * tb) * env_adsr(seg, 0.3, 0.3, 0.7, 0.8) * 0.35
            L[i:i + seg] += bass
            R[i:i + seg] += bass
        t0 += chord_len
        ci += 1

    # Motif / melody: sparse piano notes from the scale
    t0 = bar
    while t0 < dur - 1:
        if rng.random() < density:
            d = prog[int(t0 // chord_len) % len(prog)] + int(rng.choice([0, 2, 4, 7]))
            f = hz(deg(d, 2))
            nd = min(3.0, dur - t0)
            s = _piano(f, nd, rng) * 0.28
            i = int(t0 * SR)
            pan = rng.uniform(-0.6, 0.6)
            L[i:i + len(s)] += s * (1 - pan) / 2 * 1.4
            R[i:i + len(s)] += s * (1 + pan) / 2 * 1.4
        t0 += beat * rng.choice([1, 2, 2, 3])

    if colour == "pulse":
        t0 = 0.0
        while t0 < dur:
            Lp = int(0.15 * SR)
            k = band(noise(Lp, "brown", rng), None, 150, 2) * np.exp(-np.arange(Lp) / (0.05 * SR)) * 0.5
            i = int(t0 * SR)
            m = max(0, min(Lp, n - i))
            L[i:i + m] += k[:m]
            R[i:i + m] += k[:m]
            t0 += beat

    if intensity_curve:
        tn = np.arange(n) / n
        g = np.array([intensity_curve(x) for x in tn[:: SR // 10]])
        g = np.interp(np.arange(n), np.arange(len(g)) * (SR // 10), g).astype(np.float32)
        L *= 0.4 + 0.6 * g
        R *= 0.4 + 0.6 * g

    L, R = reverb(L, 3.0, 0.35, rng), reverb(R, 3.1, 0.35, np.random.default_rng(seed + 1))
    fade = np.minimum(1, np.minimum(np.arange(n) / (2 * SR), (n - np.arange(n)) / (3 * SR)))
    out = np.stack([L * fade, R * fade], axis=1)
    return norm(out, 0.8)
