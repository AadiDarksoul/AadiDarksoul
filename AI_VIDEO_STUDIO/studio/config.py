"""Studio-wide defaults and tool locations."""
import os
import shutil

from .boot import STUDIO_HOME, VENV

DATA = os.environ.get("STUDIO_DATA", "/opt/ai_video_studio")
MODELS = os.path.join(DATA, "models")
PIPER_DIR = os.path.join(MODELS, "piper")
HF_HOME = os.path.join(MODELS, "hf")
os.environ.setdefault("HF_HOME", HF_HOME)

WIDTH, HEIGHT, FPS = 1920, 1080, 24
SAMPLE_RATE = 48000

# Character voice presets: piper voice + prosody. Pitch is in semitones (applied with ffmpeg).
VOICES = {
    "narrator": {"model": "en_US-joe-medium", "length_scale": 1.08, "pitch": 0.0},  # US English narrator
    "narrator_uk": {"model": "en_GB-alan-medium", "length_scale": 1.12, "pitch": -1.5},
    "female": {"model": "en_US-lessac-medium", "length_scale": 1.0, "pitch": 0.0},
    "male": {"model": "en_US-ryan-medium", "length_scale": 1.0, "pitch": 0.0},
    "child": {"model": "en_US-lessac-medium", "length_scale": 0.95, "pitch": 4.0},
    "old_man": {"model": "en_US-ryan-medium", "length_scale": 1.2, "pitch": -3.0},
    "demon": {"model": "en_US-ryan-medium", "length_scale": 1.35, "pitch": -7.0},
    "whisper": {"model": "en_US-lessac-medium", "length_scale": 1.15, "pitch": -1.0, "whisper": True},
}


def tool(name):
    """Find an executable in PATH, the studio bin dir or the venv."""
    for d in (os.path.join(DATA, "bin"), os.path.join(VENV, "bin")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return shutil.which(name)


def require(name):
    p = tool(name)
    if not p:
        raise RuntimeError(f"Required tool '{name}' not found. Run AI_VIDEO_STUDIO/install.sh")
    return p
