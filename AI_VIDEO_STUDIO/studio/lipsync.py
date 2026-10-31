"""Automatic lip-sync with Rhubarb Lip Sync (CPU). Produces Preston-Blair mouth cues A-H,X."""
import json
import os
import subprocess
import tempfile

from .config import tool

# Rhubarb shapes -> simple parametric mouth (openness 0..1, width 0..1, round 0..1)
MOUTH = {
    "X": (0.0, 0.5, 0.0),  # rest
    "A": (0.05, 0.55, 0.0),  # M B P closed
    "B": (0.25, 0.6, 0.0),  # most consonants, slightly open
    "C": (0.5, 0.65, 0.0),  # EH AE open
    "D": (0.85, 0.7, 0.0),  # AA wide open
    "E": (0.45, 0.45, 0.6),  # AO ER rounded
    "F": (0.25, 0.3, 1.0),  # UW OO puckered
    "G": (0.15, 0.6, 0.0),  # F V teeth on lip
    "H": (0.4, 0.6, 0.0),  # L tongue
}


def cues(wav, dialog_text=None, recognizer="pocketSphinx"):
    """Run rhubarb on a wav; returns list of {start,end,value}. Falls back to amplitude-based cues."""
    rh = tool("rhubarb")
    if rh:
        with tempfile.TemporaryDirectory() as td:
            args = [rh, "-q", "-f", "json", "-r", recognizer, "--extendedShapes", "GHX"]
            if dialog_text:
                dp = os.path.join(td, "d.txt")
                open(dp, "w").write(dialog_text)
                args += ["-d", dp]
            p = subprocess.run(args + [wav], capture_output=True, text=True)
            if p.returncode == 0:
                return json.loads(p.stdout)["mouthCues"], "rhubarb"
    return amplitude_cues(wav), "amplitude-fallback"


def amplitude_cues(wav, fps=24):
    import numpy as np
    from .audio_io import load
    from .config import SAMPLE_RATE as SR
    a = np.abs(load(wav).mean(axis=1))
    hop = SR // fps
    out = []
    for i in range(0, len(a), hop):
        v = a[i:i + hop].mean() if i < len(a) else 0
        shape = "X" if v < 0.01 else "B" if v < 0.05 else "C" if v < 0.12 else "D"
        t = i / SR
        if out and out[-1]["value"] == shape:
            out[-1]["end"] = t + 1 / fps
        else:
            out.append({"start": t, "end": t + 1 / fps, "value": shape})
    return out


def shape_at(cue_list, t):
    for c in cue_list:
        if c["start"] <= t < c["end"]:
            return c["value"]
    return "X"
