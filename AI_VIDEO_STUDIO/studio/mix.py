"""Multitrack audio timeline: dialogue / music / sfx / ambience buses with ducking + loudness."""
import os
import tempfile

import numpy as np

from .audio_io import load, save, stereo
from .config import SAMPLE_RATE as SR
from .media import ffmpeg
from .config import require


class Timeline:
    BUSES = ("dialogue", "music", "sfx", "ambience")

    def __init__(self, duration):
        self.duration = float(duration)
        self.n = int(self.duration * SR)
        self.bus = {b: np.zeros((self.n, 2), np.float32) for b in self.BUSES}
        self.events = []

    def add(self, clip, start, bus="sfx", gain_db=0.0, pan=0.0, fade_in=0.0, fade_out=0.0):
        """clip: path to wav, mono array or stereo array."""
        if isinstance(clip, str):
            data = load(clip)
        else:
            data = np.asarray(clip, np.float32)
            if data.ndim == 1:
                data = stereo(data, pan)
        if pan and isinstance(clip, str):
            data = stereo(data.mean(axis=1), pan)
        data = data * (10 ** (gain_db / 20))
        if fade_in:
            k = min(len(data), int(fade_in * SR))
            data[:k] *= np.linspace(0, 1, k)[:, None]
        if fade_out:
            k = min(len(data), int(fade_out * SR))
            data[-k:] *= np.linspace(1, 0, k)[:, None]
        i = int(max(0, start) * SR)
        if i >= self.n:
            return
        m = min(len(data), self.n - i)
        self.bus[bus][i:i + m] += data[:m]
        self.events.append({"bus": bus, "start": start, "dur": m / SR,
                            "src": clip if isinstance(clip, str) else "generated"})

    def render(self, out_wav, duck_db=-10.0, bus_gain=None, lufs=-16.0, true_peak=-1.5):
        """Mix buses with music/ambience ducked under dialogue, then EBU R128 normalize."""
        g = {"dialogue": 0.0, "music": -6.0, "sfx": -3.0, "ambience": -8.0}
        g.update(bus_gain or {})
        dia = self.bus["dialogue"]
        envl = np.abs(dia).max(axis=1)
        # smoothed sidechain envelope (attack/release ~ 150 ms / 400 ms via moving max + mean)
        win = int(0.15 * SR)
        if envl.any():
            kernel = np.ones(win) / win
            envl = np.convolve(envl, kernel, mode="same")
            envl = np.convolve((envl > 0.01).astype(np.float32), np.ones(int(0.4 * SR)) / int(0.4 * SR), mode="same")
        duck = 10 ** ((duck_db * np.clip(envl, 0, 1)) / 20)
        mix = np.zeros((self.n, 2), np.float32)
        for b in self.BUSES:
            gain = 10 ** (g[b] / 20)
            sig = self.bus[b] * gain
            if b in ("music", "ambience"):
                sig = sig * duck[:, None]
            mix += sig
        with tempfile.TemporaryDirectory() as td:
            raw = os.path.join(td, "mix.wav")
            save(raw, mix / max(1.0, np.max(np.abs(mix)) / 0.98))
            loudnorm_2pass(raw, out_wav, lufs, true_peak)
        return out_wav


def loudnorm_2pass(src, out_wav, lufs=-16.0, true_peak=-1.5, lra=11):
    """Accurate EBU R128 normalisation (measure, then linear correction)."""
    import json
    import subprocess
    r = subprocess.run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", src, "-af",
                        f"loudnorm=I={lufs}:TP={true_peak}:LRA={lra}:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = r.stderr
    m = json.loads(txt[txt.rindex("{"): txt.rindex("}") + 1])
    af = (f"loudnorm=I={lufs}:TP={true_peak}:LRA={lra}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    ffmpeg("-i", src, "-af", af, "-ar", str(SR), "-ac", "2", out_wav)
    return out_wav


def measure_lufs(path):
    import subprocess
    r = subprocess.run([require("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-af",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    I = tp = None
    for line in txt.splitlines()[-20:]:
        line = line.strip()
        if line.startswith("I:"):
            I = float(line.split()[1])
        if line.startswith("Peak:"):
            tp = float(line.split()[1])
    return I, tp
