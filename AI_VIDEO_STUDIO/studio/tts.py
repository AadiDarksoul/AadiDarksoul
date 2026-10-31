"""Local CPU text-to-speech: Piper (neural, primary) with espeak-ng fallback.

Each character gets a voice preset (model + speed + pitch) so voices stay consistent across a film.
"""
import os
import subprocess
import tempfile

from .config import PIPER_DIR, SAMPLE_RATE, VOICES, tool
from .media import ffmpeg, duration


class TTSError(RuntimeError):
    pass


def available_voices():
    if not os.path.isdir(PIPER_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(PIPER_DIR) if f.endswith(".onnx"))


def _voice(v):
    if isinstance(v, dict):
        base = dict(VOICES.get(v.get("preset", "narrator"), VOICES["narrator"]))
        base.update({k: val for k, val in v.items() if k != "preset"})
        return base
    if v in VOICES:
        return dict(VOICES[v])
    return {"model": v, "length_scale": 1.0, "pitch": 0.0}


def _postprocess(raw, out, pitch=0.0, whisper=False, gain_db=0.0):
    """Resample to 48k, pitch shift (semitones, duration preserved), optional whisper colour."""
    filters = ["aresample=22050"]  # normalise rate so pitch math is exact
    if pitch:
        ratio = 2 ** (pitch / 12.0)
        filters += [f"asetrate={int(22050 * ratio)}", "aresample=22050", f"atempo={1 / ratio:.5f}"]
    if whisper:
        filters += ["highpass=f=900", "afftdn=nf=-20", "aecho=0.6:0.5:40:0.25"]
    filters += [f"volume={gain_db}dB", f"aresample={SAMPLE_RATE}"]
    ffmpeg("-i", raw, "-af", ",".join(filters), "-ac", "1", out)


def speak(text, out_wav, voice="narrator"):
    """Synthesize one line to out_wav (mono 48 kHz). Returns (path, seconds, engine)."""
    v = _voice(voice)
    model = os.path.join(PIPER_DIR, v["model"] + ".onnx")
    with tempfile.TemporaryDirectory() as td:
        raw = os.path.join(td, "raw.wav")
        engine = None
        piper = tool("piper")
        if piper and os.path.exists(model):
            p = subprocess.run([piper, "-m", model, "-f", raw,
                                "--length-scale", str(v.get("length_scale", 1.0)),
                                "--noise-scale", str(v.get("noise_scale", 0.667)),
                                "--sentence-silence", str(v.get("sentence_silence", 0.25))],
                               input=text, text=True, capture_output=True)
            if p.returncode == 0 and os.path.exists(raw):
                engine = "piper:" + v["model"]
        if engine is None:
            esp = tool("espeak-ng")
            if not esp:
                raise TTSError("No TTS engine: install piper voices or espeak-ng")
            subprocess.run([esp, "-v", v.get("espeak_voice", "en-us"), "-s",
                            str(int(160 / v.get("length_scale", 1.0))), "-w", raw, text], check=True)
            engine = "espeak-ng"
        # espeak outputs 22050 Hz too, so the same pitch math applies.
        _postprocess(raw, out_wav, v.get("pitch", 0.0), v.get("whisper", False), v.get("gain_db", 0.0))
    return out_wav, duration(out_wav), engine
